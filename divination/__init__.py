import pywintypes
import sys, platform

os = platform.system()

# global instance of driver class
DRIVER = None

if os == 'Windows':
    from .driver import WinDriver
    try:
        DRIVER = WinDriver()
    except pywintypes.error as error:
        if error.args[0] == 2:
            print('divination module error:\n  Failed to open handle to device driver. Is DivinationDrv.sys loaded?\n  Please see README (https://github.com/depletionmode/divination/blob/master/README.md) for details.\n')
            sys.exit()
elif os == 'Linux':
    from .driver import LinDriver
    try:
        DRIVER = LinDriver()
    except pywintypes.error as error:
        if error.args[0] == 2:
            print('divination module error:\n  Failed to open handle to device driver. Is divination_drv.ko loaded?\n  Please see README (https://github.com/depletionmode/divination/blob/master/README.md) for details.\n')
            sys.exit()
else:
    print('divination module error:\n Unsupported OS!\n')

from .impl import MemoryObject, MemoryType, PciDevice, Msr