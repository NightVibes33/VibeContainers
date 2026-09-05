#include "VPhoneRuntimeCore.h"
#include "VPhoneAArch64.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define VP_PAGE_BUCKETS 4096u

#define VP_MH_MAGIC_64 UINT32_C(0xfeedfacf)
#define VP_CPU_TYPE_ARM64 UINT32_C(0x0100000c)
#define VP_MH_EXECUTE 2u
#define VP_MH_DYLINKER 7u
#define VP_LC_SEGMENT_64 UINT32_C(0x19)
#define VP_LC_LOAD_DYLIB UINT32_C(0x0c)
#define VP_LC_LOAD_DYLINKER UINT32_C(0x0e)
#define VP_LC_CODE_SIGNATURE UINT32_C(0x1d)
#define VP_LC_MAIN UINT32_C(0x80000028)
#define VP_LC_UNIXTHREAD UINT32_C(0x05)
#define VP_MACHO_MAX_COMMANDS 16384u
#define VP_MACHO_MAX_SEGMENTS 256u
#define VP_MAX_READONLY_MAPPINGS 64u

typedef struct {
    uint64_t guest_address;
    uint64_t length;
    uint64_t backing_offset;
    VPReadOnlyBackingHandler handler;
    void *context;
} VPReadOnlyMapping;

typedef struct VPPage {
    uint64_t index;
    struct VPPage *next;
    uint8_t bytes[VP_GUEST_PAGE_SIZE];
} VPPage;

struct VPRuntime {
    VPMachineConfig config;
    VPRuntimeState state;
    VPPage *buckets[VP_PAGE_BUCKETS];
    uint64_t committed_pages;
    VPReadOnlyMapping readonly_mappings[VP_MAX_READONLY_MAPPINGS];
    uint32_t readonly_mapping_count;
    VPSerialCallback serial_callback;
    void *serial_context;
    VPSyscallHandler syscall_handler;
    void *syscall_context;
    VPBlockReadHandler block_read_handler;
    VPBlockWriteHandler block_write_handler;
    VPBlockFlushHandler block_flush_handler;
    void *block_context;
    VPNetworkGetHandler network_get_handler;
    void *network_context;
    uint64_t boot_vector;
    uint64_t initial_stack_pointer;
    int initial_userspace;
    uint64_t instruction_budget;
    uint64_t instructions_retired;
    VPAArch64CPU cpu;
    int cpu_initialized;
    int stop_requested;
    VPFramebufferInfo framebuffer;
    int framebuffer_ready;
    VPTouchEvent touch_queue[16];
    uint32_t touch_head;
    uint32_t touch_count;
};

static uint64_t vp_page_index(uint64_t address) {
    return address >> VP_GUEST_PAGE_SHIFT;
}

static uint32_t vp_bucket(uint64_t page_index) {
    page_index ^= page_index >> 33;
    page_index *= UINT64_C(0xff51afd7ed558ccd);
    page_index ^= page_index >> 33;
    return (uint32_t)(page_index & (VP_PAGE_BUCKETS - 1u));
}

static int vp_range_valid(const VPRuntime *runtime, uint64_t address, size_t length) {
    if (!runtime) return 0;
    if (length == 0) return address <= runtime->config.guest_physical_memory_size;
    if (address >= runtime->config.guest_physical_memory_size) return 0;
    if ((uint64_t)length > runtime->config.guest_physical_memory_size - address) return 0;
    return 1;
}

static VPPage *vp_find_page(VPRuntime *runtime, uint64_t index, int create) {
    const uint32_t bucket = vp_bucket(index);
    VPPage *page = runtime->buckets[bucket];
    while (page) {
        if (page->index == index) return page;
        page = page->next;
    }
    if (!create) return NULL;

    page = (VPPage *)calloc(1, sizeof(VPPage));
    if (!page) return NULL;
    page->index = index;
    page->next = runtime->buckets[bucket];
    runtime->buckets[bucket] = page;
    runtime->committed_pages++;
    return page;
}

static void vp_emit(VPRuntime *runtime, const char *message) {
    if (!runtime || !runtime->serial_callback || !message) return;
    runtime->serial_callback((const uint8_t *)message, strlen(message), runtime->serial_context);
}

static VPStatus vp_execution_failure(VPRuntime *runtime, const char *kind, const VPAArch64CPU *cpu, uint32_t insn) {
    char message[768];
    (void)snprintf(
        message, sizeof(message),
        "NYX_CPU_FAULT: kind=%s pc=0x%llx insn=0x%08x retired=%llu el=%u "
        "sp=0x%llx nzcv=0x%llx x0=0x%llx x1=0x%llx x2=0x%llx x3=0x%llx "
        "x4=0x%llx x5=0x%llx x6=0x%llx x7=0x%llx x16=0x%llx x29=0x%llx x30=0x%llx\n",
        kind, (unsigned long long)(cpu ? cpu->pc : 0), insn,
        (unsigned long long)(cpu ? cpu->instructions_retired : 0), cpu ? cpu->current_el : 0,
        (unsigned long long)(cpu ? cpu->sp : 0), (unsigned long long)(cpu ? cpu->sys.nzcv : 0),
        (unsigned long long)(cpu ? cpu->x[0] : 0), (unsigned long long)(cpu ? cpu->x[1] : 0),
        (unsigned long long)(cpu ? cpu->x[2] : 0), (unsigned long long)(cpu ? cpu->x[3] : 0),
        (unsigned long long)(cpu ? cpu->x[4] : 0), (unsigned long long)(cpu ? cpu->x[5] : 0),
        (unsigned long long)(cpu ? cpu->x[6] : 0), (unsigned long long)(cpu ? cpu->x[7] : 0),
        (unsigned long long)(cpu ? cpu->x[16] : 0), (unsigned long long)(cpu ? cpu->x[29] : 0),
        (unsigned long long)(cpu ? cpu->x[30] : 0)
    );
    vp_emit(runtime, message);
    runtime->state = VP_RUNTIME_FAILED;
    return VP_STATUS_EXECUTION_FAULT;
}

