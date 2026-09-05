#ifndef VPHONE_MICROKERNEL_H
#define VPHONE_MICROKERNEL_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define VP_KERNEL_MAX_PROCESSES 128u
#define VP_KERNEL_MAX_PORTS 512u
#define VP_KERNEL_MAX_ENTITLEMENTS 32u
#define VP_KERNEL_MAX_PATH 512u
#define VP_KERNEL_MAX_ENTITLEMENT_KEY 96u

typedef struct VPMicrokernel VPMicrokernel;

typedef enum {
    VP_KERNEL_OK = 0,
    VP_KERNEL_INVALID_ARGUMENT = 1,
    VP_KERNEL_NO_SPACE = 2,
    VP_KERNEL_NOT_FOUND = 3,
    VP_KERNEL_PERMISSION_DENIED = 4,
    VP_KERNEL_ALREADY_EXISTS = 5,
} VPKernelStatus;

typedef struct {
    int32_t pid;
    int32_t ppid;
    uint32_t uid;
    uint32_t gid;
    uint32_t euid;
    uint32_t egid;
    uint64_t task_handle;
    char path[VP_KERNEL_MAX_PATH];
} VPKernelProcess;

typedef struct {
    uint32_t name;
    int32_t owner_pid;
    uint64_t object;
    uint32_t send_rights;
    uint32_t receive_right;
} VPKernelPort;

VPMicrokernel *vp_kernel_create(void);
void vp_kernel_destroy(VPMicrokernel *kernel);

VPKernelStatus vp_kernel_register_process(
    VPMicrokernel *kernel,
    const VPKernelProcess *process
);
VPKernelStatus vp_kernel_unregister_process(VPMicrokernel *kernel, int32_t pid);
VPKernelStatus vp_kernel_lookup_process(
    const VPMicrokernel *kernel,
    int32_t pid,
    VPKernelProcess *process_out
);
VPKernelStatus vp_kernel_lookup_task(
    const VPMicrokernel *kernel,
    uint64_t task_handle,
    VPKernelProcess *process_out
);
VPKernelStatus vp_kernel_set_current_process(VPMicrokernel *kernel, int32_t pid);
VPKernelStatus vp_kernel_current_process(
    const VPMicrokernel *kernel,
    VPKernelProcess *process_out
);
size_t vp_kernel_process_count(const VPMicrokernel *kernel);

VPKernelStatus vp_kernel_grant_entitlement(
    VPMicrokernel *kernel,
    int32_t pid,
    const char *key
);
int vp_kernel_has_entitlement(
    const VPMicrokernel *kernel,
    int32_t pid,
    const char *key
);

VPKernelStatus vp_kernel_allocate_port(
    VPMicrokernel *kernel,
    int32_t owner_pid,
    uint64_t object,
    uint32_t *name_out
);
VPKernelStatus vp_kernel_lookup_port(
    const VPMicrokernel *kernel,
    uint32_t name,
    VPKernelPort *port_out
);
VPKernelStatus vp_kernel_handoff_port(
    VPMicrokernel *kernel,
    uint32_t name,
    int32_t from_pid,
    int32_t to_pid
);
size_t vp_kernel_port_count(const VPMicrokernel *kernel);

#ifdef __cplusplus
}
#endif

#endif
