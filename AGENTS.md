# Working with Divination

Divination is a Python hardware-inspection library for x86-64 Linux and Windows.
It exposes PCI configuration, MSRs, memory-mapped IO, and Linux physical memory.
See [docs/usage.rst](docs/usage.rst) for setup, examples, JSON fields, and errors.

## Choose the interface for the task

Use the CLI for environment diagnostics and individual PCI/MSR reads:

```sh
python -m divination doctor --json
python -m divination pci read 00:14.3 --json
python -m divination msr read 0xc0010015 --json
```

The installed `divination` command is equivalent to `python -m divination`.
Check the exit status and JSON `ok` field. MSR values are hexadecimal strings
so JSON consumers do not lose precision. `doctor` does not open the driver unless
`--check-driver` is supplied; a successful check does not validate hardware reads.

Use the Python API when a task needs repeated reads, control flow, decoding
binary structures, memory mappings, or writes. Do not invoke CLI subprocesses
when direct library calls would make a Python program simpler.

```python
from divination import MemoryObject, MemoryType, Msr, PciDevice

# Targets below are examples; use addresses appropriate for the actual machine.
config = PciDevice(0, 0x14, 3).read_cfg()
value = Msr(0xc0010015).read()
with MemoryObject(0xfec10000, 0x100, MemoryType.IoSpace) as registers:
    first_four_bytes = registers.read(0, 4)
```

For a requested write, use `Msr(register).write(value)` or
`MemoryObject.write(offset, buffer)` / slice assignment. Always close mappings,
preferably with a context manager. Physical RAM mapping is Linux-only;
physical-memory allocation is unsupported. `IoSpace` means MMIO, not port IO.
MSRs refer to the CPU executing the driver request, and PCI addresses use domain 0.

## Development and validation

- Install the checkout: `python -m pip install .` (or `-e .` for development).
- Run hardware-free tests: `python -m unittest discover -s tests -v`.
- CLI smoke checks: `python -m divination --help` and
  `python -m divination doctor --json`. Doctor may report a missing driver;
  do not treat that as a package test failure.
- Build distributions: `python -m pip install build twine`, `python -m build`,
  then `python -m twine check dist/*`.
- Compile Linux driver: `make -C driver/linux W=1`; use
  `KDIR=/path/to/kernel/build` for a different installed kernel's headers.
- Compile Windows driver in a VS/WDK developer prompt:
  `msbuild driver\win\DivinationDrv.vcxproj /p:Configuration=Release /p:Platform=x64`.

Use simulated drivers for automated tests. Building a driver does not require
loading it. Do not load drivers or read/write hardware as an incidental test of
software edits. When the user requests a hardware operation, use the specified
target and parameters; do not guess addresses or write register values as probes.
Report separately which checks used mocks, compilation, or actual hardware.

## Repository conventions

- Preserve the README's wording, layout, examples, and CRLF line endings. Make
  only pinpoint corrections or links; put extended instructions in `docs/`.
- Preserve the existing Python API and driver wire layouts. Validate inputs
  before issuing a driver request and release resources on failures.
- Keep JSON output stable and add regression tests for changes to its contract.
- Keep dependencies platform-specific; importing the library must not open a
  driver or exit the interpreter.
- The default branch is `master`. Put changes on a feature branch and open a PR.
- Publishing uses `.github/workflows/publish.yml` and the `pypi` environment.
  Publish only when the user requests a release; never store credentials here.
