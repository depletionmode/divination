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

* Documentation: https://divination.readthedocs.io


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

The python module is available off PyPI:

    pip install divination

The required kernel module can be built by installing VS, SDK + WDK and 
running msbuild under the `native/driver <native/driver>`_ directory from within the VS Developer 
Command Prompt.

Usage
-----

There are currently 3 classes available: PciDevice, Msr and MemoryObject. 
Examples follow for usage of each.

* PciDevice(Bus, Device, Function)

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