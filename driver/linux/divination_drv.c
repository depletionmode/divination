// SPDX-License-Identifier: GPL-2.0
/* Divination raw hardware access driver. Linux x86-64 ABI. */

#include <linux/capability.h>
#include <linux/cdev.h>
#include <linux/device.h>
#include <linux/fs.h>
#include <linux/ioctl.h>
#include <linux/mm.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/pci.h>
#include <linux/security.h>
#include <linux/slab.h>
#include <linux/uaccess.h>
#include <linux/version.h>
#include <asm/msr.h>

#ifndef CONFIG_X86_64
#error "Divination requires an x86-64 kernel"
#endif

struct div_pcicfg_read {
    __u32 bus;
    __u32 device;
    __u32 function;
    __u8 cfg_region[PCI_CFG_SPACE_SIZE];
};

struct div_msr_write {
    __u32 msr;
    __u32 reserved;
    __u64 value;
};

/* Preserve the original x86-64 pointer-sized ioctl encoding, independently
 * of each operation's actual buffer size. No 32-bit compat ABI is provided.
 */
#define DIV_IOCTL_READ_PCICFG _IOWR(0xe0, 0x00, __u64)
#define DIV_IOCTL_READ_MSR    _IOWR(0xe0, 0x01, __u64)
#define DIV_IOCTL_MAP_IOSPACE _IOWR(0xe0, 0x02, __u64)
#define DIV_IOCTL_WRITE_MSR   _IOWR(0xe0, 0x06, __u64)

struct div_file {
    struct mutex lock;
    u64 mmap_addr;
    bool mmap_ready;
};

static int div_open(struct inode *inode, struct file *file)
{
    struct div_file *state;

    if (!capable(CAP_SYS_RAWIO))
        return -EPERM;
    state = kzalloc(sizeof(*state), GFP_KERNEL);
    if (!state)
        return -ENOMEM;
    mutex_init(&state->lock);
    file->private_data = state;
    return nonseekable_open(inode, file);
}

static int div_release(struct inode *inode, struct file *file)
{
    kfree(file->private_data);
    return 0;
}

static int div_mmap(struct file *file, struct vm_area_struct *vma)
{
    struct div_file *state = file->private_data;
    unsigned long length = vma->vm_end - vma->vm_start;
    u64 address;
    int ret;

    if (!capable(CAP_SYS_RAWIO))
        return -EPERM;
    ret = security_locked_down(LOCKDOWN_DEV_MEM);
    if (ret)
        return ret;
    /* The address comes from MAP_IOSPACE; mmap offsets are not another
     * addressing interface. Shared mappings avoid undefined COW semantics.
     */
    if (vma->vm_pgoff || !(vma->vm_flags & VM_SHARED) ||
        (vma->vm_flags & VM_EXEC))
        return -EINVAL;

    mutex_lock(&state->lock);
    if (!state->mmap_ready) {
        ret = -EINVAL;
        goto out;
    }
    address = state->mmap_addr;
    if (address > U64_MAX - (length - 1)) {
        ret = -EOVERFLOW;
        goto out;
    }
    if (address + length - 1 > __PHYSICAL_MASK) {
        ret = -EINVAL;
        goto out;
    }
    vma->vm_page_prot = pgprot_noncached(vma->vm_page_prot);
#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 3, 0)
    vm_flags_set(vma, VM_IO | VM_DONTEXPAND | VM_DONTDUMP);
    vm_flags_clear(vma, VM_MAYEXEC);
#else
    vma->vm_flags |= VM_IO | VM_DONTEXPAND | VM_DONTDUMP;
    vma->vm_flags &= ~VM_MAYEXEC;
#endif
    ret = remap_pfn_range(vma, vma->vm_start, address >> PAGE_SHIFT,
                         length, vma->vm_page_prot);
out:
    mutex_unlock(&state->lock);
    return ret;
}

