#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Gimp Startrail Compositor
# https://github.com/themaninthesuitcase/gimp-startrail-compositor
# Version : 1.8
#
# Christopher Pearson
# www.cpearson.me.uk
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import os
from gimpfu import *
from time import time

import gettext
locale_directory = gimp.locale_directory
gettext.install( "gimp20-template" , locale_directory, unicode=True )

allowed_import_types = ["jpg","jpeg","tiff","tif","bmp","png"]

def xdg_config_dir():
	return (os.environ.get('XDG_CONFIG_HOME') or
		os.path.expandvars(os.path.join('$HOME', '.config')))

def xdg_user_dir(cfgpath, name):
	with open(cfgpath) as fh:
		for line in fh.readlines():
			if line.startswith(name):
				return os.path.expandvars(line[len(name)+2:-2])

def xdg_pictures_dir():
	cfgdir = xdg_config_dir()
	userdirs = os.path.join(cfgdir, "user-dirs.dirs")
	if os.path.exists(userdirs):
		picdir = xdg_user_dir(userdirs, "XDG_PICTURES_DIR")
		if os.path.exists(picdir):
			return picdir
	return os.getcwd()

def file_is_image(file_name):
	is_image = 0
	ext = os.path.splitext(file_name)[1] # get the extension
	ext = ext.replace(".", "") # rip off the . from the extension
	if ext.lower() in allowed_import_types: # is this an image?
		is_image = 1
	return(is_image)

def get_new_image(raw_image):
        if hasattr(gimp.Image, "precision"):
	        return pdb.gimp_image_new_with_precision(raw_image.active_layer.width, raw_image.active_layer.height, 0,
						         raw_image.precision)
        else:
	        return pdb.gimp_image_new(raw_image.active_layer.width, raw_image.active_layer.height, 0)

def process_dark_frame(file_name, image, layer_count):
	dark_frame = pdb.gimp_file_load(file_name,"")

	# have we got a base image to work with?
	if image == None:
		# create a base image based on the dark frame
		image = get_new_image(dark_frame)

	# get the main layer of the new frame
	dark_layer = pdb.gimp_layer_new_from_drawable(dark_frame.active_layer, image)
	# set the opacity to create an average image:
	# formula taken from http://www.cambridgeincolour.com/tutorials/image-averaging-noise.htm
	dark_layer.opacity = 100.0 / layer_count
	# add the new layer and flatten down to keep memory useage down.
	image.add_layer(dark_layer,0)
	image.flatten()
	# Get rid of the image we loaded up.
	gimp.delete(dark_frame)
	return(image)

def create_dark_image(dark_frames):
	dark_image = None
	layer_count = 1

	images = os.listdir(dark_frames)
	images.sort()
	for file_name in images:
		file_name = os.path.join(dark_frames, file_name)
		if file_is_image(file_name):
			dark_image = process_dark_frame(file_name, dark_image, layer_count)
			layer_count += 1

	return dark_image

def save_intermediate_frame(image, image_count, directory):
	# build a save file_name pad the number to 5 digits which should be plenty for any timelapse.
	intermediate_save_file_name = os.path.join(directory, "trail" + str(image_count).zfill(5) + ".jpg")
	pdb.gimp_file_save(image,pdb.gimp_image_get_active_drawable(image),intermediate_save_file_name,intermediate_save_file_name)

def process_light_frame(file_name, image, dark_image, merge_layers, image_count, subtract_skyglow, opacity):
	# load up the light frame into an image
	light_frame = pdb.gimp_file_load(file_name,"")

	# have we got a base image to work with?
	if image == None:
		# create a base image based on the light frame
		image = get_new_image(light_frame)
		image.disable_undo()

	# did we make a dark frame?
	if dark_image != None:
		# As we have a dark image we need to subtract it from the light frame.
		# create a new layer from the dark image
		dark_layer = pdb.gimp_layer_new_from_drawable(dark_image.active_layer, light_frame)
		# set the layer to layer_mode_difference
		dark_layer.mode = SUBTRACT_MODE
		# add the layer to the light_frame
		light_frame.add_layer(dark_layer, 0)
		# flatten
		light_frame.flatten()

	if subtract_skyglow != 0:
		glow_layer = pdb.gimp_layer_new_from_drawable (light_frame.active_layer, light_frame)
		glow_layer.mode = SUBTRACT_MODE
		if subtract_skyglow == 1:
			glow_layer.opacity = 25.0
		elif subtract_skyglow == 2:
			glow_layer.opacity = 50.0
		elif subtract_skyglow == 3:
			glow_layer.opacity = 75.0
		else:
			glow_layer.opacity = 100.0
		# add this as new layer
		light_frame.add_layer(glow_layer,0)
		pdb.plug_in_gauss(light_frame, glow_layer, 500, 500, 0)
		light_frame.flatten()

	# Set the light frame to layer_mode_lighten
	light_layer = pdb.gimp_layer_new_from_drawable(light_frame.active_layer, image)
	light_layer.mode = LIGHTEN_ONLY_MODE
	light_layer.opacity = opacity

	# add this as new layer
	image.add_layer(light_layer,0)

	if merge_layers == 1:
		image.flatten()
	else:
		light_layer.name = "layer " + str(image_count).zfill(5)

	# clean up our temp bits.
	gimp.delete(light_frame)
	return(image)

