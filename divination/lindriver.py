"""Linux transport. All mapping bookkeeping belongs to its device handle."""

import fcntl
import mmap
from enum import IntEnum
import os
import struct
import sys
import threading

from ._validation import buffer_bytes, integer, region


class DriverControlCodes(IntEnum):
    READ_PCICFG = 0x00
    READ_MSR = 0x01
    MAP_IOSPACE = 0x02
    WRITE_MSR = 0x06


class LinDriver:
    def __init__(self):
        self.fd = None
        self._lock = threading.RLock()
        self._mappings = {}
        self._next_address = 0x100000000
        self.fd = os.open('/dev/divination', os.O_RDWR | os.O_SYNC | os.O_CLOEXEC)

    def _check_open(self):
        if self.fd is None:
            raise ValueError('driver is closed')

    def _transact(self, ctrl_code, buf):
        with self._lock:
            self._check_open()
            data = bytearray(buf)
            fcntl.ioctl(self.fd, 0xc008e000 + ctrl_code.value, data, True)
            return bytes(data)

    def map_iospace(self, phys_addr, size):
        phys_addr, size = region(phys_addr, size)
        page_offset = phys_addr % mmap.PAGESIZE
        mapped_size = page_offset + size
        # Check the expanded mmap length before any hardware request.
        integer(mapped_size, 'mapping size', minimum=1, maximum=sys.maxsize)
        with self._lock:
            self._check_open()
            self._transact(DriverControlCodes.MAP_IOSPACE,
                           struct.pack('<Q', phys_addr - page_offset))
            mm = mmap.mmap(self.fd, mapped_size, flags=mmap.MAP_SHARED,
                           prot=mmap.PROT_READ | mmap.PROT_WRITE)
            address = self._next_address
            self._next_address += size + mmap.PAGESIZE
            self._mappings[address] = (mm, page_offset, size)
            return address

    def unmap_iospace(self, virt_addr):
        with self._lock:
            self._check_open()
            if virt_addr not in self._mappings:
                raise ValueError('address is not a mapping base')
            self._mappings[virt_addr][0].close()
            del self._mappings[virt_addr]

    def map_physmem(self, phys_addr, size):
        return self.map_iospace(phys_addr, size)

    def unmap_physmem(self, virt_addr):
        self.unmap_iospace(virt_addr)

    def read_msr(self, msr):
        msr = integer(msr, 'MSR', maximum=0xffffffff)
        return struct.unpack('<Q', self._transact(
            DriverControlCodes.READ_MSR, struct.pack('<II', msr, 0)))[0]

    def write_msr(self, msr, value):
        msr = integer(msr, 'MSR', maximum=0xffffffff)
        value = integer(value, 'MSR value', maximum=0xffffffffffffffff)
        self._transact(DriverControlCodes.WRITE_MSR, struct.pack('<IIQ', msr, 0, value))

    def read_pcicfg(self, bus, device, function):
        bus = integer(bus, 'bus', maximum=255)
        device = integer(device, 'device', maximum=31)
        function = integer(function, 'function', maximum=7)
        result = self._transact(DriverControlCodes.READ_PCICFG,
                               struct.pack('<III256s', bus, device, function, b''))
        return result[12:]

    def _find_mapping(self, address, size):
        self._check_open()
        address = integer(address, 'virtual address')
        size = integer(size, 'size')
        for base, (mm, page_offset, length) in self._mappings.items():
            offset = address - base
            if 0 <= offset <= length and size <= length - offset:
                return mm, page_offset + offset
        raise ValueError('access exceeds mapped memory range')

    def ReadMappedMemory(self, virt_addr, size):
        size = integer(size, 'size')
        with self._lock:
            mm, offset = self._find_mapping(virt_addr, size)
            return mm[offset:offset + size]

    def WriteMappedMemory(self, virt_addr, buf):
        data = buffer_bytes(buf)
        with self._lock:
            mm, offset = self._find_mapping(virt_addr, len(data))
            mm[offset:offset + len(data)] = data

    def close(self):
        with self._lock:
            if self.fd is None:
                return
            for address in list(self._mappings):
                self.unmap_iospace(address)
            fd = self.fd
            # Linux releases the descriptor even if close reports an I/O error.
            # Never retry it: another thread may already have reused the number.
            self.fd = None
            os.close(fd)

    def __enter__(self):
        self._check_open()
        return self

    def __exit__(self, *exc):
        self.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
