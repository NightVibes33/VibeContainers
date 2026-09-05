#include "NyxRuntime.h"
#include "VPhoneKernelSurface.h"
#include "VPhoneRuntimeCore.h"

#include <CFNetwork/CFNetwork.h>

#include <errno.h>
#include <fcntl.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <unistd.h>
#include <string.h>

struct NyxVM {
    VPRuntime *runtime;
    VPKernelSurface *surface;
    NyxLogCallback log_callback;
    void *log_context;
    int disk_fd;
    uint64_t disk_size;
    int dyld_cache_fd;
    uint64_t dyld_cache_size;
    uint64_t dyld_entry;
    uint64_t launchd_entry;
    char diagnostics[16384];
    size_t diagnostics_length;
};

static void nyx_runtime_serial(const uint8_t *bytes, size_t length, void *context);

static VPStatus nyx_network_https_get(
    const char *url, uint8_t *response, size_t capacity, size_t *response_length, void *context
);

static void nyx_runtime_serial(const uint8_t *bytes, size_t length, void *context) {
    NyxVM *vm = (NyxVM *)context;
    if (!vm || !bytes || !length) return;
    const size_t delivered_length = length;
    size_t available = sizeof(vm->diagnostics) - 1u - vm->diagnostics_length;
    if (length > available) length = available;
    if (length) memcpy(vm->diagnostics + vm->diagnostics_length, bytes, length);
    vm->diagnostics_length += length;
    vm->diagnostics[vm->diagnostics_length] = 0;
    if (vm->log_callback) vm->log_callback(bytes, delivered_length, vm->log_context);
}

static void nyx_emit(NyxVM *vm, const char *message) {
    if (!vm || !message) return;
    nyx_runtime_serial((const uint8_t *)message, strlen(message), vm);
}

const char *nyx_runtime_version(void) {
    return "NyxRuntime/0.19-dyld-bit-operations";
}

uint32_t nyx_runtime_abi_version(void) {
    return NYX_RUNTIME_ABI_VERSION;
}

NyxVM *nyx_vm_create(const NyxVMConfig *config) {
    if (!config) return NULL;
    NyxVM *vm = (NyxVM *)calloc(1, sizeof(*vm));
    if (!vm) return NULL;
    vm->disk_fd = -1;
    vm->dyld_cache_fd = -1;
    VPMachineConfig core_config = {
        .cpu_count = config->cpu_count,
        .guest_physical_memory_size = config->guest_physical_memory_size,
        .screen_width = config->screen_width,
        .screen_height = config->screen_height,
        .pixels_per_inch = config->pixels_per_inch,
        .screen_scale = config->screen_scale,
    };
    vm->runtime = vp_runtime_create(&core_config);
    if (!vm->runtime) {
        free(vm);
        return NULL;
    }
    vp_runtime_set_network_handler(vm->runtime, nyx_network_https_get, vm);
    vm->surface = vp_ksurface_attach(vm->runtime);
    if (!vm->surface) {
        vp_runtime_destroy(vm->runtime);
        free(vm);
        return NULL;
    }
    vp_runtime_set_serial_callback(vm->runtime, nyx_runtime_serial, vm);
    return vm;
}

void nyx_vm_destroy(NyxVM *vm) {
    if (!vm) return;
    if (vm->disk_fd >= 0) close(vm->disk_fd);
    if (vm->dyld_cache_fd >= 0) close(vm->dyld_cache_fd);
    if (vm->surface) vp_ksurface_destroy(vm->surface);
    if (vm->runtime) vp_runtime_destroy(vm->runtime);
    memset(vm, 0, sizeof(*vm));
    free(vm);
}

static VPStatus nyx_disk_read(uint64_t offset, void *dst, size_t length, void *context) {
    NyxVM *vm = (NyxVM *)context;
    if (!vm || vm->disk_fd < 0 || offset > vm->disk_size || length > vm->disk_size - offset) {
        return VP_STATUS_ADDRESS_OUT_OF_RANGE;
    }
    uint8_t *bytes = (uint8_t *)dst;
    size_t done = 0;
    while (done < length) {
        const ssize_t count = pread(vm->disk_fd, bytes + done, length - done, (off_t)(offset + done));
        if (count < 0 && errno == EINTR) continue;
        if (count <= 0) return VP_STATUS_EXECUTION_FAULT;
        done += (size_t)count;
    }
    return VP_STATUS_OK;
}

