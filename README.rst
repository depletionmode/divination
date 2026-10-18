==============================================================
divination - platform, IO space and physical memory inspection
==============================================================

Divination provides Python access to PCI configuration space, model-specific
registers (MSRs), and mapped device memory through a companion kernel driver.
It is intended for hardware development on machines you control. Device access
requires administrator/root privileges; incorrect addresses or writes can crash
the machine or damage its state.

Supported platforms are **64-bit x86 Linux** and **Windows x64**, with 64-bit
Python 3.9 or newer. Other architectures and 32-bit processes are unsupported.
Importing ``divination`` does not open a device or require an installed driver.
The driver is opened on the first hardware operation, and errors propagate as
Python exceptions.

Features and limits
-------------------

* Read the conventional 256-byte PCI configuration space using
  ``PciDevice(bus, device, function).read_cfg()``. Linux addresses PCI domain
  zero; the API does not accept a domain number.
* Read and write 64-bit MSRs using ``Msr(register).read()`` and
  ``Msr(register).write(value)``. Operations affect the CPU executing the driver
  request; this interface does not select a CPU or program all CPUs.
* Map device IO memory with ``MemoryType.IoSpace`` on Linux and Windows.
* Map existing physical memory with ``MemoryType.PhysMem`` on Linux, subject to
  kernel and platform mapping restrictions. Windows physical RAM mapping is not
  implemented and raises ``NotImplementedError``.
* Use bounded byte reads/writes and slices on ``MemoryObject``, and release
  mappings deterministically with a context manager or ``close()``.

``IoSpace`` means memory-mapped IO, not x86 port IO. PCI writes and extended PCI
configuration space are not exposed. Physical memory allocation is not provided:
``MemoryObject(0, size, MemoryType.PhysMem, alloc=True)`` raises
``NotImplementedError``. Invalid allocation parameters raise ``ValueError``. Mapped memory is
not a general-purpose substitute for a device-specific driver.

Installation
------------

Install this checkout in a virtual environment::

    python -m venv .venv
    # Linux:
    . .venv/bin/activate
    # Windows PowerShell:
    # .venv\Scripts\Activate.ps1
    python -m pip install .

The Python package depends on ``pywin32`` on Windows only. The flash-dump
example optionally uses ``tqdm`` for progress output; install it with::

    python -m pip install ".[examples]"

Installing the Python package does not build, install, or load a kernel driver.
**Rebuild the driver from this checkout when updating the Python package**:
MSR writes and the corrected request handling require the matching driver.

Linux driver
^^^^^^^^^^^^

Install a compiler, make, and headers matching the target kernel, then build::

    make -C driver/linux

To build against another installed kernel tree, pass its header directory as
``KDIR=/path/to/kernel/build``.

Load the resulting module as root::

    sudo insmod driver/linux/divination.ko

The driver creates ``/dev/divination``. Access requires root/appropriate raw IO
privileges. Run hardware scripts with the Python interpreter in the environment
where the package was installed. To unload after closing every mapping and
process using the device::

    sudo rmmod divination

Kernel lockdown, module signing policy, or unavailable mappings may prevent
loading or accessing hardware. Loading this module does not make all physical
addresses valid.

Windows driver
^^^^^^^^^^^^^^

The source is an x64 WDM driver. Install Visual Studio with the C++ build tools
and matching Windows SDK/WDK. From a VS developer command prompt, build::

    msbuild driver\win\DivinationDrv.vcxproj /p:Configuration=Release /p:Platform=x64

Use the generated ``DivinationDrv.sys`` from the build output. Load it through a
kernel-driver service from an elevated command prompt, substituting the absolute
path to your built driver::

    sc.exe create Divination type= kernel binPath= "C:\absolute\path\DivinationDrv.sys"
    sc.exe start Divination

The device is exposed as ``\\.\Divination`` and is restricted to administrators
and SYSTEM. A test driver must satisfy the machine's driver-signing policy;
configure a dedicated test machine using the WDK test-signing workflow. Do not
production-sign or broadly distribute a driver that exposes unrestricted hardware
access. The project enables ``/INTEGRITYCHECK`` for its process-exit cleanup
callback, so use a properly test-signed build rather than an unsigned binary.
Close client processes before stopping or removing the service::

    sc.exe stop Divination
    sc.exe delete Divination

Usage
-----

The addresses and register below are examples, not portable hardware discovery.
Use addresses documented for your own hardware::

    from divination import MemoryObject, MemoryType, Msr, PciDevice

    config = PciDevice(0, 0x14, 3).read_cfg()
    print(config.hex())

    register = Msr(0xC0010015)
    value = register.read()
    # register.write(new_value)  # Only after consulting the CPU documentation.

    with MemoryObject(0xFEC10000, 0x100, MemoryType.IoSpace) as registers:
        data = registers[:]
        first_four_bytes = registers.read(0, 4)
        # registers.write(0, b"\x00\x00\x00\x00")
        # registers[4:6] = b"\x01\x02"

``MemoryObject(base_address, range, mem_type, alloc=False)`` maps an existing
nonempty address range. ``read(offset, size)`` returns bytes; ``write(offset,
buffer)`` writes a bytes-like buffer. Explicit reads and writes must stay within
the mapped range. Slice assignment cannot resize a mapping. Integer indexing
returns a one-byte ``bytes`` object; integer assignment accepts a byte value.
Negative indices count from the end. Slices follow Python clipping and step
semantics, including reverse slices; explicit ``read``/``write`` offsets must
be nonnegative.
Access after ``close()`` fails, and repeated ``close()`` calls are harmless.
Use a ``with`` block to release mappings even if another operation raises.

The AMD Family 16h flash example selects an enabled LPC ROM range containing
the reset vector, writes both inclusive endpoints, and closes each mapped chunk::

    python examples/amd_dump_flash.py flash.bin

It is specific to that hardware family's register layout; checking the AMD
vendor ID does not identify the CPU family. Run it only on matching hardware.
Importing the example or requesting ``--help`` does not touch hardware.

Development and validation
--------------------------

Run the hardware-free regression suite with::

    python -m unittest discover -s tests -v

Build source and wheel distributions with::

    python -m pip install build
    python -m build

The source distribution includes driver sources and examples; a wheel installs
the Python library only. Hardware-free tests use simulated backends and validate
Python behavior and request layouts. They do not prove that hardware mappings,
MSR operations, or kernel drivers work on a particular machine. Windows WDK
builds and privileged hardware integration tests require a suitable test host.
