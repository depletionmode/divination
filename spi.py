import struct

print("""
AMD Family 17h - SPI ROM interface test code by @depletionmode
      """)

from divination import MemoryObject, MemoryType #, ReadPciConfig

print('LPC Bridge @ D14F3')

# todo
# pci_cfg = ReadPciConfig(0, 14, 3)
# spi_base_addr = (pci_cfg[0xa0] >> 6) << 6
spi_base_addr = 0xfec10000
print('SPI_BASE_ADDR @ D14F3xA0[31:6] : {}'.format(hex(spi_base_addr)))

spi_bar = MemoryObject(0xfec10000, 0x100, MemoryType.IoSpace)

spi_x00 = struct.unpack("<I", spi_bar[:3])
print("""
SPIx00: {:#x} {:#032b}
SPI_READMODE @ SPIx00[30:29 + 18] : {:#b}
SPI_CLKGATE @ SPIx00[28] : {:#b}
""".format(
    spi_x00,
    spi_x00,
    (((spi_x00 & 0x60000000) >> 29) << 1) | (spi_x00 & 0x40000) >> 18,
    (spi_x00 & 0x10000000) >> 28
))