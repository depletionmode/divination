===================================================
divination - Windows iospace and physmem inspection
===================================================


.. image:: https://img.shields.io/pypi/v/divination.svg
        :target: https://pypi.python.org/pypi/divination

Overview
--------

*divination* is a python package that exposes a simple interface for transacting 
with physical memory and IO space on Windows (10+). 

IO and physical memory regions are mapped into the usermode process and are 
read directly with the assistance of pywin32 memory primitives.

The module requires a resident kernel-mode driver.

Features
--------

* Reading PCI configuration space
* Reading MSRs (writing MSRs currently unimplemented)
* Mapping and RW from/to IO regions
* Mapping and RW from/to physical memory regions (currently unimplemented)

Dependencies
------------

* pywin32

Installation
------------

Python module
^^^^^^^^^^^^^

The python module is available off PyPI:

    pip install divination

Kernel module
^^^^^^^^^^^^^

The required KMDF driver can be built by installing VS, SDK + WDK and 
running msbuild under the `native/driver <native/driver>`_ directory from within the VS Developer 
Command Prompt.

Please **do not (non-test-)sign** this kernel module; we do not want to further enable attackers!
Unless a restrictive DeviceGuard policy is employed, enabling testsigning should be sufficient to allow the driver to run:

    bcdedit /set testsigning on ; shutdown -f -t 0 -r

Usage
-----

There are currently 3 classes available: PciDevice, Msr and MemoryObject. 
Examples follow for usage of each.

* PciDevice(bus, device, function)

    >>> amd_lpc = PciDevice(0, 0x14, 3)     # LPC Bridge @ D14F3
    >>> hexdump.hexdump(amd_lpc.read_cfg()) 
    00000000: 22 10 0E 79 0F 00 20 02  51 00 01 06 00 00 80 00  "..y.. .Q.......
    00000010: 00 00 00 00 00 00 00 00  00 00 00 00 00 00 00 00  ................
    00000020: 00 00 00 00 00 00 00 00  00 00 00 00 62 14 37 7C  ............b.7|
    00000030: 00 00 00 00 00 00 00 00  00 00 00 00 00 00 00 00  ................
    00000040: 04 00 00 00 40 C0 03 20  07 FF 20 03 00 00 00 00  ....@.. .. .....
    00000050: 00 00 00 00 00 00 00 00  00 00 00 00 00 00 00 00  ................
    00000060: 00 00 00 00 40 16 00 0A  00 00 0F 00 00 FF FF FF  ....@...........
    00000070: 67 45 23 00 08 00 00 00  90 02 00 00 07 0A 00 00  gE#.............
    00000080: 08 00 03 A8 00 00 00 00  00 00 00 00 00 00 00 00  ................
    00000090: E0 03 00 00 00 00 00 00  00 00 00 00 00 00 00 00  ................
    000000A0: 02 00 C1 FE 2F 01 00 00  00 00 00 00 00 00 00 00  ..../...........
    000000B0: 00 00 00 00 00 00 00 00  04 00 E9 3F 00 00 00 00  ...........?....
    000000C0: 00 00 00 00 00 00 00 00  00 00 00 80 00 00 F7 FF  ................
    000000D0: 86 FF FD 08 42 00 00 00  00 00 00 00 00 00 00 00  ....B...........
    000000E0: 00 00 00 00 00 00 00 00  00 00 00 00 00 00 00 00  ................
    000000F0: 00 00 00 00 00 00 00 00  00 00 00 00 00 00 00 00  ................

* Msr(register)

    >>> amd_hwcr = Msr(0xc0010015)
    >>> hex(amd_hwcr.read())   
    '0x89000111'

* MemoryObject(base_address, range, mem_type, alloc=False)

    >>> spi_bar = MemoryObject(0xfec10000, 0x100, MemoryType.IoSpace)
    >>> hexdump.hexdump(spi_bar[0:])  # MemoryObjects are sliceable and can be read from + written to
    00000000: 05 21 CC 4F 00 00 00 00  00 00 00 00 6A 00 00 02  .!.O........j...
    00000010: 06 20 04 04 06 04 9F 05  03 0B 0A 02 FF 98 06 02  . ..............
    00000020: 13 07 33 10 08 20 20 20  0C 14 06 0E C0 54 C0 14  ..3..   .....T..
    00000030: C0 14 08 46 03 00 00 00  FC FC FC FC FC 88 00 00  ...F............
    00000040: 3B 6B BB EB 00 05 00 00  01 00 00 02 02 00 06 00  ;k..............
    00000050: 00 00 00 00 00 00 00 00  00 00 00 00 00 00 00 00  ................
    00000060: 00 00 00 00 00 00 00 00  00 00 00 00 00 00 00 00  ................
    00000070: 00 00 00 00 00 00 00 00  00 00 00 00 00 00 00 00  ................
    00000080: 00 40 40 69 24 6A 4A 16  CA C5 EB 7B E2 95 09 4C  .@@i$jJ....{...L
    00000090: C8 AD 4A FC CB 1D 83 A9  C4 82 C1 D9 7E 35 F9 27  ..J.........~5.'
    000000A0: 92 8A 43 4B 78 D3 6B 04  9C B8 AF 79 8C 68 C6 E8  ..CKx.k....y.h..
    000000B0: 2E 24 04 68 F4 97 2A CC  83 74 C9 E2 17 C0 5A C7  .$.h..*..t....Z.
    000000C0: C7 C7 C7 00 00 00 00 00  00 00 00 00 00 00 00 00  ................
    000000D0: 00 00 00 00 00 00 00 00  00 00 00 00 00 00 00 00  ................
    000000E0: 00 00 00 00 00 00 00 00  00 00 00 00 00 00 00 00  ................
    000000F0: 00 00 00 00 00 00 00 00  00 00 00 00 00 00 00 00  ................

Contributing
------------

As you can tell, not all the planned functionality is implemented and I will 
fill in gaps as my personal needs arise.
Contributions are, of course, most welcome!