static void vp_runtime_invalidate_cpu(VPRuntime *runtime) {
    if (!runtime) return;
    memset(&runtime->cpu, 0, sizeof(runtime->cpu));
    runtime->cpu_initialized = 0;
    runtime->instructions_retired = 0;
}

uint32_t vp_runtime_abi_version(void) {
    return VP_RUNTIME_ABI_VERSION;
}

VPRuntime *vp_runtime_create(const VPMachineConfig *config) {
    if (!config || config->cpu_count == 0 || config->guest_physical_memory_size == 0) return NULL;
    VPRuntime *runtime = (VPRuntime *)calloc(1, sizeof(VPRuntime));
    if (!runtime) return NULL;
    runtime->config = *config;
    runtime->state = VP_RUNTIME_READY;
    runtime->instruction_budget = VP_DEFAULT_INSTRUCTION_BUDGET;
    return runtime;
}

void vp_runtime_destroy(VPRuntime *runtime) {
    if (!runtime) return;
    for (uint32_t i = 0; i < VP_PAGE_BUCKETS; i++) {
        VPPage *page = runtime->buckets[i];
        while (page) {
            VPPage *next = page->next;
            free(page);
            page = next;
        }
    }
    memset(runtime, 0, sizeof(*runtime));
    free(runtime);
}

VPRuntimeState vp_runtime_state(const VPRuntime *runtime) {
    return runtime ? runtime->state : VP_RUNTIME_FAILED;
}

const VPMachineConfig *vp_runtime_config(const VPRuntime *runtime) {
    return runtime ? &runtime->config : NULL;
}

void vp_runtime_set_serial_callback(VPRuntime *runtime, VPSerialCallback callback, void *context) {
    if (!runtime) return;
    runtime->serial_callback = callback;
    runtime->serial_context = context;
}

void vp_runtime_set_syscall_handler(VPRuntime *runtime, VPSyscallHandler handler, void *context) {
    if (!runtime || runtime->state == VP_RUNTIME_RUNNING) return;
    runtime->syscall_handler = handler;
    runtime->syscall_context = context;
}

void vp_runtime_set_block_handlers(
    VPRuntime *runtime, VPBlockReadHandler read_handler, VPBlockWriteHandler write_handler,
    VPBlockFlushHandler flush_handler, void *context
) {
    if (!runtime || runtime->state == VP_RUNTIME_RUNNING) return;
    runtime->block_read_handler = read_handler;
    runtime->block_write_handler = write_handler;
    runtime->block_flush_handler = flush_handler;
    runtime->block_context = context;
}

void vp_runtime_set_network_handler(
    VPRuntime *runtime, VPNetworkGetHandler get_handler, void *context
) {
    if (!runtime || runtime->state == VP_RUNTIME_RUNNING) return;
    runtime->network_get_handler = get_handler;
    runtime->network_context = context;
}

VPStatus vp_runtime_dispatch_syscall(
    VPRuntime *runtime,
    uint64_t number,
    const uint64_t args[8],
    uint64_t *result
) {
    if (!runtime || !result) return VP_STATUS_INVALID_ARGUMENT;
    if (!runtime->syscall_handler) return VP_STATUS_BACKEND_UNAVAILABLE;
    return runtime->syscall_handler(runtime, number, args, result, runtime->syscall_context);
}

static const VPReadOnlyMapping *vp_find_readonly_mapping(
    const VPRuntime *runtime, uint64_t address, uint64_t length
) {
    if (!runtime) return NULL;
    for (uint32_t i = 0; i < runtime->readonly_mapping_count; i++) {
        const VPReadOnlyMapping *mapping = &runtime->readonly_mappings[i];
        if (address >= mapping->guest_address && length <= mapping->length &&
            address - mapping->guest_address <= mapping->length - length) {
            return mapping;
        }
    }
    return NULL;
}

VPStatus vp_runtime_map_readonly_backing(
    VPRuntime *runtime, uint64_t guest_address, uint64_t length, uint64_t backing_offset,
    VPReadOnlyBackingHandler handler, void *context
) {
    if (!runtime || !handler || !length || runtime->state == VP_RUNTIME_RUNNING ||
        runtime->readonly_mapping_count >= VP_MAX_READONLY_MAPPINGS ||
        (guest_address & (VP_GUEST_PAGE_SIZE - 1u)) != 0 ||
        (length & (VP_GUEST_PAGE_SIZE - 1u)) != 0 ||
        (backing_offset & (VP_GUEST_PAGE_SIZE - 1u)) != 0 ||
        length > runtime->config.guest_physical_memory_size ||
        guest_address > runtime->config.guest_physical_memory_size - length) {
        return VP_STATUS_INVALID_ARGUMENT;
    }
    for (uint32_t i = 0; i < runtime->readonly_mapping_count; i++) {
        const VPReadOnlyMapping *existing = &runtime->readonly_mappings[i];
        if (guest_address < existing->guest_address + existing->length &&
            existing->guest_address < guest_address + length) {
            return VP_STATUS_INVALID_STATE;
        }
    }
    runtime->readonly_mappings[runtime->readonly_mapping_count++] = (VPReadOnlyMapping){
        .guest_address = guest_address, .length = length, .backing_offset = backing_offset,
        .handler = handler, .context = context,
    };
    return VP_STATUS_OK;
}

