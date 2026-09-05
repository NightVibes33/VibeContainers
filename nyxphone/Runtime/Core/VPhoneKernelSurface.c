#include "VPhoneKernelSurface.h"

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct VPKernelSurface {
    VPRuntime *runtime;
    VPProcessIdentity identity;
    char process_name[32];
    char process_path[1024];
    char entitlements[VP_KSURFACE_MAX_ENTITLEMENTS][VP_KSURFACE_MAX_ENTITLEMENT_KEY];
    uint32_t entitlement_count;
    uint64_t handled;
    uint64_t rejected;
    uint32_t mode;
    uint32_t build_type;
    uint32_t next_port;
    uint32_t message_port;
    size_t message_length;
    uint8_t message[256];
    int message_ready;
};

static uint64_t vp_errno_result(int value) {
    return (uint64_t)(int64_t)-value;
}

VPKernelSurface *vp_ksurface_create(VPRuntime *runtime) {
    if (!runtime) return NULL;
    VPKernelSurface *surface = (VPKernelSurface *)calloc(1, sizeof(VPKernelSurface));
    if (!surface) return NULL;
    surface->runtime = runtime;
    surface->identity.pid = 1;
    surface->identity.ppid = 0;
    surface->identity.uid = 0;
    surface->identity.gid = 0;
    surface->identity.euid = 0;
    surface->identity.egid = 0;
    surface->identity.task_handle = UINT64_C(0x4E595849414E0001);
    (void)snprintf(surface->process_name, sizeof(surface->process_name), "nyxinit");
    (void)snprintf(surface->process_path, sizeof(surface->process_path), "/sbin/nyxinit");
    surface->mode = VP_KSURFACE_MODE_NORMAL;
    surface->next_port = 100u;
#ifdef DEBUG
    surface->build_type = VP_KSURFACE_BUILD_DEBUG;
#else
    surface->build_type = VP_KSURFACE_BUILD_RELEASE;
#endif
    return surface;
}

VPKernelSurface *vp_ksurface_attach(VPRuntime *runtime) {
    VPKernelSurface *surface = vp_ksurface_create(runtime);
    if (!surface) return NULL;
    vp_runtime_set_syscall_handler(runtime, vp_ksurface_handle_syscall, surface);
    return surface;
}

void vp_ksurface_destroy(VPKernelSurface *surface) {
    if (!surface) return;
    memset(surface, 0, sizeof(*surface));
    free(surface);
}

void vp_ksurface_set_identity(VPKernelSurface *surface, const VPProcessIdentity *identity) {
    if (!surface || !identity) return;
    surface->identity = *identity;
}

void vp_ksurface_set_process_name(VPKernelSurface *surface, const char *process_name) {
    if (!surface || !process_name || !process_name[0]) return;
    (void)snprintf(surface->process_name, sizeof(surface->process_name), "%s", process_name);
}

VPStatus vp_ksurface_set_process_path(VPKernelSurface *surface, const char *process_path) {
    if (!surface || !process_path || process_path[0] != '/' ||
        strlen(process_path) >= sizeof(surface->process_path)) return VP_STATUS_INVALID_ARGUMENT;
    (void)snprintf(surface->process_path, sizeof(surface->process_path), "%s", process_path);
    return VP_STATUS_OK;
}

VPStatus vp_ksurface_grant_entitlement(VPKernelSurface *surface, const char *key) {
    if (!surface || !key || !key[0] || strlen(key) >= VP_KSURFACE_MAX_ENTITLEMENT_KEY) {
        return VP_STATUS_INVALID_ARGUMENT;
    }
    for (uint32_t i = 0; i < surface->entitlement_count; i++) {
        if (strcmp(surface->entitlements[i], key) == 0) return VP_STATUS_OK;
    }
    if (surface->entitlement_count >= VP_KSURFACE_MAX_ENTITLEMENTS) return VP_STATUS_OUT_OF_MEMORY;
    (void)snprintf(surface->entitlements[surface->entitlement_count++],
                   VP_KSURFACE_MAX_ENTITLEMENT_KEY, "%s", key);
    return VP_STATUS_OK;
}

int vp_ksurface_has_entitlement(const VPKernelSurface *surface, const char *key) {
    if (!surface || !key) return 0;
    for (uint32_t i = 0; i < surface->entitlement_count; i++) {
        if (strcmp(surface->entitlements[i], key) == 0) return 1;
    }
    return 0;
}

VPProcessIdentity vp_ksurface_identity(const VPKernelSurface *surface) {
    VPProcessIdentity empty;
    memset(&empty, 0, sizeof(empty));
    return surface ? surface->identity : empty;
}

