#ifndef NYX_RUNTIME_H
#define NYX_RUNTIME_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define NYX_RUNTIME_ABI_VERSION 14u

typedef struct NyxVM NyxVM;

typedef struct {
    uint32_t cpu_count;
    uint64_t guest_physical_memory_size;
    uint32_t screen_width;
    uint32_t screen_height;
    uint32_t pixels_per_inch;
    double screen_scale;
} NyxVMConfig;

typedef struct {
    uint32_t width;
    uint32_t height;
    uint32_t stride;
    uint32_t pixel_format;
    uint64_t byte_length;
} NyxFramebufferInfo;

typedef struct {
    uint32_t id;
    float x;
    float y;
    float pressure;
    uint32_t phase;
} NyxTouchEvent;

typedef void (*NyxLogCallback)(const uint8_t *bytes, size_t length, void *context);

const char *nyx_runtime_version(void);
uint32_t nyx_runtime_abi_version(void);
NyxVM *nyx_vm_create(const NyxVMConfig *config);
void nyx_vm_destroy(NyxVM *vm);
int32_t nyx_vm_mount_disk(NyxVM *vm, const char *path, uint64_t disk_size);
void nyx_vm_set_log_callback(NyxVM *vm, NyxLogCallback callback, void *context);
int32_t nyx_vm_copy_diagnostics(NyxVM *vm, char *buffer, size_t capacity, size_t *length);
int32_t nyx_vm_map_dyld_cache(
    NyxVM *vm, const char *path, uint32_t *mapping_count, uint64_t *mapped_bytes
);
int32_t nyx_vm_load_macho(
    NyxVM *vm, const void *bytes, size_t length, uint64_t slide,
    uint64_t *entry_address, uint32_t *dylib_count
);
int32_t nyx_vm_prepare_launchd(NyxVM *vm, uint64_t *stack_pointer);
int32_t nyx_vm_start_launchd(NyxVM *vm);
int32_t nyx_vm_load_kernel_bytes(
    NyxVM *vm,
    const void *bytes,
    size_t length,
    uint64_t load_address,
    uint64_t entry_address
);
int32_t nyx_vm_start(NyxVM *vm);
int32_t nyx_vm_stop(NyxVM *vm);
uint32_t nyx_vm_state(const NyxVM *vm);
uint64_t nyx_vm_instructions_retired(const NyxVM *vm);
int32_t nyx_vm_copy_framebuffer(
    NyxVM *vm, void *frame_buffer, size_t frame_capacity, NyxFramebufferInfo *frame_info
);
int32_t nyx_vm_touch(NyxVM *vm, const NyxTouchEvent *event);
int32_t nyx_vm_touch_capture_frame(
    NyxVM *vm, const NyxTouchEvent *event,
    void *frame_buffer, size_t frame_capacity, NyxFramebufferInfo *frame_info
);
int32_t nyx_vm_boot_kernel_capture(
    const void *bytes,
    size_t length,
    uint64_t load_address,
    uint64_t entry_address,
    char *log_buffer,
    size_t log_capacity,
    size_t *log_length
);

int32_t nyx_vm_boot_kernel_device(
    const void *bytes, size_t length, uint64_t load_address, uint64_t entry_address,
    char *log_buffer, size_t log_capacity, size_t *log_length,
    void *frame_buffer, size_t frame_capacity, NyxFramebufferInfo *frame_info,
    NyxVM **vm_out
);
int32_t nyx_vm_boot_kernel_device_storage(
    const void *bytes, size_t length, uint64_t load_address, uint64_t entry_address,
    const char *disk_path, uint64_t disk_size,
    char *log_buffer, size_t log_capacity, size_t *log_length,
    void *frame_buffer, size_t frame_capacity, NyxFramebufferInfo *frame_info, NyxVM **vm_out
);
int32_t nyx_vm_boot_kernel_capture_frame(
    const void *bytes, size_t length, uint64_t load_address, uint64_t entry_address,
    char *log_buffer, size_t log_capacity, size_t *log_length,
    void *frame_buffer, size_t frame_capacity, NyxFramebufferInfo *frame_info
);

#ifdef __cplusplus
}
#endif

#endif
