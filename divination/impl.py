"""Public hardware objects and checked access to fixed-size mappings."""

from enum import Enum
import operator
import threading

from ._validation import buffer_bytes, integer, region


def _driver():
    import divination
    return divination.DRIVER


class MemoryType(Enum):
    IoSpace = 1
    PhysMem = 2


class MemoryObject:
    def __init__(self, base_address, range, mem_type, alloc=False):
        self.virt_addr = 0
        self._lock = threading.RLock()
        self.base_address, self.range = region(base_address, range)
        if not isinstance(mem_type, MemoryType):
            raise ValueError('invalid memory type')
        self.mem_type = mem_type
        self.is_allocated = False
        if alloc:
            if base_address != 0 or mem_type != MemoryType.PhysMem:
                raise ValueError('allocation requires address zero and PhysMem')
            raise NotImplementedError('physical memory allocation is not supported')
        self._driver = _driver()
        mapper = (self._driver.map_iospace if mem_type == MemoryType.IoSpace
                  else self._driver.map_physmem)
        address = mapper(self.base_address, self.range)
        if not isinstance(address, int) or address <= 0:
            raise OSError('invalid virtual address returned by driver')
        self.virt_addr = address

    @property
    def closed(self):
        return self.virt_addr == 0

    def close(self):
        with self._lock:
            if not self.closed:
                unmap = (self._driver.unmap_iospace if self.mem_type == MemoryType.IoSpace
                         else self._driver.unmap_physmem)
                unmap(self.virt_addr)
                self.virt_addr = 0

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

    def __len__(self):
        return self.range

    def _check_open(self):
        if self.closed:
            raise ValueError('memory object is closed')

    def _bounds(self, offset, size):
        self._check_open()
        offset = integer(offset, 'offset')
        size = integer(size, 'size')
        if offset > self.range or size > self.range - offset:
            raise ValueError('access exceeds mapped memory range')
        return offset, size

    def _index(self, key):
        index = operator.index(key)
        if index < 0:
            index += self.range
        if index < 0 or index >= self.range:
            raise IndexError('index out of range')
        return index

    def __getitem__(self, key):
        with self._lock:
            self._check_open()
            if isinstance(key, slice):
                start, stop, step = key.indices(self.range)
                if step == 1:
                    return self.read(start, max(0, stop - start))
                return b''.join(self.read(i, 1) for i in range(start, stop, step))
            # Preserve the original API: an integer index returns one byte as bytes.
            return self.read(self._index(key), 1)

    def __setitem__(self, key, value):
        with self._lock:
            self._check_open()
            if isinstance(key, slice):
                start, stop, step = key.indices(self.range)
                indices = range(start, stop, step)
                data = buffer_bytes(value)
                if len(data) != len(indices):
                    raise ValueError('slice assignment cannot resize mapped memory')
                if step == 1:
                    self.write(start, data)
                else:
                    for i, byte in zip(indices, data):
                        self.write(i, bytes((byte,)))
            else:
                index = self._index(key)
                byte = integer(value, 'byte', maximum=255)
                self.write(index, bytes((byte,)))

    def read(self, offset, len):
        with self._lock:
            offset, size = self._bounds(offset, len)
            if size == 0:
                return b''
            return bytes(self._driver.ReadMappedMemory(self.virt_addr + offset, size))

    def write(self, offset, buf):
        with self._lock:
            data = buffer_bytes(buf)
            offset, size = self._bounds(offset, len(data))
            if size:
                self._driver.WriteMappedMemory(self.virt_addr + offset, data)


class PciDevice:
    def __init__(self, bus, device, function):
        self.bus = integer(bus, 'bus', maximum=255)
        self.device = integer(device, 'device', maximum=31)
        self.function = integer(function, 'function', maximum=7)

    def read_cfg(self):
        return _driver().read_pcicfg(self.bus, self.device, self.function)


class Msr:
    def __init__(self, msr):
        self.msr = integer(msr, 'MSR', maximum=0xffffffff)

    def read(self):
        return _driver().read_msr(self.msr)

    def write(self, value):
        value = integer(value, 'MSR value', maximum=0xffffffffffffffff)
        return _driver().write_msr(self.msr, value)
