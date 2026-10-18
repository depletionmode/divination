"""Dump an enabled AMD Family 16h ROM range containing the x86 reset vector."""

import argparse
import struct

import divination


def dump_memory(start, end, filename):
    """Dump the inclusive physical address interval [start, end] to a file."""
    if not isinstance(start, int) or not isinstance(end, int):
        raise TypeError("start and end must be integer addresses")
    if start < 0 or end < start or end >= 1 << 64:
        raise ValueError("invalid inclusive address range")

    page_size = 0x1000
    addresses = range(start, end + 1, page_size)
    try:
        from tqdm import tqdm
    except ImportError:
        pass
    else:
        addresses = tqdm(addresses, unit="pages")

    with open(filename, "wb") as output:
        for address in addresses:
            size = min(page_size, end - address + 1)
            with divination.MemoryObject(
                address, size, divination.MemoryType.IoSpace
            ) as memory:
                output.write(memory[:])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", nargs="?", default="flash.bin", help="output file (default: flash.bin)")
    args = parser.parse_args(argv)

    print("AMD Family 16h flash dumping tool")
    amd_lpc = divination.PciDevice(0, 0x14, 3)
    lpc_cfg = amd_lpc.read_cfg()
    if len(lpc_cfg) != 0x100 or struct.unpack_from("<H", lpc_cfg)[0] != 0x1022:
        print("[!] Expected an AMD LPC bridge at D14F3; no dump attempted")
        return 1
    print("[+] Read LPC PCI config @ D14F3")

    # AMD Family 16h BKDG: D14F3x48 enables ROM ranges at x68 and x6C.
    config = struct.unpack_from("<I", lpc_cfg, 0x48)[0]
    candidates = []
    for index, offset in enumerate((0x68, 0x6C), start=1):
        low, high = struct.unpack_from("<HH", lpc_cfg, offset)
        start, end = low << 16, (high << 16) | 0xFFFF
        enabled = bool(config & (1 << (index + 2)))
        print("[+] ROM address range {}: 0x{:x}-0x{:x} (enabled={})".format(
            index, start, end, enabled
        ))
        if enabled and start <= 0xFFFFFFF0 <= end:
            candidates.append((start, end))

    if not candidates:
        print("[!] No enabled ROM address range contains the x86 reset vector")
        return 1

    # Overlapping decode windows may both contain the reset vector. Dump once.
    start, end = candidates[0]
    print("[+] Dumping flash to {}".format(args.output))
    dump_memory(start, end, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