static VPStatus nyx_disk_write(uint64_t offset, const void *src, size_t length, void *context) {
    NyxVM *vm = (NyxVM *)context;
    if (!vm || vm->disk_fd < 0 || offset > vm->disk_size || length > vm->disk_size - offset) {
        return VP_STATUS_ADDRESS_OUT_OF_RANGE;
    }
    const uint8_t *bytes = (const uint8_t *)src;
    size_t done = 0;
    while (done < length) {
        const ssize_t count = pwrite(vm->disk_fd, bytes + done, length - done, (off_t)(offset + done));
        if (count < 0 && errno == EINTR) continue;
        if (count <= 0) return VP_STATUS_EXECUTION_FAULT;
        done += (size_t)count;
    }
    return VP_STATUS_OK;
}

static VPStatus nyx_disk_flush(void *context) {
    NyxVM *vm = (NyxVM *)context;
    return vm && vm->disk_fd >= 0 && fsync(vm->disk_fd) == 0 ? VP_STATUS_OK : VP_STATUS_EXECUTION_FAULT;
}

#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
static VPStatus nyx_network_https_get(
    const char *url_string, uint8_t *response, size_t capacity, size_t *response_length, void *context
) {
    (void)context;
    if (!url_string || !response || !response_length || capacity == 0) return VP_STATUS_INVALID_ARGUMENT;
    VPStatus status = VP_STATUS_EXECUTION_FAULT;
    CFURLRef url = CFURLCreateWithBytes(
        kCFAllocatorDefault, (const UInt8 *)url_string, (CFIndex)strlen(url_string),
        kCFStringEncodingUTF8, NULL
    );
    if (!url) return VP_STATUS_INVALID_ARGUMENT;
    CFHTTPMessageRef request = CFHTTPMessageCreateRequest(
        kCFAllocatorDefault, CFSTR("GET"), url, kCFHTTPVersion1_1
    );
    if (!request) { CFRelease(url); return VP_STATUS_OUT_OF_MEMORY; }
    CFHTTPMessageSetHeaderFieldValue(request, CFSTR("User-Agent"), CFSTR("NyxPhone-Nyxian/0.6"));
    CFHTTPMessageSetHeaderFieldValue(request, CFSTR("Accept"), CFSTR("*/*"));
    CFReadStreamRef stream = CFReadStreamCreateForHTTPRequest(kCFAllocatorDefault, request);
    if (!stream) { CFRelease(request); CFRelease(url); return VP_STATUS_OUT_OF_MEMORY; }
    (void)CFReadStreamSetProperty(stream, kCFStreamPropertyHTTPShouldAutoredirect, kCFBooleanTrue);
    if (CFReadStreamOpen(stream)) {
        size_t total = 0;
        while (total < capacity) {
            const CFIndex count = CFReadStreamRead(
                stream, response + total, (CFIndex)(capacity - total)
            );
            if (count > 0) { total += (size_t)count; continue; }
            if (count == 0) break;
            total = 0;
            break;
        }
        CFHTTPMessageRef headers = (CFHTTPMessageRef)CFReadStreamCopyProperty(
            stream, kCFStreamPropertyHTTPResponseHeader
        );
        if (headers) {
            const CFIndex response_status = CFHTTPMessageGetResponseStatusCode(headers);
            if (response_status >= 200 && response_status < 400 && total > 0) {
                *response_length = total;
                status = VP_STATUS_OK;
            }
            CFRelease(headers);
        }
    }
    CFReadStreamClose(stream);
    CFRelease(stream);
    CFRelease(request);
    CFRelease(url);
    return status;
}
#pragma clang diagnostic pop

int32_t nyx_vm_mount_disk(NyxVM *vm, const char *path, uint64_t disk_size) {
    if (!vm || !path || !path[0] || disk_size == 0 || disk_size > INT64_MAX || vm->disk_fd >= 0) {
        return (int32_t)VP_STATUS_INVALID_ARGUMENT;
    }
    const int fd = open(path, O_RDWR | O_CREAT, 0600);
    if (fd < 0) return (int32_t)VP_STATUS_BACKEND_UNAVAILABLE;
    struct stat st;
    if (fstat(fd, &st) != 0 || st.st_size < 0 ||
        ((uint64_t)st.st_size < disk_size && ftruncate(fd, (off_t)disk_size) != 0)) {
        close(fd);
        return (int32_t)VP_STATUS_BACKEND_UNAVAILABLE;
    }
    vm->disk_fd = fd;
    vm->disk_size = disk_size;
    vp_runtime_set_block_handlers(vm->runtime, nyx_disk_read, nyx_disk_write, nyx_disk_flush, vm);
    return (int32_t)VP_STATUS_OK;
}

