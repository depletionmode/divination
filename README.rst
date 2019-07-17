===================================================
divination - Windows iospace and physmem inspection
===================================================


.. image:: https://img.shields.io/pypi/v/divination.svg
        :target: https://pypi.python.org/pypi/divination

Overview
--------

divination is a python package that exposes a simple interface for transacting 
with physical memory and IO space on Windows (10+). 

IO and physical memory regions are mapped into the usermode process and are 
read directly with the assistance of pywin32 memory primitives.

The module requires a resident kernel-mode driver.

* Documentation: https://divination.readthedocs.io


Features
--------

* Reading PCI configuration space
* Reading MSRs (writing MSRS currently unimplemented)
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

