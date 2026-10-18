"""Command-line diagnostics and reads with a versioned JSON output contract."""

import argparse
import errno
import importlib.util
import json
import os
import platform
import re
import stat
import struct
import sys

from .driver import Driver


class CommandError(Exception):
    def __init__(self, code, message, exit_status=1):
        super().__init__(message)
        self.code = code
        self.exit_status = exit_status


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise CommandError('invalid_argument', message, 2)


def _bdf(value):
    match = re.fullmatch(r'(?:(?P<domain>[0-9a-fA-F]{4}):)?'
                         r'(?P<bus>[0-9a-fA-F]{1,2}):'
                         r'(?P<device>[0-9a-fA-F]{1,2})\.(?P<function>[0-7])', value)
    if match is None:
        raise argparse.ArgumentTypeError('PCI address must be hex BB:DD.F (for example 00:14.3)')
    if match['domain'] is not None and int(match['domain'], 16) != 0:
        raise argparse.ArgumentTypeError('only PCI domain 0000 is supported')
    bus, device, function = (int(match[name], 16) for name in ('bus', 'device', 'function'))
    if device > 31:
        raise argparse.ArgumentTypeError('PCI device number must be between 00 and 1f')
    return bus, device, function


def _register(value):
    try:
        number = int(value, 16 if value.lower().startswith('0x') else 10)
    except ValueError:
        raise argparse.ArgumentTypeError('MSR must be decimal or hexadecimal with a 0x prefix') from None
    if not 0 <= number <= 0xffffffff:
        raise argparse.ArgumentTypeError('MSR must fit in an unsigned 32-bit integer')
    return number


def _parser():
    # Suppressed defaults let --json appear before or after any subcommand
    # without a child parser overwriting a flag supplied to its parent.
    common = ArgumentParser(add_help=False)
    common.add_argument('--json', action='store_true', default=argparse.SUPPRESS,
                        help='emit one JSON object, including errors, on stdout')
    parser = ArgumentParser(prog='divination', parents=[common],
                            description='Inspect x86-64 hardware using the Divination driver.')
    commands = parser.add_subparsers(dest='command', required=True)
    doctor = commands.add_parser('doctor', parents=[common],
                                 help='check platform, dependencies, and device presence')
    doctor.add_argument('--check-driver', action='store_true',
                        help='also open and close the driver; never reads registers or maps memory')
    pci = commands.add_parser('pci', parents=[common], help='PCI configuration space')
    pci_actions = pci.add_subparsers(dest='operation', required=True)
    pci_read = pci_actions.add_parser('read', parents=[common], help='read 256 bytes of configuration')
    pci_read.add_argument('address', type=_bdf, metavar='BB:DD.F', help='PCI address in hexadecimal')
    msr = commands.add_parser('msr', parents=[common], help='model-specific registers')
    msr_actions = msr.add_subparsers(dest='operation', required=True)
    msr_read = msr_actions.add_parser('read', parents=[common], help='read one 64-bit MSR value')
    msr_read.add_argument('register', type=_register, help='register number in decimal or 0x hexadecimal')
    return parser


def _error(error):
    if isinstance(error, CommandError):
        return error
    if isinstance(error, NotImplementedError):
        return CommandError('unsupported_platform', str(error), 3)
    if isinstance(error, ImportError):
        return CommandError('missing_dependency',
                            '{}; install divination and its platform dependencies in this interpreter'.format(error))
    # pywintypes.error exposes winerror but is not necessarily an OSError.
    windows_code = getattr(error, 'winerror', None)
    unix_code = getattr(error, 'errno', None)
    if isinstance(error, PermissionError) or windows_code == 5 or unix_code in (errno.EPERM, errno.EACCES):
        return CommandError('permission_denied',
                            'Driver access denied. Check administrator/root privileges and system policy. {}'.format(error))
    if isinstance(error, FileNotFoundError) or windows_code in (2, 3):
        return CommandError('driver_not_found',
                            'Divination driver not found. Build and load the matching kernel driver. {}'.format(error))
    return CommandError('operation_failed', '{}: {}'.format(type(error).__name__, error))


