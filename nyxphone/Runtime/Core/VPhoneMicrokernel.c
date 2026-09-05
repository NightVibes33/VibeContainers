#include "VPhoneMicrokernel.h"

#include <stdlib.h>
#include <string.h>

#define VP_KERNEL_FIRST_DYNAMIC_PORT 0x100u

typedef struct {
    int used;
    VPKernelProcess process;
    char entitlements[VP_KERNEL_MAX_ENTITLEMENTS][VP_KERNEL_MAX_ENTITLEMENT_KEY];
    size_t entitlement_count;
} VPProcessSlot;

typedef struct {
    int used;
    VPKernelPort port;
} VPPortSlot;

struct VPMicrokernel {
    VPProcessSlot processes[VP_KERNEL_MAX_PROCESSES];
    VPPortSlot ports[VP_KERNEL_MAX_PORTS];
    size_t process_count;
    size_t port_count;
    int32_t current_pid;
    uint32_t next_port_name;
};

static VPProcessSlot *vp_process_slot(VPMicrokernel *kernel, int32_t pid) {
    if (!kernel || pid <= 0) return NULL;
    for (size_t i = 0; i < VP_KERNEL_MAX_PROCESSES; ++i) {
        if (kernel->processes[i].used && kernel->processes[i].process.pid == pid) {
            return &kernel->processes[i];
        }
    }
    return NULL;
}

static const VPProcessSlot *vp_process_slot_const(const VPMicrokernel *kernel, int32_t pid) {
    return vp_process_slot((VPMicrokernel *)kernel, pid);
}

static VPPortSlot *vp_port_slot(VPMicrokernel *kernel, uint32_t name) {
    if (!kernel || name == 0) return NULL;
    for (size_t i = 0; i < VP_KERNEL_MAX_PORTS; ++i) {
        if (kernel->ports[i].used && kernel->ports[i].port.name == name) {
            return &kernel->ports[i];
        }
    }
    return NULL;
}

static const VPPortSlot *vp_port_slot_const(const VPMicrokernel *kernel, uint32_t name) {
    return vp_port_slot((VPMicrokernel *)kernel, name);
}

VPMicrokernel *vp_kernel_create(void) {
    VPMicrokernel *kernel = (VPMicrokernel *)calloc(1, sizeof(VPMicrokernel));
    if (!kernel) return NULL;
    kernel->next_port_name = VP_KERNEL_FIRST_DYNAMIC_PORT;
    return kernel;
}

void vp_kernel_destroy(VPMicrokernel *kernel) {
    if (!kernel) return;
    memset(kernel, 0, sizeof(*kernel));
    free(kernel);
}

VPKernelStatus vp_kernel_register_process(
    VPMicrokernel *kernel,
    const VPKernelProcess *process
) {
    if (!kernel || !process || process->pid <= 0 || process->task_handle == 0) {
        return VP_KERNEL_INVALID_ARGUMENT;
    }
    if (vp_process_slot(kernel, process->pid)) return VP_KERNEL_ALREADY_EXISTS;
    for (size_t i = 0; i < VP_KERNEL_MAX_PROCESSES; ++i) {
        if (!kernel->processes[i].used) {
            kernel->processes[i].used = 1;
            kernel->processes[i].process = *process;
            kernel->processes[i].process.path[VP_KERNEL_MAX_PATH - 1u] = '\0';
            kernel->processes[i].entitlement_count = 0;
            kernel->process_count++;
            if (kernel->current_pid == 0) kernel->current_pid = process->pid;
            return VP_KERNEL_OK;
        }
    }
    return VP_KERNEL_NO_SPACE;
}

VPKernelStatus vp_kernel_unregister_process(VPMicrokernel *kernel, int32_t pid) {
    VPProcessSlot *slot = vp_process_slot(kernel, pid);
    if (!slot) return VP_KERNEL_NOT_FOUND;

    for (size_t i = 0; i < VP_KERNEL_MAX_PORTS; ++i) {
        if (kernel->ports[i].used && kernel->ports[i].port.owner_pid == pid) {
            memset(&kernel->ports[i], 0, sizeof(kernel->ports[i]));
            if (kernel->port_count) kernel->port_count--;
        }
    }
    memset(slot, 0, sizeof(*slot));
    if (kernel->process_count) kernel->process_count--;
    if (kernel->current_pid == pid) kernel->current_pid = 0;
    return VP_KERNEL_OK;
}

VPKernelStatus vp_kernel_lookup_process(
    const VPMicrokernel *kernel,
    int32_t pid,
    VPKernelProcess *process_out
) {
    if (!kernel || !process_out) return VP_KERNEL_INVALID_ARGUMENT;
    const VPProcessSlot *slot = vp_process_slot_const(kernel, pid);
    if (!slot) return VP_KERNEL_NOT_FOUND;
    *process_out = slot->process;
    return VP_KERNEL_OK;
}

VPKernelStatus vp_kernel_lookup_task(
    const VPMicrokernel *kernel,
    uint64_t task_handle,
    VPKernelProcess *process_out
) {
    if (!kernel || !process_out || task_handle == 0) return VP_KERNEL_INVALID_ARGUMENT;
    for (size_t i = 0; i < VP_KERNEL_MAX_PROCESSES; ++i) {
        const VPProcessSlot *slot = &kernel->processes[i];
        if (slot->used && slot->process.task_handle == task_handle) {
            *process_out = slot->process;
            return VP_KERNEL_OK;
        }
    }
    return VP_KERNEL_NOT_FOUND;
}

