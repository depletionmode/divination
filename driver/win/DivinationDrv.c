/* Divination: privileged, synchronous x64 hardware inspection interface. */
#include <ntifs.h>
#include <wdmsec.h>
#include <intrin.h>

#define DIV_POOL_TAG 'nviD'
#define DIV_READ_PCICFG 0x00
#define DIV_READ_MSR 0x01
#define DIV_MAP_IOSPACE 0x02
#define DIV_UNMAP_IOSPACE 0x03
#define DIV_MAP_PHYSMEM 0x04
#define DIV_UNMAP_PHYSMEM 0x05
#define DIV_WRITE_MSR 0x06

static const UNICODE_STRING DivDeviceName = RTL_CONSTANT_STRING(L"\\Device\\Divination");
static const UNICODE_STRING DivLinkName = RTL_CONSTANT_STRING(L"\\??\\Divination");
/* Only SYSTEM and elevated administrators may obtain hardware access. */
static const UNICODE_STRING DivSecurity = RTL_CONSTANT_STRING(L"D:P(A;;GA;;;SY)(A;;GA;;;BA)");
static const GUID DivClassGuid =
    {0xe1188ff1, 0x555c, 0x462f, {0xa1, 0x17, 0x32, 0x8b, 0x4e, 0x02, 0xda, 0xc9}};
static FAST_IO_DISPATCH DivFastIo;
static FAST_MUTEX DivFilesLock;
static LIST_ENTRY DivFiles;

/* Wire records have fixed widths, independent of compiler pointer types. */
typedef struct _DIV_MAP_REQUEST {
    ULONGLONG PhysicalAddress;
    ULONGLONG Size;
} DIV_MAP_REQUEST;

typedef struct _DIV_MSR_WRITE {
    ULONG Register;
    ULONG Reserved;
    ULONGLONG Value;
} DIV_MSR_WRITE;

typedef union _DIV_INPUT {
    DIV_MAP_REQUEST Map;
    DIV_MSR_WRITE MsrWrite;
    ULONG Pci[3];
    ULONG Register;
    ULONGLONG Address;
} DIV_INPUT;

typedef struct _DIV_MAPPING {
    LIST_ENTRY Link;
    PMDL Mdl;
    PVOID BaseAddress;
    ULONGLONG Address;
} DIV_MAPPING, *PDIV_MAPPING;

typedef struct _DIV_FILE_CONTEXT {
    LIST_ENTRY Link;
    FAST_MUTEX Lock;
    LIST_ENTRY Mappings;
    PEPROCESS Process;
    BOOLEAN Cleaned;
} DIV_FILE_CONTEXT, *PDIV_FILE_CONTEXT;

C_ASSERT(sizeof(DIV_MAP_REQUEST) == 16);
C_ASSERT(sizeof(DIV_MSR_WRITE) == 16);

DRIVER_INITIALIZE DriverEntry;
DRIVER_UNLOAD DivUnload;
DRIVER_DISPATCH DivCreate;
DRIVER_DISPATCH DivCleanup;
DRIVER_DISPATCH DivClose;
DRIVER_DISPATCH DivUnsupported;
FAST_IO_DEVICE_CONTROL DivDeviceControl;

static NTSTATUS
DivComplete(PIRP Irp, NTSTATUS Status)
{
    Irp->IoStatus.Status = Status;
    Irp->IoStatus.Information = 0;
    IoCompleteRequest(Irp, IO_NO_INCREMENT);
    return Status;
}

/* Caller holds the file mutex and is attached to the owning process. */
static VOID
DivFreeMapping(PDIV_MAPPING Mapping)
{
    if (Mapping->BaseAddress != NULL) {
        MmUnmapLockedPages(Mapping->BaseAddress, Mapping->Mdl);
    }
    if (Mapping->Mdl != NULL) {
        /* MmAllocateMdlForIoSpace pages are not probe-locked RAM. */
        IoFreeMdl(Mapping->Mdl);
    }
    ExFreePoolWithTag(Mapping, DIV_POOL_TAG);
}

