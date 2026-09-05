#include "VPhoneMMU.h"

#include <stddef.h>
#include <string.h>

#define VP_SCTLR_M UINT64_C(1)
#define VP_DESC_VALID UINT64_C(1)
#define VP_DESC_TABLE_OR_PAGE UINT64_C(2)
#define VP_DESC_AF (UINT64_C(1) << 10)
#define VP_DESC_AP_RO (UINT64_C(1) << 7)
#define VP_DESC_PXN (UINT64_C(1) << 53)
#define VP_DESC_UXN (UINT64_C(1) << 54)
#define VP_TTBR_BADDR_MASK UINT64_C(0x0000FFFFFFFFC000)
#define VP_DESC_OA_16K_MASK UINT64_C(0x0000FFFFFFFFC000)

static void vp_mmu_clear_fault(VPMMUFault *fault) {
    if (fault) memset(fault, 0, sizeof(*fault));
}

static VPMMUResult vp_mmu_fault(
    VPMMUFault *fault,
    VPMMUResult kind,
    uint32_t level,
    uint32_t fsc,
    VPMMUAccess access,
    uint64_t va,
    uint64_t descriptor_address,
    uint64_t descriptor
) {
    if (fault) {
        fault->kind = kind;
        fault->level = level;
        fault->fsc = fsc;
        fault->write = access == VP_MMU_ACCESS_WRITE;
        fault->execute = access == VP_MMU_ACCESS_EXECUTE;
        fault->virtual_address = va;
        fault->descriptor_address = descriptor_address;
        fault->descriptor = descriptor;
    }
    return kind;
}

static uint64_t vp_low_mask(unsigned bits) {
    if (bits >= 64u) return UINT64_MAX;
    if (bits == 0u) return 0;
    return (UINT64_C(1) << bits) - 1u;
}

static int vp_is_canonical_for_region(uint64_t va, unsigned va_bits, int upper) {
    if (va_bits == 0u || va_bits > 64u) return 0;
    if (va_bits == 64u) return 1;
    const uint64_t high_mask = ~vp_low_mask(va_bits);
    return upper ? (va & high_mask) == high_mask : (va & high_mask) == 0;
}

static int vp_read_descriptor(VPRuntime *runtime, uint64_t address, uint64_t *descriptor) {
    return vp_runtime_memory_read(runtime, address, descriptor, sizeof(*descriptor)) == VP_STATUS_OK;
}

static unsigned vp_start_level_for_16k(unsigned va_bits) {
    if (va_bits <= VP_GUEST_PAGE_SHIFT) return 3u;
    const unsigned translated_bits = va_bits - VP_GUEST_PAGE_SHIFT;
    const unsigned levels = (translated_bits + 10u) / 11u;
    if (levels <= 1u) return 3u;
    if (levels == 2u) return 2u;
    if (levels == 3u) return 1u;
    return 0u;
}

static uint32_t vp_translation_fsc(unsigned level) {
    return 0x04u + (level & 3u);
}

static uint32_t vp_access_flag_fsc(unsigned level) {
    return 0x08u + (level & 3u);
}

static uint32_t vp_permission_fsc(unsigned level) {
    return 0x0Cu + (level & 3u);
}

int vp_mmu_enabled(const VPMMUContext *context) {
    return context && (context->sctlr_el1 & VP_SCTLR_M) != 0;
}

