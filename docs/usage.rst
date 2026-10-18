Divination usage guide
======================

Divination provides Python and CLI access to x86-64 hardware: PCI configuration
space, model-specific registers (MSRs), memory-mapped IO (MMIO), and physical
memory on Linux. It requires 64-bit Python 3.9+ and a matching kernel driver.
Windows physical RAM mapping and physical-memory allocation are unsupported.

Installation and drivers
------------------------

Install version 2.2.0 or later for both the Python API and CLI::

    python -m pip install --upgrade divination
    python -m divination --help
    python -m divination doctor --json

The package also provides the equivalent ``divination`` command.
For development, install a source checkout with ``python -m pip install .``.
On Windows, pip installs pywin32 automatically. Installing the Python package
does not build or load its kernel driver. Source distributions include driver
sources; wheels contain only the Python library.

On Linux, install compiler/make and matching kernel headers, then::

    make -C driver/linux
    sudo insmod driver/linux/divination.ko

The device is ``/dev/divination``. Driver operations require ``CAP_SYS_RAWIO``
and device-file access (normally root); kernel lockdown policy may deny them.
A different header tree can be selected with ``KDIR=/path/to/kernel/build``.
After closing clients and mappings, unload with ``sudo rmmod divination``.

On Windows, build from a Visual Studio developer prompt with SDK/WDK installed::

    msbuild driver\win\DivinationDrv.vcxproj /p:Configuration=Release /p:Platform=x64

CI also compiles and links Debug and Release x64 drivers with a pinned SDK/WDK
NuGet toolchain on Visual Studio 2026. To reproduce that build::

    nuget restore driver/win/packages.config -PackagesDirectory driver/win/packages -NonInteractive
    msbuild driver\win\DivinationDrv.vcxproj /p:Configuration=Release /p:Platform=x64 /p:UseNuGetWdk=true /p:SignMode=Off

These CI builds are unsigned and do not load the driver or test hardware access.
The Windows Python tests continue to use simulated drivers.

Use a test-signed build on a test machine configured for test signing; this WDM
driver requires ``/INTEGRITYCHECK``. From an elevated command prompt, substitute
the actual absolute path to the built driver::

    sc.exe create Divination type= kernel binPath= "C:\absolute\path\DivinationDrv.sys"
    sc.exe start Divination

The device is ``\\.\Divination`` and permits administrators and SYSTEM.
After closing clients, stop with ``sc.exe stop Divination``. Rebuild the matching
driver when updating the Python package. Hardware addresses and supported MSRs
vary by machine; the examples below do not discover suitable targets for you.

Windows PCI reads still use the legacy ``HalGetBusDataByOffset`` API. They are
not supported on systems with both an SDEV ACPI table and virtualization-based
security enabled: Windows can bug-check on this access. See Microsoft's
`PCI configuration access guidance <https://learn.microsoft.com/en-us/windows-hardware/drivers/pci/accessing-pci-device-configuration-space>`_.
A successful CI build does not establish runtime compatibility on those systems.

Choose CLI or Python
--------------------

Use the CLI for diagnostics and individual PCI/MSR reads. Use Python for loops,
binary decoding, memory mappings, writes, and integration into other programs.
Both interfaces use the same driver backends. The CLI has no write commands.

CLI examples
^^^^^^^^^^^^

These commands use example hardware targets; substitute your own::

    divination doctor --json
    divination doctor --check-driver --json
    divination pci read 00:14.3 --json
    divination msr read 0xc0010015 --json

``doctor`` checks OS/architecture, Python dependencies, and Linux device-node
presence without opening the driver. ``--check-driver`` additionally opens and
closes it; neither mode reads hardware registers or maps memory. A successful
diagnostic does not prove ABI compatibility or that a particular read will work.

PCI addresses are hexadecimal ``BB:DD.F``; an optional ``0000:`` domain prefix
is accepted. Other domains are unsupported. PCI reads return all 256 bytes of
conventional configuration space. MSR numbers accept decimal or ``0x`` hex.
MSR operations affect the CPU executing the request; CPU selection is not exposed.

JSON contract
^^^^^^^^^^^^^

``--json`` can appear before or after subcommands. Normal results and errors are
one JSON object on stdout, with no diagnostics on stderr. ``--help`` remains
ordinary help text. Without ``--json``, output is human-readable and errors go
to stderr.