static VOID
DivReleaseMappings(PDIV_FILE_CONTEXT Context)
{
    KAPC_STATE apcState;
    BOOLEAN attached = FALSE;

    ExAcquireFastMutex(&Context->Lock);
    Context->Cleaned = TRUE;
    if (!IsListEmpty(&Context->Mappings)) {
        if (PsGetCurrentProcess() != Context->Process) {
            KeStackAttachProcess((PKPROCESS)Context->Process, &apcState);
            attached = TRUE;
        }
        while (!IsListEmpty(&Context->Mappings)) {
            PLIST_ENTRY entry = RemoveHeadList(&Context->Mappings);
            DivFreeMapping(CONTAINING_RECORD(entry, DIV_MAPPING, Link));
        }
        if (attached) {
            KeUnstackDetachProcess(&apcState);
        }
    }
    ExReleaseFastMutex(&Context->Lock);
}

static VOID
DivProcessNotify(PEPROCESS Process, HANDLE ProcessId, PPS_CREATE_NOTIFY_INFO CreateInfo)
{
    PLIST_ENTRY entry;
    UNREFERENCED_PARAMETER(ProcessId);
    if (CreateInfo != NULL) {
        return;
    }
    /* A duplicated handle can survive its original process. Unmap while that
       process still owns an address space, before the last thread exits. Lock
       order is always the global file list followed by an individual file. */
    ExAcquireFastMutex(&DivFilesLock);
    for (entry = DivFiles.Flink; entry != &DivFiles; entry = entry->Flink) {
        PDIV_FILE_CONTEXT context = CONTAINING_RECORD(entry, DIV_FILE_CONTEXT, Link);
        if (context->Process == Process) {
            DivReleaseMappings(context);
        }
    }
    ExReleaseFastMutex(&DivFilesLock);
}

NTSTATUS
DivCreate(PDEVICE_OBJECT DeviceObject, PIRP Irp)
{
    PIO_STACK_LOCATION stack = IoGetCurrentIrpStackLocation(Irp);
    PDIV_FILE_CONTEXT context;
    UNREFERENCED_PARAMETER(DeviceObject);

    /* FILE_DEVICE_SECURE_OPEN applies the ACL to names as well. No subpaths exist. */
    if (stack->FileObject->FileName.Length != 0) {
        return DivComplete(Irp, STATUS_OBJECT_NAME_NOT_FOUND);
    }
    context = ExAllocatePoolWithTag(NonPagedPoolNx, sizeof(*context), DIV_POOL_TAG);
    if (context == NULL) {
        return DivComplete(Irp, STATUS_INSUFFICIENT_RESOURCES);
    }
    RtlZeroMemory(context, sizeof(*context));
    ExInitializeFastMutex(&context->Lock);
    InitializeListHead(&context->Mappings);
    context->Process = PsGetCurrentProcess();
    ObReferenceObject(context->Process);
    stack->FileObject->FsContext = context;
    ExAcquireFastMutex(&DivFilesLock);
    InsertTailList(&DivFiles, &context->Link);
    ExReleaseFastMutex(&DivFilesLock);
    return DivComplete(Irp, STATUS_SUCCESS);
}

NTSTATUS
DivCleanup(PDEVICE_OBJECT DeviceObject, PIRP Irp)
{
    PDIV_FILE_CONTEXT context = IoGetCurrentIrpStackLocation(Irp)->FileObject->FsContext;
    UNREFERENCED_PARAMETER(DeviceObject);
    if (context != NULL) {
        DivReleaseMappings(context);
    }
    return DivComplete(Irp, STATUS_SUCCESS);
}

