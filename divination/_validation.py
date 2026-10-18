"""Validation shared by the public API and Linux transport."""

import operator
import sys


def integer(value, name, minimum=0, maximum=None):
    value = operator.index(value)
    if value < minimum or (maximum is not None and value > maximum):
        raise ValueError('{} is out of range'.format(name))
    return value


def region(address, size):
    address = integer(address, 'address', maximum=(1 << 64) - 1)
    size = integer(size, 'size', minimum=1, maximum=sys.maxsize)
    if address + size > 1 << 64:
        raise ValueError('physical address range overflows')
    return address, size


def buffer_bytes(value):
    # bytes(3) would silently turn a mistaken length into three zero bytes.
    try:
        return memoryview(value).tobytes()
    except TypeError:
        raise TypeError('data must be a bytes-like object') from None