static VPStatus vp_read_readonly_backing(
    const VPRuntime *runtime, uint64_t address, void *dst, size_t length, int *found
) {
    const VPReadOnlyMapping *mapping = vp_find_readonly_mapping(runtime, address, length);
    if (!mapping) {
        if (found) *found = 0;
        return VP_STATUS_OK;
    }
    if (found) *found = 1;
    const uint64_t relative = address - mapping->guest_address;
    if (relative > UINT64_MAX - mapping->backing_offset) return VP_STATUS_ADDRESS_OUT_OF_RANGE;
    return mapping->handler(mapping->backing_offset + relative, dst, length, mapping->context);
}

static uint32_t vp_macho_u32(const uint8_t *bytes) {
    uint32_t value;
    memcpy(&value, bytes, sizeof(value));
    return value;
}

static uint64_t vp_macho_u64(const uint8_t *bytes) {
    uint64_t value;
    memcpy(&value, bytes, sizeof(value));
    return value;
}

static int vp_macho_add_u64(uint64_t a, uint64_t b, uint64_t *result) {
    if (!result || b > UINT64_MAX - a) return 0;
    *result = a + b;
    return 1;
}

VPStatus vp_runtime_load_macho(
    VPRuntime *runtime, const void *image, size_t length, uint64_t slide, VPMachOImageInfo *info
) {
    if (!runtime || !image || !info || length < 32u || runtime->state == VP_RUNTIME_RUNNING) {
        return VP_STATUS_INVALID_ARGUMENT;
    }
    const uint8_t *bytes = (const uint8_t *)image;
    const uint32_t file_type = vp_macho_u32(bytes + 12u);
    if (vp_macho_u32(bytes) != VP_MH_MAGIC_64 || vp_macho_u32(bytes + 4u) != VP_CPU_TYPE_ARM64 ||
        (file_type != VP_MH_EXECUTE && file_type != VP_MH_DYLINKER)) {
        return VP_STATUS_INVALID_ARGUMENT;
    }
    const uint32_t ncmds = vp_macho_u32(bytes + 16u);
    const uint32_t sizeofcmds = vp_macho_u32(bytes + 20u);
    if (ncmds == 0 || ncmds > VP_MACHO_MAX_COMMANDS || sizeofcmds > length - 32u) {
        return VP_STATUS_INVALID_ARGUMENT;
    }

    VPMachOImageInfo parsed;
    memset(&parsed, 0, sizeof(parsed));
    parsed.preferred_load_address = UINT64_MAX;
    parsed.file_type = file_type;
    uint64_t entry_file_offset = UINT64_MAX;
    uint64_t thread_entry_address = UINT64_MAX;
    size_t cursor = 32u;
    for (uint32_t index = 0; index < ncmds; index++) {
        if (cursor > 32u + sizeofcmds || 32u + sizeofcmds - cursor < 8u) return VP_STATUS_INVALID_ARGUMENT;
        const uint32_t command = vp_macho_u32(bytes + cursor);
        const uint32_t command_size = vp_macho_u32(bytes + cursor + 4u);
        if (command_size < 8u || command_size > 32u + sizeofcmds - cursor) return VP_STATUS_INVALID_ARGUMENT;
        if (command == VP_LC_SEGMENT_64) {
            if (command_size < 72u || parsed.segment_count >= VP_MACHO_MAX_SEGMENTS) return VP_STATUS_INVALID_ARGUMENT;
            const uint64_t vm_address = vp_macho_u64(bytes + cursor + 24u);
            const uint64_t vm_size = vp_macho_u64(bytes + cursor + 32u);
            const uint64_t file_offset = vp_macho_u64(bytes + cursor + 40u);
            const uint64_t file_size = vp_macho_u64(bytes + cursor + 48u);
            uint64_t mapped_address;
            if (file_size > vm_size || file_offset > length || file_size > length - file_offset ||
                !vp_macho_add_u64(vm_address, slide, &mapped_address) ||
                vm_size > runtime->config.guest_physical_memory_size ||
                mapped_address > runtime->config.guest_physical_memory_size - vm_size) {
                return VP_STATUS_ADDRESS_OUT_OF_RANGE;
            }
            const int is_pagezero = memcmp(bytes + cursor + 8u, "__PAGEZERO", 10u) == 0;
            if (!is_pagezero && vm_size && vm_address < parsed.preferred_load_address) {
                parsed.preferred_load_address = vm_address;
            }
            if (!is_pagezero) {
                if (vm_size > UINT64_MAX - parsed.mapped_byte_count) return VP_STATUS_ADDRESS_OUT_OF_RANGE;
                parsed.mapped_byte_count += vm_size;
            }
            parsed.segment_count++;
        } else if (command == VP_LC_MAIN) {
            if (command_size < 24u || entry_file_offset != UINT64_MAX) return VP_STATUS_INVALID_ARGUMENT;
            entry_file_offset = vp_macho_u64(bytes + cursor + 8u);
        } else if (command == VP_LC_UNIXTHREAD) {
            if (command_size < 288u || thread_entry_address != UINT64_MAX ||
                vp_macho_u32(bytes + cursor + 12u) < 68u) return VP_STATUS_INVALID_ARGUMENT;
            thread_entry_address = vp_macho_u64(bytes + cursor + 272u);
        } else if (command == VP_LC_LOAD_DYLINKER) {
            if (command_size < 12u || parsed.has_dylinker) return VP_STATUS_INVALID_ARGUMENT;
            const uint32_t path_offset = vp_macho_u32(bytes + cursor + 8u);
            if (path_offset >= command_size) return VP_STATUS_INVALID_ARGUMENT;
            const size_t capacity = command_size - path_offset;
            const char *path = (const char *)(bytes + cursor + path_offset);
            const void *terminator = memchr(path, 0, capacity);
            if (!terminator) return VP_STATUS_INVALID_ARGUMENT;
            size_t path_length = (const char *)terminator - path;
            if (path_length == 0 || path_length >= sizeof(parsed.dylinker_path)) return VP_STATUS_INVALID_ARGUMENT;
            memcpy(parsed.dylinker_path, path, path_length + 1u);
            parsed.has_dylinker = 1u;
        } else if (command == VP_LC_LOAD_DYLIB) {
            if (command_size < 24u) return VP_STATUS_INVALID_ARGUMENT;
            const uint32_t path_offset = vp_macho_u32(bytes + cursor + 8u);
            if (path_offset >= command_size || !memchr(bytes + cursor + path_offset, 0, command_size - path_offset)) {
                return VP_STATUS_INVALID_ARGUMENT;
            }
            parsed.dylib_count++;
        } else if (command == VP_LC_CODE_SIGNATURE) {
            if (command_size < 16u || parsed.code_signature_size != 0) return VP_STATUS_INVALID_ARGUMENT;
            parsed.code_signature_offset = vp_macho_u32(bytes + cursor + 8u);
            parsed.code_signature_size = vp_macho_u32(bytes + cursor + 12u);
            if (parsed.code_signature_offset > length || parsed.code_signature_size > length - parsed.code_signature_offset) {
                return VP_STATUS_INVALID_ARGUMENT;
            }
        }
        cursor += command_size;
    }
    if (cursor != 32u + sizeofcmds || parsed.segment_count == 0 || parsed.code_signature_size == 0 ||
        (file_type == VP_MH_EXECUTE && (entry_file_offset == UINT64_MAX || !parsed.has_dylinker)) ||
        (file_type == VP_MH_DYLINKER && entry_file_offset == UINT64_MAX && thread_entry_address == UINT64_MAX)) {
        return VP_STATUS_INVALID_ARGUMENT;
    }

    cursor = 32u;
    int entry_found = 0;
    static const uint8_t zero_page[4096] = {0};
    for (uint32_t index = 0; index < ncmds; index++) {
        const uint32_t command = vp_macho_u32(bytes + cursor);
        const uint32_t command_size = vp_macho_u32(bytes + cursor + 4u);
        if (command == VP_LC_SEGMENT_64) {
            const uint64_t vm_address = vp_macho_u64(bytes + cursor + 24u);
            const uint64_t vm_size = vp_macho_u64(bytes + cursor + 32u);
            const uint64_t file_offset = vp_macho_u64(bytes + cursor + 40u);
            const uint64_t file_size = vp_macho_u64(bytes + cursor + 48u);
            const uint64_t mapped_address = vm_address + slide;
            const int is_pagezero = memcmp(bytes + cursor + 8u, "__PAGEZERO", 10u) == 0;
            if (!is_pagezero && file_size) {
                VPStatus status = vp_runtime_memory_write(runtime, mapped_address, bytes + file_offset, (size_t)file_size);
                if (status != VP_STATUS_OK) return status;
            }
            uint64_t remaining = is_pagezero ? 0u : vm_size - file_size;
            uint64_t zero_address = mapped_address + file_size;
            while (remaining) {
                const size_t chunk = remaining < sizeof(zero_page) ? (size_t)remaining : sizeof(zero_page);
                VPStatus status = vp_runtime_memory_write(runtime, zero_address, zero_page, chunk);
                if (status != VP_STATUS_OK) return status;
                zero_address += chunk;
                remaining -= chunk;
            }
            if (entry_file_offset >= file_offset && entry_file_offset - file_offset < file_size) {
                parsed.entry_address = mapped_address + (entry_file_offset - file_offset);
                entry_found = 1;
            }
        }
        cursor += command_size;
    }
    if (!entry_found && thread_entry_address != UINT64_MAX &&
        vp_macho_add_u64(thread_entry_address, slide, &parsed.entry_address)) entry_found = 1;
    if (!entry_found) return VP_STATUS_INVALID_ARGUMENT;
    parsed.preferred_load_address += slide;
    *info = parsed;
    vp_emit(runtime, "[NYXMACHO] arm64 executable mapped\n");
    return VP_STATUS_OK;
}