NTSTATUS
DivClose(PDEVICE_OBJECT DeviceObject, PIRP Irp)
{
    PFILE_OBJECT file = IoGetCurrentIrpStackLocation(Irp)->FileObject;
    PDIV_FILE_CONTEXT context = file->FsContext;
    UNREFERENCED_PARAMETER(DeviceObject);
    if (context != NULL) {
        ExAcquireFastMutex(&DivFilesLock);
        DivReleaseMappings(context);
        RemoveEntryList(&context->Link);
        ExReleaseFastMutex(&DivFilesLock);
        ObDereferenceObject(context->Process);
        ExFreePoolWithTag(context, DIV_POOL_TAG);
        file->FsContext = NULL;
    }
    return DivComplete(Irp, STATUS_SUCCESS);
}

NTSTATUS
DivUnsupported(PDEVICE_OBJECT DeviceObject, PIRP Irp)
{
    UNREFERENCED_PARAMETER(DeviceObject);
    return DivComplete(Irp, STATUS_INVALID_DEVICE_REQUEST);
}

static NTSTATUS
DivMapIo(PDIV_FILE_CONTEXT Context, const DIV_MAP_REQUEST *Request,
         PDIV_MAPPING *NewMapping)
{
    MM_PHYSICAL_ADDRESS_LIST range;
    PDIV_MAPPING mapping;
    ULONGLONG offset = Request->PhysicalAddress & (PAGE_SIZE - 1);
    ULONGLONG length;
    NTSTATUS status;

    /* Physical addresses are represented by a signed LARGE_INTEGER in the WDK. */
    if (Request->Size == 0 || Request->Size > MAXULONG - (PAGE_SIZE - 1) ||
        Request->PhysicalAddress > MAXLONGLONG ||
        Request->Size - 1 > MAXLONGLONG - Request->PhysicalAddress) {
        return STATUS_INVALID_PARAMETER;
    }
    length = (Request->Size + offset + PAGE_SIZE - 1) & ~((ULONGLONG)PAGE_SIZE - 1);
    if (length > MAXULONG) {
        return STATUS_INVALID_PARAMETER;
    }
    mapping = ExAllocatePoolWithTag(NonPagedPoolNx, sizeof(*mapping), DIV_POOL_TAG);
    if (mapping == NULL) {
        return STATUS_INSUFFICIENT_RESOURCES;
    }
    RtlZeroMemory(mapping, sizeof(*mapping));
    range.PhysicalAddress.QuadPart = (LONGLONG)(Request->PhysicalAddress - offset);
    range.NumberOfBytes = (SIZE_T)length;
    /* This documented API rejects ranges used as operating-system RAM. */
    status = MmAllocateMdlForIoSpace(&range, 1, &mapping->Mdl);
    if (!NT_SUCCESS(status)) {
        DivFreeMapping(mapping);
        return status;
    }
    __try {
        mapping->BaseAddress = MmMapLockedPagesSpecifyCache(
            mapping->Mdl, UserMode, MmNonCached, NULL, FALSE,
            NormalPagePriority | MdlMappingNoExecute);
        if (mapping->BaseAddress == NULL) {
            status = STATUS_INSUFFICIENT_RESOURCES;
        }
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        status = GetExceptionCode();
    }
    if (!NT_SUCCESS(status)) {
        DivFreeMapping(mapping);
        return status;
    }
    mapping->Address = (ULONGLONG)(ULONG_PTR)mapping->BaseAddress + offset;
    InsertTailList(&Context->Mappings, &mapping->Link);
    *NewMapping = mapping;
    return STATUS_SUCCESS;
}

static NTSTATUS
DivUnmapIo(PDIV_FILE_CONTEXT Context, ULONGLONG Address)
{
    PLIST_ENTRY entry;
    for (entry = Context->Mappings.Flink; entry != &Context->Mappings; entry = entry->Flink) {
        PDIV_MAPPING mapping = CONTAINING_RECORD(entry, DIV_MAPPING, Link);
        if (mapping->Address == Address) {
            RemoveEntryList(entry);
            DivFreeMapping(mapping);
            return STATUS_SUCCESS;
        }
    }
    return STATUS_NOT_FOUND;
}

