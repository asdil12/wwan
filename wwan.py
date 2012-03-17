#!/usr/bin/python
# -*- coding: utf-8 -*-

# Author: Barry John Williams, Dominik Heidler
# Creative Commons Attribute-Share Alike 2.5 UK:Scotland Licence

import serial
import string
import sys
import os
import shlex
import pygtk
pygtk.require('2.0')
import gtk
import pynotify
import time
import radio
import threading
import signal
import subprocess

class Monitor:

	ERINFO_GPRS = '0,1,0'
	ERINFO_UMTS = '0,0,1'
	ERINFO_HSPA = '0,0,2'

	GPRS = 'GPRS'
	UMTS = '3G'
	HSPA = '3G+'
	NONE = 'NONE'

	def __init__(self):
		self.setSerial(serial.Serial())
		self.reset()

	def reset(self):
		print 'Values reset'
		self.cur_network = ''
		self.cur_type = ''
		self.cur_signal = 0

	def setSerial(self, ser):
		self.ser = ser

	def getSerial(self):
		return self.ser

	def call(self, ser, command):
		ser.write(command + '\r\n')
		response = [r.replace('\r\n', '') for r in ser.readlines() if not r.startswith(('^', '_')) and r.replace('\r\n', '')]
		return response

	# This function returns meaningful results only when in GPRS mode - it therefore isn't used but kept for reference
	def get_csq_signal(self):
		signal_res = call(self.ser, 'AT+CSQ')
		if len(signal_res) > 2:
			csq = signal_res[1].replace('+CSQ: ', '')
			csq_val = int(csq[:string.find(csq, ',')])
			strength = 100 * csq_val / 31
			# following calculation taken from http://www.gprsmodems.co.uk/acatalog/Technical_Topics.html
			rssi = -113 + csq_val * 2
			return [strength, rssi]
		else:
			return [0, 0]

	def get_type(self):
		return self.cur_type

	def get_network(self):
		return self.cur_network

	def get_signal(self):
		return self.cur_signal

	# Returns True if the state of the access type has changed since the last call
	def update_type(self):
		erinfo_res = self.call(self.ser, 'AT*ERINFO?')
		type = self.NONE
		if len(erinfo_res) > 2:
			erinfo = erinfo_res[1].replace('*ERINFO: ', '')
			if erinfo == self.ERINFO_GPRS:
				type = self.GPRS
			elif erinfo == self.ERINFO_UMTS:
				type = self.UMTS
			elif erinfo == self.ERINFO_HSPA:
				type = self.HSPA
			if type != self.cur_type:
				self.cur_type = type
				return True
		return False

	# Returns True if the signal level has changed since the last call
	def update_signal(self):
		cind_res = self.call(self.ser, 'AT+CIND?')
		signal = 0
		if len(cind_res) > 2:
			cind_only = cind_res[1].replace('+CIND: ', '')
			cind = cind_only.replace(',', ' ')
			cinds = shlex.split(cind)
			if len(cinds) > 2:
				signal = int(cinds[1])
			if signal != self.cur_signal:
				self.cur_signal = signal
				return True
		return False

	# Returns True if the network has changed since the last call
	def update_network(self):
		response = self.call(self.ser, 'AT+COPS?')
		network = 'Searching'
		if len(response) > 2:
			if (response[1])[:6] == '+COPS:':
				index = string.find(response[1], '"')
				index2 = string.find((response[1])[index + 1:], '"') + index
				network_string = (response[1])[index + 1:index2 + 1]
				if index2 > index:
					network = network_string
					if network != self.cur_network:
						self.cur_network = network
						return True
		return False

	def close(self):
		if self.ser.isOpen():
			self.ser.close()