def startrail(frames, use_dark_frames, dark_frames, save_intermediate, save_directory, live_display, merge_layers, subtract_skyglow, fade):
	#Do some santity checking before we start
	# Light frames
	if len(frames) == 0:
		pdb.gimp_message("No light frame path provided.")
		return

	if not os.path.exists(frames):
		pdb.gimp_message("Light frame path doesn't exist.")
		return

	# Dark frames
	if use_dark_frames == 1 and not os.path.exists(dark_frames):
		pdb.gimp_message("Dark frame save path doesn't exist.")
		return

	# Intermediate frame path
	if save_intermediate == 1 and not os.path.exists(save_directory):
		pdb.gimp_message("Intermediate frame save path doesn't exist.")
		return

	# start a timer
	start = time()

	# create 1 dark frame averaged from all of them
	dark_image = None
	if use_dark_frames == 1:
		dark_image = create_dark_image(dark_frames)

	# Create a counter to count the frames we layer
	image_count = 0

	opacity = 100.0

	# Define an image to work in.
	# This will be created from the first light frame we process
	image = None
	images = os.listdir(frames)
	images.sort()
	for file_name in images:
		file_name = os.path.join(frames, file_name)

		if file_is_image(file_name):
			if fade == 1: # Fade in
				opacity = (image_count * 100.0 / len(images))
                        elif fade == 2: # Fade out
				opacity = 100.0 - (image_count * 100.0 / len(images))
			image_count += 1
			image = process_light_frame(file_name, image, dark_image, merge_layers,image_count, subtract_skyglow, opacity)
			if save_intermediate == 1:
				save_intermediate_frame(image, image_count, save_directory)

			if live_display == 1:
				# If first frame display the image to screen.
				if image_count == 1:
					gimp.Display(image)
				# Update the display
				gimp.displays_flush()

	# end the timer
	elapsed = time() - start

	# show the new image if we managed to make one.
	if image == None:
		pdb.gimp_message("No images found to stack")

	if image != None:
		image.enable_undo()
		if live_display == 1 :
			gimp.displays_flush()
		else:
			gimp.Display(image)
		pdb.gimp_message("Image created in " + str(round(elapsed)).rstrip('0').rstrip('.') + "s")

	if dark_image != None:
		gimp.delete(dark_image) # we don't need this any more so get rid of it so not to leak.


register(
	"startrail",
	"",
	"",
	"Christopher Pearson",
	"GPL v3",
	"2011",
	_("Startrail"),
	"",
	[
		(PF_DIRNAME, "frames","Light Frames", xdg_pictures_dir()),
		(PF_TOGGLE, "use_dark_frames","Use dark frame",0),
		(PF_DIRNAME, "dark_frames","Dark Frames", xdg_pictures_dir()),
		(PF_TOGGLE, "save_intermediate","Save intermediate frames",0),
		(PF_DIRNAME, "save_directory","Intermediate save directory", xdg_pictures_dir()),
		(PF_TOGGLE, "live_display","Live display update (much slower)",0),
		(PF_TOGGLE, "merge_layers","Merge all images to a single layer",1),
		(PF_OPTION, "subtract_skyglow","Subtract skyglow (much slower)",0, ["None", "Light", "Moderate", "Heavy", "Full"]),
		(PF_OPTION, "fade", "Fade trails", 0, ["None", "In", "Out"]),
	],
	[],
	startrail,
	menu="<Image>/File/Create",
	domain=("gimp20-template", locale_directory)
	)

main()