BOOLEAN
DivDeviceControl(PFILE_OBJECT FileObject, BOOLEAN Wait, PVOID InputBuffer,
                 ULONG InputBufferLength, PVOID OutputBuffer, ULONG OutputBufferLength,
                 ULONG IoControlCode, PIO_STATUS_BLOCK IoStatus, PDEVICE_OBJECT DeviceObject)
{
    PDIV_FILE_CONTEXT context = FileObject->FsContext;
    PDIV_MAPPING newMapping = NULL;
    DIV_INPUT input;
    UCHAR output[0x100];
    ULONG inputSize = 0, outputSize = 0;
    NTSTATUS status = STATUS_INVALID_DEVICE_REQUEST;
    BOOLEAN locked = FALSE;
    UNREFERENCED_PARAMETER(DeviceObject);

    IoStatus->Information = 0;
    if (!Wait || KeGetCurrentIrql() > APC_LEVEL) {
        return FALSE;
    }
    if (context == NULL || context->Process != PsGetCurrentProcess()) {
        status = STATUS_ACCESS_DENIED;
        goto done;
    }
    /* The protocol and driver build support x64 callers only. */
    if (IoIs32bitProcess(NULL)) {
        status = STATUS_NOT_SUPPORTED;
        goto done;
    }
    switch (IoControlCode) {
    case DIV_READ_PCICFG: inputSize = 12; outputSize = sizeof(output); break;
    case DIV_READ_MSR: inputSize = 4; outputSize = 8; break;
    case DIV_WRITE_MSR: inputSize = sizeof(DIV_MSR_WRITE); break;
    case DIV_MAP_IOSPACE: inputSize = sizeof(DIV_MAP_REQUEST); outputSize = 8; break;
    case DIV_UNMAP_IOSPACE: inputSize = 8; break;
    case DIV_MAP_PHYSMEM:
    case DIV_UNMAP_PHYSMEM:
        status = STATUS_NOT_SUPPORTED;
        goto done;
    default: goto done;
    }
    if (InputBufferLength != inputSize || OutputBufferLength < outputSize) {
        status = STATUS_INVALID_BUFFER_SIZE;
        goto done;
    }
    RtlZeroMemory(&input, sizeof(input));
    RtlZeroMemory(output, sizeof(output));
    ExAcquireFastMutex(&context->Lock);
    locked = TRUE;
    if (context->Cleaned) {
        status = STATUS_FILE_CLOSED;
        goto done;
    }
    /* Probe AND every subsequent user-buffer access are protected by SEH. Copy
       input once so a caller cannot change a validated request underneath us. */
    __try {
        if (ExGetPreviousMode() != KernelMode) {
            ProbeForRead(InputBuffer, inputSize, 1);
            if (outputSize != 0) {
                ProbeForWrite(OutputBuffer, outputSize, 1);
            }
        }
        RtlCopyMemory(&input, InputBuffer, inputSize);
        switch (IoControlCode) {
        case DIV_READ_PCICFG:
        {
            PCI_SLOT_NUMBER slot;
            ULONG bytesRead;
            if (input.Pci[0] > 255 || input.Pci[1] > 31 || input.Pci[2] > 7) {
                status = STATUS_INVALID_PARAMETER;
                break;
            }
            slot.u.AsULONG = 0;
            slot.u.bits.DeviceNumber = input.Pci[1];
            slot.u.bits.FunctionNumber = input.Pci[2];
            bytesRead = HalGetBusDataByOffset(PCIConfiguration, input.Pci[0],
                                             slot.u.AsULONG, output, 0, sizeof(output));
            status = bytesRead == sizeof(output) ? STATUS_SUCCESS : STATUS_NO_SUCH_DEVICE;
            break;
        }
        case DIV_READ_MSR:
        {
            ULONGLONG value = __readmsr(input.Register);
            RtlCopyMemory(output, &value, sizeof(value));
            status = STATUS_SUCCESS;
            break;
        }
        case DIV_WRITE_MSR:
            if (input.MsrWrite.Reserved != 0) {
                status = STATUS_INVALID_PARAMETER;
                break;
            }
            __writemsr(input.MsrWrite.Register, input.MsrWrite.Value);
            status = STATUS_SUCCESS;
            break;
        case DIV_MAP_IOSPACE:
            status = DivMapIo(context, &input.Map, &newMapping);
            if (NT_SUCCESS(status)) {
                RtlCopyMemory(output, &newMapping->Address, sizeof(newMapping->Address));
            }
            break;
        case DIV_UNMAP_IOSPACE:
            status = DivUnmapIo(context, input.Address);
            break;
        }
        if (NT_SUCCESS(status) && outputSize != 0) {
            RtlCopyMemory(OutputBuffer, output, outputSize);
        }
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        status = GetExceptionCode();
    }
    if (!NT_SUCCESS(status) && newMapping != NULL) {
        RemoveEntryList(&newMapping->Link);
        DivFreeMapping(newMapping);
    }
    if (NT_SUCCESS(status)) {
        IoStatus->Information = outputSize;
    }
done:
    if (locked) {
        ExReleaseFastMutex(&context->Lock);
    }
    IoStatus->Status = status;
    /* TRUE means handled, including errors. FALSE would retry the request as an
       IRP with a different buffering method (legacy opcodes are not CTL_CODEs). */
    return TRUE;
}

