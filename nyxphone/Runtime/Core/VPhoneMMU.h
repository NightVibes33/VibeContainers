#ifndef VPHONE_MMU_H
#define VPHONE_MMU_H

#include "VPhoneRuntimeCore.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    VP_MMU_ACCESS_READ = 0,
    VP_MMU_ACCESS_WRITE = 1,
    VP_MMU_ACCESS_EXECUTE = 2,
} VPMMUAccess;

typedef enum {
    VP_MMU_OK = 0,
    VP_MMU_TRANSLATION_FAULT = 1,
    VP_MMU_ACCESS_FLAG_FAULT = 2,
    VP_MMU_PERMISSION_FAULT = 3,
    VP_MMU_UNSUPPORTED_GRANULE = 4,
    VP_MMU_PHYSICAL_FAULT = 5,
    VP_MMU_ADDRESS_SIZE_FAULT = 6,
} VPMMUResult;

typedef struct {
    uint64_t sctlr_el1;
    uint64_t tcr_el1;
    uint64_t ttbr0_el1;
    uint64_t ttbr1_el1;
    uint32_t current_el;
} VPMMUContext;

typedef struct {
    VPMMUResult kind;
    uint32_t level;
    uint32_t fsc;
    uint32_t write;
    uint32_t execute;
    uint64_t virtual_address;
    uint64_t descriptor_address;
    uint64_t descriptor;
} VPMMUFault;

int vp_mmu_enabled(const VPMMUContext *context);
VPMMUResult vp_mmu_translate(
    VPRuntime *runtime,
    const VPMMUContext *context,
    uint64_t virtual_address,
    VPMMUAccess access,
    uint64_t *physical_address,
    VPMMUFault *fault
);

#ifdef __cplusplus
}
#endif

#endif