VPMMUResult vp_mmu_translate(
    VPRuntime *runtime,
    const VPMMUContext *context,
    uint64_t virtual_address,
    VPMMUAccess access,
    uint64_t *physical_address,
    VPMMUFault *fault
) {
    if (!runtime || !context || !physical_address) {
        return vp_mmu_fault(fault, VP_MMU_PHYSICAL_FAULT, 0, 0, access,
                            virtual_address, 0, 0);
    }

    vp_mmu_clear_fault(fault);

    if (!vp_mmu_enabled(context)) {
        const VPMachineConfig *config = vp_runtime_config(runtime);
        if (!config || virtual_address >= config->guest_physical_memory_size) {
            return vp_mmu_fault(fault, VP_MMU_PHYSICAL_FAULT, 0, 0, access,
                                virtual_address, 0, 0);
        }
        *physical_address = virtual_address;
        return VP_MMU_OK;
    }

    /*
     * Apple arm64 mobile kernels use a 16 KiB stage-1 granule. TCR encodings:
     * TG0=10b for 16 KiB, TG1=01b for 16 KiB.
     */
    const unsigned tg0 = (unsigned)((context->tcr_el1 >> 14) & 3u);
    const unsigned tg1 = (unsigned)((context->tcr_el1 >> 30) & 3u);
    const int upper = (virtual_address >> 63) != 0;
    const unsigned txsz = upper
        ? (unsigned)((context->tcr_el1 >> 16) & 0x3Fu)
        : (unsigned)(context->tcr_el1 & 0x3Fu);
    const unsigned va_bits = 64u - txsz;

    if ((!upper && tg0 != 2u) || (upper && tg1 != 1u)) {
        return vp_mmu_fault(fault, VP_MMU_UNSUPPORTED_GRANULE, 0, 0, access,
                            virtual_address, 0, 0);
    }
    if (va_bits < VP_GUEST_PAGE_SHIFT + 1u || va_bits > 48u ||
        !vp_is_canonical_for_region(virtual_address, va_bits, upper)) {
        return vp_mmu_fault(fault, VP_MMU_ADDRESS_SIZE_FAULT, 0, 0, access,
                            virtual_address, 0, 0);
    }

    const uint64_t ttbr = upper ? context->ttbr1_el1 : context->ttbr0_el1;
    uint64_t table = ttbr & VP_TTBR_BADDR_MASK;
    unsigned level = vp_start_level_for_16k(va_bits);

    for (; level <= 3u; ++level) {
        const unsigned shift = VP_GUEST_PAGE_SHIFT + 11u * (3u - level);
        unsigned index_bits = 11u;
        if (level == vp_start_level_for_16k(va_bits)) {
            const unsigned consumed_below = VP_GUEST_PAGE_SHIFT + 11u * (3u - level);
            if (va_bits > consumed_below && va_bits - consumed_below < 11u) {
                index_bits = va_bits - consumed_below;
            }
        }
        const uint64_t index = (virtual_address >> shift) & vp_low_mask(index_bits);
        const uint64_t descriptor_address = table + index * sizeof(uint64_t);
        uint64_t descriptor = 0;
        if (!vp_read_descriptor(runtime, descriptor_address, &descriptor)) {
            return vp_mmu_fault(fault, VP_MMU_PHYSICAL_FAULT, level,
                                vp_translation_fsc(level), access,
                                virtual_address, descriptor_address, 0);
        }
        if ((descriptor & VP_DESC_VALID) == 0) {
            return vp_mmu_fault(fault, VP_MMU_TRANSLATION_FAULT, level,
                                vp_translation_fsc(level), access,
                                virtual_address, descriptor_address, descriptor);
        }

        const int table_or_page = (descriptor & VP_DESC_TABLE_OR_PAGE) != 0;
        if (level < 3u && table_or_page) {
            table = descriptor & VP_DESC_OA_16K_MASK;
            continue;
        }

        if (level == 0u && !table_or_page) {
            return vp_mmu_fault(fault, VP_MMU_TRANSLATION_FAULT, level,
                                vp_translation_fsc(level), access,
                                virtual_address, descriptor_address, descriptor);
        }
        if (level == 3u && !table_or_page) {
            return vp_mmu_fault(fault, VP_MMU_TRANSLATION_FAULT, level,
                                vp_translation_fsc(level), access,
                                virtual_address, descriptor_address, descriptor);
        }
        if ((descriptor & VP_DESC_AF) == 0) {
            return vp_mmu_fault(fault, VP_MMU_ACCESS_FLAG_FAULT, level,
                                vp_access_flag_fsc(level), access,
                                virtual_address, descriptor_address, descriptor);
        }
        if (access == VP_MMU_ACCESS_WRITE && (descriptor & VP_DESC_AP_RO) != 0) {
            return vp_mmu_fault(fault, VP_MMU_PERMISSION_FAULT, level,
                                vp_permission_fsc(level), access,
                                virtual_address, descriptor_address, descriptor);
        }
        if (access == VP_MMU_ACCESS_EXECUTE) {
            const int execute_never = context->current_el == 0
                ? (descriptor & VP_DESC_UXN) != 0
                : (descriptor & VP_DESC_PXN) != 0;
            if (execute_never) {
                return vp_mmu_fault(fault, VP_MMU_PERMISSION_FAULT, level,
                                    vp_permission_fsc(level), access,
                                    virtual_address, descriptor_address, descriptor);
            }
        }

        const unsigned offset_bits = VP_GUEST_PAGE_SHIFT + 11u * (3u - level);
        const uint64_t offset_mask = vp_low_mask(offset_bits);
        const uint64_t output_base = descriptor & VP_DESC_OA_16K_MASK & ~offset_mask;
        const uint64_t pa = output_base | (virtual_address & offset_mask);
        const VPMachineConfig *config = vp_runtime_config(runtime);
        if (!config || pa >= config->guest_physical_memory_size) {
            return vp_mmu_fault(fault, VP_MMU_PHYSICAL_FAULT, level,
                                vp_translation_fsc(level), access,
                                virtual_address, descriptor_address, descriptor);
        }
        *physical_address = pa;
        return VP_MMU_OK;
    }

    return vp_mmu_fault(fault, VP_MMU_TRANSLATION_FAULT, 3,
                        vp_translation_fsc(3), access,
                        virtual_address, 0, 0);
}
