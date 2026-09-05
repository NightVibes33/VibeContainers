#ifndef VPHONE_RUNTIME_CORE_H
#define VPHONE_RUNTIME_CORE_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define VP_GUEST_PAGE_SHIFT 14u
#define VP_GUEST_PAGE_SIZE  (1u << VP_GUEST_PAGE_SHIFT)
#define VP_RUNTIME_ABI_VERSION 20u
#define VP_DEFAULT_INSTRUCTION_BUDGET UINT64_C(1000000)

typedef enum {
    VP_STATUS_OK = 0,
    VP_STATUS_INVALID_ARGUMENT = 1,
    VP_STATUS_OUT_OF_MEMORY = 2,
    VP_STATUS_ADDRESS_OUT_OF_RANGE = 3,
    VP_STATUS_BACKEND_UNAVAILABLE = 4,
    VP_STATUS_INVALID_STATE = 5,
    VP_STATUS_EXECUTION_FAULT = 6,
    VP_STATUS_BUDGET_EXHAUSTED = 7,
    VP_STATUS_GUEST_WAITING = 8,
} VPStatus;

typedef enum {
    VP_RUNTIME_CREATED = 0,
    VP_RUNTIME_READY = 1,
    VP_RUNTIME_RUNNING = 2,
    VP_RUNTIME_STOPPED = 3,
    VP_RUNTIME_FAILED = 4,
    VP_RUNTIME_WAITING = 5,
    VP_RUNTIME_PAUSED = 6,
} VPRuntimeState;

typedef struct {
    uint32_t cpu_count;
    uint64_t guest_physical_memory_size;
    uint32_t screen_width;
    uint32_t screen_height;
    uint32_t pixels_per_inch;
    double screen_scale;
} VPMachineConfig;

typedef struct VPRuntime VPRuntime;

typedef struct {
    uint64_t guest_address;
    uint32_t width;
    uint32_t height;
    uint32_t stride;
    uint32_t pixel_format;
    uint64_t byte_length;
} VPFramebufferInfo;

typedef struct {
    uint32_t id;
    float x;
    float y;
    float pressure;
    uint32_t phase;
} VPTouchEvent;

typedef void (*VPSerialCallback)(const uint8_t *bytes, size_t length, void *context);
typedef VPStatus (*VPBlockReadHandler)(uint64_t offset, void *dst, size_t length, void *context);
typedef VPStatus (*VPBlockWriteHandler)(uint64_t offset, const void *src, size_t length, void *context);
typedef VPStatus (*VPBlockFlushHandler)(void *context);
typedef VPStatus (*VPReadOnlyBackingHandler)(uint64_t offset, void *dst, size_t length, void *context);
typedef VPStatus (*VPNetworkGetHandler)(
    const char *url, uint8_t *response, size_t capacity, size_t *response_length, void *context
);

typedef VPStatus (*VPSyscallHandler)(
    VPRuntime *runtime,
    uint64_t number,
    const uint64_t args[8],
    uint64_t *result,
    void *context
);

/* One Apple boot artifact and the guest-physical address where it is staged. */
typedef struct {
    const void *bytes;
    size_t length;
    uint64_t guest_address;
} VPBootImage;

/*
 * Physical layout for the vphone-style Apple boot chain. Images may be omitted
 * by setting bytes=NULL and length=0, but the selected entry image must exist.
 * This API only stages user-supplied Apple artifacts; it ships no Apple bytes.
 */
typedef struct {
    VPBootImage iboot;
    VPBootImage kernelcache;
    VPBootImage device_tree;
    VPBootImage trust_cache;
    VPBootImage ramdisk;
    uint64_t entry_address;
} VPBootImageLayout;

uint32_t vp_runtime_abi_version(void);
VPRuntime *vp_runtime_create(const VPMachineConfig *config);
void vp_runtime_destroy(VPRuntime *runtime);
VPRuntimeState vp_runtime_state(const VPRuntime *runtime);
const VPMachineConfig *vp_runtime_config(const VPRuntime *runtime);
void vp_runtime_set_serial_callback(VPRuntime *runtime, VPSerialCallback callback, void *context);
void vp_runtime_set_syscall_handler(VPRuntime *runtime, VPSyscallHandler handler, void *context);
void vp_runtime_set_block_handlers(
    VPRuntime *runtime, VPBlockReadHandler read_handler, VPBlockWriteHandler write_handler,
    VPBlockFlushHandler flush_handler, void *context
);
void vp_runtime_set_network_handler(
    VPRuntime *runtime, VPNetworkGetHandler get_handler, void *context
);
VPStatus vp_runtime_dispatch_syscall(
    VPRuntime *runtime,
    uint64_t number,
    const uint64_t args[8],
    uint64_t *result
);