VPStatus vp_runtime_memory_read(VPRuntime *runtime, uint64_t address, void *dst, size_t length) {
    if (!runtime || (!dst && length)) return VP_STATUS_INVALID_ARGUMENT;
    if (!vp_range_valid(runtime, address, length)) return VP_STATUS_ADDRESS_OUT_OF_RANGE;

    uint8_t *out = (uint8_t *)dst;
    size_t remaining = length;
    while (remaining) {
        const uint64_t index = vp_page_index(address);
        const size_t offset = (size_t)(address & (VP_GUEST_PAGE_SIZE - 1u));
        size_t chunk = VP_GUEST_PAGE_SIZE - offset;
        if (chunk > remaining) chunk = remaining;

        VPPage *page = vp_find_page(runtime, index, 0);
        if (page) {
            memcpy(out, page->bytes + offset, chunk);
        } else {
            int backed = 0;
            VPStatus backing_status = vp_read_readonly_backing(runtime, address, out, chunk, &backed);
            if (backing_status != VP_STATUS_OK) return backing_status;
            if (!backed) memset(out, 0, chunk);
        }

        address += chunk;
        out += chunk;
        remaining -= chunk;
    }
    return VP_STATUS_OK;
}

VPStatus vp_runtime_memory_write(VPRuntime *runtime, uint64_t address, const void *src, size_t length) {
    if (!runtime || (!src && length)) return VP_STATUS_INVALID_ARGUMENT;
    if (!vp_range_valid(runtime, address, length)) return VP_STATUS_ADDRESS_OUT_OF_RANGE;

    const uint8_t *in = (const uint8_t *)src;
    size_t remaining = length;
    while (remaining) {
        const uint64_t index = vp_page_index(address);
        const size_t offset = (size_t)(address & (VP_GUEST_PAGE_SIZE - 1u));
        size_t chunk = VP_GUEST_PAGE_SIZE - offset;
        if (chunk > remaining) chunk = remaining;

        VPPage *page = vp_find_page(runtime, index, 0);
        if (!page) {
            uint8_t initial[VP_GUEST_PAGE_SIZE];
            int backed = 0;
            const uint64_t page_address = index << VP_GUEST_PAGE_SHIFT;
            VPStatus backing_status = vp_read_readonly_backing(
                runtime, page_address, initial, sizeof(initial), &backed
            );
            if (backing_status != VP_STATUS_OK) return backing_status;
            if (!backed) memset(initial, 0, sizeof(initial));
            page = vp_find_page(runtime, index, 1);
            if (!page) return VP_STATUS_OUT_OF_MEMORY;
            memcpy(page->bytes, initial, sizeof(initial));
        }
        memcpy(page->bytes + offset, in, chunk);

        address += chunk;
        in += chunk;
        remaining -= chunk;
    }
    return VP_STATUS_OK;
}

