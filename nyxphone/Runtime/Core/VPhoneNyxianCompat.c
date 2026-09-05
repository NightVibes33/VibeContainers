#include "VPhoneKernelSurface.h"
#include "ksurface_abi.h"

/* Build-time ABI lock against the pinned Nyxian source tree. */
_Static_assert(VP_NYX_SYS_GETTASK == SYS_gettask, "Nyxian SYS_gettask ABI drift");
_Static_assert(VP_NYX_SYS_PROCPATH == SYS_procpath, "Nyxian SYS_procpath ABI drift");
_Static_assert(VP_NYX_SYS_HANDOFFEP == SYS_handoffep, "Nyxian SYS_handoffep ABI drift");
_Static_assert(VP_NYX_SYS_WAITTASK == SYS_waittask, "Nyxian SYS_waittask ABI drift");
_Static_assert(VP_NYX_SYS_PECTL == SYS_pectl, "Nyxian SYS_pectl ABI drift");
_Static_assert(VP_NYX_SYS_SIGN == SYS_sign, "Nyxian SYS_sign ABI drift");
_Static_assert(VP_PECTL_CATEGORY_USERSPACE == kPECTLCategoryUserspace, "Nyxian userspace category ABI drift");
_Static_assert(VP_PECTL_CATEGORY_MISC == kPECTLCategoryMisceleanous, "Nyxian misc category ABI drift");
_Static_assert(VP_PECTL_USERSPACE_GETMODE == kPECTLUserspaceGetMode, "Nyxian get-mode ABI drift");
_Static_assert(VP_PECTL_MISC_GETBUILDTYPE == kPECTLMisceleanousGetBuildType, "Nyxian build-type ABI drift");

int vp_nyxian_abi_compatible(void) {
    return 1;
}
