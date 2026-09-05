#ifndef VPHONE_AARCH64_H
#define VPHONE_AARCH64_H

#include "VPhoneRuntimeCore.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    uint64_t sctlr_el1;
    uint64_t ttbr0_el1;
    uint64_t ttbr1_el1;
    uint64_t tcr_el1;
    uint64_t mair_el1;
    uint64_t vbar_el1;
    uint64_t esr_el1;
    uint64_t far_el1;
    uint64_t elr_el1;
    uint64_t spsr_el1;
    uint64_t sp_el0;
    uint64_t tpidr_el0;
    uint64_t tpidrro_el0;
    uint64_t tpidr_el1;
    uint64_t cntfrq_el0;
    uint64_t counter_ticks;
    uint64_t daif;
    uint64_t nzcv;
    uint32_t spsel;
} VPAArch64SystemRegisters;

typedef struct {
    uint64_t x[31];
    uint64_t sp;
    uint64_t pc;
    uint64_t pstate;
    VPAArch64SystemRegisters sys;
    uint64_t instructions_retired;
    uint64_t syscalls_retired;
    uint32_t current_el;
    uint32_t waiting;
    uint32_t halted;
} VPAArch64CPU;

typedef enum {
    VP_CPU_STEP_OK = 0,
    VP_CPU_STEP_HALTED = 1,
    VP_CPU_STEP_MEMORY_FAULT = 2,
    VP_CPU_STEP_UNIMPLEMENTED = 3,
    VP_CPU_STEP_SYSCALL_FAULT = 4,
    VP_CPU_STEP_WAITING = 5,
    VP_CPU_STEP_SYSTEM_REGISTER_FAULT = 6,
} VPCPUStepResult;

void vp_aarch64_reset(VPAArch64CPU *cpu, uint64_t reset_vector);
void vp_aarch64_wake(VPAArch64CPU *cpu);
VPCPUStepResult vp_aarch64_step(VPRuntime *runtime, VPAArch64CPU *cpu, uint32_t *instruction_out);

#ifdef __cplusplus
}
#endif

#endif
