import win32file, win32gui
import struct
from enum import Enum

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
                raise ValueError, 'Invalid parameter'
            # todo - alloc physmem

        if mem_type == MemoryType.IoSpace:
            self._map_iospace()
        elif mem_type == MemoryType.PhysMem:
            pass # todo
        else:
            raise ValueError, 'Invalid memory type'

    def __del__(self):
        if self.mem_type == MemoryType.IoSpace:
            self._unmap_iospace()
        elif self.mem_type == MemoryType.PhysMem:
            pass # todo

    def __len__(self):
        return self.range

    def __getitem__(self, key):
        if isinstance(key, int):
            if key < 0 or key >= len(self):
                raise IndexError, 'Index out of range'
            return self.read(key, 1)
        elif isinstance(key, slice):
            return [self[i] for i in xrange(*key.indices(len(self)))]
        else:
            raise TypeError, 'Invalid type'
            
    def __setitem__(self, key, value):
        if isinstance(key, int):
            if key < 0 or key >= len(self):
                raise IndexError, 'Index out of range'
            self.write(key, 1, value)
        elif isinstance(key, slice):
            for i in xrange(*key.indices(len(self))):
                self[i] = value[i]
        else:
            raise TypeError, 'Invalid type'

    def _map_iospace(self):
        self.virt_addr = DRIVER.map_iospace(self.base_address, self.range)

    def _unmap_iospace(self):
        if self.virt_addr = 0:
            raise IOError, 'Invalid address'
            
        DRIVER.unmap_iospace(self.virt_addr)
        self.virt_addr = 0


class DriverControlCodes(Enum):
    READ_MSR        = 0x01
    READ_PCI_CFG    = 0x00
    MAP_IOSPACE     = 0x02
    UNMAP_IOSPACE   = 0x03
    MAP_PHYSMEM     = 0x04
    UNMAP_PHYSMEM   = 0x05

class Driver():
    def __init__(self):
        self.hDriver = win32file.CreateFile('\Device\Desperado', win32file.GENERIC_READ | win32file.GENERIC_WRITE, 0, win32file.OPEN_EXISTING, 0, 0)

    def _transact(self, ctrl_code, in_buf, out_size=0):
        return win32file.DeviceIoControl(self.hDriver, ctrl_code, in_buf, out_size)

    def map_iospace(self, phys_addr, size):
        in_buf = struct.pack("@QQ", phys_addr, size)
        out_buf = self._transact(DriverControlCodes.MAP_IOSPACE, in_buf, 8)    # returns usermode virt_addr of mapped space
        return struct.unpack("@Q", out_buf)[0]

    def unmap_iospace(self, virt_addr):
        in_buf = struct.pack("@Q", virt_addr)
        self._transact(DriverControlCodes.UNMAP_IOSPACE, in_buf)

    def map_physmem(self, phys_addr, size):
        in_buf = struct.pack("@QQ", phys_addr, size)
        out_buf = self._transact(DriverControlCodes.MAP_PHYSMEM, in_buf, 8)    # returns usermode virt_addr of mapped space
        return struct.unpack("@Q", out_buf)[0]

    def unmap_physmem(self, virt_addr):
        in_buf = struct.pack("@Q", virt_addr)
        self._transact(DriverControlCodes.UNMAP_PHYSMEM, in_buf)

    def read_msr(self, msr):
        in_buf = struct.pack("@I", msr)
        out_buf = self._transact(DriverControlCodes.READ_MSR, in_buf, 4)    # returns msr value
        return struct.unpack("@Q", out_buf)[0]

    @staticmethod
    def ReadMappedMemory(virt_addr, size):
        return win32gui.PyGetMemory(virt_addr, size)

    @staticmethod
    def WriteMappedMemory(virt_addr, buf):
        win32gui.PySetMemory(virt_addr, buf)

# global instance of driver class
DRIVER = Driver()