'''
   Copyright (c) 2019 Jack Farley
   This file is part of pymobiledevice2
   Usage or distribution of this software/code is subject to the
   terms of the GNU GENERAL PUBLIC LICENSE.
   quickstart.py

   Quickstart python script leveraging the fantastic work of IOSForensics/pymobiledevice's work

'''

from usbmux.usbmux import USBMux
from lockdown import LockdownClient
from afc import AFCShell, AFC2Client
import logging
import sys

def set_logger(log_level):

    if log_level == 1:
        logging.basicConfig(level=logging.DEBUG,
                            format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
                            datefmt='%m-%d %H:%M')
        log = logging.getLogger()
        return log
    if log_level == 0:
        logging.basicConfig(level=logging.INFO,
                            format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
                            datefmt='%m-%d %H:%M')
        log = logging.getLogger()
        return log
    else:
        print("Not a valid logging type. Use 0 for INFO and 1 for DEBUG. Default is INFO")
        sys.exit()

def get_serial(log):
    log.info("Starting USBMux")
    mux = USBMux()
    if not mux.devices:
        mux.process(0.1)
    serial_number = mux.devices[0].serial
    return serial_number

def quickAfc(log_level = 0):
    log = set_logger(log_level)

    serial_number = get_serial(log)
