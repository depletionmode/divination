from .driver import Driver
import pywintypes
import sys

# global instance of driver class
DRIVER = None
try:
    DRIVER = Driver()
except pywintypes.error as error:
    if error.args[0] == 2:
        print('divination module error:\n  Failed to open handle to device driver. Is DivinationDrv.sys running?\n  Please see README (https://github.com/depletionmode/divination/blob/master/README.md) for details.')
        sys.exit()

from .impl import MemoryObject, MemoryType, PciDevice, Msr