void nyx_vm_set_log_callback(NyxVM *vm, NyxLogCallback callback, void *context) {
    if (!vm) return;
    vm->log_callback = callback;
    vm->log_context = context;
    nyx_emit(vm, "[NYXRT] runtime initialized\n");
}

typedef struct {
    uint64_t address;
    uint64_t size;
    uint64_t file_offset;
    uint32_t max_protection;
    uint32_t initial_protection;
} NyxDyldCacheMapping;

static VPStatus nyx_dyld_cache_read(
    uint64_t offset, void *dst, size_t length, void *context
) {
    NyxVM *vm = (NyxVM *)context;
    if (!vm || vm->dyld_cache_fd < 0 || offset > vm->dyld_cache_size ||
        length > vm->dyld_cache_size - offset) return VP_STATUS_ADDRESS_OUT_OF_RANGE;
    uint8_t *bytes = (uint8_t *)dst;
    size_t done = 0;
    while (done < length) {
        const ssize_t count = pread(
            vm->dyld_cache_fd, bytes + done, length - done, (off_t)(offset + done)
        );
        if (count < 0 && errno == EINTR) continue;
        if (count <= 0) return VP_STATUS_EXECUTION_FAULT;
        done += (size_t)count;
    }
    return VP_STATUS_OK;
}

int32_t nyx_vm_copy_diagnostics(
    NyxVM *vm, char *buffer, size_t capacity, size_t *length
) {
    if (!vm || !buffer || capacity == 0) return (int32_t)VP_STATUS_INVALID_ARGUMENT;
    size_t count = vm->diagnostics_length;
    if (count >= capacity) count = capacity - 1u;
    if (count) memcpy(buffer, vm->diagnostics, count);
    buffer[count] = 0;
    if (length) *length = count;
    return (int32_t)VP_STATUS_OK;
}

int32_t nyx_vm_map_dyld_cache(
    NyxVM *vm, const char *path, uint32_t *mapping_count, uint64_t *mapped_bytes
) {
    if (!vm || !path || !path[0] || !mapping_count || !mapped_bytes || vm->dyld_cache_fd >= 0) {
        return (int32_t)VP_STATUS_INVALID_ARGUMENT;
    }
    const int fd = open(path, O_RDONLY);
    if (fd < 0) return (int32_t)VP_STATUS_BACKEND_UNAVAILABLE;
    struct stat st;
    uint8_t header[40];
    if (fstat(fd, &st) != 0 || st.st_size < (off_t)sizeof(header) ||
        pread(fd, header, sizeof(header), 0) != (ssize_t)sizeof(header)) {
        close(fd);
        return (int32_t)VP_STATUS_INVALID_ARGUMENT;
    }
    if (memcmp(header, "dyld_v1 ", 8u) != 0 ||
        (!memchr(header + 8u, 'a', 8u) || memcmp(header + 8u, " arm64", 6u) != 0)) {
        close(fd);
        return (int32_t)VP_STATUS_INVALID_ARGUMENT;
    }
    uint32_t mappings_offset;
    uint32_t mappings_count;
    memcpy(&mappings_offset, header + 16u, sizeof(mappings_offset));
    memcpy(&mappings_count, header + 20u, sizeof(mappings_count));
    const uint64_t file_size = (uint64_t)st.st_size;
    if (mappings_count == 0 || mappings_count > 64u || mappings_offset > file_size ||
        (uint64_t)mappings_count * sizeof(NyxDyldCacheMapping) > file_size - mappings_offset) {
        close(fd);
        return (int32_t)VP_STATUS_INVALID_ARGUMENT;
    }
    NyxDyldCacheMapping mappings[64];
    const size_t table_size = (size_t)mappings_count * sizeof(NyxDyldCacheMapping);
    if (pread(fd, mappings, table_size, (off_t)mappings_offset) != (ssize_t)table_size) {
        close(fd);
        return (int32_t)VP_STATUS_EXECUTION_FAULT;
    }
    uint64_t total = 0;
    const VPMachineConfig *config = vp_runtime_config(vm->runtime);
    if (!config) { close(fd); return (int32_t)VP_STATUS_INVALID_STATE; }
    for (uint32_t i = 0; i < mappings_count; i++) {
        const NyxDyldCacheMapping *mapping = &mappings[i];
        if (!mapping->size || (mapping->address & (VP_GUEST_PAGE_SIZE - 1u)) != 0 ||
            (mapping->size & (VP_GUEST_PAGE_SIZE - 1u)) != 0 ||
            (mapping->file_offset & (VP_GUEST_PAGE_SIZE - 1u)) != 0 ||
            mapping->file_offset > file_size || mapping->size > file_size - mapping->file_offset ||
            mapping->size > config->guest_physical_memory_size ||
            mapping->address > config->guest_physical_memory_size - mapping->size ||
            mapping->size > UINT64_MAX - total) {
            close(fd);
            return (int32_t)VP_STATUS_INVALID_ARGUMENT;
        }
        for (uint32_t prior = 0; prior < i; prior++) {
            const NyxDyldCacheMapping *other = &mappings[prior];
            if (mapping->address < other->address + other->size &&
                other->address < mapping->address + mapping->size) {
                close(fd);
                return (int32_t)VP_STATUS_INVALID_ARGUMENT;
            }
        }
        total += mapping->size;
    }
    vm->dyld_cache_fd = fd;
    vm->dyld_cache_size = file_size;
    for (uint32_t i = 0; i < mappings_count; i++) {
        const NyxDyldCacheMapping *mapping = &mappings[i];
        const VPStatus status = vp_runtime_map_readonly_backing(
            vm->runtime, mapping->address, mapping->size, mapping->file_offset,
            nyx_dyld_cache_read, vm
        );
        if (status != VP_STATUS_OK) {
            close(vm->dyld_cache_fd);
            vm->dyld_cache_fd = -1;
            vm->dyld_cache_size = 0;
            return (int32_t)status;
        }
    }
    *mapping_count = mappings_count;
    *mapped_bytes = total;
    nyx_emit(vm, "[NYXDYLD] shared cache demand-mapped\n");
    return (int32_t)VP_STATUS_OK;
}

