"""Lazy, platform-independent driver dispatch."""

import platform
import struct
import threading


class Driver:
    def __init__(self):
        self.driver = None
        self._closed = False
        self._lock = threading.RLock()

    def _get_driver(self):
        if self._closed:
            raise ValueError('driver is closed')
        if self.driver is None:
            if struct.calcsize('P') != 8 or platform.machine().lower() not in (
                'x86_64', 'amd64',
            ):
                raise NotImplementedError('divination requires 64-bit x86 Python and OS')
            system = platform.system()
            if system == 'Windows':
                from .windriver import WinDriver
                self.driver = WinDriver()
            elif system == 'Linux':
                from .lindriver import LinDriver
                self.driver = LinDriver()
            else:
                raise NotImplementedError('unsupported operating system: ' + system)
        return self.driver

    def _call(self, method, *args):
        with self._lock:
            return getattr(self._get_driver(), method)(*args)

    def map_iospace(self, phys_addr, size):
        return self._call('map_iospace', phys_addr, size)

    def unmap_iospace(self, virt_addr):
        return self._call('unmap_iospace', virt_addr)

    def map_physmem(self, phys_addr, size):
        return self._call('map_physmem', phys_addr, size)

    def unmap_physmem(self, virt_addr):
        return self._call('unmap_physmem', virt_addr)

    def read_msr(self, msr):
        return self._call('read_msr', msr)

    def write_msr(self, msr, value):
        return self._call('write_msr', msr, value)

    def read_pcicfg(self, bus, device, function):
        return self._call('read_pcicfg', bus, device, function)

    def ReadMappedMemory(self, virt_addr, size):
        return self._call('ReadMappedMemory', virt_addr, size)

    def WriteMappedMemory(self, virt_addr, buf):
        return self._call('WriteMappedMemory', virt_addr, buf)

    def close(self):
        with self._lock:
            if not self._closed:
                if self.driver is not None:
                    self.driver.close()
                self._closed = True

    def __enter__(self):
        with self._lock:
            self._get_driver()
        return self

    def __exit__(self, *exc):
        self.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
