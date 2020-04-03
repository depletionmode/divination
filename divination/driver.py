import platform

class Driver():
    def __init__(self):
        self.driver = None

        os = platform.system()
        
        if os == 'Windows':
            from .windriver import WinDriver
            self.driver = WinDriver()
        elif os == 'Linux':
            from .lindriver import LinDriver
            self.driver = LinDriver()
        else:
            raise NotImplementedError()

    def map_iospace(self, phys_addr, size):
        return self.driver.map_iospace(phys_addr, size)

    def unmap_iospace(self, virt_addr):
        self.driver.unmap_iospace(virt_addr)

    def map_physmem(self, phys_addr, size):
        return self.driver.map_physmem(phys_addr, size)

    def unmap_physmem(self, virt_addr):
        self.driver.unmap_physmem(virt_addr)

    def read_msr(self, msr):
        return self.driver.read_msr(msr)

    def read_pcicfg(self, bus, device, function):
        return self.driver.read_pcicfg(bus, device, function)

    def ReadMappedMemory(virt_addr, size):
        return self.driver.ReadMappedMemory(virt_addr, size)

    def WriteMappedMemory(virt_addr, buf):
        return self.driver.WriteMappedMemory(virt_addr, buf)
