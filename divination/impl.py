import struct
from enum import Enum
from .driver import Driver
from divination import *

class MemoryType(Enum):
    IoSpace = 1
    PhysMem = 2

class MemoryObject():
    def __init__(self, base_address, range, mem_type, alloc=False):
        self.base_address = base_address
        self.range = range
        self.mem_type = mem_type
        self.is_allocated = alloc
        self.virt_addr = 0

        if alloc:
            if base_address != 0 or mem_type != MemoryType.PhysMem:
                pass
                raise ValueError('Invalid parameter')
            # todo - alloc physmem

        if mem_type == MemoryType.IoSpace:
            self._map_iospace()
        elif mem_type == MemoryType.PhysMem:
            pass # todo
        else:
            raise ValueError('Invalid memory type')

    def __del__(self):
        if self.mem_type == MemoryType.IoSpace and self.virt_addr != 0:
            self._unmap_iospace()
        elif self.mem_type == MemoryType.PhysMem and self.virt_addr != 0:
            pass # todo

    def __len__(self):
        return self.range

    def __getitem__(self, key):
        if isinstance(key, int):
            if key < 0 or key >= len(self):
                raise IndexError('Index out of range')
                
            return self.read(key, 1)

        elif isinstance(key, slice):
            return b''.join([self[i] for i in range(*key.indices(len(self)))])

        else:
            raise TypeError('Invalid type')
            
    def __setitem__(self, key, value):
        if isinstance(key, int):
            if key < 0 or key >= len(self):
                raise IndexError('Index out of range')

            b = bytearray(1)
            b[0] = value
            self.write(key, b)

        elif isinstance(key, slice):
            ii = 0
            for i in range(*key.indices(len(self))):
                self[i] = value[ii]
                ii += 1

        else:
            raise TypeError('Invalid type')

    def _map_iospace(self):
        self.virt_addr = DRIVER.map_iospace(self.base_address, self.range)
        if self.virt_addr == 0:
            raise OSError('Invalid virtual address received')

    def _unmap_iospace(self):
        if self.virt_addr == 0:
            raise OSError('Address not mapped')
            
        DRIVER.unmap_iospace(self.virt_addr)
        self.virt_addr = 0

    def read(self, offset, len):
        return bytes(Driver.ReadMappedMemory(self.virt_addr + offset, len))

    def write(self, offset, buf):
        Driver.WriteMappedMemory(self.virt_addr + offset, buf)

class PciDevice():
    def __init__(self, bus, device, function):
        self.bus = bus
        self.device = device
        self.function = function

    def read_cfg(self):
        return DRIVER.read_pcicfg(self.bus, self.device, self.function)

class Msr():
    def __init__(self, msr):
        self.msr = msr

    def read(self):
        return DRIVER.read_msr(self.msr)