class StatusIcon:

	NONE_ICON = 'notification-gsm-disconnected.svg'

	UMTS_ICON = [
		'notification-gsm-disconnected.svg',
		'notification-gsm-3g-none.svg',
		'notification-gsm-3g-low.svg',
		'notification-gsm-3g-medium.svg',
		'notification-gsm-3g-high.svg',
		'notification-gsm-3g-full.svg',
		]

	HSPA_ICON = [
		'notification-gsm-disconnected.svg',
		'notification-gsm-h-none.svg',
		'notification-gsm-h-low.svg',
		'notification-gsm-h-medium.svg',
		'notification-gsm-h-high.svg',
		'notification-gsm-h-full.svg',
		]

	GPRS_ICON = [
		'notification-gsm-disconnected.svg',
		'notification-gsm-none.svg',
		'notification-gsm-low.svg',
		'notification-gsm-medium.svg',
		'notification-gsm-high.svg',
		'notification-gsm-full.svg',
		]

	def __init__(self, controller):
		self.controller = controller
		file = os.path.join('icons', StatusIcon.NONE_ICON)
		if not os.access(file, os.F_OK):
			print "Can't access icon %s" % StatusIcon.NONE_ICON
		self.status_icon = gtk.status_icon_new_from_file(file)
		self.status_icon.set_visible(True)

		# Build Context Menu
		menu = gtk.Menu()

		self.radioRadioMenu = dict()

		normalRadioMenuItem = gtk.RadioMenuItem(None, 'Normal (Prefer 3G)')
		normalRadioMenuItem.connect('toggled', self.normalRadio_menu_cb)
		self.radioRadioMenu[radio.PREFER] = normalRadioMenuItem
		menu.append(normalRadioMenuItem)

		umtsRadioMenuItem = gtk.RadioMenuItem(normalRadioMenuItem, 'UMTS/HSPA (3G Only)')
		self.radioRadioMenu[radio.UMTS] = umtsRadioMenuItem
		umtsRadioMenuItem.connect('toggled', self.umtsRadio_menu_cb)
		menu.append(umtsRadioMenuItem)

		gprsRadioMenuItem = gtk.RadioMenuItem(umtsRadioMenuItem, 'GPRS Only')
		self.radioRadioMenu[radio.GPRS] = gprsRadioMenuItem
		gprsRadioMenuItem.connect('toggled', self.gprsRadio_menu_cb)
		menu.append(gprsRadioMenuItem)

		menu.append(gtk.SeparatorMenuItem())

		enabledMenuItem = gtk.CheckMenuItem('Enabled')
		enabledMenuItem.connect('toggled', self.enable_menu_cb)
		menu.append(enabledMenuItem)

		menu.append(gtk.SeparatorMenuItem())

		aboutMenuItem = gtk.MenuItem("About")
		aboutMenuItem.connect('activate', self.show_about_dialog_cb)
		menu.append(aboutMenuItem)

#		exitMenuItem = gtk.MenuItem('Exit')
#		exitMenuItem.connect('activate', self.close_menu_cb)
#		menu.append(exitMenuItem)

#		self.status_icon.connect('activate', self.activate_cb)
		self.status_icon.connect('popup-menu', self.popup_menu_cb, menu)

	def popup_menu_cb(self, statusicon, button, time, menu=None):
		if button == 3:
			if menu:
				menu.show_all()
				menu.popup(None, None, gtk.status_icon_position_menu, button, time, statusicon)
		pass

	def normalRadio_menu_cb(self, widget, data=None):
		self.controller.setRadio(radio.PREFER)

	def umtsRadio_menu_cb(self, widget, data=None):
		self.controller.setRadio(radio.UMTS)

	def gprsRadio_menu_cb(self, widget, data=None):
		self.controller.setRadio(radio.GPRS)

	def enable_menu_cb(self, widget, data=None):
		state = radio.PREFER if widget.get_active() else radio.OFF
		self.controller.setRadio(state)

	def close_menu_cb(self, widget, data=None):
		# Hide the icon first to give instant semantic feedback
		self.status_icon.set_visible(False)
		# The controller should close this status icon properly once its thread has completed
		self.controller.close()

	def show_about_dialog_cb(self, widget):
		about_dialog = gtk.AboutDialog()

		about_dialog.set_destroy_with_parent(True)
		about_dialog.set_name('wwan control')
		about_dialog.set_version('0.1')
		about_dialog.set_authors(['Barry John Williams', 'Dominik Heidler'])
		about_dialog.set_license("Creative Commons Attribute-Share Alike 2.5 UK:Scotland Licence")

		about_dialog.run()
		about_dialog.destroy()

