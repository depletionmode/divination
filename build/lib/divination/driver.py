import win32file, win32gui
import struct
from enum import Enum

class DriverControlCodes(Enum):
    READ_PCICFG     = 0x00
    READ_MSR        = 0x01
    MAP_IOSPACE     = 0x02
    UNMAP_IOSPACE   = 0x03
    MAP_PHYSMEM     = 0x04
    UNMAP_PHYSMEM   = 0x05

class Driver():
    def __init__(self):
        self.hDriver = win32file.CreateFile(r'\\.\Divination', 
                                            win32file.GENERIC_READ | win32file.GENERIC_WRITE, 
                                            0, 
                                            None, 
                                            win32file.OPEN_EXISTING, 
                                            0, 
                                            None)

    def _transact(self, ctrl_code, in_buf, out_size=0):
        return win32file.DeviceIoControl(self.hDriver, ctrl_code.value, in_buf, out_size)

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
        out_buf = self._transact(DriverControlCodes.READ_MSR, in_buf, 8)    # returns msr value
        return struct.unpack("@Q", out_buf)[0]

    def read_pcicfg(self, bus, device, function):
        in_buf = struct.pack("@III", bus, device, function)
        out_buf = self._transact(DriverControlCodes.READ_PCICFG, in_buf, 0x100)    # returns pci cfg
        return out_buf

    @staticmethod
    def ReadMappedMemory(virt_addr, size):
        return win32gui.PyGetMemory(virt_addr, size)

    @staticmethod
    def WriteMappedMemory(virt_addr, buf):
        win32gui.PySetMemory(virt_addr, buf)