def _doctor(check_driver):
    system = platform.system()
    machine = platform.machine()
    bits = struct.calcsize('P') * 8
    supported = (system in ('Linux', 'Windows') and machine.lower() in ('x86_64', 'amd64')
                 and bits == 64 and sys.version_info >= (3, 9))
    data = {
        'platform': system,
        'architecture': machine,
        'python_version': platform.python_version(),
        'pointer_bits': bits,
        'driver_open': None,
        'checks': [],
    }
    failures = []

    def record(name, status, message, failure=None):
        item = {'name': name, 'status': status, 'message': message}
        if failure is not None:
            item['code'] = failure.code
            failures.append(failure)
        data['checks'].append(item)

    if supported:
        record('platform', 'pass', 'Supported x86-64 OS and Python interpreter')
    else:
        failure = CommandError('unsupported_platform',
                               'Requires Linux or Windows on x86-64 with 64-bit Python 3.9+', 3)
        record('platform', 'fail', str(failure), failure)

    if system == 'Windows':
        missing = [name for name in ('win32file', 'win32gui') if importlib.util.find_spec(name) is None]
        if missing:
            failure = CommandError('missing_dependency', 'Install pywin32 in this Python environment')
            record('dependencies', 'fail', str(failure), failure)
        else:
            record('dependencies', 'pass', 'pywin32 modules found; loading them is checked by --check-driver')
    elif system == 'Linux':
        record('dependencies', 'pass', 'No additional Linux Python dependencies')
    else:
        record('dependencies', 'not_checked', 'No platform backend available')

    if system == 'Linux':
        try:
            device = os.stat('/dev/divination')
            if not stat.S_ISCHR(device.st_mode):
                raise CommandError('invalid_device', '/dev/divination is not a character device')
        except Exception as error:
            failure = _error(error)
            record('driver_device', 'fail', str(failure), failure)
        else:
            record('driver_device', 'pass', '/dev/divination exists; permissions and driver compatibility are unverified')
    else:
        record('driver_device', 'not_checked', 'Device presence requires --check-driver on Windows'
               if system == 'Windows' else 'No driver for this operating system')

    if check_driver and not failures:
        try:
            with Driver():
                pass
        except Exception as error:
            data['driver_open'] = False
            failure = _error(error)
            record('driver_access', 'fail', str(failure), failure)
        else:
            data['driver_open'] = True
            record('driver_access', 'pass', 'Driver opened and closed; hardware operations and ABI compatibility are unverified')
    else:
        record('driver_access', 'not_checked', 'Skipped because a prerequisite failed' if check_driver
               else 'Use --check-driver to test opening the device; no hardware registers will be read')
    return data, failures[0] if failures else None


def _read(args):
    with Driver() as driver:
        if args.command == 'pci':
            bus, device, function = args.address
            config = driver.read_pcicfg(bus, device, function)
            if not isinstance(config, (bytes, bytearray)) or len(config) != 256:
                raise CommandError('invalid_response', 'Driver must return exactly 256 PCI configuration bytes')
            return {
                'address': '{:02x}:{:02x}.{:x}'.format(bus, device, function),
                'vendor_id': '0x{:04x}'.format(int.from_bytes(config[:2], 'little')),
                'device_id': '0x{:04x}'.format(int.from_bytes(config[2:4], 'little')),
                'size': len(config),
                'config_hex': config.hex(),
            }
        value = driver.read_msr(args.register)
        if not isinstance(value, int) or not 0 <= value <= 0xffffffffffffffff:
            raise CommandError('invalid_response', 'Driver must return an unsigned 64-bit MSR value')
        # Hex strings preserve all 64 bits in JSON consumers using IEEE doubles.
        return {'register': '0x{:08x}'.format(args.register), 'value': '0x{:016x}'.format(value)}


def _emit(payload, json_mode):
    if json_mode:
        print(json.dumps(payload, sort_keys=True))
        return
    data = payload.get('data')
    if data is not None:
        if payload['command'] == 'doctor':
            print('{} {} / Python {} ({}-bit)'.format(
                data['platform'], data['architecture'], data['python_version'], data['pointer_bits']))
            for check in data['checks']:
                print('{}: {} — {}'.format(check['name'], check['status'], check['message']))
        elif payload['command'] == 'pci read':
            print('{} vendor={} device={}'.format(data['address'], data['vendor_id'], data['device_id']))
            print(data['config_hex'])
        else:
            print('{} = {}'.format(data['register'], data['value']))
    if not payload['ok']:
        print('{}: {}'.format(payload['error']['code'], payload['error']['message']), file=sys.stderr)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    option_args = argv[:argv.index('--')] if '--' in argv else argv
    json_mode = '--json' in option_args
    payload = {'schema_version': 1, 'command': None, 'ok': False}
    failure = None
    try:
        args = _parser().parse_args(argv)
        json_mode = getattr(args, 'json', False)
        payload['command'] = args.command + (' read' if args.command in ('pci', 'msr') else '')
        if args.command == 'doctor':
            payload['data'], failure = _doctor(args.check_driver)
        else:
            payload['data'] = _read(args)
    except KeyboardInterrupt:
        failure = CommandError('interrupted', 'Operation interrupted', 130)
    except Exception as error:
        failure = _error(error)
    if failure is not None:
        payload['error'] = {'code': failure.code, 'message': str(failure)}
    payload['ok'] = failure is None
    _emit(payload, json_mode)
    return failure.exit_status if failure else 0