#	def activate_cb(self, widget, data=None):
#		bandwidth = self.get_bandwidth()
#		message = 'Bandwidth: %s' % bandwidth
#		print message
#		n = pynotify.Notification('Mobile Broadband', message)
#		if not n.show():
#			print 'Failed to send notification'

	def get_icon_file(self, type, signal):
		iconname = StatusIcon.NONE_ICON
		if type == Monitor.GPRS:
			iconname = self.GPRS_ICON[signal]
		elif type == Monitor.UMTS:
			iconname = self.UMTS_ICON[signal]
		elif type == Monitor.HSPA:
			iconname = self.HSPA_ICON[signal]
		return os.path.join('icons', iconname)

	def update(self, radiostate, network, type, signal):
		filename = self.get_icon_file(type, signal)
		if not os.access(filename, os.F_OK):
			print "Can't access icon %s" % filename
		if not network:
			message = 'No Network'
		else:
			message = '%s (%s)' % (network, type)
		gtk.gdk.threads_enter()
		self.status_icon.set_from_file(filename)
		if radiostate == radio.ERROR or radiostate == radio.OFF:
			#self.status_icon.set_has_tooltip(False)
			self.status_icon.set_tooltip('Disabled')
			[item.set_sensitive(False) for item in self.radioRadioMenu.values()]
		else:
			self.status_icon.set_has_tooltip(True)
			self.status_icon.set_tooltip(message)
			[item.set_sensitive(True) for item in self.radioRadioMenu.values()]
			self.radioRadioMenu[radiostate].set_active(True)
		gtk.gdk.threads_leave()

	def notify_status(self,	network, type, signal):
		if type == Monitor.NONE:
			message = 'Searching'
		else:
			message = network + ' (' + type + ')'
		n = pynotify.Notification('Mobile Broadband', message)  # , self.get_icon_file(type,signal))
		if not n.show():
			print 'Failed to send notification'

	def main(self):
		gtk.main()

	def stop(self):
		gtk.main_quit()


class Controller(threading.Thread):

	def __init__(self, serialNode):
		print 'Controller on %s' % serialNode
		self.monitor = Monitor()
		self.ui = StatusIcon(self)
		self.running = True
		self.event = threading.Event()
		self.updateRadioState = False
		self.setRadioState = radio.PREFER
		self.serialNode = serialNode
		threading.Thread.__init__(self)

	def close(self):
		self.running = False
		self.event.set()

	def getRadioState(self):
		ser = self.monitor.getSerial()
		if ser.isOpen():
			return radio.status(ser)
		return radio.ERROR

	def setRadio(self, state):
		print 'Requsted state %s' % state
		self.updateRadioState = True
		self.setRadioState = state
		self.event.set()

	def run(self):
		print 'Starting monitoring loop'
		while self.running:
			try:
				# Reopen Monitor
				try:
					self.monitor.setSerial(serial.Serial(self.serialNode, 19200, timeout=0.1))
				except serial.serialutil.SerialException:
					print 'Failure Opening Serial Port'
					self.monitor.reset()
					self.monitor.setSerial(serial.Serial())

				# If radio state change request has been made
				if self.updateRadioState:
					print 'Changing Radio State to %s' % self.setRadioState
					ser = self.monitor.getSerial()
					radio.set_status(ser, self.setRadioState)
					self.updateRadioState = False

				# Fetch new data using serial
				if self.monitor.getSerial().isOpen():
					self.monitor.update_signal()
					if self.monitor.update_network() | self.monitor.update_type():
						self.ui.notify_status(self.monitor.get_network(), self.monitor.get_type(), self.monitor.get_signal())
				else:
					self.monitor.reset()

			except OSError as e:
				try:
					print 'Error: %s' % e.args[-1]
				except:
					print 'Error: OSError'
				self.monitor.reset()

			# Update UI
			radioState = self.getRadioState()
			#if radioState != radio.ERROR:
			self.ui.update(radioState, self.monitor.get_network(), self.monitor.get_type(), self.monitor.get_signal())

			# Close Monitor
			self.monitor.close()

			# Wait 4 Seconds
			self.event.clear()
			self.event.wait(4)

		print 'Exiting'
		self.monitor.close()
		self.ui.stop()


if __name__ == '__main__':
	if not pynotify.init('Basics'):
		sys.exit(1)

	# Set the working folder to that set in command line
	serialNode = None
	if len(sys.argv) > 0:
		serialNode = sys.argv[1]

	if len(sys.argv) > 1:
		dir = sys.argv[2]
		if os.access(dir, os.F_OK):
			print 'Working Dir: %s' % dir
			os.chdir(dir)
		else:
			print 'Dir %s does not exist' % dir
			sys.exit(1)

	if serialNode != None:
		# controller = Controller('/dev/ttyACM1')
		controller = Controller(serialNode)

		def signal_handler(sig, frame):
			print 'Caught Signal ' + str(sig)
			controller.close()

		signal.signal(signal.SIGTERM, signal_handler)
		signal.signal(signal.SIGINT, signal_handler)

		gtk.gdk.threads_init()

		# Start the controller thread
		controller.start()

		# Start the UI
		controller.ui.main()
	else:
		print 'Missing serial device'
		sys.exit(1)
