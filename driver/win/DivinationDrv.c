/*
 * @depletionmode 2019
 */

#include <Ntddk.h>

static const UNICODE_STRING DivpDeviceName = RTL_CONSTANT_STRING(L"\\Device\\Divination");
static const UNICODE_STRING DivpWin32DeviceName = RTL_CONSTANT_STRING(L"\\??\\Divination");

#define DIV_IOCTL_READ_PCICFG   0x00
#define DIV_IOCTL_READ_MSR      0x01

#define DIV_IOCTL_MAP_IOSPACE   0x02
#define DIV_IOCTL_UNMAP_IOSPACE 0x03
#define DIV_IOCTL_MAP_PHYSMEM   0x04
#define DIV_IOCTL_UNMAP_PHYSMEM 0x05

#define DIV_IOCTL_ALLOC_PHYSMEM 0x0a
#define DIV_IOCTL_FREE_PHYSMEM  0x0b

typedef struct _DIV_PCICFG_REQUEST {
    ULONG Bus;
    ULONG Device;
    ULONG Function;

} DIV_PCICFG_REQUEST, *PDIV_PCICFG_REQUEST;

typedef struct _DIV_MAP_REQUEST {
    PVOID PhysicalAddress;
    SIZE_T Size;

} DIV_MAP_REQUEST, *PDIV_MAP_REQUEST;

DRIVER_INITIALIZE DriverEntry;
DRIVER_UNLOAD DivDriverUnload;

NTSTATUS
DriverEntry (
    _In_ PDRIVER_OBJECT DriverObject,
    _In_ PUNICODE_STRING RegistryPath
    );

VOID DivDriverUnload (
    _In_ PDRIVER_OBJECT DriverObject
    );

NTSTATUS
DivDispatchCreate (
    _In_ PDEVICE_OBJECT DeviceObject,
    _In_ PIRP Irp
    );

BOOLEAN
DivDispatchFastIoDeviceControl (
    _In_ struct _FILE_OBJECT *FileObject,
    _In_ BOOLEAN Wait,
    _In_opt_ PVOID InputBuffer,
    _In_ ULONG InputBufferLength,
    _Out_opt_ PVOID OutputBuffer,
    _In_ ULONG OutputBufferLength,
    _In_ ULONG IoControlCode,
    _Out_ PIO_STATUS_BLOCK IoStatus,
    _In_ struct _DEVICE_OBJECT *DeviceObject
    );

#pragma alloc_text(INIT, DriverEntry)
#pragma alloc_text(PAGE, DivDriverUnload)
#pragma alloc_text(PAGE, DivDispatchCreate)
#pragma alloc_text(PAGE, DivDispatchFastIoDeviceControl)

typedef struct _DIV_CONTEXT {
    PDEVICE_OBJECT DeviceObject;
    FAST_IO_DISPATCH FastIoDispatchTbl;

    LIST_ENTRY MdlList;

} DIV_CONTEXT, *PDIV_CONTEXT;

typedef struct _DIV_MDL_NODE {
    PVOID Address;
    PMDL Mdl;

    BOOLEAN Locked;

    LIST_ENTRY ListEntry;

} DIV_MDL_NODE, *PDIV_MDL_NODE;

#define POOL_TAG_(n) #@n
#define POOL_TAG(n) POOL_TAG_(n##seD)

static DIV_CONTEXT DivContext = { 0 };

NTSTATUS
_unmapVaFromUserModeProcess (
    _In_ ULONG_PTR UserModeVirtualAddress
    );

NTSTATUS
_mapVaIntoUserModeProcess (
    _In_ PVOID VirtualAddress,
    _In_ ULONG Size,
    _Out_ ULONG_PTR* UserModeVirtualAddress
    );

NTSTATUS
DriverEntry (
    _In_ PDRIVER_OBJECT DriverObject,
    _In_ PUNICODE_STRING RegistryPath
    )
{
    NTSTATUS status;

    UNREFERENCED_PARAMETER(RegistryPath);

    PAGED_CODE();

    DivContext.FastIoDispatchTbl.SizeOfFastIoDispatch = sizeof(FAST_IO_DISPATCH);
    DivContext.FastIoDispatchTbl.FastIoDeviceControl = (PFAST_IO_DEVICE_CONTROL)DivDispatchFastIoDeviceControl;

    DriverObject->DriverUnload = DivDriverUnload;
    DriverObject->FastIoDispatch = &DivContext.FastIoDispatchTbl;
    DriverObject->MajorFunction[IRP_MJ_CREATE] = DivDispatchCreate;

    status = IoCreateDevice(DriverObject,
                            0,
                            (PUNICODE_STRING)&DivpDeviceName,
                            FILE_DEVICE_UNKNOWN,
                            FILE_DEVICE_SECURE_OPEN,
                            FALSE,
                            &DivContext.DeviceObject);
    if (!NT_SUCCESS(status)) {
        goto end;
    }

    status = IoCreateSymbolicLink((PUNICODE_STRING)&DivpWin32DeviceName,
                                  (PUNICODE_STRING)&DivpDeviceName);
    if (!NT_SUCCESS(status)) {
        goto end;
    }

    InitializeListHead(&DivContext.MdlList);

end:
    return status;
}