VPStatus vp_runtime_console_write(VPRuntime *runtime, uint64_t guest_address, size_t length) {
    if (!runtime) return VP_STATUS_INVALID_ARGUMENT;
    if (!vp_range_valid(runtime, guest_address, length)) return VP_STATUS_ADDRESS_OUT_OF_RANGE;
    uint8_t buffer[256];
    size_t remaining = length;
    while (remaining) {
        size_t chunk = remaining < sizeof(buffer) ? remaining : sizeof(buffer);
        VPStatus status = vp_runtime_memory_read(runtime, guest_address, buffer, chunk);
        if (status != VP_STATUS_OK) return status;
        if (runtime->serial_callback) {
            runtime->serial_callback(buffer, chunk, runtime->serial_context);
        }
        guest_address += chunk;
        remaining -= chunk;
    }
    return VP_STATUS_OK;
}

void vp_runtime_host_log(VPRuntime *runtime, const char *message) {
    vp_emit(runtime, message);
}

VPStatus vp_runtime_publish_framebuffer(
    VPRuntime *runtime, uint64_t guest_address, uint32_t width, uint32_t height, uint32_t stride
) {
    if (!runtime || width == 0 || height == 0 || width > UINT32_MAX / 4u || stride < width * 4u) {
        return VP_STATUS_INVALID_ARGUMENT;
    }
    const uint64_t byte_length = (uint64_t)stride * height;
    if (byte_length > SIZE_MAX || !vp_range_valid(runtime, guest_address, (size_t)byte_length)) {
        return VP_STATUS_ADDRESS_OUT_OF_RANGE;
    }
    runtime->framebuffer = (VPFramebufferInfo){
        .guest_address = guest_address,
        .width = width,
        .height = height,
        .stride = stride,
        .pixel_format = 1u, /* RGBA8888 */
        .byte_length = byte_length,
    };
    const int first_frame = !runtime->framebuffer_ready;
    runtime->framebuffer_ready = 1;
    vp_emit(runtime, first_frame ? "[NYXDISPLAY] first frame\n" : "[NYXDISPLAY] frame ready\n");
    return VP_STATUS_OK;
}

VPStatus vp_runtime_copy_framebuffer(
    VPRuntime *runtime, void *dst, size_t capacity, VPFramebufferInfo *info
) {
    if (!runtime || !dst || !info || !runtime->framebuffer_ready) return VP_STATUS_INVALID_STATE;
    if (runtime->framebuffer.byte_length > capacity) return VP_STATUS_INVALID_ARGUMENT;
    VPStatus status = vp_runtime_memory_read(
        runtime, runtime->framebuffer.guest_address, dst, (size_t)runtime->framebuffer.byte_length
    );
    if (status == VP_STATUS_OK) *info = runtime->framebuffer;
    return status;
}