static long div_read_pcicfg(void __user *arg)
{
    struct div_pcicfg_read config = { 0 };
    struct pci_dev *pdev;
    int ret, i;

    ret = security_locked_down(LOCKDOWN_PCI_ACCESS);
    if (ret)
        return ret;
    if (copy_from_user(&config, arg, sizeof(config)))
        return -EFAULT;
    if (config.bus > 255 || config.device > 31 || config.function > 7)
        return -EINVAL;
    /* The legacy ABI addresses domain zero only. The PCI core serializes
     * configuration-port access and keeps the device alive during the read.
     */
    pdev = pci_get_domain_bus_and_slot(0, config.bus,
                                     PCI_DEVFN(config.device, config.function));
    if (!pdev)
        return -ENODEV;
    for (i = 0; i < sizeof(config.cfg_region); i++) {
        ret = pci_read_config_byte(pdev, i, &config.cfg_region[i]);
        if (ret)
            break;
    }
    pci_dev_put(pdev);
    if (ret)
        return pcibios_err_to_errno(ret);
    return copy_to_user(arg, &config, sizeof(config)) ? -EFAULT : 0;
}

static long div_ioctl(struct file *file, unsigned int cmd, unsigned long arg)
{
    struct div_file *state = file->private_data;
    void __user *user_arg = (void __user *)arg;
    int ret;

    if (!capable(CAP_SYS_RAWIO))
        return -EPERM;
    switch (cmd) {
    case DIV_IOCTL_READ_PCICFG:
        return div_read_pcicfg(user_arg);
    case DIV_IOCTL_READ_MSR: {
        u32 msr, low, high;
        u64 value;

        if (copy_from_user(&msr, user_arg, sizeof(msr)))
            return -EFAULT;
        ret = rdmsr_safe(msr, &low, &high);
        if (ret)
            return -EIO;
        value = ((u64)high << 32) | low;
        return copy_to_user(user_arg, &value, sizeof(value)) ? -EFAULT : 0;
    }
    case DIV_IOCTL_WRITE_MSR: {
        struct div_msr_write request;

        ret = security_locked_down(LOCKDOWN_MSR);
        if (ret)
            return ret;
        if (copy_from_user(&request, user_arg, sizeof(request)))
            return -EFAULT;
        if (request.reserved)
            return -EINVAL;
        ret = wrmsr_safe(request.msr, (u32)request.value,
                         (u32)(request.value >> 32));
        return ret ? -EIO : 0;
    }
    case DIV_IOCTL_MAP_IOSPACE: {
        u64 address;

        ret = security_locked_down(LOCKDOWN_DEV_MEM);
        if (ret)
            return ret;
        if (copy_from_user(&address, user_arg, sizeof(address)))
            return -EFAULT;
        if (!IS_ALIGNED(address, PAGE_SIZE) || address > __PHYSICAL_MASK)
            return -EINVAL;
        mutex_lock(&state->lock);
        state->mmap_addr = address;
        state->mmap_ready = true;
        mutex_unlock(&state->lock);
        return 0;
    }
    default:
        return -ENOTTY;
    }
}

static const char div_name[] = "divination";
static dev_t div_dev;
static struct cdev div_cdev;
static struct class *div_class;

static const struct file_operations div_fops = {
    .owner = THIS_MODULE,
    .open = div_open,
    .release = div_release,
    .mmap = div_mmap,
    .unlocked_ioctl = div_ioctl,
};

static int __init div_init(void)
{
    struct device *device;
    int ret;

    ret = alloc_chrdev_region(&div_dev, 0, 1, div_name);
    if (ret)
        return ret;
    cdev_init(&div_cdev, &div_fops);
    ret = cdev_add(&div_cdev, div_dev, 1);
    if (ret)
        goto unregister;
#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 4, 0)
    div_class = class_create(div_name);
#else
    div_class = class_create(THIS_MODULE, div_name);
#endif
    if (IS_ERR(div_class)) {
        ret = PTR_ERR(div_class);
        goto delete_cdev;
    }
    device = device_create(div_class, NULL, div_dev, NULL, div_name);
    if (IS_ERR(device)) {
        ret = PTR_ERR(device);
        goto destroy_class;
    }
    pr_info("divination: module loaded\n");
    return 0;

destroy_class:
    class_destroy(div_class);
delete_cdev:
    cdev_del(&div_cdev);
unregister:
    unregister_chrdev_region(div_dev, 1);
    return ret;
}

static void __exit div_exit(void)
{
    device_destroy(div_class, div_dev);
    class_destroy(div_class);
    cdev_del(&div_cdev);
    unregister_chrdev_region(div_dev, 1);
    pr_info("divination: module unloaded\n");
}

module_init(div_init);
module_exit(div_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Privileged x86-64 hardware access for Divination");