int32_t nyx_vm_load_macho(
    NyxVM *vm, const void *bytes, size_t length, uint64_t slide,
    uint64_t *entry_address, uint32_t *dylib_count
) {
    if (!vm || !bytes || !entry_address || !dylib_count) return (int32_t)VP_STATUS_INVALID_ARGUMENT;
    VPMachOImageInfo info;
    const VPStatus status = vp_runtime_load_macho(vm->runtime, bytes, length, slide, &info);
    if (status == VP_STATUS_OK) {
        *entry_address = info.entry_address;
        *dylib_count = info.dylib_count;
        if (info.file_type == 7u) {
            vm->dyld_entry = info.entry_address;
            nyx_emit(vm, "[NYXDYLD] standalone dyld staged\n");
        } else {
            vp_ksurface_set_process_name(vm->surface, "launchd");
            (void)vp_ksurface_set_process_path(vm->surface, "/sbin/launchd");
            (void)vp_ksurface_grant_entitlement(vm->surface, "com.nyxphone.virtual-signing");
            vm->launchd_entry = info.entry_address;
            nyx_emit(vm, "[NYXLAUNCHD] user Mach-O staged\n");
        }
    }
    return (int32_t)status;
}

int32_t nyx_vm_prepare_launchd(NyxVM *vm, uint64_t *stack_pointer) {
    if (!vm || !stack_pointer || !vm->dyld_entry || !vm->launchd_entry || vm->dyld_cache_fd < 0) {
        return (int32_t)VP_STATUS_INVALID_STATE;
    }
    VPDarwinProcessBootstrap bootstrap;
    const VPStatus status = vp_runtime_prepare_darwin_process(
        vm->runtime, vm->dyld_entry, UINT64_C(0x7F0000000), "/sbin/launchd", &bootstrap
    );
    if (status == VP_STATUS_OK) {
        *stack_pointer = bootstrap.stack_pointer;
        nyx_emit(vm, "[NYXLAUNCHD] dyld entry and initial stack ready\n");
    }
    return (int32_t)status;
}

int32_t nyx_vm_start_launchd(NyxVM *vm) {
    if (!vm) return (int32_t)VP_STATUS_INVALID_ARGUMENT;
    uint64_t stack_pointer = 0;
    const int32_t status = nyx_vm_prepare_launchd(vm, &stack_pointer);
    if (status != (int32_t)VP_STATUS_OK) return status;
    vp_runtime_set_instruction_budget(vm->runtime, UINT64_C(500000));
    return (int32_t)vp_runtime_boot(vm->runtime);
}

