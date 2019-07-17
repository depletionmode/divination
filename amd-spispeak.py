import struct
import hexdump

### I apologise profusely for the messiness of this code - @depletionmode ###

print("""
AMD Family 17h - SPI ROM interface test code by @depletionmode
""")

from divination import MemoryObject, MemoryType #, ReadPciConfig

#amd-spispeak

# todo
# pci_cfg = ReadPciConfig(0, 14, 3)
# print('LPC Bridge @ D14F3 Configuration:')
# hexdump.hexdump(pci_cfg)
# spi_base_addr = (pci_cfg[0xa0] >> 6) << 6
# spi_rom_enable = (pci_cfg[0xa0] >> 1) & 1
spi_base_addr = 0xfec10000
spi_rom_enable = 1
print('SPI_BASE_ADDR @ D14F3xA0[31:6] : {}'.format(hex(spi_base_addr)))
print('SPI_ROM_ENABLE @ D14F3xA0[1] : {}'.format(spi_rom_enable == 1))

spi_bar = MemoryObject(0xfec10000, 0x100, MemoryType.IoSpace)

print('\nSPI_BAR DUMP:')
hexdump.hexdump(spi_bar[0:])

spi_x00 = struct.unpack("<I", spi_bar[:4])[0]
print("""
SPIx00: {:#x} {:#032b}
--> SPI_READMODE @ SPIx00[30:29 + 18] : {:#b}
--> SPI_CLKGATE @ SPIx00[28] : {:#b}
""".format(
    spi_x00,
    spi_x00,
    (((spi_x00 >> 29) & 3) << 1) | ((spi_x00 >> 18) & 1),
    (spi_x00 >> 28) & 1
))