VOID
DivUnload(PDRIVER_OBJECT DriverObject)
{
    PsSetCreateProcessNotifyRoutineEx(DivProcessNotify, TRUE);
    IoDeleteSymbolicLink((PUNICODE_STRING)&DivLinkName);
    IoDeleteDevice(DriverObject->DeviceObject);
}

NTSTATUS
DriverEntry(PDRIVER_OBJECT DriverObject, PUNICODE_STRING RegistryPath)
{
    PDEVICE_OBJECT device = NULL;
    NTSTATUS status;
    ULONG i;
    UNREFERENCED_PARAMETER(RegistryPath);

    ExInitializeFastMutex(&DivFilesLock);
    InitializeListHead(&DivFiles);

    for (i = 0; i <= IRP_MJ_MAXIMUM_FUNCTION; ++i) {
        DriverObject->MajorFunction[i] = DivUnsupported;
    }
    DriverObject->MajorFunction[IRP_MJ_CREATE] = DivCreate;
    DriverObject->MajorFunction[IRP_MJ_CLEANUP] = DivCleanup;
    DriverObject->MajorFunction[IRP_MJ_CLOSE] = DivClose;
    DriverObject->DriverUnload = DivUnload;
    DivFastIo.SizeOfFastIoDispatch = sizeof(DivFastIo);
    DivFastIo.FastIoDeviceControl = DivDeviceControl;
    DriverObject->FastIoDispatch = &DivFastIo;

    status = IoCreateDeviceSecure(DriverObject, 0, (PUNICODE_STRING)&DivDeviceName,
        FILE_DEVICE_UNKNOWN, FILE_DEVICE_SECURE_OPEN, FALSE,
        &DivSecurity, &DivClassGuid, &device);
    if (!NT_SUCCESS(status)) {
        return status;
    }
    status = PsSetCreateProcessNotifyRoutineEx(DivProcessNotify, FALSE);
    if (!NT_SUCCESS(status)) {
        IoDeleteDevice(device);
        return status;
    }
    status = IoCreateSymbolicLink((PUNICODE_STRING)&DivLinkName,
                                  (PUNICODE_STRING)&DivDeviceName);
    if (!NT_SUCCESS(status)) {
        PsSetCreateProcessNotifyRoutineEx(DivProcessNotify, TRUE);
        IoDeleteDevice(device);
        return status;
    }
    device->Flags &= ~DO_DEVICE_INITIALIZING;
    return STATUS_SUCCESS;
}
