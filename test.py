import divination

msr = divination.Msr(0x1b)
print(hex(msr.read()))

amd_lpc = divination.PciDevice(0, 0x14, 3)  # LPC Bridge @ D14F3
lpc_cfg = amd_lpc.read_cfg()
print(lpc_cfg)