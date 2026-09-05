#include "VPhoneAArch64.h"

#include <string.h>

#define VP_SYSREG(op0, op1, crn, crm, op2) \
    ((((uint16_t)(op0) & 3u) << 14) | (((uint16_t)(op1) & 7u) << 11) | \
     (((uint16_t)(crn) & 15u) << 7) | (((uint16_t)(crm) & 15u) << 3) | \
     ((uint16_t)(op2) & 7u))

#define VP_SYS_CURRENTEL   VP_SYSREG(3, 0, 4, 2, 2)
#define VP_SYS_SPSEL       VP_SYSREG(3, 0, 4, 2, 0)
#define VP_SYS_NZCV        VP_SYSREG(3, 3, 4, 2, 0)
#define VP_SYS_DAIF        VP_SYSREG(3, 3, 4, 2, 1)
#define VP_SYS_SCTLR_EL1   VP_SYSREG(3, 0, 1, 0, 0)
#define VP_SYS_TTBR0_EL1   VP_SYSREG(3, 0, 2, 0, 0)
#define VP_SYS_TTBR1_EL1   VP_SYSREG(3, 0, 2, 0, 1)
#define VP_SYS_TCR_EL1     VP_SYSREG(3, 0, 2, 0, 2)
#define VP_SYS_SPSR_EL1    VP_SYSREG(3, 0, 4, 0, 0)
#define VP_SYS_ELR_EL1     VP_SYSREG(3, 0, 4, 0, 1)
#define VP_SYS_SP_EL0      VP_SYSREG(3, 0, 4, 1, 0)
#define VP_SYS_ESR_EL1     VP_SYSREG(3, 0, 5, 2, 0)
#define VP_SYS_FAR_EL1     VP_SYSREG(3, 0, 6, 0, 0)
#define VP_SYS_MAIR_EL1    VP_SYSREG(3, 0, 10, 2, 0)
#define VP_SYS_VBAR_EL1    VP_SYSREG(3, 0, 12, 0, 0)
#define VP_SYS_TPIDR_EL0   VP_SYSREG(3, 3, 13, 0, 2)
#define VP_SYS_TPIDRRO_EL0 VP_SYSREG(3, 3, 13, 0, 3)
#define VP_SYS_TPIDR_EL1   VP_SYSREG(3, 0, 13, 0, 4)
#define VP_SYS_CNTFRQ_EL0  VP_SYSREG(3, 3, 14, 0, 0)
#define VP_SYS_CNTPCT_EL0  VP_SYSREG(3, 3, 14, 0, 1)
#define VP_SYS_CNTVCT_EL0  VP_SYSREG(3, 3, 14, 0, 2)

static int64_t vp_sign_extend(uint64_t value, unsigned bits) {
    const uint64_t sign = UINT64_C(1) << (bits - 1u);
    return (int64_t)((value ^ sign) - sign);
}

static uint64_t vp_reg_read(const VPAArch64CPU *cpu, uint32_t reg, int sp_allowed) {
    if (reg < 31u) return cpu->x[reg];
    return sp_allowed ? cpu->sp : 0;
}

static void vp_reg_write(VPAArch64CPU *cpu, uint32_t reg, uint64_t value, int is64, int sp_allowed) {
    if (!is64) value = (uint32_t)value;
    if (reg < 31u) cpu->x[reg] = value;
    else if (sp_allowed) cpu->sp = value;
}

static int vp_sysreg_read(VPAArch64CPU *cpu, uint16_t reg, uint64_t *value) {
    if (!cpu || !value) return 0;
    switch (reg) {
        case VP_SYS_CURRENTEL:   *value = ((uint64_t)cpu->current_el & 3u) << 2; return 1;
        case VP_SYS_SPSEL:       *value = cpu->sys.spsel & 1u; return 1;
        case VP_SYS_NZCV:        *value = cpu->sys.nzcv; return 1;
        case VP_SYS_DAIF:        *value = cpu->sys.daif; return 1;
        case VP_SYS_SCTLR_EL1:   *value = cpu->sys.sctlr_el1; return 1;
        case VP_SYS_TTBR0_EL1:   *value = cpu->sys.ttbr0_el1; return 1;
        case VP_SYS_TTBR1_EL1:   *value = cpu->sys.ttbr1_el1; return 1;
        case VP_SYS_TCR_EL1:     *value = cpu->sys.tcr_el1; return 1;
        case VP_SYS_SPSR_EL1:    *value = cpu->sys.spsr_el1; return 1;
        case VP_SYS_ELR_EL1:     *value = cpu->sys.elr_el1; return 1;
        case VP_SYS_SP_EL0:      *value = cpu->sys.sp_el0; return 1;
        case VP_SYS_ESR_EL1:     *value = cpu->sys.esr_el1; return 1;
        case VP_SYS_FAR_EL1:     *value = cpu->sys.far_el1; return 1;
        case VP_SYS_MAIR_EL1:    *value = cpu->sys.mair_el1; return 1;
        case VP_SYS_VBAR_EL1:    *value = cpu->sys.vbar_el1; return 1;
        case VP_SYS_TPIDR_EL0:   *value = cpu->sys.tpidr_el0; return 1;
        case VP_SYS_TPIDRRO_EL0: *value = cpu->sys.tpidrro_el0; return 1;
        case VP_SYS_TPIDR_EL1:   *value = cpu->sys.tpidr_el1; return 1;
        case VP_SYS_CNTFRQ_EL0:  *value = cpu->sys.cntfrq_el0; return 1;
        case VP_SYS_CNTPCT_EL0:
        case VP_SYS_CNTVCT_EL0:  *value = cpu->sys.counter_ticks; return 1;
        default: return 0;
    }
}