VPKernelStatus vp_kernel_set_current_process(VPMicrokernel *kernel, int32_t pid) {
    if (!kernel) return VP_KERNEL_INVALID_ARGUMENT;
    if (!vp_process_slot(kernel, pid)) return VP_KERNEL_NOT_FOUND;
    kernel->current_pid = pid;
    return VP_KERNEL_OK;
}

VPKernelStatus vp_kernel_current_process(
    const VPMicrokernel *kernel,
    VPKernelProcess *process_out
) {
    if (!kernel || !process_out) return VP_KERNEL_INVALID_ARGUMENT;
    if (kernel->current_pid <= 0) return VP_KERNEL_NOT_FOUND;
    return vp_kernel_lookup_process(kernel, kernel->current_pid, process_out);
}

size_t vp_kernel_process_count(const VPMicrokernel *kernel) {
    return kernel ? kernel->process_count : 0;
}

VPKernelStatus vp_kernel_grant_entitlement(
    VPMicrokernel *kernel,
    int32_t pid,
    const char *key
) {
    if (!kernel || !key || !*key || strlen(key) >= VP_KERNEL_MAX_ENTITLEMENT_KEY) {
        return VP_KERNEL_INVALID_ARGUMENT;
    }
    VPProcessSlot *slot = vp_process_slot(kernel, pid);
    if (!slot) return VP_KERNEL_NOT_FOUND;
    for (size_t i = 0; i < slot->entitlement_count; ++i) {
        if (strcmp(slot->entitlements[i], key) == 0) return VP_KERNEL_OK;
    }
    if (slot->entitlement_count >= VP_KERNEL_MAX_ENTITLEMENTS) return VP_KERNEL_NO_SPACE;
    strcpy(slot->entitlements[slot->entitlement_count++], key);
    return VP_KERNEL_OK;
}

int vp_kernel_has_entitlement(
    const VPMicrokernel *kernel,
    int32_t pid,
    const char *key
) {
    if (!kernel || !key) return 0;
    const VPProcessSlot *slot = vp_process_slot_const(kernel, pid);
    if (!slot) return 0;
    for (size_t i = 0; i < slot->entitlement_count; ++i) {
        if (strcmp(slot->entitlements[i], key) == 0) return 1;
    }
    return 0;
}

VPKernelStatus vp_kernel_allocate_port(
    VPMicrokernel *kernel,
    int32_t owner_pid,
    uint64_t object,
    uint32_t *name_out
) {
    if (!kernel || !name_out || owner_pid <= 0) return VP_KERNEL_INVALID_ARGUMENT;
    if (!vp_process_slot(kernel, owner_pid)) return VP_KERNEL_NOT_FOUND;

    size_t free_index = VP_KERNEL_MAX_PORTS;
    for (size_t i = 0; i < VP_KERNEL_MAX_PORTS; ++i) {
        if (!kernel->ports[i].used) {
            free_index = i;
            break;
        }
    }
    if (free_index == VP_KERNEL_MAX_PORTS) return VP_KERNEL_NO_SPACE;

    uint32_t candidate = kernel->next_port_name;
    do {
        if (++kernel->next_port_name == 0) kernel->next_port_name = VP_KERNEL_FIRST_DYNAMIC_PORT;
        if (!vp_port_slot(kernel, candidate)) break;
        candidate = kernel->next_port_name;
    } while (candidate != kernel->next_port_name);
    if (vp_port_slot(kernel, candidate)) return VP_KERNEL_NO_SPACE;

    VPPortSlot *slot = &kernel->ports[free_index];
    slot->used = 1;
    slot->port.name = candidate;
    slot->port.owner_pid = owner_pid;
    slot->port.object = object;
    slot->port.send_rights = 1;
    slot->port.receive_right = 1;
    kernel->port_count++;
    *name_out = candidate;
    return VP_KERNEL_OK;
}

VPKernelStatus vp_kernel_lookup_port(
    const VPMicrokernel *kernel,
    uint32_t name,
    VPKernelPort *port_out
) {
    if (!kernel || !port_out) return VP_KERNEL_INVALID_ARGUMENT;
    const VPPortSlot *slot = vp_port_slot_const(kernel, name);
    if (!slot) return VP_KERNEL_NOT_FOUND;
    *port_out = slot->port;
    return VP_KERNEL_OK;
}

VPKernelStatus vp_kernel_handoff_port(
    VPMicrokernel *kernel,
    uint32_t name,
    int32_t from_pid,
    int32_t to_pid
) {
    if (!kernel || from_pid <= 0 || to_pid <= 0) return VP_KERNEL_INVALID_ARGUMENT;
    VPPortSlot *slot = vp_port_slot(kernel, name);
    if (!slot) return VP_KERNEL_NOT_FOUND;
    if (slot->port.owner_pid != from_pid || !slot->port.receive_right) {
        return VP_KERNEL_PERMISSION_DENIED;
    }
    if (!vp_process_slot(kernel, to_pid)) return VP_KERNEL_NOT_FOUND;
    slot->port.owner_pid = to_pid;
    return VP_KERNEL_OK;
}

size_t vp_kernel_port_count(const VPMicrokernel *kernel) {
    return kernel ? kernel->port_count : 0;
}
