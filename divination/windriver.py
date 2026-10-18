"""Windows x64 driver transport and ownership of mapped I/O regions."""

import operator
import struct
import threading
from enum import Enum

import win32file
import win32gui


class DriverControlCodes(Enum):
    READ_PCICFG = 0x00
    READ_MSR = 0x01
    MAP_IOSPACE = 0x02
    UNMAP_IOSPACE = 0x03
    MAP_PHYSMEM = 0x04
    UNMAP_PHYSMEM = 0x05
    WRITE_MSR = 0x06


def _uint(value, bits, name):
    value = operator.index(value)
    if value < 0 or value >= 1 << bits:
        raise ValueError(f"{name} must be an unsigned {bits}-bit integer")
    return value


class WinDriver:
    def __init__(self):
        self.hDriver = None
        self._mappings = {}
        self._lock = threading.RLock()
        if struct.calcsize("P") != 8:
            raise OSError("Divination requires 64-bit Python on Windows")
        # Preserve native error information (missing driver, access denied, etc.).
        self.hDriver = win32file.CreateFile(
            r"\\.\Divination", win32file.GENERIC_READ | win32file.GENERIC_WRITE,
            win32file.FILE_SHARE_READ | win32file.FILE_SHARE_WRITE, None,
            win32file.OPEN_EXISTING, 0, None,
        )

    def _ensure_open(self):
        if self.hDriver is None:
            raise ValueError("Driver is closed")

    def _transact(self, ctrl_code, in_buf, out_size=0):
        with self._lock:
            self._ensure_open()
            result = win32file.DeviceIoControl(
                self.hDriver, ctrl_code.value, in_buf, out_size
            )
            if len(result) != out_size:
                raise OSError(f"Driver returned {len(result)} bytes; expected {out_size}")
            return result

    def map_iospace(self, phys_addr, size):
        phys_addr = _uint(phys_addr, 64, "physical address")
        size = _uint(size, 32, "size")
        # The driver's I/O MDL is page aligned and has a ULONG byte count.
        if not size or size + (phys_addr & 0xFFF) > 0xFFFFF000:
            raise ValueError("Invalid mapping size")
        if phys_addr + size > 1 << 63:
            raise ValueError("Physical address range exceeds the driver limit")
        with self._lock:
            address, = struct.unpack("<Q", self._transact(
                DriverControlCodes.MAP_IOSPACE, struct.pack("<QQ", phys_addr, size), 8
            ))
            if not address or address + size > 1 << 64:
                raise OSError("Driver returned an invalid mapping address")
            self._mappings[address] = size
            return address

    def unmap_iospace(self, virt_addr):
        virt_addr = _uint(virt_addr, 64, "virtual address")
        with self._lock:
            self._ensure_open()
            if virt_addr not in self._mappings:
                raise ValueError("Address is not owned by this driver instance")
            self._transact(DriverControlCodes.UNMAP_IOSPACE, struct.pack("<Q", virt_addr))
            del self._mappings[virt_addr]

    def map_physmem(self, phys_addr, size):
        self._ensure_open()
        raise NotImplementedError("Windows does not support mapping arbitrary physical RAM")

    def unmap_physmem(self, virt_addr):
        self._ensure_open()
        raise NotImplementedError("Windows does not support mapping arbitrary physical RAM")

    def read_msr(self, msr):
        msr = _uint(msr, 32, "MSR")
        return struct.unpack("<Q", self._transact(
            DriverControlCodes.READ_MSR, struct.pack("<I", msr), 8
        ))[0]

    def write_msr(self, msr, value):
        msr = _uint(msr, 32, "MSR")
        value = _uint(value, 64, "MSR value")
        self._transact(DriverControlCodes.WRITE_MSR, struct.pack("<IIQ", msr, 0, value))

    def read_pcicfg(self, bus, device, function):
        bus = _uint(bus, 8, "bus")
        device = _uint(device, 5, "device")
        function = _uint(function, 3, "function")
        return self._transact(
            DriverControlCodes.READ_PCICFG, struct.pack("<III", bus, device, function), 0x100
        )

    def _check_range(self, address, size):
        self._ensure_open()
        address = _uint(address, 64, "virtual address")
        size = _uint(size, 64, "size")
        for base, length in self._mappings.items():
            if base <= address <= base + length and size <= base + length - address:
                return address, size
        raise ValueError("Memory access falls outside this driver's mappings")

    def ReadMappedMemory(self, virt_addr, size):
        with self._lock:
            address, size = self._check_range(virt_addr, size)
            return bytes(win32gui.PyGetMemory(address, size)) if size else b""

    def WriteMappedMemory(self, virt_addr, buf):
        # memoryview rejects integers (bytes(integer) would silently write zeros).
        data = memoryview(buf).tobytes()
        with self._lock:
            address, size = self._check_range(virt_addr, len(data))
            if size:
                win32gui.PySetMemory(address, data)

    def close(self):
        with self._lock:
            if self.hDriver is not None:
                # IRP_MJ_CLEANUP releases every mapping, including after exceptions.
                win32file.CloseHandle(self.hDriver)
                self.hDriver = None
                self._mappings.clear()

    def __enter__(self):
        self._ensure_open()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
