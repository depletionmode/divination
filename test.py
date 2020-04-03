import divination

msr = divination.Msr(0x1b)
print(hex(msr.read()))