VPStatus vp_runtime_enqueue_touch(VPRuntime *runtime, const VPTouchEvent *event) {
    if (!runtime || !event || event->x < 0.0f || event->x > 1.0f ||
        event->y < 0.0f || event->y > 1.0f || event->pressure < 0.0f || event->phase > 2u) {
        return VP_STATUS_INVALID_ARGUMENT;
    }
    if (runtime->touch_count == 16u) {
        runtime->touch_head = (runtime->touch_head + 1u) % 16u;
        runtime->touch_count--;
    }
    const uint32_t tail = (runtime->touch_head + runtime->touch_count) % 16u;
    runtime->touch_queue[tail] = *event;
    runtime->touch_count++;
    return VP_STATUS_OK;
}

VPStatus vp_runtime_dequeue_touch(VPRuntime *runtime, VPTouchEvent *event) {
    if (!runtime || !event) return VP_STATUS_INVALID_ARGUMENT;
    if (runtime->touch_count == 0) return VP_STATUS_INVALID_STATE;
    *event = runtime->touch_queue[runtime->touch_head];
    runtime->touch_head = (runtime->touch_head + 1u) % 16u;
    runtime->touch_count--;
    return VP_STATUS_OK;
}

VPStatus vp_runtime_block_read(VPRuntime *runtime, uint64_t guest_address, uint64_t offset, size_t length) {
    if (!runtime || !runtime->block_read_handler || length > 4096u) return VP_STATUS_BACKEND_UNAVAILABLE;
    if (!vp_range_valid(runtime, guest_address, length)) return VP_STATUS_ADDRESS_OUT_OF_RANGE;
    uint8_t buffer[4096];
    VPStatus status = runtime->block_read_handler(offset, buffer, length, runtime->block_context);
    if (status != VP_STATUS_OK) return status;
    return vp_runtime_memory_write(runtime, guest_address, buffer, length);
}

VPStatus vp_runtime_block_write(VPRuntime *runtime, uint64_t guest_address, uint64_t offset, size_t length) {
    if (!runtime || !runtime->block_write_handler || length > 4096u) return VP_STATUS_BACKEND_UNAVAILABLE;
    if (!vp_range_valid(runtime, guest_address, length)) return VP_STATUS_ADDRESS_OUT_OF_RANGE;
    uint8_t buffer[4096];
    VPStatus status = vp_runtime_memory_read(runtime, guest_address, buffer, length);
    if (status != VP_STATUS_OK) return status;
    return runtime->block_write_handler(offset, buffer, length, runtime->block_context);
}

VPStatus vp_runtime_block_flush(VPRuntime *runtime) {
    if (!runtime || !runtime->block_flush_handler) return VP_STATUS_BACKEND_UNAVAILABLE;
    return runtime->block_flush_handler(runtime->block_context);
}

VPStatus vp_runtime_network_https_get(
    VPRuntime *runtime, uint64_t url_address, size_t url_length,
    uint64_t response_address, size_t response_capacity, size_t *response_length
) {
    if (!runtime || !response_length || !runtime->network_get_handler ||
        url_length == 0 || url_length > 2047u || response_capacity == 0 || response_capacity > 4096u) {
        return VP_STATUS_INVALID_ARGUMENT;
    }
    if (!vp_range_valid(runtime, url_address, url_length) ||
        !vp_range_valid(runtime, response_address, response_capacity)) {
        return VP_STATUS_ADDRESS_OUT_OF_RANGE;
    }
    char url[2048];
    uint8_t response[4096];
    VPStatus status = vp_runtime_memory_read(runtime, url_address, url, url_length);
    if (status != VP_STATUS_OK) return status;
    url[url_length] = 0;
    if (url_length < 8u || memcmp(url, "https://", 8u) != 0) return VP_STATUS_INVALID_ARGUMENT;
    size_t received = 0;
    status = runtime->network_get_handler(
        url, response, response_capacity, &received, runtime->network_context
    );
    if (status != VP_STATUS_OK) return status;
    if (received == 0 || received > response_capacity) return VP_STATUS_EXECUTION_FAULT;
    status = vp_runtime_memory_write(runtime, response_address, response, received);
    if (status == VP_STATUS_OK) *response_length = received;
    return status;
}

uint64_t vp_runtime_committed_pages(const VPRuntime *runtime) {
    return runtime ? runtime->committed_pages : 0;
}

uint64_t vp_runtime_committed_bytes(const VPRuntime *runtime) {
    return vp_runtime_committed_pages(runtime) * (uint64_t)VP_GUEST_PAGE_SIZE;
}

static int vp_boot_image_valid(const VPRuntime *runtime, const VPBootImage *image) {
    if (!image) return 0;
    if (image->length == 0) return image->bytes == NULL;
    if (!image->bytes) return 0;
    return vp_range_valid(runtime, image->guest_address, image->length);
}

static int vp_boot_image_contains(const VPBootImage *image, uint64_t address) {
    if (!image || !image->bytes || image->length == 0) return 0;
    if (address < image->guest_address) return 0;
    return address - image->guest_address < (uint64_t)image->length;
}

