import fcntl
from enum import Enum
import os

class DriverControlCodes(Enum):
    READ_PCICFG     = 0x00
    READ_MSR        = 0x01
    MAP_IOSPACE     = 0x02
    UNMAP_IOSPACE   = 0x03
    MAP_PHYSMEM     = 0x04
    UNMAP_PHYSMEM   = 0x05

class LinDriver():
    def __init__(self):
        os.stat
        try:
            self.fd = os.open('/dev/divination', os.O_TRUNC)
        except:
            raise FileNotFoundError('divination.ko')

    def _transact(self, ctrl_code, buf):
        fcntl.ioctl(self.fd, 0xc008e000 + ctrl_code.value, buf)

    def map_iospace(self, phys_addr, size):
        raise NotImplementedError

    def unmap_iospace(self, virt_addr):
        raise NotImplementedError

    def map_physmem(self, phys_addr, size):
        raise NotImplementedError

    def unmap_physmem(self, virt_addr):
        raise NotImplementedError

    def read_msr(self, msr):
        buf = struct.pack("@II", msr, 0)
        self._transact(DriverControlCodes.READ_MSR, buf)
        return struct.unpack("@Q", buf)[0]

    def read_pcicfg(self, bus, device, function):
        buf = struct.pack("@III256s", bus, device, function)
        self._transact(DriverControlCodes.READ_PCICFG, buf)
        return struct.unpack("@III256s", buf)[3]

    @staticmethod
    def ReadMappedMemory(virt_addr, size):
        pass

    @staticmethod
    def WriteMappedMemory(virt_addr, buf):
        pass
