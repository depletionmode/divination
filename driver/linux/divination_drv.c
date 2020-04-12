/*
 * @depletionmode 2020
 */

#include <linux/init.h>
#include <linux/module.h>
#include <linux/fs.h>
#include <linux/ioctl.h>
#include <linux/uaccess.h>
#include <asm/msr.h>
#include <linux/cdev.h>
#include <linux/device.h>
#include <linux/pci.h>
#include <asm/pci_x86.h>

typedef struct {
    uint32_t bus;
    uint32_t device;
    uint32_t function;

#define PCICFG_READ_SIZE 0x100
    uint8_t cfg_region[PCICFG_READ_SIZE];

} div_pcicfg_read_t;

typedef struct {
    void* phys_addr;
    size_t size;

    void* virt_addr;

} div_map_mem_t;

#define DIV_IOCTL_READ_PCICFG   _IOWR(0xe0,0x00,div_pcicfg_read_t*)
#define DIV_IOCTL_READ_MSR      _IOWR(0xe0,0x01,uint64_t*)
#define DIV_IOCTL_MAP_IOSPACE   _IOWR(0xe0,0x02,div_map_mem_t*)
#define DIV_IOCTL_UNMAP_IOSPACE _IOWR(0xe0,0x03,void*)

/* global variable to hold phys mem/io space address for subsequent mmap */
uint64_t _mmap_addr;

static uint32_t _raw_pci_read_byte(unsigned int bus, unsigned int dev, unsigned int fcn, int off)
{
/* arch/x86/pci/direct.c */
#define PCI_ADDRESS(bus, devfn, off) \
	(0x80000000 | ((off & 0xF00) << 16) | (bus << 16) \
	| (devfn << 8) | (off & 0xFC))

    outl(PCI_ADDRESS(bus, PCI_DEVFN(dev, fcn), off), 0xcf8);
    return inb(0xcfc + (off & 3));
}

static int div_mmap(struct file* f, struct vm_area_struct* vma)
{
    int res;

    printk(KERN_NOTICE "divination: map phys/io address (physaddr=%llx) stage2\n", _mmap_addr);

    vma->vm_page_prot = pgprot_noncached(vma->vm_page_prot);
    vma->vm_flags |= VM_IO;
    
   res = remap_pfn_range(vma, vma->vm_start, PFN_DOWN(_mmap_addr), vma->vm_end - vma->vm_start, vma->vm_page_prot);
    if (res < 0) {
        printk(KERN_ALERT "divination: failed to map phys/io address (err=%i, physaddr=%llx)\n", res, _mmap_addr);
        goto r_err;
    }

r_err:
    return res;
}

static long int div_ioctl(struct file* f, unsigned int cmd, unsigned long arg)
{
    switch(cmd) {
    case DIV_IOCTL_READ_PCICFG:
        {
            div_pcicfg_read_t pcicfg = { 0 };
            uint32_t val = 0;
            int i;
            
            copy_from_user(&pcicfg, (void __user *)arg, sizeof(pcicfg));

            for (i = 0; i < 0x100; i++) {
                val = _raw_pci_read_byte(pcicfg.bus, pcicfg.device, pcicfg.function, i);
                pcicfg.cfg_region[i] = val;
            }

            copy_to_user((void __user *)arg, &pcicfg, sizeof(pcicfg));
        }
        break;
    case DIV_IOCTL_READ_MSR:
        {
            uint32_t msr;
            uint64_t msr_val;
            uint32_t msr_low, msr_high;
            
            copy_from_user(&msr, (void __user *)arg, sizeof(msr));

            rdmsr_safe(msr, &msr_low, &msr_high);
            msr_val = (uint64_t)msr_high << 32 | msr_low;

            copy_to_user((void __user *)arg, &msr_val, sizeof(msr_val));
        }
        break;
    case DIV_IOCTL_MAP_IOSPACE:
        {
            ///div_map_mem_t mem_details = { 0 };
            
            //copy_from_user(&mem_details, (void __user *)arg, sizeof(mem_details));

            //uint64_t addr;  /* address in phys mem or io space; linux does not differentiate at this level */
            _mmap_addr = 0;
            copy_from_user(&_mmap_addr, (void __user *)arg, sizeof(_mmap_addr));
            printk(KERN_NOTICE "divination: map phys/io address (physaddr=%llx) stage1\n", _mmap_addr);

            //copy_to_user((void __user *)arg, &mem_details, sizeof(mem_details));
        }
        break;
    case DIV_IOCTL_UNMAP_IOSPACE:
        {
            void* virt_addr = 0;
            
            copy_from_user(&virt_addr, (void __user *)arg, sizeof(virt_addr));
        }
        break;
    default:
        return EINVAL;
    }

    return 0;
}

static const char _devname[] = "divination";
static dev_t _dev = 0;
static struct cdev _cdev;
static struct class *_devclass = NULL;

static struct file_operations div_fops = {
    .owner = THIS_MODULE,
    .mmap = div_mmap,
    .unlocked_ioctl = div_ioctl
};

static int div_init(void)
{
    int res;
    struct device* dev;

    res = alloc_chrdev_region(&_dev, 0, 1, _devname);
    if (res < 0) {
        printk(KERN_ALERT "divination: failed to allocate char device region (err=%i)\n", res);
        goto r_err;
    }

    cdev_init(&_cdev, &div_fops);
    res = cdev_add(&_cdev, _dev, 1);
    if (res < 0) {
        printk(KERN_ALERT "divination: failed to add char device (err=%i)\n", res);
        goto r_alloc_region;
    }

    _devclass = class_create(THIS_MODULE, _devname);
    if (IS_ERR(_devclass)) {
        printk(KERN_ALERT "divination: failed to create device class (err=%li)\n", PTR_ERR(_devclass));
        goto r_dev_add;
    }

    dev = device_create(_devclass, NULL, _dev, NULL, _devname);
    if (IS_ERR(dev)) {
        printk(KERN_ALERT "divination: failed to create device (err=%li)\n", PTR_ERR(dev));
        goto r_class_create;
    }
    
    printk(KERN_NOTICE "divination: module loaded\n");

    return 0;

r_class_create:
    class_destroy(_devclass);
r_dev_add:
    cdev_del(&_cdev);
r_alloc_region:
    unregister_chrdev_region(_dev, 1);
r_err:
    return -1;
}

static void div_exit(void)
{
    device_destroy(_devclass, _dev);
    class_destroy(_devclass);
    cdev_del(&_cdev);
    unregister_chrdev_region(_dev, 1);

    printk(KERN_NOTICE "divination: module unloaded\n");
}

module_init(div_init);
module_exit(div_exit);
MODULE_LICENSE("GPL");
