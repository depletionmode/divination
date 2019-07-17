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
SPI_CNTRL0 @ SPIx00: {:#x} {:#032b}
--> SPI_READMODE @ SPIx00[30:29 + 18] : {:#b}
--> SPI_CLKGATE @ SPIx00[28] : {:#b}
--> SPI_HOSTACCESSROMEN @ SPIx00[23] : {:#b}
--> SPI_ACCESSMACROMEN @ SPIx00[22] : {:#b}
--> SPI_ARBENABLE @ SPIx00[19] : {:#b}
""".format(
    spi_x00,
    spi_x00,
    (((spi_x00 >> 29) & 3) << 1) | ((spi_x00 >> 18) & 1),
    (spi_x00 >> 28) & 1,
    (spi_x00 >> 23) & 1,
    (spi_x00 >> 22) & 1,
    (spi_x00 >> 19) & 1
))

spi_x0C = struct.unpack("<I", spi_bar[0xc:0xc+4])[0]
print("""
SPI_CNTRL1 @ SPIx0C: {:#x} {:#032b}
--> SPI_BYTECMD @ SPIx0C[31:24] : {:#x}
--> SPI_WAITCNT @ SPIx0C[21:16] : {:#x}
--> SPI_PARAMS @ SPIx0C[7:0] : {:#x}
""".format(
    spi_x0C,
    spi_x0C,
    (spi_x0C >> 24) & 0xff,
    (spi_x0C >> 16) & 0x3f,
    spi_x0C & 0xff
))

print('SPI_FIFO @ SPIx[C6:80]:')
spi_fifo = spi_bar[0x80:0xc6]
hexdump.hexdump(spi_fifo)