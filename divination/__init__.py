import pywintypes
import sys, platform

os = platform.system()

# global instance of driver class
DRIVER = None

try:
    DRIVER = WinDriver()
except FileNotFoundException as error:
    print('divination module error:\n  Failed to open handle to device driver. Is {error} loaded?\n  Please see README (https://github.com/depletionmode/divination/blob/master/README.md) for details.\n')
    sys.exit()
except NotImplementedException:
    print('divination module error:\n  Unsupported OS!')

from .impl import MemoryObject, MemoryType, PciDevice, Msr