import fcntl, mmap
from enum import Enum
import os
import struct
import ctypes

mm_base_addr_next = 0x0100000000
mm_objs = {}

def _find_mm_obj(addr):
    for k,v in mm_objs.items():
        if addr in k:
            return k[0], v, k
    return None, None, None

class DriverControlCodes(Enum):
    READ_PCICFG     = 0x00
    READ_MSR        = 0x01
    MAP_IOSPACE     = 0x02

class LinDriver():
    def __init__(self):
        os.stat
        try:
            self.fd = os.open('/dev/divination', os.O_RDWR | os.O_SYNC)
        except:
            raise FileNotFoundError('divination.ko')

    def _transact(self, ctrl_code, buf):
        return fcntl.ioctl(self.fd, 0xc008e000 + ctrl_code.value, buf, True)

    def map_iospace(self, phys_addr, size):
        buf = struct.pack("@Q", phys_addr)
        self._transact(DriverControlCodes.MAP_IOSPACE, buf)
        mm = mmap.mmap(self.fd, size, prot= mmap.PROT_READ | mmap.PROT_WRITE)

        global mm_base_addr_next
        global mm_objs

        mm_base_addr_next <<= 1    # create fake va for indexing into the directory of mm objects
        addr = mm_base_addr_next 
        mm_objs[range(addr, addr+size)] = mm
        
        return addr

    def unmap_iospace(self, virt_addr):
        global _find_mm_obj
        global mm_objs

        _, mm, k = _find_mm_obj(virt_addr)
        mm.close()

        del mm_objs[k]
        
        # todo - remove mapping from dict

    def map_physmem(self, phys_addr, size):
        return self.map_iospace(phys_addr, size)

    def unmap_physmem(self, virt_addr):
        self.unmap_iospace(virt_addr)

    def read_msr(self, msr):
        buf = struct.pack("@II", msr, 0)
        buf = self._transact(DriverControlCodes.READ_MSR, buf)
        return struct.unpack("@Q", buf)[0]

    def read_pcicfg(self, bus, device, function):
        buf = struct.pack("@III256s", bus, device, function, bytearray(256))
        buf = self._transact(DriverControlCodes.READ_PCICFG, buf)
        return struct.unpack("@III256s", buf)[3]

    @staticmethod
    def ReadMappedMemory(virt_addr, size):
        addr, mm, _ = _find_mm_obj(virt_addr)
        offset = virt_addr - addr
        return mm[offset:offset + size]
        #return ctypes.string_at(virt_addr, size)

    @staticmethod
    def WriteMappedMemory(virt_addr, buf):
        addr, mm, _ = _find_mm_obj(virt_addr)
        offset = virt_addr - addr
        mm[offset:offset + len(buf)] = buf