int32_t nyx_vm_load_kernel_bytes(
    NyxVM *vm,
    const void *bytes,
    size_t length,
    uint64_t load_address,
    uint64_t entry_address
) {
    if (!vm || !bytes || length == 0) return (int32_t)VP_STATUS_INVALID_ARGUMENT;
    VPStatus status = vp_runtime_memory_write(vm->runtime, load_address, bytes, length);
    if (status != VP_STATUS_OK) return (int32_t)status;
    status = vp_runtime_set_boot_vector(vm->runtime, entry_address);
    if (status == VP_STATUS_OK) nyx_emit(vm, "[NYXRT] Nyxian loaded\n");
    return (int32_t)status;
}

int32_t nyx_vm_start(NyxVM *vm) {
    if (!vm) return (int32_t)VP_STATUS_INVALID_ARGUMENT;
    return (int32_t)vp_runtime_boot(vm->runtime);
}

int32_t nyx_vm_stop(NyxVM *vm) {
    if (!vm) return (int32_t)VP_STATUS_INVALID_ARGUMENT;
    return (int32_t)vp_runtime_stop(vm->runtime);
}

uint32_t nyx_vm_state(const NyxVM *vm) {
    return vm && vm->runtime ? (uint32_t)vp_runtime_state(vm->runtime) : (uint32_t)VP_RUNTIME_FAILED;
}

uint64_t nyx_vm_instructions_retired(const NyxVM *vm) {
    return vm && vm->runtime ? vp_runtime_instructions_retired(vm->runtime) : 0;
}

typedef struct {
    char *bytes;
    size_t capacity;
    size_t length;
} NyxCaptureBuffer;

static void nyx_capture_log(const uint8_t *bytes, size_t length, void *context) {
    NyxCaptureBuffer *capture = (NyxCaptureBuffer *)context;
    if (!capture || !capture->bytes || capture->capacity == 0) return;
    size_t available = capture->capacity - 1u - capture->length;
    if (length > available) length = available;
    if (length) memcpy(capture->bytes + capture->length, bytes, length);
    capture->length += length;
    capture->bytes[capture->length] = 0;
}

int32_t nyx_vm_copy_framebuffer(
    NyxVM *vm, void *frame_buffer, size_t frame_capacity, NyxFramebufferInfo *frame_info
) {
    if (!vm || !frame_buffer || !frame_info) return (int32_t)VP_STATUS_INVALID_ARGUMENT;
    VPFramebufferInfo core_info = {0};
    const VPStatus status = vp_runtime_copy_framebuffer(vm->runtime, frame_buffer, frame_capacity, &core_info);
    if (status == VP_STATUS_OK) {
        frame_info->width = core_info.width;
        frame_info->height = core_info.height;
        frame_info->stride = core_info.stride;
        frame_info->pixel_format = core_info.pixel_format;
        frame_info->byte_length = core_info.byte_length;
    }
    return (int32_t)status;
}

int32_t nyx_vm_touch(NyxVM *vm, const NyxTouchEvent *event) {
    if (!vm || !event) return (int32_t)VP_STATUS_INVALID_ARGUMENT;
    const VPTouchEvent core_event = {event->id, event->x, event->y, event->pressure, event->phase};
    VPStatus status = vp_runtime_enqueue_touch(vm->runtime, &core_event);
    if (status != VP_STATUS_OK) return (int32_t)status;
    status = vp_runtime_signal_event(vm->runtime);
    return (int32_t)status;
}

int32_t nyx_vm_touch_capture_frame(
    NyxVM *vm, const NyxTouchEvent *event,
    void *frame_buffer, size_t frame_capacity, NyxFramebufferInfo *frame_info
) {
    int32_t status = nyx_vm_touch(vm, event);
    if (status == (int32_t)VP_STATUS_OK) status = nyx_vm_start(vm);
    if (status == (int32_t)VP_STATUS_GUEST_WAITING) status = (int32_t)VP_STATUS_OK;
    if (status == (int32_t)VP_STATUS_OK) {
        status = nyx_vm_copy_framebuffer(vm, frame_buffer, frame_capacity, frame_info);
    }
    return status;
}