static int vp_sysreg_write(VPAArch64CPU *cpu, uint16_t reg, uint64_t value) {
    if (!cpu) return 0;
    switch (reg) {
        case VP_SYS_SPSEL:       cpu->sys.spsel = (uint32_t)(value & 1u); return 1;
        case VP_SYS_NZCV:        cpu->sys.nzcv = value & UINT64_C(0xF0000000); return 1;
        case VP_SYS_DAIF:        cpu->sys.daif = value & UINT64_C(0x3C0); return 1;
        case VP_SYS_SCTLR_EL1:   cpu->sys.sctlr_el1 = value; return 1;
        case VP_SYS_TTBR0_EL1:   cpu->sys.ttbr0_el1 = value; return 1;
        case VP_SYS_TTBR1_EL1:   cpu->sys.ttbr1_el1 = value; return 1;
        case VP_SYS_TCR_EL1:     cpu->sys.tcr_el1 = value; return 1;
        case VP_SYS_SPSR_EL1:    cpu->sys.spsr_el1 = value; return 1;
        case VP_SYS_ELR_EL1:     cpu->sys.elr_el1 = value; return 1;
        case VP_SYS_SP_EL0:      cpu->sys.sp_el0 = value; return 1;
        case VP_SYS_ESR_EL1:     cpu->sys.esr_el1 = value; return 1;
        case VP_SYS_FAR_EL1:     cpu->sys.far_el1 = value; return 1;
        case VP_SYS_MAIR_EL1:    cpu->sys.mair_el1 = value; return 1;
        case VP_SYS_VBAR_EL1:    cpu->sys.vbar_el1 = value; return 1;
        case VP_SYS_TPIDR_EL0:   cpu->sys.tpidr_el0 = value; return 1;
        case VP_SYS_TPIDRRO_EL0: cpu->sys.tpidrro_el0 = value; return 1;
        case VP_SYS_TPIDR_EL1:   cpu->sys.tpidr_el1 = value; return 1;
        case VP_SYS_CNTFRQ_EL0:  cpu->sys.cntfrq_el0 = value; return 1;
        default: return 0;
    }
}

static void vp_set_nzcv_addsub(
    VPAArch64CPU *cpu, uint64_t lhs, uint64_t rhs, uint64_t result, int is64, int subtract
) {
    const uint64_t mask = is64 ? UINT64_MAX : UINT64_C(0xFFFFFFFF);
    const uint64_t sign = is64 ? UINT64_C(1) << 63 : UINT64_C(1) << 31;
    lhs &= mask; rhs &= mask; result &= mask;
    const int n = (result & sign) != 0;
    const int z = result == 0;
    const int c = subtract ? lhs >= rhs : result < lhs;
    const int v = subtract ? (((lhs ^ rhs) & (lhs ^ result) & sign) != 0)
                           : (((~(lhs ^ rhs)) & (lhs ^ result) & sign) != 0);
    cpu->sys.nzcv = ((uint64_t)n << 31) | ((uint64_t)z << 30) |
                    ((uint64_t)c << 29) | ((uint64_t)v << 28);
}

static void vp_set_nzcv_logical(VPAArch64CPU *cpu, uint64_t result, int is64) {
    if (!is64) result = (uint32_t)result;
    cpu->sys.nzcv = ((uint64_t)((result >> (is64 ? 63u : 31u)) & 1u) << 31) |
                    ((uint64_t)(result == 0) << 30);
}

static int vp_condition_holds(const VPAArch64CPU *cpu, uint32_t condition) {
    const int n = (int)((cpu->sys.nzcv >> 31) & 1u);
    const int z = (int)((cpu->sys.nzcv >> 30) & 1u);
    const int c = (int)((cpu->sys.nzcv >> 29) & 1u);
    const int v = (int)((cpu->sys.nzcv >> 28) & 1u);
    switch (condition & 15u) {
        case 0: return z; case 1: return !z; case 2: return c; case 3: return !c;
        case 4: return n; case 5: return !n; case 6: return v; case 7: return !v;
        case 8: return c && !z; case 9: return !c || z; case 10: return n == v;
        case 11: return n != v; case 12: return !z && n == v; case 13: return z || n != v;
        case 14: return 1; default: return 0;
    }
}

static uint64_t vp_shift_register(uint64_t value, uint32_t type, uint32_t amount, int is64) {
    const uint32_t width = is64 ? 64u : 32u;
    if (!is64) value = (uint32_t)value;
    if (amount == 0) return value;
    if (type == 0u) return (value << amount) & (is64 ? UINT64_MAX : UINT64_C(0xFFFFFFFF));
    if (type == 1u) return value >> amount;
    if (type == 2u) return is64 ? (uint64_t)((int64_t)value >> amount)
                                : (uint32_t)((int32_t)value >> amount);
    amount %= width;
    return ((value >> amount) | (value << (width - amount))) &
           (is64 ? UINT64_MAX : UINT64_C(0xFFFFFFFF));
}

static int vp_decode_logical_immediate(
    uint32_t n, uint32_t immr, uint32_t imms, uint32_t width, uint64_t *mask_out
) {
    if (!mask_out || (width != 32u && width != 64u) || (width == 32u && n != 0u)) return 0;
    const uint32_t selector = (n << 6) | ((~imms) & 63u);
    int length = -1;
    for (int bit = 6; bit >= 1; bit--) {
        if (selector & (1u << bit)) { length = bit; break; }
    }
    if (length < 1) return 0;
    const uint32_t levels = (1u << (uint32_t)length) - 1u;
    const uint32_t s = imms & levels;
    const uint32_t r = immr & levels;
    if (s == levels) return 0;
    const uint32_t element_width = 1u << (uint32_t)length;
    if (element_width > width) return 0;
    const uint64_t element_mask = element_width == 64u
        ? UINT64_MAX : ((UINT64_C(1) << element_width) - 1u);
    uint64_t element = (UINT64_C(1) << (s + 1u)) - 1u;
    if (r != 0u) element = ((element >> r) | (element << (element_width - r))) & element_mask;
    uint64_t result = 0;
    for (uint32_t offset = 0; offset < width; offset += element_width) result |= element << offset;
    *mask_out = width == 32u ? (uint32_t)result : result;
    return 1;
}

static uint64_t vp_extend_register(uint64_t value, uint32_t option) {
    switch (option & 7u) {
        case 0: return (uint8_t)value;
        case 1: return (uint16_t)value;
        case 2: return (uint32_t)value;
        case 3: return value;
        case 4: return (uint64_t)(int64_t)(int8_t)value;
        case 5: return (uint64_t)(int64_t)(int16_t)value;
        case 6: return (uint64_t)(int64_t)(int32_t)value;
        default: return (uint64_t)(int64_t)value;
    }
}

static uint64_t vp_reverse_bits(uint64_t value, uint32_t width) {
    uint64_t result = 0;
    for (uint32_t bit = 0; bit < width; bit++) {
        result |= ((value >> bit) & 1u) << (width - 1u - bit);
    }
    return width == 32u ? (uint32_t)result : result;
}