VOID
DivDriverUnload (
    _In_ PDRIVER_OBJECT DriverObject
    )
{
    UNREFERENCED_PARAMETER(DriverObject);

    PAGED_CODE();

    if (NULL != DivContext.DeviceObject) {
        IoDeleteSymbolicLink((PUNICODE_STRING)&DivpWin32DeviceName);
        IoDeleteDevice(DivContext.DeviceObject);
        DivContext.DeviceObject = NULL;
    }
}

NTSTATUS
DivDispatchCreate (
    _In_ PDEVICE_OBJECT DeviceObject,
    _In_ PIRP Irp
    )
{
    NTSTATUS status = STATUS_SUCCESS;

    UNREFERENCED_PARAMETER(DeviceObject);

    PAGED_CODE();

    Irp->IoStatus.Status = status;
    Irp->IoStatus.Information = 0;
    IoCompleteRequest(Irp, IO_NO_INCREMENT);

    return status;
}

BOOLEAN
DivDispatchFastIoDeviceControl (
    _In_ struct _FILE_OBJECT *FileObject,
    _In_ BOOLEAN Wait,
    _In_opt_ PVOID InputBuffer,
    _In_ ULONG InputBufferLength,
    _Out_opt_ PVOID OutputBuffer,
    _In_ ULONG OutputBufferLength,
    _In_ ULONG IoControlCode,
    _Out_ PIO_STATUS_BLOCK IoStatus,
    _In_ struct _DEVICE_OBJECT *DeviceObject
    )
{
    NTSTATUS status;
    ULONG responseLength = 0;

    UNREFERENCED_PARAMETER(Wait);
    UNREFERENCED_PARAMETER(FileObject);
    UNREFERENCED_PARAMETER(DeviceObject);

    PAGED_CODE();

    switch (IoControlCode) {
    case DIV_IOCTL_READ_PCICFG:
    {
        PDIV_PCICFG_REQUEST request;
        PCI_SLOT_NUMBER slot;
        ULONG bytesRead;

#define PCICFG_READ_SIZE 0x100

        if (InputBufferLength < sizeof(DIV_PCICFG_REQUEST) ||
            OutputBufferLength < PCICFG_READ_SIZE) {
            status = STATUS_INVALID_PARAMETER;
            goto end;
        }

        __try {
            ProbeForRead(InputBuffer, sizeof(DIV_PCICFG_REQUEST), 1);
            ProbeForWrite(OutputBuffer, PCICFG_READ_SIZE, 1);

        } __except (EXCEPTION_EXECUTE_HANDLER) {
            status = GetExceptionCode();
            goto end;
        }

        request = (PDIV_PCICFG_REQUEST)InputBuffer;

        slot.u.AsULONG = 0;
        slot.u.bits.DeviceNumber = request->Device;
        slot.u.bits.FunctionNumber = request->Function;

        bytesRead = HalGetBusDataByOffset(PCIConfiguration,
                                          request->Bus,
                                          slot.u.AsULONG,
                                          OutputBuffer,
                                          0,
                                          PCICFG_READ_SIZE);
        if (0 == bytesRead) {
            status = STATUS_UNSUCCESSFUL;
            goto end;
        }

        status = STATUS_SUCCESS;
        responseLength = bytesRead;

        break;
    }
    case DIV_IOCTL_READ_MSR:
    {
        if (InputBufferLength < sizeof(ULONG) ||
            OutputBufferLength < sizeof(ULONG64)) {
            status = STATUS_INVALID_PARAMETER;
            goto end;
        }

        __try {
            ProbeForRead(InputBuffer, sizeof(ULONG), 1);
            ProbeForWrite(OutputBuffer, sizeof(ULONG64), 1);

        } __except (EXCEPTION_EXECUTE_HANDLER) {
            status = GetExceptionCode();
            goto end;
        }

        __try {
            *(PULONG64)OutputBuffer = __readmsr(*(PULONG)InputBuffer);

        } __except (EXCEPTION_EXECUTE_HANDLER) {
            status = GetExceptionCode();
            goto end;
        }

        status = STATUS_SUCCESS;
        responseLength = sizeof(ULONG64);

        break;
    }   

    case DIV_IOCTL_MAP_IOSPACE:
    {
        PDIV_MAP_REQUEST request;
        PHYSICAL_ADDRESS pa;
        PVOID va;

        if (InputBufferLength < sizeof(DIV_MAP_REQUEST) ||
            OutputBufferLength < sizeof(ULONG_PTR)) {
            status = STATUS_INVALID_PARAMETER;
            goto end;
        }

        __try {
            ProbeForRead(InputBuffer, sizeof(DIV_MAP_REQUEST), 1);
            ProbeForWrite(OutputBuffer, sizeof(ULONG_PTR), 1);

        } __except (EXCEPTION_EXECUTE_HANDLER) {
            status = GetExceptionCode();
            goto end;
        }

        request = (PDIV_MAP_REQUEST)InputBuffer;

        pa.QuadPart = (LONGLONG)request->PhysicalAddress;

        va = MmMapIoSpace(pa, request->Size, MmNonCached);
        if (NULL == va) {
            status = STATUS_INSUFFICIENT_RESOURCES;
            goto end;
        }

        status = _mapVaIntoUserModeProcess(va, (ULONG)request->Size, OutputBuffer);
        if (!NT_SUCCESS(status)) {
            goto end;
        }

        status = STATUS_SUCCESS;
        responseLength = sizeof(ULONG_PTR);

        break;
    }

    case DIV_IOCTL_UNMAP_IOSPACE:
    {
        if (InputBufferLength < sizeof(ULONG_PTR)) {
            status = STATUS_INVALID_PARAMETER;
            goto end;
        }

        __try {
            ProbeForRead(InputBuffer, sizeof(ULONG_PTR), 1);

        } __except (EXCEPTION_EXECUTE_HANDLER) {
            status = GetExceptionCode();
            goto end;
        }

        status = _unmapVaFromUserModeProcess(*(PULONG_PTR)InputBuffer);

        break;
    }

    default:
        
        status = STATUS_INVALID_PARAMETER;
    }

end:
    IoStatus->Information = responseLength;
    IoStatus->Status = status;

    return status == STATUS_SUCCESS;
}