static int32_t nyx_vm_boot_kernel_device_internal(
    const void *bytes,
    size_t length,
    uint64_t load_address,
    uint64_t entry_address,
    char *log_buffer,
    size_t log_capacity,
    size_t *log_length,
    void *frame_buffer,
    size_t frame_capacity,
    NyxFramebufferInfo *frame_info,
    const char *disk_path, uint64_t disk_size, NyxVM **vm_out
) {
    if (!bytes || length == 0 || !log_buffer || log_capacity == 0 || !vm_out) {
        return (int32_t)VP_STATUS_INVALID_ARGUMENT;
    }
    *vm_out = NULL;
    NyxVMConfig config = {6, UINT64_C(32) * 1024u * 1024u * 1024u, 1290, 2796, 460, 3.0};
    NyxVM *vm = nyx_vm_create(&config);
    if (!vm) return (int32_t)VP_STATUS_OUT_OF_MEMORY;
    if (disk_path) {
        const int32_t mount_status = nyx_vm_mount_disk(vm, disk_path, disk_size);
        if (mount_status != (int32_t)VP_STATUS_OK) {
            nyx_vm_destroy(vm);
            return mount_status;
        }
    }
    NyxCaptureBuffer capture = {log_buffer, log_capacity, 0};
    log_buffer[0] = 0;
    nyx_vm_set_log_callback(vm, nyx_capture_log, &capture);
    int32_t status = nyx_vm_load_kernel_bytes(vm, bytes, length, load_address, entry_address);
    if (status == (int32_t)VP_STATUS_OK) status = nyx_vm_start(vm);
    if (status == (int32_t)VP_STATUS_GUEST_WAITING) status = (int32_t)VP_STATUS_OK;
    if (status == (int32_t)VP_STATUS_OK && frame_buffer && frame_info) {
        status = nyx_vm_copy_framebuffer(vm, frame_buffer, frame_capacity, frame_info);
    }
    if (log_length) *log_length = capture.length;
    if (status == (int32_t)VP_STATUS_OK) {
        nyx_vm_set_log_callback(vm, NULL, NULL);
        *vm_out = vm;
    }
    else nyx_vm_destroy(vm);
    return status;
}

int32_t nyx_vm_boot_kernel_device(
    const void *bytes, size_t length, uint64_t load_address, uint64_t entry_address,
    char *log_buffer, size_t log_capacity, size_t *log_length,
    void *frame_buffer, size_t frame_capacity, NyxFramebufferInfo *frame_info, NyxVM **vm_out
) {
    return nyx_vm_boot_kernel_device_internal(
        bytes, length, load_address, entry_address, log_buffer, log_capacity, log_length,
        frame_buffer, frame_capacity, frame_info, NULL, 0, vm_out
    );
}

int32_t nyx_vm_boot_kernel_device_storage(
    const void *bytes, size_t length, uint64_t load_address, uint64_t entry_address,
    const char *disk_path, uint64_t disk_size,
    char *log_buffer, size_t log_capacity, size_t *log_length,
    void *frame_buffer, size_t frame_capacity, NyxFramebufferInfo *frame_info, NyxVM **vm_out
) {
    if (!disk_path) return (int32_t)VP_STATUS_INVALID_ARGUMENT;
    return nyx_vm_boot_kernel_device_internal(
        bytes, length, load_address, entry_address, log_buffer, log_capacity, log_length,
        frame_buffer, frame_capacity, frame_info, disk_path, disk_size, vm_out
    );
}

int32_t nyx_vm_boot_kernel_capture_frame(
    const void *bytes, size_t length, uint64_t load_address, uint64_t entry_address,
    char *log_buffer, size_t log_capacity, size_t *log_length,
    void *frame_buffer, size_t frame_capacity, NyxFramebufferInfo *frame_info
) {
    NyxVM *vm = NULL;
    const int32_t status = nyx_vm_boot_kernel_device(
        bytes, length, load_address, entry_address, log_buffer, log_capacity, log_length,
        frame_buffer, frame_capacity, frame_info, &vm
    );
    nyx_vm_destroy(vm);
    return status;
}

int32_t nyx_vm_boot_kernel_capture(
    const void *bytes, size_t length, uint64_t load_address, uint64_t entry_address,
    char *log_buffer, size_t log_capacity, size_t *log_length
) {
    return nyx_vm_boot_kernel_capture_frame(
        bytes, length, load_address, entry_address, log_buffer, log_capacity, log_length, NULL, 0, NULL
    );
}
