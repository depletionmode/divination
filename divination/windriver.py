import win32file, win32gui

class WinDriver():
    def __init__(self):
        try:
            self.hDriver = win32file.CreateFile(r'\\.\Divination', 
                                                win32file.GENERIC_READ | win32file.GENERIC_WRITE, 
                                                0, 
                                                None, 
                                                win32file.OPEN_EXISTING, 
                                                0, 
                                                None)
        except:
            raise FileNotFoundError('Divination.sys')

    def transact(self, ctrl_code, in_buf, out_size=0):
        return win32file.DeviceIoControl(self.hDriver, ctrl_code.value, in_buf, out_size)

    @staticmethod
    def ReadMappedMemory(virt_addr, size):
        return win32gui.PyGetMemory(virt_addr, size)

    @staticmethod
    def WriteMappedMemory(virt_addr, buf):
        win32gui.PySetMemory(virt_addr, buf)
