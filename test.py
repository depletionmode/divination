import divination
import hexdump

amd_hwcr = divination.Msr(0xc0010015)
print(hex(amd_hwcr.read()))

amd_lpc = divination.PciDevice(0, 0x14, 3)  # LPC Bridge @ D14F3
lpc_cfg = amd_lpc.read_cfg()
hexdump.hexdump(lpc_cfg)