NTSTATUS
_mapVaIntoUserModeProcess (
    _In_ PVOID VirtualAddress,
    _In_ ULONG Size,
    _Out_ ULONG_PTR* UserModeVirtualAddress
    )
{
    NTSTATUS status;
    PDIV_MDL_NODE mdlNode;

    mdlNode = ExAllocatePoolWithTag(NonPagedPoolNx, 
                                    sizeof(DIV_MDL_NODE), 
                                    POOL_TAG(M));
    if (NULL == mdlNode) {
        status = STATUS_INSUFFICIENT_RESOURCES;
        goto end;
    }
    RtlZeroMemory(mdlNode, sizeof(DIV_MDL_NODE));

    mdlNode->Mdl = IoAllocateMdl(VirtualAddress,
                                 Size,
                                 FALSE,
                                 FALSE,
                                 NULL);
    if (NULL == mdlNode->Mdl) {
        status = STATUS_INSUFFICIENT_RESOURCES;
        goto end;
    }

    __try{
        MmProbeAndLockPages(mdlNode->Mdl, KernelMode, IoModifyAccess);
        mdlNode->Locked = TRUE;

        mdlNode->Address = MmMapLockedPagesSpecifyCache(mdlNode->Mdl,
                                                        UserMode,
                                                        MmNonCached,
                                                        NULL,
                                                        FALSE,
                                                        NormalPagePriority);
        if (NULL == mdlNode->Address) {
            status = STATUS_INSUFFICIENT_RESOURCES;
            goto end;
        }

    } __except (EXCEPTION_EXECUTE_HANDLER) {
        status = GetExceptionCode();
        goto end;
    }

    InsertTailList(&DivContext.MdlList, &mdlNode->ListEntry);

    *UserModeVirtualAddress = (ULONG_PTR)mdlNode->Address;

    status = STATUS_SUCCESS;

end:
    if (!NT_SUCCESS(status)) {
        if (mdlNode) {
            if (mdlNode->Address) {
                MmUnmapLockedPages(mdlNode->Address, mdlNode->Mdl);
            }

            if (mdlNode->Locked) {
                MmUnlockPages(mdlNode->Mdl);
                mdlNode->Locked = FALSE;
            }

            if (mdlNode->Mdl) {
                IoFreeMdl(mdlNode->Mdl);
                mdlNode->Mdl = NULL;
            }

            ExFreePoolWithTag(mdlNode, POOL_TAG(M));
            mdlNode = NULL;
        }
    }

    return status;
}

NTSTATUS
_unmapVaFromUserModeProcess (
    _In_ ULONG_PTR UserModeVirtualAddress
    )
{
    NTSTATUS status;
    PLIST_ENTRY entry;
    PMDL mdl = NULL;
    PDIV_MDL_NODE mdlNode;

    entry = DivContext.MdlList.Flink;
    while (entry != &DivContext.MdlList) {
        mdlNode = CONTAINING_RECORD(entry, DIV_MDL_NODE, ListEntry);

        if (mdlNode->Address == (PVOID)UserModeVirtualAddress) {
            mdl = mdlNode->Mdl;
            RemoveEntryList(&mdlNode->ListEntry);
            ExFreePoolWithTag(mdlNode, POOL_TAG(M));
            break;
        }

        entry = entry->Flink;
    }

    if (NULL == mdl) {
        status = STATUS_NOT_FOUND;
        goto end;
    }

    MmUnmapLockedPages((PVOID)UserModeVirtualAddress, mdl);
    MmUnlockPages(mdl);
    MmUnmapIoSpace(mdl->StartVa, mdl->Size);
    IoFreeMdl(mdl);

    status = STATUS_SUCCESS;

end:
    return status;
}
