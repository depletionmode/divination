from divination import MemoryObject, MemoryType
import struct

spi_bar = MemoryObject(0xfec10000, 0x100, MemoryType.IoSpace)
spi_x00 = struct.unpack("<I", spi_bar[:3])