VPStatus vp_runtime_prepare_darwin_process(
    VPRuntime *runtime, uint64_t entry_address, uint64_t stack_top,
    const char *executable_path, VPDarwinProcessBootstrap *bootstrap
) {
    static const char environment[] = "PATH=/usr/bin:/bin:/usr/sbin:/sbin";
    static const char os_version[] = "kern.osversion=Nyxian";
    if (!runtime || !executable_path || !bootstrap || runtime->state == VP_RUNTIME_RUNNING ||
        executable_path[0] != '/' || strlen(executable_path) > 1024u ||
        !vp_range_valid(runtime, entry_address, sizeof(uint32_t)) || stack_top > runtime->config.guest_physical_memory_size ||
        stack_top < VP_GUEST_PAGE_SIZE) return VP_STATUS_INVALID_ARGUMENT;

    char executable_apple[1050];
    const int apple_length = snprintf(
        executable_apple, sizeof(executable_apple), "executable_path=%s", executable_path
    );
    if (apple_length <= 0 || (size_t)apple_length >= sizeof(executable_apple)) return VP_STATUS_INVALID_ARGUMENT;

    uint64_t cursor = stack_top;
    const char *strings[] = {executable_path, environment, executable_apple, os_version};
    uint64_t addresses[4];
    for (size_t i = 0; i < 4u; i++) {
        const size_t string_length = strlen(strings[i]) + 1u;
        if (cursor < string_length) return VP_STATUS_ADDRESS_OUT_OF_RANGE;
        cursor -= string_length;
        const VPStatus status = vp_runtime_memory_write(runtime, cursor, strings[i], string_length);
        if (status != VP_STATUS_OK) return status;
        addresses[i] = cursor;
    }
    cursor &= ~UINT64_C(15);
    const uint64_t vector_bytes = 8u * sizeof(uint64_t);
    if (cursor < vector_bytes) return VP_STATUS_ADDRESS_OUT_OF_RANGE;
    const uint64_t stack_pointer = (cursor - vector_bytes) & ~UINT64_C(15);
    const uint64_t vectors[8] = {1u, addresses[0], 0u, addresses[1], 0u, addresses[2], addresses[3], 0u};
    VPStatus status = vp_runtime_memory_write(runtime, stack_pointer, vectors, sizeof(vectors));
    if (status != VP_STATUS_OK) return status;
    status = vp_runtime_set_boot_vector(runtime, entry_address);
    if (status != VP_STATUS_OK) return status;
    runtime->initial_stack_pointer = stack_pointer;
    runtime->initial_userspace = 1;
    *bootstrap = (VPDarwinProcessBootstrap){
        .stack_pointer = stack_pointer, .argv_address = stack_pointer + sizeof(uint64_t),
        .envp_address = stack_pointer + 3u * sizeof(uint64_t),
        .apple_address = stack_pointer + 5u * sizeof(uint64_t), .argc = 1u,
    };
    vp_emit(runtime, "[NYXDARWIN] initial process stack ready\n");
    return VP_STATUS_OK;
}

static VPStatus vp_stage_one_boot_image(VPRuntime *runtime, const VPBootImage *image) {
    if (!image || image->length == 0) return VP_STATUS_OK;
    return vp_runtime_memory_write(runtime, image->guest_address, image->bytes, image->length);
}

VPStatus vp_runtime_stage_boot_images(VPRuntime *runtime, const VPBootImageLayout *layout) {
    if (!runtime || !layout) return VP_STATUS_INVALID_ARGUMENT;
    if (runtime->state == VP_RUNTIME_RUNNING) return VP_STATUS_INVALID_STATE;

    const VPBootImage *images[] = {
        &layout->iboot,
        &layout->kernelcache,
        &layout->device_tree,
        &layout->trust_cache,
        &layout->ramdisk,
    };

    int has_image = 0;
    int entry_is_staged = 0;
    for (size_t i = 0; i < sizeof(images) / sizeof(images[0]); i++) {
        if (!vp_boot_image_valid(runtime, images[i])) return VP_STATUS_ADDRESS_OUT_OF_RANGE;
        if (images[i]->length != 0) has_image = 1;
        if (vp_boot_image_contains(images[i], layout->entry_address)) entry_is_staged = 1;
    }
    if (!has_image || !entry_is_staged) return VP_STATUS_INVALID_ARGUMENT;

    for (size_t i = 0; i < sizeof(images) / sizeof(images[0]); i++) {
        const VPStatus status = vp_stage_one_boot_image(runtime, images[i]);
        if (status != VP_STATUS_OK) return status;
    }

    runtime->boot_vector = layout->entry_address;
    runtime->initial_stack_pointer = 0;
    runtime->initial_userspace = 0;
    runtime->framebuffer_ready = 0;
    memset(&runtime->framebuffer, 0, sizeof(runtime->framebuffer));
    runtime->touch_head = 0;
    runtime->touch_count = 0;
    vp_runtime_invalidate_cpu(runtime);
    runtime->state = VP_RUNTIME_READY;
    vp_emit(runtime, "[VibePhone] staged Apple boot image set into guest physical memory\n");
    return VP_STATUS_OK;
}

VPStatus vp_runtime_set_boot_vector(VPRuntime *runtime, uint64_t guest_address) {
    if (!runtime) return VP_STATUS_INVALID_ARGUMENT;
    if (runtime->state == VP_RUNTIME_RUNNING) return VP_STATUS_INVALID_STATE;
    if (!vp_range_valid(runtime, guest_address, sizeof(uint32_t))) return VP_STATUS_ADDRESS_OUT_OF_RANGE;
    runtime->boot_vector = guest_address;
    runtime->initial_stack_pointer = 0;
    runtime->initial_userspace = 0;
    runtime->framebuffer_ready = 0;
    memset(&runtime->framebuffer, 0, sizeof(runtime->framebuffer));
    runtime->touch_head = 0;
    runtime->touch_count = 0;
    vp_runtime_invalidate_cpu(runtime);
    runtime->state = VP_RUNTIME_READY;
    return VP_STATUS_OK;
}

