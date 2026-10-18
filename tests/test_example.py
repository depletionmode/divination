"""Hardware-free regressions for the AMD ROM dump example."""

from contextlib import redirect_stdout
import importlib.util
import io
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


EXAMPLE = Path(__file__).resolve().parents[1] / 'examples' / 'amd_dump_flash.py'


class FlashExampleTests(unittest.TestCase):
    def setUp(self):
        self.mappings = []
        self.read_error = None
        test = self

        class Memory:
            def __init__(self, address, size, kind):
                self.address, self.size = address, size
                self.closed = False
                test.mappings.append(self)

            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.closed = True

            def __getitem__(self, key):
                if test.read_error is not None:
                    raise test.read_error
                return bytes((self.address + index) % 256 for index in range(self.size))

        self.backend = SimpleNamespace(
            MemoryObject=Memory,
            MemoryType=SimpleNamespace(IoSpace=1),
            PciDevice=Mock(side_effect=AssertionError('unexpected hardware access')),
        )
        self.module_patch = patch.dict(sys.modules, {'divination': self.backend, 'tqdm': None})
        self.module_patch.start()
        self.addCleanup(self.module_patch.stop)
        spec = importlib.util.spec_from_file_location('amd_dump_flash_example', EXAMPLE)
        self.example = importlib.util.module_from_spec(spec)
        with redirect_stdout(io.StringIO()) as output:
            spec.loader.exec_module(self.example)
        self.assertEqual(output.getvalue(), '')
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.output = Path(self.folder.name) / 'flash.bin'

    def test_import_and_help_do_not_access_hardware(self):
        self.backend.PciDevice.assert_not_called()
        with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as result:
            self.example.main(['--help'])
        self.assertEqual(result.exception.code, 0)
        self.backend.PciDevice.assert_not_called()
        self.assertEqual(self.mappings, [])

    def test_dump_includes_both_endpoints_and_only_requested_bytes(self):
        for start, end in ((0x1000, 0x1000), (0x1000, 0x1FFF), (0x1003, 0x2012)):
            with self.subTest(start=start, end=end):
                self.mappings.clear()
                self.example.dump_memory(start, end, self.output)
                self.assertEqual(self.output.read_bytes(), bytes(i % 256 for i in range(start, end + 1)))
                self.assertTrue(all(mapping.closed for mapping in self.mappings))
                self.assertEqual(sum(mapping.size for mapping in self.mappings), end - start + 1)
                self.assertTrue(all(mapping.size <= 4096 for mapping in self.mappings))
                self.assertEqual(self.mappings[-1].address + self.mappings[-1].size - 1, end)

    def test_invalid_intervals_fail_before_opening_output(self):
        for start, end, error in (
            (-1, 0, ValueError), (2, 1, ValueError), (0, 1 << 64, ValueError),
            ('1', 2, TypeError), (1, 2.0, TypeError),
        ):
            with self.subTest(start=start, end=end), self.assertRaises(error):
                self.example.dump_memory(start, end, self.output)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.mappings, [])

    def test_read_failure_closes_current_mapping_and_output(self):
        self.read_error = OSError('simulated read failure')
        with self.assertRaisesRegex(OSError, 'simulated read failure'):
            self.example.dump_memory(0x1000, 0x2FFF, self.output)
        self.assertEqual(len(self.mappings), 1)
        self.assertTrue(self.mappings[0].closed)
        # Windows refuses to unlink an open file, so this also checks file closure.
        self.output.unlink()

    def configure_pci(self, enables=0, vendor=0x1022):
        config = bytearray(256)
        struct.pack_into('<H', config, 0, vendor)
        struct.pack_into('<I', config, 0x48, enables)
        struct.pack_into('<HHHH', config, 0x68, 0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF)
        self.backend.PciDevice = Mock(return_value=SimpleNamespace(read_cfg=lambda: config))
        return config

    def test_overlapping_enabled_ranges_dump_once(self):
        self.configure_pci((1 << 3) | (1 << 4))
        with patch.object(self.example, 'dump_memory') as dump, redirect_stdout(io.StringIO()):
            self.assertEqual(self.example.main([str(self.output)]), 0)
        dump.assert_called_once_with(0xFFFF0000, 0xFFFFFFFF, str(self.output))

    def test_disabled_ranges_and_wrong_vendor_never_dump(self):
        for enables, vendor in ((0, 0x1022), (1 << 3, 0x8086)):
            with self.subTest(enables=enables, vendor=vendor):
                self.configure_pci(enables, vendor)
                with patch.object(self.example, 'dump_memory') as dump, redirect_stdout(io.StringIO()):
                    self.assertEqual(self.example.main([str(self.output)]), 1)
                dump.assert_not_called()

    def test_enabled_range_without_reset_vector_never_dumps(self):
        config = self.configure_pci(1 << 3)
        struct.pack_into('<HH', config, 0x68, 0x1000, 0x1001)
        with patch.object(self.example, 'dump_memory') as dump, redirect_stdout(io.StringIO()):
            self.assertEqual(self.example.main([str(self.output)]), 1)
        dump.assert_not_called()


if __name__ == '__main__':
    unittest.main()
