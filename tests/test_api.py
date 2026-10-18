from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import divination
from divination import Driver, MemoryObject, MemoryType, Msr, PciDevice


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.driver = Mock()
        self.driver.map_iospace.return_value = 0x1000
        self.driver.map_physmem.return_value = 0x1000
        self.data = bytearray(b'abcdefgh')
        self.driver.ReadMappedMemory.side_effect = lambda address, size: self.data[address-0x1000:address-0x1000+size]
        def write(address, data):
            self.data[address-0x1000:address-0x1000+len(data)] = data
        self.driver.WriteMappedMemory.side_effect = write
        self.patch = patch.object(divination, 'DRIVER', self.driver)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.memory = MemoryObject(0x1234, 8, MemoryType.IoSpace)
        self.addCleanup(self.memory.close)

    def test_mapping_and_context_cleanup(self):
        self.driver.map_iospace.assert_called_once_with(0x1234, 8)
        with self.memory as memory:
            self.assertIs(memory, self.memory)
            self.assertEqual(len(memory), 8)
        self.memory.close()
        self.driver.unmap_iospace.assert_called_once_with(0x1000)
        self.assertTrue(memory.closed)

    def test_physical_mapping(self):
        with MemoryObject(0, 8, MemoryType.PhysMem) as memory:
            self.assertEqual(memory[:], b'abcdefgh')
        self.driver.map_physmem.assert_called_once_with(0, 8)
        self.driver.unmap_physmem.assert_called_once_with(0x1000)

    def test_context_exception_cleanup(self):
        with self.assertRaises(RuntimeError):
            with self.memory:
                raise RuntimeError('test')
        self.assertTrue(self.memory.closed)

    def test_reads_and_slices_match_bytes(self):
        for key in (slice(None), slice(2, 6), slice(None, None, -1),
                    slice(6, 2), slice(-5, -1), slice(100), slice(100, 200),
                    slice(None, None, 2), slice(5, 1, -2)):
            with self.subTest(key=key):
                self.assertEqual(self.memory[key], bytes(self.data[key]))
        self.assertEqual(self.memory[0], b'a')
        self.assertEqual(self.memory[-1], b'h')
        self.assertEqual(self.memory[-8], b'a')

    def test_contiguous_read_is_one_transaction(self):
        self.assertEqual(self.memory[:], b'abcdefgh')
        self.driver.ReadMappedMemory.assert_called_once_with(0x1000, 8)

    def test_invalid_indices(self):
        for key in (-9, 8):
            with self.assertRaises(IndexError):
                self.memory[key]
        with self.assertRaises(TypeError):
            self.memory[1.5]
        with self.assertRaises(ValueError):
            self.memory[::0]

    def test_writes(self):
        self.memory[-1] = 255
        self.memory[1:3] = b'XY'
        self.memory[4:8:2] = memoryview(b'12')
        self.assertEqual(self.data, b'aXYd1f2\xff')
        self.memory[::-1] = b'87654321'
        self.assertEqual(self.data, b'12345678')

    def test_invalid_slice_assignment_never_partially_writes(self):
        for key, value in ((slice(0, 3), b'12'), (slice(0, 2), b'123'),
                           (slice(None, None, 2), b'12'), (slice(0, 2), 2)):
            with self.subTest(key=key, value=value):
                with self.assertRaises((ValueError, TypeError)):
                    self.memory[key] = value
        self.driver.WriteMappedMemory.assert_not_called()

    def test_invalid_byte(self):
        for value in (-1, 256, b'a', 1.5):
            with self.assertRaises((ValueError, TypeError)):
                self.memory[0] = value
        self.driver.WriteMappedMemory.assert_not_called()

    def test_bounds(self):
        for offset, size in ((-1, 1), (0, -1), (7, 2), (9, 0), (0, 9)):
            with self.subTest(offset=offset, size=size):
                with self.assertRaises(ValueError):
                    self.memory.read(offset, size)
        for offset, data in ((-1, b'x'), (7, b'xx'), (9, b'')):
            with self.assertRaises(ValueError):
                self.memory.write(offset, data)
        self.driver.ReadMappedMemory.assert_not_called()
        self.driver.WriteMappedMemory.assert_not_called()

    def test_empty_access(self):
        self.assertEqual(self.memory.read(8, 0), b'')
        self.memory.write(8, b'')
        self.memory[6:2] = b''
        self.driver.ReadMappedMemory.assert_not_called()
        self.driver.WriteMappedMemory.assert_not_called()

    def test_closed_access(self):
        self.memory.close()
        for call in (lambda: self.memory[:], lambda: self.memory.read(0, 0),
                     lambda: self.memory.write(0, b''), self.memory.__enter__):
            with self.assertRaises(ValueError):
                call()

    def test_mapping_retains_owner(self):
        other = Mock()
        with patch.object(divination, 'DRIVER', other):
            self.assertEqual(self.memory[0], b'a')
            self.memory.close()
        other.assert_not_called()
        self.driver.unmap_iospace.assert_called_once()

    def test_failed_close_can_be_retried(self):
        self.driver.unmap_iospace.side_effect = [OSError('busy'), None]
        with self.assertRaises(OSError):
            self.memory.close()
        self.assertFalse(self.memory.closed)
        self.memory.close()
        self.assertTrue(self.memory.closed)

    def test_constructor_validation(self):
        for address, length, mem_type in ((-1, 8, MemoryType.IoSpace),
                                         (0, 0, MemoryType.IoSpace),
                                         (2**64-1, 2, MemoryType.IoSpace),
                                         (0, 8, 1)):
            with self.assertRaises(ValueError):
                MemoryObject(address, length, mem_type)
        with self.assertRaises(NotImplementedError):
            MemoryObject(0, 8, MemoryType.PhysMem, alloc=True)
        with self.assertRaises(ValueError):
            MemoryObject(0, 8, MemoryType.IoSpace, alloc=True)

    def test_failed_mapping(self):
        self.driver.map_iospace.return_value = 0
        with self.assertRaises(OSError):
            MemoryObject(0, 8, MemoryType.IoSpace)
        self.driver.map_iospace.side_effect = PermissionError('denied')
        with self.assertRaises(PermissionError):
            MemoryObject(0, 8, MemoryType.IoSpace)


