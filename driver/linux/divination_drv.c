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

typedef struct {
    uint32_t bus;
    uint32_t device;
    uint32_t function;

#define PCICFG_READ_SIZE 0x100
    uint8_t cfg_region[PCICFG_READ_SIZE];

} div_pcicfg_read_t;

#define DIV_IOCTL_READ_PCICFG   _IOWR(0xe0,0x00,div_pcicfg_read_t*)
#define DIV_IOCTL_READ_MSR      _IOWR(0xe0,0x01,uint64_t*)

//int div_init();
//void div_exit();
//int div_ioctl(struct file*, unsigned int, unsigned long);

static long int div_ioctl(struct file* file, unsigned int cmd, unsigned long arg)
{
    switch(cmd) {
    case DIV_IOCTL_READ_PCICFG:
        {
            div_pcicfg_read_t pcicfg = { 0 };
            
            copy_from_user(&pcicfg, (void __user *)arg, sizeof(pcicfg));
            //TODO impl
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
    
    printk(KERN_NOTICE "divination: module loaded %lx\n");

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