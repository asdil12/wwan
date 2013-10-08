#!/usr/bin/env python2

from distutils.core import setup
import os

working_dir = os.path.dirname(os.path.abspath(__file__))
icons_dir = os.path.join(working_dir, 'icons')
icons = [os.path.join('icons', icon) for icon in os.listdir(icons_dir)]

setup(
	name='wwan',
	version='2.0.0',
	license='GPL',
	description='Tray-icon based configuration of the Ericsson F3507g UMTS card on linux',
	author='Dominik Heidler',
	author_email='dheidler@gmail.com',
	url='http://github.com/asdil12/wwan',
	packages=['wwan'],
	scripts=['bin/wwan'],
	data_files=[
		#('/etc', ['wwan.conf']),
		('/usr/share/wwan/icons', icons),
	],
)

