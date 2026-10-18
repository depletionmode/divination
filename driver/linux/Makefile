TARGET_MODULE := divination

ifneq ($(KERNELRELEASE),)
obj-m := $(TARGET_MODULE).o
$(TARGET_MODULE)-y := divination_drv.o
else
KDIR ?= /lib/modules/$(shell uname -r)/build
# Retain the old override for existing build scripts.
BUILDSYSTEM_DIR ?= $(KDIR)
MODULE_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))

.PHONY: all clean load unload
all:
	$(MAKE) -C "$(BUILDSYSTEM_DIR)" M="$(MODULE_DIR)" modules
clean:
	$(MAKE) -C "$(BUILDSYSTEM_DIR)" M="$(MODULE_DIR)" clean
load:
	insmod "$(MODULE_DIR)/$(TARGET_MODULE).ko"
unload:
	rmmod $(TARGET_MODULE)
endif
