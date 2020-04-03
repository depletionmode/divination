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

#define DIV_IOCTL_READ_PCICFG   _IOWR(0xc0,0x00,div_pcicfg_read_t*)
#define DIV_IOCTL_READ_MSR      _IOWR(0xc0,0x01,uint64_t*)

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
            uint64_t msr;
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

static const char _device_name[] = "divination";
static int _char_dev = 0;

static struct file_operations div_fops = {
    .owner = THIS_MODULE,
    .unlocked_ioctl = div_ioctl
};

static int div_init(void)
{
    int res = register_chrdev(0, _device_name, &div_fops);
    if (res < 0) {
        printk(KERN_ALERT "divination: failed to register char device (err=%i)\n", res);
    }

    _char_dev = res;
    printk(KERN_NOTICE "divination: module loaded (chardev=%i)\n", _char_dev);

    return 0;
}

static void div_exit(void)
{
    if (_char_dev != 0) {
        unregister_chrdev(_char_dev, _device_name);
    }

    printk(KERN_NOTICE "divination: module unloaded\n");
}

module_init(div_init);
module_exit(div_exit);
MODULE_LICENSE("GPL");