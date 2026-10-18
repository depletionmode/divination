import mmap
import struct
import sys
import threading
import unittest
from unittest.mock import patch

if sys.platform.startswith('linux'):
    from divination.lindriver import LinDriver


@unittest.skipUnless(sys.platform.startswith('linux'), 'Linux transport')
class LinuxTests(unittest.TestCase):
    def setUp(self):
        self.open = patch('divination.lindriver.os.open', return_value=42).start()
        self.close = patch('divination.lindriver.os.close').start()
        self.ioctl = patch('divination.lindriver.fcntl.ioctl', return_value=0).start()
        self.addCleanup(patch.stopall)
        self.driver = LinDriver()
        self.addCleanup(self.driver.close)

    def map_memory(self, address=0x1234, size=8):
        # A real anonymous mmap exercises slicing/close without hardware access.
        real_map = mmap.mmap(-1, address % mmap.PAGESIZE + size)
        with patch('divination.lindriver.mmap.mmap', return_value=real_map) as factory:
            base = self.driver.map_iospace(address, size)
        return base, real_map, factory

    def test_unaligned_mapping(self):
        base, mm, factory = self.map_memory()
        factory.assert_called_once_with(42, 0x234+8, flags=mmap.MAP_SHARED,
                                        prot=mmap.PROT_READ | mmap.PROT_WRITE)
        self.ioctl.assert_called_once_with(42, 0xc008e002, bytearray(struct.pack('<Q', 0x1000)), True)
        self.driver.WriteMappedMemory(base, b'abcdefgh')
        self.assertEqual(mm[0x234:0x23c], b'abcdefgh')
        self.assertEqual(mm[:0x234], bytes(0x234))
        self.assertEqual(self.driver.ReadMappedMemory(base+2, 3), b'cde')
        self.driver.unmap_iospace(base)
        self.assertTrue(mm.closed)

    def test_mapping_zero_and_page_crossing(self):
        base, mm, _ = self.map_memory(0, 4)
        self.assertGreater(base, 0)
        self.driver.WriteMappedMemory(base, b'zero')
        self.assertEqual(mm[:], b'zero')
        base, mm, _ = self.map_memory(mmap.PAGESIZE-1, 3)
        self.driver.WriteMappedMemory(base, b'abc')
        self.assertEqual(mm[mmap.PAGESIZE-1:], b'abc')

    def test_bounds_and_unknown_mapping(self):
        base, _, _ = self.map_memory()
        for address, size in ((base-1, 1), (base+7, 2), (base, -1), (base+9, 0)):
            with self.assertRaises(ValueError):
                self.driver.ReadMappedMemory(address, size)
        with self.assertRaises(ValueError):
            self.driver.WriteMappedMemory(base+7, b'xx')
        with self.assertRaises(ValueError):
            self.driver.unmap_iospace(base+1)
        self.assertEqual(self.driver.ReadMappedMemory(base+8, 0), b'')
        self.driver.unmap_iospace(base)
        with self.assertRaises(ValueError):
            self.driver.ReadMappedMemory(base, 1)

    def test_multiple_mappings_do_not_overlap(self):
        first, _, _ = self.map_memory(0, 0x10000)
        second, _, _ = self.map_memory(0, 16)
        self.assertGreaterEqual(second, first+0x10000)
        self.driver.WriteMappedMemory(first, b'a')
        self.driver.WriteMappedMemory(second, b'b')
        self.assertEqual(self.driver.ReadMappedMemory(first, 1), b'a')
        self.assertEqual(self.driver.ReadMappedMemory(second, 1), b'b')

    def test_mapping_ioctl_and_mmap_are_one_serialized_operation(self):
        first_in_mmap = threading.Event()
        release_first = threading.Event()
        second_attempted_lock = threading.Event()
        second_lock_results = []
        calls = []
        errors = []
        addresses = []
        real_maps = [mmap.mmap(-1, 8), mmap.mmap(-1, 8)]
        for mm in real_maps:
            self.addCleanup(mm.close)

        # Observe a real acquisition attempt, rather than assuming the second
        # worker was scheduled after an arbitrary sleep. Timeouts bound failures.
        class ObservedLock:
            def __init__(self):
                self.lock = threading.RLock()

            def __enter__(self):
                acquired = self.lock.acquire(blocking=False)
                if threading.current_thread().name == 'second-mapper':
                    second_lock_results.append(acquired)
                    second_attempted_lock.set()
                if not acquired and not self.lock.acquire(timeout=5):
                    raise TimeoutError('mapping lock was never released')
                return self

            def __exit__(self, *exc):
                self.lock.release()

        self.driver._lock = ObservedLock()

        def ioctl(fd, code, data, mutate):
            calls.append(('ioctl', struct.unpack('<Q', data)[0]))

        def map_region(*args, **kwargs):
            worker = threading.current_thread().name
            calls.append(('mmap', worker))
            if worker == 'first-mapper':
                first_in_mmap.set()
                if not release_first.wait(5):
                    raise TimeoutError('first mapping was never released')
                return real_maps[0]
            return real_maps[1]

        def worker(physical):
            try:
                addresses.append(self.driver.map_iospace(physical, 8))
            except Exception as error:
                errors.append(error)

        first = threading.Thread(target=worker, args=(0x1000,),
                                 name='first-mapper', daemon=True)
        second = threading.Thread(target=worker, args=(0x2000,),
                                  name='second-mapper', daemon=True)
        self.ioctl.side_effect = ioctl
        with patch('divination.lindriver.mmap.mmap', side_effect=map_region):
            first.start()
            try:
                self.assertTrue(first_in_mmap.wait(5), 'first worker did not reach mmap')
                second.start()
                self.assertTrue(second_attempted_lock.wait(5), 'second worker did not run')
                self.assertFalse(second_lock_results[0],
                                 'second mapping entered before first mmap completed')
                self.assertEqual(calls, [('ioctl', 0x1000), ('mmap', 'first-mapper')])
            finally:
                release_first.set()
                first.join(5)
                if second.ident is not None:
                    second.join(5)
        self.assertFalse(first.is_alive() or second.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(len(set(addresses)), 2)
        self.assertEqual(calls, [('ioctl', 0x1000), ('mmap', 'first-mapper'),
                                ('ioctl', 0x2000), ('mmap', 'second-mapper')])

    def test_mapping_ownership_is_per_instance(self):
        base, mm, _ = self.map_memory()
        self.driver.WriteMappedMemory(base, b'owned')
        self.open.return_value = 43
        with LinDriver() as other:
            with self.assertRaises(ValueError):
                other.ReadMappedMemory(base, 1)
            with self.assertRaises(ValueError):
                other.unmap_iospace(base)
        self.assertFalse(mm.closed)
        self.assertEqual(self.driver.ReadMappedMemory(base, 5), b'owned')

    def test_close_releases_all_resources(self):
        _, one, _ = self.map_memory()
        _, two, _ = self.map_memory()
        self.driver.close()
        self.driver.close()
        self.assertTrue(one.closed and two.closed)
        self.close.assert_called_once_with(42)
        with self.assertRaises(ValueError):
            self.driver.read_msr(0)

    def test_close_error_never_retries_released_descriptor(self):
        _, mm, _ = self.map_memory()
        self.close.side_effect = OSError('close failed')
        with self.assertRaises(OSError):
            self.driver.close()
        self.assertTrue(mm.closed)
        self.driver.close()
        self.close.assert_called_once_with(42)

    def test_index_protocol_size(self):
        class Size:
            def __index__(self):
                return 1

        base, _, _ = self.map_memory()
        self.driver.WriteMappedMemory(base, b'a')
        self.assertEqual(self.driver.ReadMappedMemory(base, Size()), b'a')

    def test_msr_wire_protocol(self):
        def ioctl(fd, code, data, mutate):
            self.assertEqual(code, 0xc008e001)
            self.assertEqual(data, struct.pack('<II', 0x123, 0))
            data[:] = struct.pack('<Q', 0x0123456789abcdef)
        self.ioctl.side_effect = ioctl
        self.assertEqual(self.driver.read_msr(0x123), 0x0123456789abcdef)
        self.ioctl.side_effect = None
        self.driver.write_msr(0x123, 0x0123456789abcdef)
        self.ioctl.assert_called_with(42, 0xc008e006,
            bytearray(struct.pack('<IIQ', 0x123, 0, 0x0123456789abcdef)), True)

    def test_pci_wire_protocol(self):
        def ioctl(fd, code, data, mutate):
            self.assertEqual(code, 0xc008e000)
            self.assertEqual(data[:12], struct.pack('<III', 255, 31, 7))
            data[12:] = bytes(range(256))
        self.ioctl.side_effect = ioctl
        self.assertEqual(self.driver.read_pcicfg(255, 31, 7), bytes(range(256)))

    def test_invalid_requests_do_not_reach_kernel(self):
        for call in (lambda: self.driver.map_iospace(-1, 1),
                     lambda: self.driver.map_iospace(0, 0),
                     lambda: self.driver.map_iospace(2**64-1, 2),
                     lambda: self.driver.read_msr(2**32),
                     lambda: self.driver.write_msr(0, 2**64),
                     lambda: self.driver.read_pcicfg(0, 32, 0)):
            with self.assertRaises(ValueError):
                call()
        self.ioctl.assert_not_called()

    def test_ioctl_failure_does_not_create_mapping(self):
        self.ioctl.side_effect = OSError('ioctl failed')
        with patch('divination.lindriver.mmap.mmap') as factory:
            with self.assertRaises(OSError):
                self.driver.map_iospace(0, 8)
        factory.assert_not_called()
        self.assertEqual(self.driver._mappings, {})

    def test_mmap_failure_does_not_create_mapping(self):
        with patch('divination.lindriver.mmap.mmap', side_effect=OSError('mmap failed')):
            with self.assertRaises(OSError):
                self.driver.map_iospace(0, 8)
        self.assertEqual(self.driver._mappings, {})

    def test_permission_error_is_preserved(self):
        self.open.side_effect = PermissionError('denied')
        with self.assertRaises(PermissionError):
            LinDriver()


if __name__ == '__main__':
    unittest.main()
