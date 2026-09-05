#ifndef VPHONE_HOST_RUNTIME_H
#define VPHONE_HOST_RUNTIME_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Process-wide runtime owned by the VibeContainers host application. */
int32_t vp_host_runtime_start(void);
void vp_host_runtime_stop(void);
uint32_t vp_host_runtime_state(void);
uint32_t vp_host_runtime_abi(void);
uint64_t vp_host_runtime_committed_bytes(void);
uint64_t vp_host_runtime_syscalls_handled(void);
uint64_t vp_host_runtime_syscalls_rejected(void);

/*
 * Load an AArch64 image into sparse guest physical memory and execute it from
 * entry_address.  Call this off the UI thread; interpretation is synchronous.
 */
int32_t vp_host_runtime_load_and_boot(
    const void *bytes,
    size_t length,
    uint64_t load_address,
    uint64_t entry_address
);

#ifdef __cplusplus
}
#endif

#endif
