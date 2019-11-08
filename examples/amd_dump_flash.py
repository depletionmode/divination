import divination
import struct
import tqdm

# Implementation based on BKDG for AMD Family 16h

print('AMD flash dumping tool')
print(' - @depletionmode\n')

amd_lpc = divination.PciDevice(0, 0x14, 3)  # LPC Bridge @ D14F3
lpc_cfg = amd_lpc.read_cfg()
print('[+] Read LPC PCI config @ D14F3')

cfg = struct.unpack_from('<I', lpc_cfg, 0x48)[0]     # D14F3x48 - IO/Mem Port Decode Enable
rom_range1_enable = cfg & (1 << 3) > 0
rom_range2_enable = cfg & (1 << 4) > 0

rom_range1 = struct.unpack_from('<HH', lpc_cfg, 0x68)     # D14F3x68 - ROM Address Range 1
rom_range2 = struct.unpack_from('<HH', lpc_cfg, 0x6c)     # D14F3x6C - ROM Address Range 2

rom_range1 = (rom_range1[0] << 16, rom_range1[1] << 16 | 0xffff)
rom_range2 = (rom_range2[0] << 16, rom_range2[1] << 16 | 0xffff)

print('[+] Rom Address Range 1: 0x{:x}-0x{:x} (enabled={})'.format(rom_range1[0], rom_range1[1], rom_range1_enable))
print('[+] Rom Address Range 2: 0x{:x}-0x{:x} (enabled={})'.format(rom_range2[0], rom_range2[1], rom_range2_enable))

if not rom_range1_enable and not rom_range2_enable:
    print('[!] Neither rom address ranges are enabled according to LPC cfg but no matter, dump will be attempted anyway')

def dump_memory(start, end, filename):
    with open(filename, 'wb') as f:
        page_size = 0x1000
        for address in tqdm.tqdm(range(start, end, page_size), unit='pages'):
            # dump a page at a time so can update progress
            mem_range = divination.MemoryObject(address, page_size, divination.MemoryType.IoSpace)
            f.write(mem_range[:])

# Search for reset vector in rom ranges
idx = 1
found = False
rom_ranges = (rom_range1, rom_range2)
for r in rom_ranges:
    reset_vector = 0xfffffff0
    if reset_vector < r[0] or reset_vector > r[1]:
        print('[!] x86 reset vector not found in rom address range {}'.format(idx))
    else:
        found = True
        print('[+] x86 reset vector found in rom address range {}; dumping flash...'.format(idx))
        dump_memory(r[0], r[1], r'flash.bin')
    idx += 1

if not found:
    print('[!] Failed to dump flash!')