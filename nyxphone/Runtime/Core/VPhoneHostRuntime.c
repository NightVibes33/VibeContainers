#include "VPhoneHostRuntime.h"
#include "VPhoneKernelSurface.h"
#include "VPhoneRuntimeCore.h"

#include <stdio.h>

static VPRuntime *g_runtime;
static VPKernelSurface *g_surface;

static void vp_host_serial(const uint8_t *bytes, size_t length, void *context) {
    (void)context;
    if (!bytes || !length) return;
    (void)fwrite(bytes, 1, length, stderr);
    (void)fflush(stderr);
}

int32_t vp_host_runtime_start(void) {
    if (g_runtime && g_surface) return (int32_t)VP_STATUS_OK;

    const VPMachineConfig config = {
        .cpu_count = 6,
        .guest_physical_memory_size = UINT64_C(6) * 1024u * 1024u * 1024u,
        .screen_width = 1290,
        .screen_height = 2796,
        .pixels_per_inch = 460,
        .screen_scale = 3.0,
    };

    g_runtime = vp_runtime_create(&config);
    if (!g_runtime) return (int32_t)VP_STATUS_OUT_OF_MEMORY;
    vp_runtime_set_serial_callback(g_runtime, vp_host_serial, NULL);

    g_surface = vp_ksurface_create(g_runtime);
    if (!g_surface) {
        vp_runtime_destroy(g_runtime);
        g_runtime = NULL;
        return (int32_t)VP_STATUS_OUT_OF_MEMORY;
    }
    vp_runtime_set_syscall_handler(g_runtime, vp_ksurface_handle_syscall, g_surface);
    fprintf(stderr, "[NyxPhone] runtime ABI %u ready (Nyxian ksurface ABI + custom AArch64)\n", vp_runtime_abi_version());
    return (int32_t)VP_STATUS_OK;
}

void vp_host_runtime_stop(void) {
    if (g_runtime) (void)vp_runtime_stop(g_runtime);
    if (g_surface) {
        vp_ksurface_destroy(g_surface);
        g_surface = NULL;
    }
    if (g_runtime) {
        vp_runtime_destroy(g_runtime);
        g_runtime = NULL;
    }
}

uint32_t vp_host_runtime_state(void) {
    return g_runtime ? (uint32_t)vp_runtime_state(g_runtime) : (uint32_t)VP_RUNTIME_CREATED;
}

uint32_t vp_host_runtime_abi(void) {
    return vp_runtime_abi_version();
}

uint64_t vp_host_runtime_committed_bytes(void) {
    return g_runtime ? vp_runtime_committed_bytes(g_runtime) : 0;
}

uint64_t vp_host_runtime_syscalls_handled(void) {
    return g_surface ? vp_ksurface_syscalls_handled(g_surface) : 0;
}

uint64_t vp_host_runtime_syscalls_rejected(void) {
    return g_surface ? vp_ksurface_syscalls_rejected(g_surface) : 0;
}

int32_t vp_host_runtime_load_and_boot(
    const void *bytes,
    size_t length,
    uint64_t load_address,
    uint64_t entry_address
) {
    if (!bytes || !length) return (int32_t)VP_STATUS_INVALID_ARGUMENT;
    const int32_t start = vp_host_runtime_start();
    if (start != (int32_t)VP_STATUS_OK) return start;

    VPStatus status = vp_runtime_memory_write(g_runtime, load_address, bytes, length);
    if (status != VP_STATUS_OK) return (int32_t)status;
    status = vp_runtime_set_boot_vector(g_runtime, entry_address);
    if (status != VP_STATUS_OK) return (int32_t)status;
    return (int32_t)vp_runtime_boot(g_runtime);
}
