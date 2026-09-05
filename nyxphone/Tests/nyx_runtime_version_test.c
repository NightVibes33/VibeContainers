#include "../Runtime/include/NyxRuntime.h"
#include <stdio.h>
#include <string.h>

int main(void) {
    const char *version = nyx_runtime_version();
    if (!version || strcmp(version, "NyxRuntime/0.2-interpreter") != 0) return 1;
    if (nyx_runtime_abi_version() != NYX_RUNTIME_ABI_VERSION) return 2;
    puts(version);
    return 0;
}