uint64_t vp_ksurface_syscalls_handled(const VPKernelSurface *surface) {
    return surface ? surface->handled : 0;
}

uint64_t vp_ksurface_syscalls_rejected(const VPKernelSurface *surface) {
    return surface ? surface->rejected : 0;
}

static VPStatus vp_pectl(VPKernelSurface *surface, const uint64_t args[8], uint64_t *result) {
    const uint64_t category = args ? args[0] : UINT64_MAX;
    const uint64_t operation = args ? args[1] : UINT64_MAX;

    if (category == VP_PECTL_CATEGORY_USERSPACE && operation == VP_PECTL_USERSPACE_GETMODE) {
        *result = surface->mode;
        return VP_STATUS_OK;
    }
    if (category == VP_PECTL_CATEGORY_MISC && operation == VP_PECTL_MISC_GETBUILDTYPE) {
        *result = surface->build_type;
        return VP_STATUS_OK;
    }
    if (category == VP_PECTL_CATEGORY_USERSPACE && operation == VP_PECTL_USERSPACE_REBOOT) {
        *result = vp_errno_result(EPERM);
        return VP_STATUS_OK;
    }

    *result = vp_errno_result(ENOTSUP);
    return VP_STATUS_OK;
}

VPStatus vp_ksurface_handle_syscall(
    VPRuntime *runtime,
    uint64_t number,
    const uint64_t args[8],
    uint64_t *result,
    void *context
) {
    VPKernelSurface *surface = (VPKernelSurface *)context;
    if (!runtime || !surface || surface->runtime != runtime || !result) {
        return VP_STATUS_INVALID_ARGUMENT;
    }

    switch (number) {
        case VP_NYX_SYS_CONSOLE_WRITE:
            if (args[1] > 4096u) {
                *result = vp_errno_result(E2BIG);
                surface->rejected++;
                return VP_STATUS_OK;
            }
            if (vp_runtime_console_write(runtime, args[0], (size_t)args[1]) != VP_STATUS_OK) {
                *result = vp_errno_result(EFAULT);
                surface->rejected++;
                return VP_STATUS_OK;
            }
            *result = 0;
            surface->handled++;
            return VP_STATUS_OK;
        case VP_NYX_SYS_HTTPS_GET: {
            size_t response_length = 0;
            const VPStatus network_status = vp_runtime_network_https_get(
                runtime, args[0], (size_t)args[1], args[2], (size_t)args[3], &response_length
            );
            if (network_status != VP_STATUS_OK) {
                *result = 0;
                surface->rejected++;
                return VP_STATUS_OK;
            }
            *result = response_length;
            surface->handled++;
            return VP_STATUS_OK;
        }
        case VP_NYX_SYS_BLOCK_READ:
            if (args[2] > 4096u || vp_runtime_block_read(runtime, args[0], args[1], (size_t)args[2]) != VP_STATUS_OK) {
                *result = vp_errno_result(EIO);
                surface->rejected++;
                return VP_STATUS_OK;
            }
            *result = 0;
            surface->handled++;
            return VP_STATUS_OK;
        case VP_NYX_SYS_BLOCK_WRITE:
            if (args[2] > 4096u || vp_runtime_block_write(runtime, args[0], args[1], (size_t)args[2]) != VP_STATUS_OK) {
                *result = vp_errno_result(EIO);
                surface->rejected++;
                return VP_STATUS_OK;
            }
            *result = 0;
            surface->handled++;
            return VP_STATUS_OK;
        case VP_NYX_SYS_BLOCK_FLUSH:
            if (vp_runtime_block_flush(runtime) != VP_STATUS_OK) {
                *result = vp_errno_result(EIO);
                surface->rejected++;
                return VP_STATUS_OK;
            }
            *result = 0;
            surface->handled++;
            return VP_STATUS_OK;
        case VP_NYX_SYS_FRAMEBUFFER_PUBLISH:
            if (vp_runtime_publish_framebuffer(
                    runtime, args[0], (uint32_t)args[1], (uint32_t)args[2], (uint32_t)args[3]
                ) != VP_STATUS_OK) {
                *result = vp_errno_result(EFAULT);
                surface->rejected++;
                return VP_STATUS_OK;
            }
            *result = 0;
            surface->handled++;
            return VP_STATUS_OK;
        case VP_NYX_SYS_TOUCH_DEQUEUE: {
            VPTouchEvent event;
            const VPStatus touch_status = vp_runtime_dequeue_touch(runtime, &event);
            if (touch_status == VP_STATUS_INVALID_STATE) {
                *result = 0;
                surface->handled++;
                return VP_STATUS_OK;
            }
            if (touch_status != VP_STATUS_OK ||
                vp_runtime_memory_write(runtime, args[0], &event, sizeof(event)) != VP_STATUS_OK) {
                *result = vp_errno_result(EFAULT);
                surface->rejected++;
                return VP_STATUS_OK;
            }
            *result = 1;
            surface->handled++;
            return VP_STATUS_OK;
        }
        case VP_NYX_SYS_MACH_PORT_ALLOCATE:
            *result = surface->next_port++;
            surface->handled++;
            return VP_STATUS_OK;
        case VP_NYX_SYS_MACH_MSG_SEND:
            if (args[0] < 100u || args[0] >= surface->next_port || args[2] == 0 || args[2] > sizeof(surface->message) ||
                vp_runtime_memory_read(runtime, args[1], surface->message, (size_t)args[2]) != VP_STATUS_OK) {
                *result = vp_errno_result(EINVAL);
                surface->rejected++;
                return VP_STATUS_OK;
            }
            surface->message_port = (uint32_t)args[0];
            surface->message_length = (size_t)args[2];
            surface->message_ready = 1;
            *result = 0;
            surface->handled++;
            return VP_STATUS_OK;
        case VP_NYX_SYS_MACH_MSG_RECEIVE:
            if (!surface->message_ready || args[0] != surface->message_port || args[2] < surface->message_length ||
                vp_runtime_memory_write(runtime, args[1], surface->message, surface->message_length) != VP_STATUS_OK) {
                *result = 0;
                surface->rejected++;
                return VP_STATUS_OK;
            }
            *result = surface->message_length;
            surface->message_ready = 0;
            surface->handled++;
            return VP_STATUS_OK;
        case VP_DARWIN_SYS_GETPID:
            *result = (uint64_t)(uint32_t)surface->identity.pid;
            break;
        case VP_DARWIN_SYS_GETUID:
            *result = surface->identity.uid;
            break;
        case VP_DARWIN_SYS_GETEUID:
            *result = surface->identity.euid;
            break;
        case VP_DARWIN_SYS_GETGID:
            *result = surface->identity.gid;
            break;
        case VP_DARWIN_SYS_GETEGID:
            *result = surface->identity.egid;
            break;
        case VP_NYX_SYS_GETTASK:
        case VP_NYX_SYS_WAITTASK:
            *result = surface->identity.task_handle;
            break;
        case VP_NYX_SYS_PECTL:
            surface->handled++;
            return vp_pectl(surface, args, result);
        case VP_NYX_SYS_PROCPATH: {
            const size_t path_length = strlen(surface->process_path);
            if (args[1] <= path_length ||
                vp_runtime_memory_write(runtime, args[0], surface->process_path, path_length + 1u) != VP_STATUS_OK) {
                *result = vp_errno_result(args[1] <= path_length ? ERANGE : EFAULT);
                surface->rejected++;
                return VP_STATUS_OK;
            }
            *result = path_length;
            surface->handled++;
            return VP_STATUS_OK;
        }
        case VP_NYX_SYS_HANDOFFEP:
            *result = vp_errno_result(ENOTSUP);
            surface->rejected++;
            return VP_STATUS_OK;
        case VP_NYX_SYS_SIGN:
            /* Guest-only policy mediation. This never signs or changes the host device. */
            if (!vp_ksurface_has_entitlement(surface, "com.nyxphone.virtual-signing")) {
                *result = vp_errno_result(EPERM);
                surface->rejected++;
                return VP_STATUS_OK;
            }
            if (args[1] == 0 || args[1] > 64u * 1024u * 1024u) {
                *result = vp_errno_result(EINVAL);
                surface->rejected++;
                return VP_STATUS_OK;
            }
            *result = 0;
            surface->handled++;
            return VP_STATUS_OK;
        default: {
            char diagnostic[256];
            (void)snprintf(
                diagnostic, sizeof(diagnostic),
                "NYX_MISSING_SYSCALL: pid=%d process=%s number=%llu arguments=%llx,%llx,%llx,%llx,%llx,%llx,%llx,%llx\n",
                surface->identity.pid, surface->process_name, (unsigned long long)number,
                (unsigned long long)args[0], (unsigned long long)args[1],
                (unsigned long long)args[2], (unsigned long long)args[3],
                (unsigned long long)args[4], (unsigned long long)args[5],
                (unsigned long long)args[6], (unsigned long long)args[7]
            );
            vp_runtime_host_log(runtime, diagnostic);
            *result = vp_errno_result(ENOSYS);
            surface->rejected++;
            return VP_STATUS_OK;
        }
    }

    surface->handled++;
    return VP_STATUS_OK;
}