static uint64_t vp_reverse_bytes(uint64_t value, uint32_t width, uint32_t container) {
    uint64_t result = 0;
    for (uint32_t base = 0; base < container; base += width) {
        for (uint32_t byte = 0; byte < width; byte += 8u) {
            result |= ((value >> (base + byte)) & UINT64_C(0xFF))
                      << (base + width - 8u - byte);
        }
    }
    return container == 32u ? (uint32_t)result : result;
}

static uint32_t vp_count_leading(uint64_t value, uint32_t width, int sign) {
    const uint64_t expected = sign ? (value >> (width - 1u)) & 1u : 0u;
    uint32_t count = 0;
    for (uint32_t bit = width; bit > 0; bit--) {
        if (((value >> (bit - 1u)) & 1u) != expected) break;
        count++;
    }
    return sign && count ? count - 1u : count;
}

static VPCPUStepResult vp_retire(VPAArch64CPU *cpu, uint64_t next_pc) {
    cpu->pc = next_pc;
    cpu->instructions_retired++;
    cpu->sys.counter_ticks++;
    return VP_CPU_STEP_OK;
}

void vp_aarch64_reset(VPAArch64CPU *cpu, uint64_t reset_vector) {
    if (!cpu) return;
    memset(cpu, 0, sizeof(*cpu));
    cpu->pc = reset_vector;
    cpu->current_el = 1;
    cpu->pstate = UINT64_C(0x5); /* EL1h. */
    cpu->sys.spsel = 1;
    cpu->sys.cntfrq_el0 = UINT64_C(24000000);
    cpu->sys.daif = UINT64_C(0x3C0);
}

void vp_aarch64_wake(VPAArch64CPU *cpu) {
    if (!cpu) return;
    cpu->waiting = 0;
}

