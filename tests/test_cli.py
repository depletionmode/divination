"""CLI behavior and diagnostics without a real device or hardware accesses."""

from contextlib import redirect_stderr, redirect_stdout
import errno
import io
import json
from pathlib import Path
import stat
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from divination import cli


class CLITests(unittest.TestCase):
    def setUp(self):
        self.backend = MagicMock()
        self.context = MagicMock()
        self.context.__enter__.return_value = self.backend
        self.factory = patch.object(cli, 'Driver', return_value=self.context).start()
        self.system = patch.object(cli.platform, 'system', return_value='Linux').start()
        self.machine = patch.object(cli.platform, 'machine', return_value='x86_64').start()
        self.bits = patch.object(cli.struct, 'calcsize', return_value=8).start()
        self.device_stat = MagicMock(return_value=SimpleNamespace(st_mode=stat.S_IFCHR))
        patch.object(cli, 'os', SimpleNamespace(stat=self.device_stat)).start()
        self.spec = patch.object(cli.importlib.util, 'find_spec', return_value=object()).start()
        self.addCleanup(patch.stopall)

    def run_cli(self, args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = cli.main(args)
        return status, stdout.getvalue(), stderr.getvalue()

    def run_json(self, args):
        status, stdout, stderr = self.run_cli(args)
        self.assertEqual(stderr, '')
        self.assertEqual(len(stdout.splitlines()), 1)
        value = json.loads(stdout)
        self.assertEqual(value['schema_version'], 1)
        self.assertIs(value['ok'], status == 0)
        return status, value

    def test_msr_read_preserves_unsigned_64_bit_value(self):
        self.backend.read_msr.return_value = 2**64 - 1
        status, result = self.run_json(['msr', 'read', '0xc0010015', '--json'])
        self.assertEqual(status, 0)
        self.assertEqual(result, {
            'schema_version': 1, 'ok': True, 'command': 'msr read',
            'data': {'register': '0xc0010015', 'value': '0xffffffffffffffff'},
        })
        self.backend.read_msr.assert_called_once_with(0xc0010015)
        self.context.__exit__.assert_called_once()

    def test_decimal_register_and_json_at_each_command_level(self):
        self.backend.read_msr.return_value = 0
        for args in (['--json', 'msr', 'read', '123'],
                     ['msr', '--json', 'read', '123'],
                     ['msr', 'read', '--json', '123']):
            with self.subTest(args=args):
                status, result = self.run_json(args)
                self.assertEqual(status, 0)
                self.assertEqual(result['data']['register'], '0x0000007b')
        self.assertEqual(self.backend.read_msr.call_count, 3)

    def test_pci_address_and_byte_order(self):
        config = bytes.fromhex('22100e79') + bytes(252)
        self.backend.read_pcicfg.return_value = config
        status, result = self.run_json(['pci', 'read', '0000:0:14.3', '--json'])
        self.assertEqual(status, 0)
        self.assertEqual(result['command'], 'pci read')
        self.assertEqual(result['data'], {
            'address': '00:14.3', 'vendor_id': '0x1022', 'device_id': '0x790e',
            'size': 256, 'config_hex': config.hex(),
        })
        self.backend.read_pcicfg.assert_called_once_with(0, 0x14, 3)
        self.context.__exit__.assert_called_once()

    def test_invalid_input_never_opens_driver(self):
        cases = [[], ['pci'], ['msr'], ['unknown'],
                 ['pci', 'read', '0001:00:14.3'], ['pci', 'read', '00:20.0'],
                 ['pci', 'read', '00:14.8'], ['pci', 'read', '256:00.0'],
                 ['pci', 'read', '00:14'], ['msr', 'read', '-1'],
                 ['msr', 'read', '4294967296'], ['msr', 'read', 'nonsense'],
                 ['msr', 'read', '0x'], ['msr', 'read', '1', '--junk'],
                 ['msr', 'write', '1', '2']]
        for args in cases:
            with self.subTest(args=args):
                status, result = self.run_json(args + ['--json'])
                self.assertEqual(status, 2)
                self.assertIsNone(result['command'])
                self.assertEqual(result['error']['code'], 'invalid_argument')
                self.assertNotIn('data', result)
        self.factory.assert_not_called()

    def test_help_does_not_open_driver(self):
        for args in (['--help'], ['pci', '--help'], ['msr', 'read', '--help']):
            with self.subTest(args=args), redirect_stdout(io.StringIO()) as output:
                with self.assertRaises(SystemExit) as result:
                    cli.main(args)
                self.assertEqual(result.exception.code, 0)
                self.assertIn('usage:', output.getvalue())
        self.factory.assert_not_called()

    def test_read_exception_still_closes_driver(self):
        self.backend.read_msr.side_effect = OSError(errno.EIO, 'unsupported MSR')
        status, result = self.run_json(['msr', 'read', '1', '--json'])
        self.assertEqual(status, 1)
        self.assertEqual(result['error']['code'], 'operation_failed')
        self.assertIn('unsupported MSR', result['error']['message'])
        self.context.__exit__.assert_called_once()

    def test_native_driver_errors_have_stable_codes(self):
        cases = ((FileNotFoundError('/dev/divination'), 'driver_not_found', 1),
                 (PermissionError('denied'), 'permission_denied', 1),
                 (OSError(errno.EPERM, 'denied by policy'), 'permission_denied', 1),
                 (ModuleNotFoundError('win32file'), 'missing_dependency', 1),
                 (NotImplementedError('unsupported OS'), 'unsupported_platform', 3))
        for error, code, expected_status in cases:
            with self.subTest(code=code):
                self.context.__enter__.side_effect = error
                status, result = self.run_json(['msr', 'read', '1', '--json'])
                self.assertEqual(status, expected_status)
                self.assertEqual(result['error']['code'], code)

    def test_win32_errors_need_not_inherit_oserror(self):
        for winerror, expected in ((2, 'driver_not_found'), (3, 'driver_not_found'),
                                   (5, 'permission_denied'), (87, 'operation_failed')):
            error = Exception('simulated native Windows error')
            error.winerror = winerror
            self.context.__enter__.side_effect = error
            status, result = self.run_json(['msr', 'read', '1', '--json'])
            self.assertEqual(status, 1)
            self.assertEqual(result['error']['code'], expected)

    def test_truncated_pci_response(self):
        self.backend.read_pcicfg.return_value = b'\xff' * 4
        status, result = self.run_json(['pci', 'read', '00:00.0', '--json'])
        self.assertEqual(status, 1)
        self.assertEqual(result['error']['code'], 'invalid_response')
        self.context.__exit__.assert_called_once()

    def test_invalid_msr_response(self):
        for value in (-1, 2**64, '1'):
            self.backend.read_msr.return_value = value
            status, result = self.run_json(['msr', 'read', '1', '--json'])
            self.assertEqual(status, 1)
            self.assertEqual(result['error']['code'], 'invalid_response')

    def test_interrupt_returns_json_and_closes_driver(self):
        self.backend.read_msr.side_effect = KeyboardInterrupt
        status, result = self.run_json(['msr', 'read', '1', '--json'])
        self.assertEqual(status, 130)
        self.assertEqual(result['error']['code'], 'interrupted')
        self.context.__exit__.assert_called_once()

    def test_human_output_and_error_stream(self):
        self.backend.read_msr.return_value = 17
        status, stdout, stderr = self.run_cli(['msr', 'read', '1'])
        self.assertEqual(status, 0)
        self.assertEqual(stdout, '0x00000001 = 0x0000000000000011\n')
        self.assertEqual(stderr, '')
        status, stdout, stderr = self.run_cli(['msr', 'read', '-1'])
        self.assertEqual(status, 2)
        self.assertEqual(stdout, '')
        self.assertIn('invalid_argument:', stderr)

    def test_doctor_does_not_open_driver_by_default(self):
        with patch('os.open', side_effect=AssertionError('must not open device')):
            status, result = self.run_json(['doctor', '--json'])
        self.assertEqual(status, 0)
        self.assertEqual(result['command'], 'doctor')
        self.assertIsNone(result['data']['driver_open'])
        checks = {item['name']: item for item in result['data']['checks']}
        self.assertEqual(checks['driver_device']['status'], 'pass')
        self.assertEqual(checks['driver_access']['status'], 'not_checked')
        self.factory.assert_not_called()

    def test_doctor_missing_device(self):
        self.device_stat.side_effect = FileNotFoundError('/dev/divination')
        status, result = self.run_json(['doctor', '--json', '--check-driver'])
        self.assertEqual(status, 1)
        self.assertEqual(result['error']['code'], 'driver_not_found')
        self.assertIsNone(result['data']['driver_open'])
        self.assertTrue(any(item['status'] == 'fail' for item in result['data']['checks']))
        self.factory.assert_not_called()

    def test_doctor_rejects_regular_file_device(self):
        self.device_stat.return_value.st_mode = stat.S_IFREG
        status, result = self.run_json(['doctor', '--json'])
        self.assertEqual(status, 1)
        self.assertEqual(result['error']['code'], 'invalid_device')
        self.factory.assert_not_called()

    def test_doctor_explicit_open_check_has_no_hardware_transactions(self):
        status, result = self.run_json(['doctor', '--check-driver', '--json'])
        self.assertEqual(status, 0)
        self.assertIs(result['data']['driver_open'], True)
        self.context.__enter__.assert_called_once()
        self.context.__exit__.assert_called_once()
        self.assertEqual(self.backend.mock_calls, [])

    def test_doctor_open_failure(self):
        self.context.__enter__.side_effect = PermissionError('denied')
        status, result = self.run_json(['doctor', '--json', '--check-driver'])
        self.assertEqual(status, 1)
        self.assertIs(result['data']['driver_open'], False)
        self.assertEqual(result['error']['code'], 'permission_denied')

    def test_doctor_unsupported_platforms_skip_open(self):
        for system, machine, bits in (('Darwin', 'x86_64', 8), ('Linux', 'aarch64', 8),
                                      ('Windows', 'AMD64', 4)):
            with self.subTest(system=system, machine=machine, bits=bits):
                self.system.return_value = system
                self.machine.return_value = machine
                self.bits.return_value = bits
                status, result = self.run_json(['doctor', '--check-driver', '--json'])
                self.assertEqual(status, 3)
                self.assertEqual(result['error']['code'], 'unsupported_platform')
        self.factory.assert_not_called()

    def test_doctor_windows_dependencies_and_unchecked_access(self):
        self.system.return_value = 'Windows'
        self.machine.return_value = 'AMD64'
        status, result = self.run_json(['doctor', '--json'])
        self.assertEqual(status, 0)
        self.assertIsNone(result['data']['driver_open'])
        self.device_stat.assert_not_called()
        self.factory.assert_not_called()
        self.spec.return_value = None
        status, result = self.run_json(['doctor', '--check-driver', '--json'])
        self.assertEqual(status, 1)
        self.assertEqual(result['error']['code'], 'missing_dependency')
        self.factory.assert_not_called()

    def test_doctor_checks_broken_windows_import_on_explicit_open(self):
        self.system.return_value = 'Windows'
        self.context.__enter__.side_effect = ImportError('DLL load failed')
        status, result = self.run_json(['doctor', '--check-driver', '--json'])
        self.assertEqual(status, 1)
        self.assertEqual(result['error']['code'], 'missing_dependency')
        self.assertIs(result['data']['driver_open'], False)

    def test_repeated_invocations_use_fresh_driver_contexts(self):
        self.backend.read_msr.return_value = 1
        for _ in range(2):
            status, _ = self.run_json(['msr', 'read', '1', '--json'])
            self.assertEqual(status, 0)
        self.assertEqual(self.factory.call_count, 2)
        self.assertEqual(self.context.__exit__.call_count, 2)


class ModuleEntryTests(unittest.TestCase):
    def test_module_entry_usage_errors_are_json_without_hardware(self):
        result = subprocess.run(
            [sys.executable, '-m', 'divination', 'msr', 'read', '-1', '--json'],
            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr, '')
        self.assertEqual(json.loads(result.stdout)['error']['code'], 'invalid_argument')


if __name__ == '__main__':
    unittest.main()