void vp_runtime_set_instruction_budget(VPRuntime *runtime, uint64_t budget) {
    if (!runtime || runtime->state == VP_RUNTIME_RUNNING) return;
    runtime->instruction_budget = budget ? budget : VP_DEFAULT_INSTRUCTION_BUDGET;
}

uint64_t vp_runtime_boot_vector(const VPRuntime *runtime) {
    return runtime ? runtime->boot_vector : 0;
}

uint64_t vp_runtime_instructions_retired(const VPRuntime *runtime) {
    return runtime ? runtime->instructions_retired : 0;
}

VPStatus vp_runtime_boot(VPRuntime *runtime) {
    if (!runtime) return VP_STATUS_INVALID_ARGUMENT;
    if (runtime->state != VP_RUNTIME_READY &&
        runtime->state != VP_RUNTIME_STOPPED &&
        runtime->state != VP_RUNTIME_PAUSED &&
        runtime->state != VP_RUNTIME_WAITING) {
        return VP_STATUS_INVALID_STATE;
    }

    if (runtime->state == VP_RUNTIME_WAITING && runtime->cpu.waiting) {
        return VP_STATUS_GUEST_WAITING;
    }

    if (!runtime->cpu_initialized ||
        runtime->state == VP_RUNTIME_READY ||
        runtime->state == VP_RUNTIME_STOPPED) {
        vp_aarch64_reset(&runtime->cpu, runtime->boot_vector);
        runtime->cpu.sp = runtime->initial_stack_pointer;
        runtime->cpu.sys.sp_el0 = runtime->initial_stack_pointer;
        if (runtime->initial_userspace) {
            runtime->cpu.current_el = 0;
            runtime->cpu.pstate = 0;
            runtime->cpu.sys.spsel = 0;
        }
        runtime->cpu_initialized = 1;
        runtime->instructions_retired = 0;
        vp_emit(runtime, "[VibePhone] custom AArch64 runtime entered guest execution\n");
    } else {
        vp_emit(runtime, "[VibePhone] resuming saved guest CPU state\n");
    }

    runtime->state = VP_RUNTIME_RUNNING;
    runtime->stop_requested = 0;
    const uint64_t start_retired = runtime->cpu.instructions_retired;
    const uint64_t budget = runtime->instruction_budget ? runtime->instruction_budget : VP_DEFAULT_INSTRUCTION_BUDGET;

    while (!runtime->stop_requested &&
           runtime->cpu.instructions_retired - start_retired < budget) {
        uint32_t insn = 0;
        const VPCPUStepResult step = vp_aarch64_step(runtime, &runtime->cpu, &insn);
        runtime->instructions_retired = runtime->cpu.instructions_retired;
        if (step == VP_CPU_STEP_OK) continue;
        if (step == VP_CPU_STEP_HALTED) {
            runtime->state = VP_RUNTIME_STOPPED;
            runtime->cpu_initialized = 0;
            vp_emit(runtime, "[VibePhone] guest execution halted cleanly\n");
            return VP_STATUS_OK;
        }
        if (step == VP_CPU_STEP_WAITING) {
            runtime->state = VP_RUNTIME_WAITING;
            vp_emit(runtime, "[VibePhone] guest CPU entered WFI/WFE wait state\n");
            return VP_STATUS_GUEST_WAITING;
        }
        if (step == VP_CPU_STEP_SYSCALL_FAULT) {
            return vp_execution_failure(runtime, "userspace kernel syscall fault", &runtime->cpu, insn);
        }
        if (step == VP_CPU_STEP_MEMORY_FAULT) {
            return vp_execution_failure(runtime, "guest memory fault", &runtime->cpu, insn);
        }
        if (step == VP_CPU_STEP_SYSTEM_REGISTER_FAULT) {
            return vp_execution_failure(runtime, "unimplemented AArch64 system register", &runtime->cpu, insn);
        }
        return vp_execution_failure(runtime, "unimplemented AArch64 instruction", &runtime->cpu, insn);
    }

    runtime->instructions_retired = runtime->cpu.instructions_retired;
    if (runtime->stop_requested) {
        runtime->state = VP_RUNTIME_STOPPED;
        runtime->cpu_initialized = 0;
        vp_emit(runtime, "[VibePhone] guest execution stopped by host\n");
        return VP_STATUS_OK;
    }

    runtime->state = VP_RUNTIME_PAUSED;
    vp_emit(runtime, "[VibePhone] instruction budget exhausted; saved CPU state yielded to host\n");
    return VP_STATUS_BUDGET_EXHAUSTED;
}

VPStatus vp_runtime_signal_event(VPRuntime *runtime) {
    if (!runtime) return VP_STATUS_INVALID_ARGUMENT;
    if (runtime->state != VP_RUNTIME_WAITING && runtime->state != VP_RUNTIME_PAUSED) {
        return VP_STATUS_INVALID_STATE;
    }
    vp_aarch64_wake(&runtime->cpu);
    runtime->state = VP_RUNTIME_PAUSED;
    vp_emit(runtime, "[VibePhone] guest wait state signaled; CPU ready to resume\n");
    return VP_STATUS_OK;
}

VPStatus vp_runtime_stop(VPRuntime *runtime) {
    if (!runtime) return VP_STATUS_INVALID_ARGUMENT;
    runtime->stop_requested = 1;
    if (runtime->state != VP_RUNTIME_RUNNING) {
        runtime->state = VP_RUNTIME_STOPPED;
        vp_runtime_invalidate_cpu(runtime);
    }
    return VP_STATUS_OK;
}