class RegisterTests(unittest.TestCase):
    def test_pci_validation(self):
        for args in ((256, 0, 0), (-1, 0, 0), (0, 32, 0), (0, 0, 8)):
            with self.assertRaises(ValueError):
                PciDevice(*args)
        with patch.object(divination, 'DRIVER') as driver:
            PciDevice(255, 31, 7).read_cfg()
            driver.read_pcicfg.assert_called_once_with(255, 31, 7)

    def test_msr_validation_and_write(self):
        for msr in (-1, 2**32):
            with self.assertRaises(ValueError):
                Msr(msr)
        with patch.object(divination, 'DRIVER') as driver:
            register = Msr(0xc0010015)
            register.read()
            register.write(2**64-1)
            driver.read_msr.assert_called_once_with(0xc0010015)
            driver.write_msr.assert_called_once_with(0xc0010015, 2**64-1)
            for value in (-1, 2**64):
                with self.assertRaises(ValueError):
                    register.write(value)


class DriverTests(unittest.TestCase):
    def test_backend_opens_lazily_once_and_failed_open_can_retry(self):
        backend = Mock()
        factory = Mock(side_effect=[PermissionError('denied'), backend])
        with patch.dict(sys.modules, {'divination.lindriver': SimpleNamespace(LinDriver=factory)}), \
                patch('platform.machine', return_value='x86_64'), \
                patch('platform.system', return_value='Linux'):
            driver = Driver()
            factory.assert_not_called()
            with self.assertRaises(PermissionError):
                driver.read_msr(1)
            self.assertIsNone(driver.driver)
            driver.read_msr(1)
            driver.read_msr(2)
            self.assertEqual(factory.call_count, 2)
            self.assertEqual(backend.read_msr.call_count, 2)
            driver.close()
            backend.close.assert_called_once()

    def test_import_does_not_open_device(self):
        root = str(Path(__file__).resolve().parents[1])
        result = subprocess.run([sys.executable, '-c',
            "from unittest.mock import patch; "
            "guard = patch('os.open', side_effect=AssertionError('device opened')); "
            "guard.start(); import divination; print('imported')"],
            cwd=root, capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout.strip(), 'imported')
        self.assertEqual(result.stderr, '')

    def test_close_without_opening(self):
        driver = Driver()
        driver.close()
        driver.close()
        with self.assertRaises(ValueError):
            driver.read_msr(1)

    def test_dispatch_and_close(self):
        backend = Mock()
        driver = Driver()
        driver.driver = backend
        driver.write_msr(1, 2)
        backend.write_msr.assert_called_once_with(1, 2)
        with driver:
            self.assertIs(driver.driver, backend)
        driver.close()
        backend.close.assert_called_once()

    def test_unsupported_os(self):
        driver = Driver()
        with patch('platform.machine', return_value='x86_64'), patch('platform.system', return_value='Darwin'):
            with self.assertRaises(NotImplementedError):
                driver.read_msr(0)
        driver.close()

    def test_unsupported_architecture(self):
        driver = Driver()
        with patch('platform.machine', return_value='aarch64'):
            with self.assertRaises(NotImplementedError):
                driver.read_msr(0)
        driver.close()


if __name__ == '__main__':
    unittest.main()
