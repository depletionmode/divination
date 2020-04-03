import fcntl
import os

class LinDriver():
    def __init__(self):
        self.fd = os.open('/dev/divination', os.O_TRUNC)

    def transact(self, ctrl_code, in_buf, out_size=0):
        return fcntl.ioctl(self.fd, 0xc0000000 + ctrl_code.value, in_buf)

    @staticmethod
    def ReadMappedMemory(virt_addr, size):
        pass

    @staticmethod
    def WriteMappedMemory(virt_addr, buf):
        pass
