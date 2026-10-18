"""Exercise the Windows wire protocol without pywin32 or hardware."""

import importlib.util
from pathlib import Path
import struct
import sys
import types
import unittest
from unittest.mock import Mock, patch


def load_backend():
    """Load an isolated backend, restoring even pre-existing pywin32 modules."""
    file_api = types.ModuleType('win32file')
    file_api.GENERIC_READ = 0x80000000
    file_api.GENERIC_WRITE = 0x40000000
    file_api.FILE_SHARE_READ = 1
    file_api.FILE_SHARE_WRITE = 2
    file_api.OPEN_EXISTING = 3
    file_api.CreateFile = Mock(return_value=object())
    file_api.CloseHandle = Mock()
    file_api.DeviceIoControl = Mock(return_value=b'')
    memory_api = types.ModuleType('win32gui')
    memory_api.PyGetMemory = Mock()
    memory_api.PySetMemory = Mock()
    path = Path(__file__).resolve().parents[1] / 'divination' / 'windriver.py'
    spec = importlib.util.spec_from_file_location('windriver_under_test', path)
    backend = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {'win32file': file_api, 'win32gui': memory_api}):
        spec.loader.exec_module(backend)
    return backend, file_api, memory_api


class WindowsTests(unittest.TestCase):
    def setUp(self):
        self.backend, self.file_api, self.memory_api = load_backend()
        # These tests exercise the x64 ABI even if their host Python is 32-bit.
        with patch.object(self.backend.struct, 'calcsize', return_value=8):
            self.driver = self.backend.WinDriver()
        self.handle = self.driver.hDriver
        self.addCleanup(self.driver.close)

    def map_memory(self, physical=0x1234, size=8, address=0x10000):
        self.file_api.DeviceIoControl.return_value = struct.pack('<Q', address)
        result = self.driver.map_iospace(physical, size)
        self.file_api.DeviceIoControl.return_value = b''
        return result

    def test_module_import_does_not_replace_existing_modules(self):
        sentinel_file = types.ModuleType('win32file')
        sentinel_gui = types.ModuleType('win32gui')
        with patch.dict(sys.modules, {'win32file': sentinel_file, 'win32gui': sentinel_gui}):
            load_backend()
            self.assertIs(sys.modules['win32file'], sentinel_file)
            self.assertIs(sys.modules['win32gui'], sentinel_gui)

    def test_device_open_parameters(self):
        self.file_api.CreateFile.assert_called_once_with(
            r'\\.\Divination', 0xc0000000, 3, None, 3, 0, None)

    def test_rejects_32_bit_python_before_opening(self):
        self.file_api.CreateFile.reset_mock()
        with patch.object(self.backend.struct, 'calcsize', return_value=4):
            with self.assertRaises(OSError):
                self.backend.WinDriver()
        self.file_api.CreateFile.assert_not_called()

    def test_mapping_and_unmapping_wire_protocol(self):
        address = self.map_memory()
        self.assertEqual(address, 0x10000)
        self.file_api.DeviceIoControl.assert_called_once_with(
            self.handle, 2, struct.pack('<QQ', 0x1234, 8), 8)
        self.driver.unmap_iospace(address)
        self.file_api.DeviceIoControl.assert_called_with(
            self.handle, 3, struct.pack('<Q', address), 0)
        with self.assertRaises(ValueError):
            self.driver.ReadMappedMemory(address, 1)

    def test_msr_read_and_write_wire_protocol(self):
        self.file_api.DeviceIoControl.return_value = struct.pack('<Q', 0x0123456789abcdef)
        self.assertEqual(self.driver.read_msr(0xc0010015), 0x0123456789abcdef)
        self.file_api.DeviceIoControl.assert_called_once_with(
            self.handle, 1, struct.pack('<I', 0xc0010015), 8)
        self.file_api.DeviceIoControl.return_value = b''
        self.driver.write_msr(0xffffffff, 0xffffffffffffffff)
        self.file_api.DeviceIoControl.assert_called_with(
            self.handle, 6, struct.pack('<IIQ', 0xffffffff, 0, 0xffffffffffffffff), 0)

    def test_pci_wire_protocol(self):
        self.file_api.DeviceIoControl.return_value = bytes(range(256))
        self.assertEqual(self.driver.read_pcicfg(255, 31, 7), bytes(range(256)))
        self.file_api.DeviceIoControl.assert_called_once_with(
            self.handle, 0, struct.pack('<III', 255, 31, 7), 256)

    def test_invalid_requests_do_not_reach_device(self):
        calls = (
            lambda: self.driver.map_iospace(-1, 8),
            lambda: self.driver.map_iospace(0, 0),
            lambda: self.driver.map_iospace(0, 2**32),
            lambda: self.driver.map_iospace(1, 0xfffff000),
            lambda: self.driver.map_iospace(2**63 - 1, 2),
            lambda: self.driver.map_iospace(2**64, 1),
            lambda: self.driver.read_msr(-1),
            lambda: self.driver.read_msr(2**32),
            lambda: self.driver.write_msr(0, -1),
            lambda: self.driver.write_msr(0, 2**64),
            lambda: self.driver.read_pcicfg(256, 0, 0),
            lambda: self.driver.read_pcicfg(0, 32, 0),
            lambda: self.driver.read_pcicfg(0, 0, 8),
            lambda: self.driver.unmap_iospace(-1),
        )
        for call in calls:
            with self.subTest(call=call):
                with self.assertRaises(ValueError):
                    call()
        with self.assertRaises(TypeError):
            self.driver.read_msr(1.5)
        self.file_api.DeviceIoControl.assert_not_called()

    def test_mapping_bounds_and_memory_access(self):
        address = self.map_memory()
        data = bytearray(b'abcdefgh')
        self.memory_api.PyGetMemory.side_effect = lambda start, size: memoryview(data)[start-address:start-address+size]

        def write(start, value):
            data[start-address:start-address+len(value)] = value

        self.memory_api.PySetMemory.side_effect = write
        self.assertEqual(self.driver.ReadMappedMemory(address+2, 3), b'cde')
        self.driver.WriteMappedMemory(address+1, memoryview(b'XY'))
        self.assertEqual(data, b'aXYdefgh')
        self.memory_api.PyGetMemory.reset_mock()
        self.memory_api.PySetMemory.reset_mock()
        for start, size in ((address-1, 1), (address+7, 2),
                            (address+9, 0), (address, -1)):
            with self.assertRaises(ValueError):
                self.driver.ReadMappedMemory(start, size)
        with self.assertRaises(ValueError):
            self.driver.WriteMappedMemory(address+7, b'xx')
        with self.assertRaises(TypeError):
            self.driver.WriteMappedMemory(address, 2)
        self.assertEqual(self.driver.ReadMappedMemory(address+8, 0), b'')
        self.driver.WriteMappedMemory(address+8, b'')
        self.memory_api.PyGetMemory.assert_not_called()
        self.memory_api.PySetMemory.assert_not_called()

    def test_unmap_requires_owned_base(self):
        address = self.map_memory()
        self.file_api.DeviceIoControl.reset_mock()
        for invalid in (address+1, address-1, address+8):
            with self.assertRaises(ValueError):
                self.driver.unmap_iospace(invalid)
        self.file_api.DeviceIoControl.assert_not_called()
        with patch.object(self.backend.struct, 'calcsize', return_value=8):
            other = self.backend.WinDriver()
        try:
            with self.assertRaises(ValueError):
                other.ReadMappedMemory(address, 1)
            with self.assertRaises(ValueError):
                other.unmap_iospace(address)
        finally:
            other.close()
        self.assertIn(address, self.driver._mappings)

    def test_open_error_is_preserved(self):
        error = PermissionError('access denied')
        self.file_api.CreateFile.side_effect = error
        with patch.object(self.backend.struct, 'calcsize', return_value=8):
            with self.assertRaises(PermissionError) as caught:
                self.backend.WinDriver()
        self.assertIs(caught.exception, error)

    def test_mapping_error_is_preserved_without_recording_mapping(self):
        error = OSError('device mapping failed')
        self.file_api.DeviceIoControl.side_effect = error
        with self.assertRaises(OSError) as caught:
            self.driver.map_iospace(0, 8)
        self.assertIs(caught.exception, error)
        self.assertEqual(self.driver._mappings, {})

    def test_unmap_error_retains_mapping_for_retry(self):
        address = self.map_memory()
        error = OSError('device unmap failed')
        self.file_api.DeviceIoControl.side_effect = error
        with self.assertRaises(OSError) as caught:
            self.driver.unmap_iospace(address)
        self.assertIs(caught.exception, error)
        self.assertIn(address, self.driver._mappings)
        self.file_api.DeviceIoControl.side_effect = None
        self.driver.unmap_iospace(address)
        self.assertEqual(self.driver._mappings, {})

    def test_wrong_response_lengths(self):
        cases = (
            (lambda: self.driver.read_msr(0), b''),
            (lambda: self.driver.read_msr(0), bytes(9)),
            (lambda: self.driver.read_pcicfg(0, 0, 0), bytes(255)),
            (lambda: self.driver.map_iospace(0, 8), bytes(7)),
            (lambda: self.driver.write_msr(0, 0), b'x'),
        )
        for operation, response in cases:
            with self.subTest(response_length=len(response)):
                self.file_api.DeviceIoControl.return_value = response
                with self.assertRaises(OSError):
                    operation()
        self.assertEqual(self.driver._mappings, {})

    def test_invalid_mapping_addresses(self):
        for address in (0, 2**64 - 1):
            with self.subTest(address=address):
                self.file_api.DeviceIoControl.return_value = struct.pack('<Q', address)
                with self.assertRaises(OSError):
                    self.driver.map_iospace(0, 8)
        self.assertEqual(self.driver._mappings, {})

    def test_physical_ram_mapping_is_explicitly_unsupported(self):
        with self.assertRaises(NotImplementedError):
            self.driver.map_physmem(0, 8)
        with self.assertRaises(NotImplementedError):
            self.driver.unmap_physmem(0x10000)
        self.file_api.DeviceIoControl.assert_not_called()

    def test_close_releases_handle_once_and_rejects_access(self):
        address = self.map_memory()
        self.driver.close()
        self.driver.close()
        self.file_api.CloseHandle.assert_called_once_with(self.handle)
        self.assertEqual(self.driver._mappings, {})
        self.assertIsNone(self.driver.hDriver)
        self.file_api.DeviceIoControl.reset_mock()
        for operation in (lambda: self.driver.read_msr(0),
                          lambda: self.driver.map_iospace(0, 8),
                          lambda: self.driver.unmap_iospace(address),
                          lambda: self.driver.ReadMappedMemory(address, 1),
                          lambda: self.driver.WriteMappedMemory(address, b'a'),
                          lambda: self.driver.map_physmem(0, 8),
                          self.driver.__enter__):
            with self.assertRaises(ValueError):
                operation()
        self.file_api.DeviceIoControl.assert_not_called()
        self.memory_api.PyGetMemory.assert_not_called()
        self.memory_api.PySetMemory.assert_not_called()

    def test_context_exception_closes_handle(self):
        with self.assertRaisesRegex(RuntimeError, 'body failed'):
            with self.driver as active:
                self.assertIs(active, self.driver)
                self.map_memory()
                raise RuntimeError('body failed')
        self.file_api.CloseHandle.assert_called_once_with(self.handle)
        self.assertEqual(self.driver._mappings, {})


if __name__ == '__main__':
    unittest.main()