An example MSR result (the value is illustrative)::

    {"schema_version": 1, "command": "msr read", "ok": true,
     "data": {"register": "0xc0010015", "value": "0x0000000089000111"}}

Every response has ``schema_version``, ``command``, and ``ok``. On success,
``data`` holds the result; on failure, ``error`` contains ``code`` and ``message``.
Argument errors use ``command: null``. Doctor can include both ``data`` and
``error`` to report all its checks and the first failure.

* ``pci read`` data: ``address`` (normalized BB:DD.F), ``vendor_id`` and
  ``device_id`` (0x-prefixed hex strings), ``size`` (256), and ``config_hex``
  (512 lowercase hex characters in byte order).
* ``msr read`` data: ``register`` (0x plus 8 hex digits) and ``value`` (0x plus
  16 hex digits). Values are strings to preserve all 64 bits in JSON clients.
* ``doctor`` data: ``platform``, ``architecture``, ``python_version``,
  ``pointer_bits``, ``driver_open`` (null unless attempted, otherwise boolean),
  and ``checks``. Each check has ``name``, ``status`` (``pass``, ``fail``, or
  ``not_checked``), and ``message``; failed checks also have ``code``.
  ``ok: true`` means no checked prerequisite failed, even if access is untested.

Exit statuses:

* ``0``: command succeeded, or doctor found no failed prerequisites.
* ``1``: missing driver/dependency, denied access, or another operation failure.
* ``2``: invalid command or arguments.
* ``3``: unsupported OS, architecture, or Python interpreter.
* ``130``: interrupted by the user.

Error codes are ``invalid_argument``, ``unsupported_platform``,
``missing_dependency``, ``driver_not_found``, ``permission_denied``,
``invalid_device``, ``invalid_response``, ``operation_failed``, and ``interrupted``.
Automate against codes and fields, not human-readable messages.

Python examples
^^^^^^^^^^^^^^^

Importing the package does not open the driver. Each example below requires
appropriate hardware targets and access privileges when executed::

    import struct
    from divination import MemoryObject, MemoryType, Msr, PciDevice

    config = PciDevice(0, 0x14, 3).read_cfg()
    vendor_id, device_id = struct.unpack_from("<HH", config)
    register = Msr(0xc0010015)
    value = register.read()

    with MemoryObject(0xfec10000, 0x100, MemoryType.IoSpace) as memory:
        header = memory.read(0, 4)
        snapshot = memory[:]

Use ``MemoryType.PhysMem`` for Linux physical RAM, subject to kernel mapping
restrictions. ``IoSpace`` means MMIO, not x86 port IO. Explicit reads/writes are
bounded; slices cannot resize mappings. Integer indexing returns one-byte
``bytes``; integer assignment accepts a value from 0 through 255. Negative
indices and stepped slices follow Python conventions. ``close()`` is idempotent.

For a requested, hardware-appropriate write, use ``register.write(value)`` or
``memory.write(offset, bytes_buffer)`` / ``memory[start:stop] = bytes_buffer``.
Do not derive write values from these example addresses. Python calls raise
exceptions on failure instead of using the CLI's JSON error envelope.

Troubleshooting
---------------

* ``driver_not_found``: build/load the matching module or start the Windows
  service. ``pip install`` alone cannot provide an active kernel driver.
* ``permission_denied``: check elevation, device permissions, and system policy.
  The CLI never elevates itself or changes permissions.
* ``missing_dependency``: install pywin32 in the same Windows interpreter used
  to run the command. ``python -m divination`` removes executable-path ambiguity.
* ``unsupported_platform``: use x86-64 Linux/Windows and 64-bit Python 3.9+.
* ``operation_failed``: inspect the message for the native driver error; confirm
  the target exists, the register is supported, and the driver matches the package.
* Doctor passes but reads fail: existence/open checks cannot validate a target,
  the ioctl ABI, or hardware behavior. Do not probe writes to diagnose a read.

For development, run ``python -m unittest discover -s tests -v``. Tests simulate
hardware; CI compilation does not substitute for testing a driver on a suitable
host. See `AGENTS.md <../AGENTS.md>`_ for repository contribution instructions.