/*
 * Sparse guest-physical memory. The runtime presents the full guest address
 * range without allocating the full iPhone RAM size in the host process.
 * Unwritten pages read as zero and are committed only on first write.
 */
VPStatus vp_runtime_map_readonly_backing(
    VPRuntime *runtime, uint64_t guest_address, uint64_t length, uint64_t backing_offset,
    VPReadOnlyBackingHandler handler, void *context
);
VPStatus vp_runtime_memory_read(VPRuntime *runtime, uint64_t guest_address, void *dst, size_t length);
VPStatus vp_runtime_memory_write(VPRuntime *runtime, uint64_t guest_address, const void *src, size_t length);
VPStatus vp_runtime_console_write(VPRuntime *runtime, uint64_t guest_address, size_t length);
void vp_runtime_host_log(VPRuntime *runtime, const char *message);
VPStatus vp_runtime_publish_framebuffer(
    VPRuntime *runtime, uint64_t guest_address, uint32_t width, uint32_t height, uint32_t stride
);
VPStatus vp_runtime_copy_framebuffer(
    VPRuntime *runtime, void *dst, size_t capacity, VPFramebufferInfo *info
);
VPStatus vp_runtime_enqueue_touch(VPRuntime *runtime, const VPTouchEvent *event);
VPStatus vp_runtime_dequeue_touch(VPRuntime *runtime, VPTouchEvent *event);
VPStatus vp_runtime_block_read(VPRuntime *runtime, uint64_t guest_address, uint64_t offset, size_t length);
VPStatus vp_runtime_block_write(VPRuntime *runtime, uint64_t guest_address, uint64_t offset, size_t length);
VPStatus vp_runtime_block_flush(VPRuntime *runtime);
VPStatus vp_runtime_network_https_get(
    VPRuntime *runtime, uint64_t url_address, size_t url_length,
    uint64_t response_address, size_t response_capacity, size_t *response_length
);
uint64_t vp_runtime_committed_bytes(const VPRuntime *runtime);
uint64_t vp_runtime_committed_pages(const VPRuntime *runtime);

typedef struct {
    uint64_t entry_address;
    uint64_t preferred_load_address;
    uint64_t mapped_byte_count;
    uint64_t code_signature_offset;
    uint64_t code_signature_size;
    uint32_t segment_count;
    uint32_t dylib_count;
    uint32_t has_dylinker;
    uint32_t file_type;
    char dylinker_path[256];
} VPMachOImageInfo;

/*
 * Validate and map a user-supplied arm64 MH_EXECUTE Mach-O into guest memory.
 * LC_SEGMENT_64 mappings, LC_MAIN, LC_LOAD_DYLINKER, LC_LOAD_DYLIB and
 * LC_CODE_SIGNATURE are parsed with overflow/bounds checks. Apple binaries
 * are never bundled; callers import them from their own IPSW/root filesystem.
 */
VPStatus vp_runtime_load_macho(
    VPRuntime *runtime, const void *bytes, size_t length, uint64_t slide, VPMachOImageInfo *info
);

/*
 * Atomically validates and stages an Apple guest boot set into sparse physical
 * memory, then selects entry_address as the next reset vector. This is the
 * native bridge used by the iOS host before the CPU executor begins.
 */
typedef struct {
    uint64_t stack_pointer;
    uint64_t argv_address;
    uint64_t envp_address;
    uint64_t apple_address;
    uint32_t argc;
} VPDarwinProcessBootstrap;

VPStatus vp_runtime_prepare_darwin_process(
    VPRuntime *runtime, uint64_t entry_address, uint64_t stack_top,
    const char *executable_path, VPDarwinProcessBootstrap *bootstrap
);
VPStatus vp_runtime_stage_boot_images(VPRuntime *runtime, const VPBootImageLayout *layout);

/* Custom interpreter execution configuration. */
VPStatus vp_runtime_set_boot_vector(VPRuntime *runtime, uint64_t guest_address);
void vp_runtime_set_instruction_budget(VPRuntime *runtime, uint64_t budget);
uint64_t vp_runtime_boot_vector(const VPRuntime *runtime);
uint64_t vp_runtime_instructions_retired(const VPRuntime *runtime);

/*
 * Runs or resumes guest AArch64 directly through VPhoneAArch64. CPU state is
 * persistent across instruction-budget yields and WFI/WFE waits. No generic
 * emulator process, companion computer, remote JIT service or macOS
 * Virtualization.framework is required.
 */
VPStatus vp_runtime_boot(VPRuntime *runtime);

/* Wake a guest stopped in WFI/WFE; the next vp_runtime_boot() resumes at its saved PC. */
VPStatus vp_runtime_signal_event(VPRuntime *runtime);
VPStatus vp_runtime_stop(VPRuntime *runtime);

#ifdef __cplusplus
}
#endif

#endif