VPCPUStepResult vp_aarch64_step(VPRuntime *runtime, VPAArch64CPU *cpu, uint32_t *instruction_out) {
    if (!runtime || !cpu) return VP_CPU_STEP_MEMORY_FAULT;
    if (cpu->halted) return VP_CPU_STEP_HALTED;
    if (cpu->waiting) return VP_CPU_STEP_WAITING;

    uint32_t insn = 0;
    if (vp_runtime_memory_read(runtime, cpu->pc, &insn, sizeof(insn)) != VP_STATUS_OK) {
        return VP_CPU_STEP_MEMORY_FAULT;
    }
    if (instruction_out) *instruction_out = insn;

    const uint64_t current_pc = cpu->pc;
    const uint64_t next_pc = current_pc + 4u;

    /* Architectural hints, including BTI and arm64e PAC/AUT stack hints. */
    if ((insn & UINT32_C(0xFFFFF01F)) == UINT32_C(0xD503201F) &&
        insn != UINT32_C(0xD503205F) && insn != UINT32_C(0xD503207F)) {
        return vp_retire(cpu, next_pc);
    }

    /* WFE / WFI complete, advance PC, then wait for a synthetic interrupt/event. */
    if (insn == UINT32_C(0xD503205F) || insn == UINT32_C(0xD503207F)) {
        cpu->waiting = 1;
        cpu->pc = next_pc;
        cpu->instructions_retired++;
        cpu->sys.counter_ticks++;
        return VP_CPU_STEP_WAITING;
    }

    /* CLREX / DSB / DMB / ISB. Ordering is implicit in the interpreter. */
    if ((insn & UINT32_C(0xFFFFF0FF)) == UINT32_C(0xD503305F) ||
        (insn & UINT32_C(0xFFFFF0FF)) == UINT32_C(0xD503309F) ||
        (insn & UINT32_C(0xFFFFF0FF)) == UINT32_C(0xD50330BF) ||
        (insn & UINT32_C(0xFFFFF0FF)) == UINT32_C(0xD50330DF)) {
        return vp_retire(cpu, next_pc);
    }

    /* MSR DAIFSet/DAIFClr, #imm4. */
    if ((insn & UINT32_C(0xFFFFF0FF)) == UINT32_C(0xD50340DF)) {
        const uint64_t imm = (insn >> 8) & 0xFu;
        cpu->sys.daif |= imm << 6;
        return vp_retire(cpu, next_pc);
    }
    if ((insn & UINT32_C(0xFFFFF0FF)) == UINT32_C(0xD50340FF)) {
        const uint64_t imm = (insn >> 8) & 0xFu;
        cpu->sys.daif &= ~(imm << 6);
        return vp_retire(cpu, next_pc);
    }

    /* MSR SPSel, #imm1. */
    if ((insn & UINT32_C(0xFFFFF0FF)) == UINT32_C(0xD50040BF)) {
        cpu->sys.spsel = (insn >> 8) & 1u;
        return vp_retire(cpu, next_pc);
    }

    /* MRS / MSR (register) for the early EL1 register set used by iBoot/XNU. */
    if ((insn & UINT32_C(0xFFE00000)) == UINT32_C(0xD5200000)) {
        const uint16_t sysreg = (uint16_t)((insn >> 5) & UINT32_C(0xFFFF));
        const uint32_t rt = insn & 31u;
        uint64_t value = 0;
        if (!vp_sysreg_read(cpu, sysreg, &value)) return VP_CPU_STEP_SYSTEM_REGISTER_FAULT;
        vp_reg_write(cpu, rt, value, 1, 0);
        return vp_retire(cpu, next_pc);
    }
    if ((insn & UINT32_C(0xFFE00000)) == UINT32_C(0xD5000000)) {
        const uint16_t sysreg = (uint16_t)((insn >> 5) & UINT32_C(0xFFFF));
        const uint32_t rt = insn & 31u;
        if (!vp_sysreg_write(cpu, sysreg, vp_reg_read(cpu, rt, 0))) {
            return VP_CPU_STEP_SYSTEM_REGISTER_FAULT;
        }
        return vp_retire(cpu, next_pc);
    }

    /* ERET. Only EL1 return state is modeled today. */
    if (insn == UINT32_C(0xD69F03E0)) {
        cpu->pc = cpu->sys.elr_el1;
        cpu->pstate = cpu->sys.spsr_el1;
        cpu->current_el = (uint32_t)((cpu->pstate >> 2) & 3u);
        cpu->instructions_retired++;
        cpu->sys.counter_ticks++;
        return VP_CPU_STEP_OK;
    }

    /* NyxBus host ABI: console (0x4E58) and RGBA framebuffer publication (0x4E59). */
    if ((insn & UINT32_C(0xFFE0001F)) == UINT32_C(0xD4000002)) {
        const uint32_t immediate = (insn >> 5) & UINT32_C(0xFFFF);
        if (immediate == UINT32_C(0x4E58)) {
            if (vp_runtime_console_write(runtime, cpu->x[0], (size_t)cpu->x[1]) != VP_STATUS_OK) {
                return VP_CPU_STEP_MEMORY_FAULT;
            }
            return vp_retire(cpu, next_pc);
        }
        if (immediate == UINT32_C(0x4E59)) {
            if (vp_runtime_publish_framebuffer(
                    runtime, cpu->x[0], (uint32_t)cpu->x[1], (uint32_t)cpu->x[2], (uint32_t)cpu->x[3]
                ) != VP_STATUS_OK) {
                return VP_CPU_STEP_MEMORY_FAULT;
            }
            return vp_retire(cpu, next_pc);
        }
        return VP_CPU_STEP_SYSTEM_REGISTER_FAULT;
    }

    /* HLT #imm16 */
    if ((insn & UINT32_C(0xFFE0001F)) == UINT32_C(0xD4400000)) {
        cpu->halted = 1;
        cpu->instructions_retired++;
        cpu->sys.counter_ticks++;
        return VP_CPU_STEP_HALTED;
    }

    /*
     * SVC #imm16. Darwin userspace uses X16 as the normal syscall selector.
     * This remains useful for userspace compatibility tests; real guest XNU
     * syscalls will be handled by XNU once the boot path reaches EL0.
     */
    if ((insn & UINT32_C(0xFFE0001F)) == UINT32_C(0xD4000001)) {
        uint64_t args[8];
        for (uint32_t i = 0; i < 8; i++) args[i] = cpu->x[i];
        uint64_t result = 0;
        const VPStatus status = vp_runtime_dispatch_syscall(runtime, cpu->x[16], args, &result);
        if (status != VP_STATUS_OK) return VP_CPU_STEP_SYSCALL_FAULT;
        cpu->x[0] = result;
        cpu->pc = next_pc;
        cpu->instructions_retired++;
        cpu->syscalls_retired++;
        cpu->sys.counter_ticks++;
        return VP_CPU_STEP_OK;
    }

    /* B / BL immediate. */
    const uint32_t branch_class = insn & UINT32_C(0xFC000000);
    if (branch_class == UINT32_C(0x14000000) || branch_class == UINT32_C(0x94000000)) {
        const int64_t offset = vp_sign_extend(insn & UINT32_C(0x03FFFFFF), 26) << 2;
        if (branch_class == UINT32_C(0x94000000)) cpu->x[30] = next_pc;
        cpu->pc = (uint64_t)((int64_t)current_pc + offset);
        cpu->instructions_retired++;
        cpu->sys.counter_ticks++;
        return VP_CPU_STEP_OK;
    }

    /* arm64e authenticated returns. Pointer authentication is identity until PAC keys are modeled. */
    if (insn == UINT32_C(0xD65F0BFF) || insn == UINT32_C(0xD65F0FFF)) {
        cpu->pc = cpu->x[30];
        cpu->instructions_retired++;
        cpu->sys.counter_ticks++;
        return VP_CPU_STEP_OK;
    }

    /* BR / BLR / RET Xn. */
    const uint32_t branch_reg = insn & UINT32_C(0xFFFFFC1F);
    if (branch_reg == UINT32_C(0xD61F0000) ||
        branch_reg == UINT32_C(0xD63F0000) ||
        branch_reg == UINT32_C(0xD65F0000)) {
        const uint32_t rn = (insn >> 5) & 31u;
        if (branch_reg == UINT32_C(0xD63F0000)) cpu->x[30] = next_pc;
        cpu->pc = vp_reg_read(cpu, rn, 0);
        cpu->instructions_retired++;
        cpu->sys.counter_ticks++;
        return VP_CPU_STEP_OK;
    }

    /* B.cond. */
    if ((insn & UINT32_C(0xFF000010)) == UINT32_C(0x54000000)) {
        const int64_t offset = vp_sign_extend((insn >> 5) & UINT32_C(0x7FFFF), 19) << 2;
        return vp_retire(
            cpu, vp_condition_holds(cpu, insn & 15u)
                ? (uint64_t)((int64_t)current_pc + offset) : next_pc
        );
    }

    /* CBZ / CBNZ, 32- and 64-bit. */
    if ((insn & UINT32_C(0x7E000000)) == UINT32_C(0x34000000)) {
        const int is64 = (int)((insn >> 31) & 1u);
        const int nonzero = (int)((insn >> 24) & 1u);
        const uint32_t rt = insn & 31u;
        uint64_t value = vp_reg_read(cpu, rt, 0);
        if (!is64) value = (uint32_t)value;
        const int take = nonzero ? value != 0 : value == 0;
        const int64_t offset = vp_sign_extend((insn >> 5) & UINT32_C(0x7FFFF), 19) << 2;
        return vp_retire(cpu, take ? (uint64_t)((int64_t)current_pc + offset) : next_pc);
    }

    /* TBZ / TBNZ. */
    if ((insn & UINT32_C(0x7E000000)) == UINT32_C(0x36000000)) {
        const uint32_t bit = (((insn >> 31) & 1u) << 5) | ((insn >> 19) & 31u);
        const int nonzero = (int)((insn >> 24) & 1u);
        const uint32_t rt = insn & 31u;
        const int bit_set = (int)((vp_reg_read(cpu, rt, 0) >> bit) & 1u);
        const int take = nonzero ? bit_set : !bit_set;
        const int64_t offset = vp_sign_extend((insn >> 5) & UINT32_C(0x3FFF), 14) << 2;
        return vp_retire(cpu, take ? (uint64_t)((int64_t)current_pc + offset) : next_pc);
    }

    /* ADR / ADRP. */
    const uint32_t adr_class = insn & UINT32_C(0x9F000000);
    if (adr_class == UINT32_C(0x10000000) || adr_class == UINT32_C(0x90000000)) {
        const uint64_t immlo = (insn >> 29) & 3u;
        const uint64_t immhi = (insn >> 5) & UINT32_C(0x7FFFF);
        const int64_t imm = vp_sign_extend((immhi << 2) | immlo, 21);
        const uint32_t rd = insn & 31u;
        uint64_t value;
        if (adr_class == UINT32_C(0x90000000)) {
            value = (uint64_t)(((int64_t)(current_pc & ~UINT64_C(0xFFF))) + (imm << 12));
        } else {
            value = (uint64_t)((int64_t)current_pc + imm);
        }
        vp_reg_write(cpu, rd, value, 1, 0);
        return vp_retire(cpu, next_pc);
    }

    /* EXTR, including the ROR-immediate alias when both source registers match. */
    if ((insn & UINT32_C(0x7F800000)) == UINT32_C(0x13800000)) {
        const int is64 = (int)((insn >> 31) & 1u);
        const uint32_t width = is64 ? 64u : 32u;
        const uint32_t n = (insn >> 22) & 1u;
        const uint32_t shift = (insn >> 10) & 63u;
        if (n != (uint32_t)is64 || shift >= width) return VP_CPU_STEP_UNIMPLEMENTED;
        const uint64_t high = vp_reg_read(cpu, (insn >> 5) & 31u, 0);
        const uint64_t low = vp_reg_read(cpu, (insn >> 16) & 31u, 0);
        const uint64_t mask = is64 ? UINT64_MAX : UINT64_C(0xFFFFFFFF);
        const uint64_t result = shift == 0u ? low & mask
            : ((low >> shift) | (high << (width - shift))) & mask;
        vp_reg_write(cpu, insn & 31u, result, is64, 0);
        return vp_retire(cpu, next_pc);
    }

    /* RBIT, REV16, REV32/REV64, CLZ, and CLS data-processing-one-source. */
    if ((insn & UINT32_C(0x7FE00000)) == UINT32_C(0x5AC00000)) {
        const int is64 = (int)((insn >> 31) & 1u);
        const uint32_t width = is64 ? 64u : 32u;
        const uint32_t opcode = (insn >> 10) & 0x3Fu;
        const uint64_t value = vp_reg_read(cpu, (insn >> 5) & 31u, 0);
        uint64_t result;
        if (opcode == 0u) result = vp_reverse_bits(value, width);
        else if (opcode == 1u) result = vp_reverse_bytes(value, 16u, width);
        else if (opcode == 2u) result = vp_reverse_bytes(value, 32u, width);
        else if (opcode == 3u && is64) result = vp_reverse_bytes(value, 64u, 64u);
        else if (opcode == 4u) result = vp_count_leading(value, width, 0);
        else if (opcode == 5u) result = vp_count_leading(value, width, 1);
        else return VP_CPU_STEP_UNIMPLEMENTED;
        vp_reg_write(cpu, insn & 31u, result, is64, 0);
        return vp_retire(cpu, next_pc);
    }

    /* LDR literal for W/X registers and signed LDRSW literal. */
    if ((insn & UINT32_C(0x3B000000)) == UINT32_C(0x18000000) &&
        ((insn >> 30) & 3u) <= 2u) {
        const uint32_t opc = (insn >> 30) & 3u;
        const int is64 = opc == 1u;
        const int is_signed_word = opc == 2u;
        const uint32_t rt = insn & 31u;
        const int64_t offset = vp_sign_extend((insn >> 5) & UINT32_C(0x7FFFF), 19) << 2;
        const uint64_t address = (uint64_t)((int64_t)current_pc + offset);
        uint64_t value = 0;
        if (vp_runtime_memory_read(runtime, address, &value, is64 ? 8u : 4u) != VP_STATUS_OK) {
            return VP_CPU_STEP_MEMORY_FAULT;
        }
        if (is_signed_word) value = (uint64_t)(int64_t)(int32_t)value;
        vp_reg_write(cpu, rt, value, is64 || is_signed_word, 0);
        return vp_retire(cpu, next_pc);
    }

    /* SBFM/UBFM aliases used for sign extension and immediate shifts. */
    const uint32_t bitfield_class = insn & UINT32_C(0x7F800000);
    if (bitfield_class == UINT32_C(0x13000000) || bitfield_class == UINT32_C(0x53000000)) {
        const int is64 = (int)((insn >> 31) & 1u);
        const uint32_t width = is64 ? 64u : 32u;
        const uint32_t immr = (insn >> 16) & 63u;
        const uint32_t imms = (insn >> 10) & 63u;
        if (((insn >> 22) & 1u) != (uint32_t)is64 || immr >= width || imms >= width) {
            return VP_CPU_STEP_UNIMPLEMENTED;
        }
        uint64_t source = vp_reg_read(cpu, (insn >> 5) & 31u, 0);
        if (!is64) source = (uint32_t)source;
        uint64_t result;
        if (imms == width - 1u) {
            result = bitfield_class == UINT32_C(0x13000000)
                ? (is64 ? (uint64_t)((int64_t)source >> immr)
                        : (uint32_t)((int32_t)source >> immr))
                : source >> immr;
        } else if (immr == 0u) {
            const uint32_t bits = imms + 1u;
            const uint64_t mask = bits == 64u ? UINT64_MAX : ((UINT64_C(1) << bits) - 1u);
            result = source & mask;
            if (bitfield_class == UINT32_C(0x13000000) && (result & (UINT64_C(1) << (bits - 1u)))) {
                result |= ~mask;
            }
        } else if (bitfield_class == UINT32_C(0x53000000) && imms + 1u == immr) {
            result = source << (width - immr);
        } else {
            return VP_CPU_STEP_UNIMPLEMENTED;
        }
        vp_reg_write(cpu, insn & 31u, result, is64, 0);
        return vp_retire(cpu, next_pc);
    }

    /* MOVN / MOVZ / MOVK (wide immediate), 32- and 64-bit. */
    const uint32_t wide_class = insn & UINT32_C(0x7F800000);
    if (wide_class == UINT32_C(0x12800000) || wide_class == UINT32_C(0x52800000) ||
        wide_class == UINT32_C(0x72800000)) {
        const int is64 = (int)((insn >> 31) & 1u);
        const uint32_t hw = (insn >> 21) & 3u;
        if (!is64 && hw > 1u) return VP_CPU_STEP_UNIMPLEMENTED;
        const uint32_t shift = hw * 16u;
        const uint64_t imm = (uint64_t)((insn >> 5) & UINT32_C(0xFFFF)) << shift;
        const uint32_t rd = insn & 31u;
        uint64_t value = wide_class == UINT32_C(0x12800000) ? ~imm : imm;
        if (wide_class == UINT32_C(0x72800000)) {
            const uint64_t mask = ~(UINT64_C(0xFFFF) << shift);
            value = (vp_reg_read(cpu, rd, 0) & mask) | imm;
        }
        vp_reg_write(cpu, rd, value, is64, 0);
        return vp_retire(cpu, next_pc);
    }

    /* ADD/SUB immediate, including ADDS/SUBS (CMP/CMN aliases). */
    const uint32_t addsub_class = insn & UINT32_C(0x7F000000);
    if (addsub_class == UINT32_C(0x11000000) || addsub_class == UINT32_C(0x31000000) ||
        addsub_class == UINT32_C(0x51000000) || addsub_class == UINT32_C(0x71000000)) {
        const int is64 = (int)((insn >> 31) & 1u);
        const int subtract = (int)((insn >> 30) & 1u);
        const int set_flags = (int)((insn >> 29) & 1u);
        uint64_t imm = (insn >> 10) & UINT32_C(0xFFF);
        if ((insn >> 22) & 1u) imm <<= 12;
        const uint32_t rn = (insn >> 5) & 31u;
        const uint32_t rd = insn & 31u;
        uint64_t lhs = vp_reg_read(cpu, rn, 1);
        if (!is64) lhs = (uint32_t)lhs;
        const uint64_t result = subtract ? lhs - imm : lhs + imm;
        if (set_flags) vp_set_nzcv_addsub(cpu, lhs, imm, result, is64, subtract);
        vp_reg_write(cpu, rd, result, is64, !set_flags);
        return vp_retire(cpu, next_pc);
    }

    /* ADD/SUB shifted register, including flag-setting forms. */
    const uint32_t addsub_reg_class = insn & UINT32_C(0x7F200000);
    if (addsub_reg_class == UINT32_C(0x0B000000) || addsub_reg_class == UINT32_C(0x2B000000) ||
        addsub_reg_class == UINT32_C(0x4B000000) || addsub_reg_class == UINT32_C(0x6B000000)) {
        const int is64 = (int)((insn >> 31) & 1u);
        const int subtract = (int)((insn >> 30) & 1u);
        const int set_flags = (int)((insn >> 29) & 1u);
        const uint32_t amount = (insn >> 10) & 63u;
        if (!is64 && amount >= 32u) return VP_CPU_STEP_UNIMPLEMENTED;
        uint64_t lhs = vp_reg_read(cpu, (insn >> 5) & 31u, 0);
        const uint64_t rhs = vp_shift_register(
            vp_reg_read(cpu, (insn >> 16) & 31u, 0), (insn >> 22) & 3u, amount, is64
        );
        if (!is64) lhs = (uint32_t)lhs;
        const uint64_t result = subtract ? lhs - rhs : lhs + rhs;
        if (set_flags) vp_set_nzcv_addsub(cpu, lhs, rhs, result, is64, subtract);
        vp_reg_write(cpu, insn & 31u, result, is64, 0);
        return vp_retire(cpu, next_pc);
    }

    /* ADD/SUB extended register, including UXTW/SXTW pointer arithmetic. */
    const uint32_t addsub_extended_class = insn & UINT32_C(0x7F200000);
    if (addsub_extended_class == UINT32_C(0x0B200000) ||
        addsub_extended_class == UINT32_C(0x2B200000) ||
        addsub_extended_class == UINT32_C(0x4B200000) ||
        addsub_extended_class == UINT32_C(0x6B200000)) {
        const int is64 = (int)((insn >> 31) & 1u);
        const int subtract = (int)((insn >> 30) & 1u);
        const int set_flags = (int)((insn >> 29) & 1u);
        const uint32_t amount = (insn >> 10) & 7u;
        if (amount > 4u) return VP_CPU_STEP_UNIMPLEMENTED;
        uint64_t lhs = vp_reg_read(cpu, (insn >> 5) & 31u, 1);
        uint64_t rhs = vp_extend_register(
            vp_reg_read(cpu, (insn >> 16) & 31u, 0), (insn >> 13) & 7u
        ) << amount;
        if (!is64) { lhs = (uint32_t)lhs; rhs = (uint32_t)rhs; }
        const uint64_t result = subtract ? lhs - rhs : lhs + rhs;
        if (set_flags) vp_set_nzcv_addsub(cpu, lhs, rhs, result, is64, subtract);
        vp_reg_write(cpu, insn & 31u, result, is64, !set_flags);
        return vp_retire(cpu, next_pc);
    }

    /* AND/ORR/EOR/ANDS logical immediate with ARM replicated-bitmask decoding. */
    const uint32_t logical_immediate_class = insn & UINT32_C(0x7F800000);
    if (logical_immediate_class == UINT32_C(0x12000000) ||
        logical_immediate_class == UINT32_C(0x32000000) ||
        logical_immediate_class == UINT32_C(0x52000000) ||
        logical_immediate_class == UINT32_C(0x72000000)) {
        const int is64 = (int)((insn >> 31) & 1u);
        uint64_t immediate = 0;
        if (!vp_decode_logical_immediate(
                (insn >> 22) & 1u, (insn >> 16) & 63u, (insn >> 10) & 63u,
                is64 ? 64u : 32u, &immediate
            )) return VP_CPU_STEP_UNIMPLEMENTED;
        const uint64_t lhs = vp_reg_read(cpu, (insn >> 5) & 31u, 0);
        const uint32_t operation = (insn >> 29) & 3u;
        uint64_t result = operation == 0u || operation == 3u ? lhs & immediate
                          : operation == 1u ? lhs | immediate : lhs ^ immediate;
        if (!is64) result = (uint32_t)result;
        if (operation == 3u) vp_set_nzcv_logical(cpu, result, is64);
        vp_reg_write(cpu, insn & 31u, result, is64, 0);
        return vp_retire(cpu, next_pc);
    }

    /* AND/ORR/EOR/ANDS shifted register (MOV/TST aliases included). */
    const uint32_t logical_class = insn & UINT32_C(0x7F200000);
    if (logical_class == UINT32_C(0x0A000000) || logical_class == UINT32_C(0x2A000000) ||
        logical_class == UINT32_C(0x4A000000) || logical_class == UINT32_C(0x6A000000)) {
        const int is64 = (int)((insn >> 31) & 1u);
        const uint32_t amount = (insn >> 10) & 63u;
        if (!is64 && amount >= 32u) return VP_CPU_STEP_UNIMPLEMENTED;
        const uint64_t lhs = vp_reg_read(cpu, (insn >> 5) & 31u, 0);
        const uint64_t rhs = vp_shift_register(
            vp_reg_read(cpu, (insn >> 16) & 31u, 0), (insn >> 22) & 3u, amount, is64
        );
        const uint32_t operation = (insn >> 29) & 3u;
        uint64_t result = operation == 0u || operation == 3u ? lhs & rhs
                          : operation == 1u ? lhs | rhs : lhs ^ rhs;
        if (!is64) result = (uint32_t)result;
        if (operation == 3u) vp_set_nzcv_logical(cpu, result, is64);
        vp_reg_write(cpu, insn & 31u, result, is64, 0);
        return vp_retire(cpu, next_pc);
    }

    /* UDIV/SDIV and register-variable LSL/LSR/ASR/ROR. */
    const uint32_t two_source_class = insn & UINT32_C(0x7FE0FC00);
    if (two_source_class == UINT32_C(0x1AC00800) || two_source_class == UINT32_C(0x1AC00C00) ||
        two_source_class == UINT32_C(0x1AC02000) || two_source_class == UINT32_C(0x1AC02400) ||
        two_source_class == UINT32_C(0x1AC02800) || two_source_class == UINT32_C(0x1AC02C00)) {
        const int is64 = (int)((insn >> 31) & 1u);
        uint64_t lhs = vp_reg_read(cpu, (insn >> 5) & 31u, 0);
        uint64_t rhs = vp_reg_read(cpu, (insn >> 16) & 31u, 0);
        if (!is64) { lhs = (uint32_t)lhs; rhs = (uint32_t)rhs; }
        uint64_t result = 0;
        if (two_source_class == UINT32_C(0x1AC00800)) {
            result = rhs == 0 ? 0 : lhs / rhs;
        } else if (two_source_class == UINT32_C(0x1AC00C00)) {
            if (rhs == 0) result = 0;
            else if (is64) {
                const int64_t dividend = (int64_t)lhs, divisor = (int64_t)rhs;
                result = dividend == INT64_MIN && divisor == -1 ? (uint64_t)INT64_MIN
                                                                  : (uint64_t)(dividend / divisor);
            } else {
                const int32_t dividend = (int32_t)lhs, divisor = (int32_t)rhs;
                result = dividend == INT32_MIN && divisor == -1 ? (uint32_t)INT32_MIN
                                                                  : (uint32_t)(dividend / divisor);
            }
        } else {
            const uint32_t type = two_source_class == UINT32_C(0x1AC02000) ? 0u
                                : two_source_class == UINT32_C(0x1AC02400) ? 1u
                                : two_source_class == UINT32_C(0x1AC02800) ? 2u : 3u;
            result = vp_shift_register(lhs, type, (uint32_t)(rhs & (is64 ? 63u : 31u)), is64);
        }
        vp_reg_write(cpu, insn & 31u, result, is64, 0);
        return vp_retire(cpu, next_pc);
    }

    /* CSEL/CSINC/CSINV/CSNEG conditional select family. */
    if ((insn & UINT32_C(0x1FE00000)) == UINT32_C(0x1A800000)) {
        const int is64 = (int)((insn >> 31) & 1u);
        const uint64_t lhs = vp_reg_read(cpu, (insn >> 5) & 31u, 0);
        const uint64_t rhs = vp_reg_read(cpu, (insn >> 16) & 31u, 0);
        const uint32_t operation = (((insn >> 30) & 1u) << 1) | ((insn >> 10) & 1u);
        uint64_t result;
        if (vp_condition_holds(cpu, (insn >> 12) & 15u)) result = lhs;
        else if (operation == 0u) result = rhs;
        else if (operation == 1u) result = rhs + 1u;
        else if (operation == 2u) result = ~rhs;
        else result = (uint64_t)(-(int64_t)rhs);
        vp_reg_write(cpu, insn & 31u, result, is64, 0);
        return vp_retire(cpu, next_pc);
    }

    /* MADD/MSUB, including MUL/MNEG aliases when Ra is XZR/WZR. */
    if ((insn & UINT32_C(0x7FE00000)) == UINT32_C(0x1B000000)) {
        const int is64 = (int)((insn >> 31) & 1u);
        uint64_t lhs = vp_reg_read(cpu, (insn >> 5) & 31u, 0);
        uint64_t rhs = vp_reg_read(cpu, (insn >> 16) & 31u, 0);
        uint64_t addend = vp_reg_read(cpu, (insn >> 10) & 31u, 0);
        if (!is64) { lhs = (uint32_t)lhs; rhs = (uint32_t)rhs; addend = (uint32_t)addend; }
        const uint64_t product = lhs * rhs;
        const uint64_t result = ((insn >> 15) & 1u) ? addend - product : addend + product;
        vp_reg_write(cpu, insn & 31u, result, is64, 0);
        return vp_retire(cpu, next_pc);
    }

    /* STP/LDP GPR pairs: signed offset, pre-index, and post-index. */
    const uint32_t pair_class = insn & UINT32_C(0x7FC00000);
    if (pair_class == UINT32_C(0x28800000) || pair_class == UINT32_C(0x28C00000) ||
        pair_class == UINT32_C(0x29000000) || pair_class == UINT32_C(0x29400000) ||
        pair_class == UINT32_C(0x29800000) || pair_class == UINT32_C(0x29C00000)) {
        const int is64 = (int)((insn >> 31) & 1u);
        const int is_load = (int)((insn >> 22) & 1u);
        const size_t width = is64 ? 8u : 4u;
        const int64_t offset = vp_sign_extend((insn >> 15) & 0x7Fu, 7) * (int64_t)width;
        const uint32_t rn = (insn >> 5) & 31u;
        const uint32_t rt = insn & 31u;
        const uint32_t rt2 = (insn >> 10) & 31u;
        const int post_index = pair_class == UINT32_C(0x28800000) || pair_class == UINT32_C(0x28C00000);
        const int pre_index = pair_class == UINT32_C(0x29800000) || pair_class == UINT32_C(0x29C00000);
        const uint64_t base = vp_reg_read(cpu, rn, 1);
        const uint64_t address = post_index ? base : (uint64_t)((int64_t)base + offset);
        if (is_load) {
            uint64_t first = 0, second = 0;
            if (vp_runtime_memory_read(runtime, address, &first, width) != VP_STATUS_OK ||
                vp_runtime_memory_read(runtime, address + width, &second, width) != VP_STATUS_OK) {
                return VP_CPU_STEP_MEMORY_FAULT;
            }
            vp_reg_write(cpu, rt, first, is64, 0);
            vp_reg_write(cpu, rt2, second, is64, 0);
        } else {
            const uint64_t first = vp_reg_read(cpu, rt, 0);
            const uint64_t second = vp_reg_read(cpu, rt2, 0);
            if (vp_runtime_memory_write(runtime, address, &first, width) != VP_STATUS_OK ||
                vp_runtime_memory_write(runtime, address + width, &second, width) != VP_STATUS_OK) {
                return VP_CPU_STEP_MEMORY_FAULT;
            }
        }
        if (pre_index || post_index) {
            vp_reg_write(cpu, rn, (uint64_t)((int64_t)base + offset), 1, 1);
        }
        return vp_retire(cpu, next_pc);
    }

    /* LDRSW/LDURSW: load a signed 32-bit word into an X register. */
    if ((insn & UINT32_C(0xFFC00000)) == UINT32_C(0xB9800000) ||
        (insn & UINT32_C(0xFFE00C00)) == UINT32_C(0xB8800000)) {
        const int unscaled = (insn & UINT32_C(0xFFE00C00)) == UINT32_C(0xB8800000);
        const int64_t offset = unscaled
            ? vp_sign_extend((insn >> 12) & 0x1FFu, 9)
            : (int64_t)(((insn >> 10) & UINT32_C(0xFFF)) * 4u);
        const uint64_t address = (uint64_t)((int64_t)vp_reg_read(cpu, (insn >> 5) & 31u, 1) + offset);
        uint32_t word = 0;
        if (vp_runtime_memory_read(runtime, address, &word, sizeof(word)) != VP_STATUS_OK) {
            return VP_CPU_STEP_MEMORY_FAULT;
        }
        vp_reg_write(cpu, insn & 31u, (uint64_t)(int64_t)(int32_t)word, 1, 0);
        return vp_retire(cpu, next_pc);
    }

    /* LDUR/STUR unscaled immediate for byte, halfword, W, and X registers. */
    const uint32_t unscaled_class = insn & UINT32_C(0x3B600C00);
    if (unscaled_class == UINT32_C(0x38000000) || unscaled_class == UINT32_C(0x38400000)) {
        const uint32_t size_log2 = (insn >> 30) & 3u;
        const size_t width = (size_t)1u << size_log2;
        const int is_load = unscaled_class == UINT32_C(0x38400000);
        const int64_t offset = vp_sign_extend((insn >> 12) & 0x1FFu, 9);
        const uint64_t address = (uint64_t)((int64_t)vp_reg_read(cpu, (insn >> 5) & 31u, 1) + offset);
        const uint32_t rt = insn & 31u;
        uint64_t value = vp_reg_read(cpu, rt, 0);
        const VPStatus status = is_load ? vp_runtime_memory_read(runtime, address, &value, width)
                                        : vp_runtime_memory_write(runtime, address, &value, width);
        if (status != VP_STATUS_OK) return VP_CPU_STEP_MEMORY_FAULT;
        if (is_load) vp_reg_write(cpu, rt, value, size_log2 == 3u, 0);
        return vp_retire(cpu, next_pc);
    }

    /* STR/LDR register offset with UXTW/LSL/SXTW/SXTX indexing. */
    if ((insn & UINT32_C(0x3B200C00)) == UINT32_C(0x38200800) &&
        ((insn >> 22) & 3u) <= 1u) {
        const uint32_t size_log2 = (insn >> 30) & 3u;
        const size_t width = (size_t)1u << size_log2;
        const int is_load = ((insn >> 22) & 3u) == 1u;
        const uint32_t option = (insn >> 13) & 7u;
        if (option != 2u && option != 3u && option != 6u && option != 7u) {
            return VP_CPU_STEP_UNIMPLEMENTED;
        }
        uint64_t offset = vp_extend_register(vp_reg_read(cpu, (insn >> 16) & 31u, 0), option);
        if ((insn >> 12) & 1u) offset <<= size_log2;
        const uint64_t address = vp_reg_read(cpu, (insn >> 5) & 31u, 1) + offset;
        const uint32_t rt = insn & 31u;
        uint64_t value = vp_reg_read(cpu, rt, 0);
        const VPStatus status = is_load ? vp_runtime_memory_read(runtime, address, &value, width)
                                        : vp_runtime_memory_write(runtime, address, &value, width);
        if (status != VP_STATUS_OK) return VP_CPU_STEP_MEMORY_FAULT;
        if (is_load) vp_reg_write(cpu, rt, value, size_log2 == 3u, 0);
        return vp_retire(cpu, next_pc);
    }

    /* STR/LDR unsigned immediate for byte, halfword, W, and X registers. */
    if ((insn & UINT32_C(0x3B000000)) == UINT32_C(0x39000000) &&
        ((insn >> 22) & 3u) <= 1u) {
        const uint32_t size_log2 = (insn >> 30) & 3u;
        const size_t width = (size_t)1u << size_log2;
        const int is_load = ((insn >> 22) & 3u) == 1u;
        const uint64_t address = vp_reg_read(cpu, (insn >> 5) & 31u, 1) +
                                 (((insn >> 10) & UINT32_C(0xFFF)) * width);
        const uint32_t rt = insn & 31u;
        uint64_t value = vp_reg_read(cpu, rt, 0);
        const VPStatus status = is_load ? vp_runtime_memory_read(runtime, address, &value, width)
                                        : vp_runtime_memory_write(runtime, address, &value, width);
        if (status != VP_STATUS_OK) return VP_CPU_STEP_MEMORY_FAULT;
        if (is_load) vp_reg_write(cpu, rt, value, size_log2 == 3u, 0);
        return vp_retire(cpu, next_pc);
    }

    return VP_CPU_STEP_UNIMPLEMENTED;
}
