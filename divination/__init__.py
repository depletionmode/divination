#import pywintypes
import sys, platform
from .driver import Driver

# global instance of driver class
DRIVER = None

try:
    DRIVER = Driver()
except FileNotFoundError as error:
    print('divination module error:\n  Failed to open handle to device driver. Is {} loaded?\n  Please see README (https://github.com/depletionmode/divination/blob/master/README.md) for details.\n'.format(error))
    sys.exit()
except NotImplementedError:
    print('divination module error:\n  Unsupported OS!')

from .impl import MemoryObject, MemoryType, PciDevice, Msr