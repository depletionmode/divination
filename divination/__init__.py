"""Hardware inspection with a lazily opened platform driver."""

from .driver import Driver

# Importing the package never opens a device or terminates the interpreter.
DRIVER = Driver()

from .impl import MemoryObject, MemoryType, Msr, PciDevice

__all__ = ['Driver', 'DRIVER', 'MemoryObject', 'MemoryType', 'Msr', 'PciDevice']
