#ifndef VPHONE_KERNEL_SURFACE_H
#define VPHONE_KERNEL_SURFACE_H

#include "VPhoneRuntimeCore.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Nyxian ksurface ABI compatibility.
 * Values intentionally match emexlab/Nyxian ksurface_abi.h. The combined
 * iOS runtime remains userspace-only; these numbers are dispatched by our
 * interpreter and are never forwarded to the host iOS kernel.
 */
#define VP_NYX_SYS_GETTASK     754u
#define VP_NYX_SYS_PROCPATH    755u
#define VP_NYX_SYS_HANDOFFEP   757u
#define VP_NYX_SYS_WAITTASK    759u
#define VP_NYX_SYS_PECTL       760u
#define VP_NYX_SYS_SIGN        761u
#define VP_NYX_SYS_CONSOLE_WRITE 0x7F00u
#define VP_NYX_SYS_TOUCH_DEQUEUE 0x7F01u
#define VP_NYX_SYS_FRAMEBUFFER_PUBLISH 0x7F02u
#define VP_NYX_SYS_BLOCK_READ  0x7F10u
#define VP_NYX_SYS_BLOCK_WRITE 0x7F11u
#define VP_NYX_SYS_BLOCK_FLUSH 0x7F12u
#define VP_NYX_SYS_HTTPS_GET   0x7F20u
#define VP_NYX_SYS_MACH_PORT_ALLOCATE 0x7E10u
#define VP_NYX_SYS_MACH_MSG_SEND      0x7E11u
#define VP_NYX_SYS_MACH_MSG_RECEIVE   0x7E12u

#define VP_PECTL_CATEGORY_LAUNCH_SERVICE 0u
#define VP_PECTL_CATEGORY_CODE_SIGNING   1u
#define VP_PECTL_CATEGORY_USER_INTERFACE 2u
#define VP_PECTL_CATEGORY_USERSPACE      3u
#define VP_PECTL_CATEGORY_MISC           4u

#define VP_PECTL_USERSPACE_REBOOT  0u
#define VP_PECTL_USERSPACE_GETMODE 1u
#define VP_PECTL_MISC_GETBUILDTYPE 0u

#define VP_DARWIN_SYS_GETPID  20u
#define VP_DARWIN_SYS_GETUID  24u
#define VP_DARWIN_SYS_GETEUID 25u
#define VP_DARWIN_SYS_GETGID  47u
#define VP_DARWIN_SYS_GETEGID 43u

#define VP_KSURFACE_MODE_NORMAL 0u
#define VP_KSURFACE_BUILD_RELEASE 0u
#define VP_KSURFACE_BUILD_DEBUG 1u
#define VP_KSURFACE_MAX_ENTITLEMENTS 32u
#define VP_KSURFACE_MAX_ENTITLEMENT_KEY 96u

typedef struct VPKernelSurface VPKernelSurface;

typedef struct {
    int32_t pid;
    int32_t ppid;
    uint32_t uid;
    uint32_t gid;
    uint32_t euid;
    uint32_t egid;
    uint64_t task_handle;
} VPProcessIdentity;

VPKernelSurface *vp_ksurface_create(VPRuntime *runtime);
VPKernelSurface *vp_ksurface_attach(VPRuntime *runtime);
void vp_ksurface_destroy(VPKernelSurface *surface);
void vp_ksurface_set_identity(VPKernelSurface *surface, const VPProcessIdentity *identity);
void vp_ksurface_set_process_name(VPKernelSurface *surface, const char *process_name);
VPStatus vp_ksurface_set_process_path(VPKernelSurface *surface, const char *process_path);
VPStatus vp_ksurface_grant_entitlement(VPKernelSurface *surface, const char *key);
int vp_ksurface_has_entitlement(const VPKernelSurface *surface, const char *key);
VPProcessIdentity vp_ksurface_identity(const VPKernelSurface *surface);
uint64_t vp_ksurface_syscalls_handled(const VPKernelSurface *surface);
uint64_t vp_ksurface_syscalls_rejected(const VPKernelSurface *surface);

VPStatus vp_ksurface_handle_syscall(
    VPRuntime *runtime,
    uint64_t number,
    const uint64_t args[8],
    uint64_t *result,
    void *context
);

#ifdef __cplusplus
}
#endif

#endif
