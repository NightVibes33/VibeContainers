# Third-party sources

## VibeContainers

- Source: https://github.com/NightVibes33/VibeContainers
- Commit: current workflow checkout (`$GITHUB_SHA`)
- License: AGPL-3.0
- Purpose: native iPhone/iPad host UI, imports, storage, diagnostics, and unsigned IPA packaging.
- Integration: authoritative host repository; NyxPhone sources are additive.

## Nyxian

- Source: https://github.com/emexlab/Nyxian
- Commit: `7488333d32aab81fa01437968bfdef7bde1771f4`
- License: see `Kernel/Nyxian/LICENSE`.
- Purpose: userspace microkernel/ksurface ABI research and guest compatibility surface.
- Integration: fetched and commit-verified by CI.

## vphone-cli

- Source: https://github.com/Lakr233/vphone-cli
- Commit: `2af884b56c4d9044cdfad8ac94f034ec767d0fb3`
- License: MIT
- Purpose: firmware, custom-firmware, boot-component, and jailbreak research only. Its macOS Virtualization.framework host is not imported.

## vphone-aio

- Source: https://github.com/34306/vphone-aio
- Commit: `1db79dccd95391d6247c41f3cc4eac523567f295`
- Purpose: reference distribution only; no prebuilt archive is imported.

## TrollStore command contract

- Source: https://github.com/opa334/TrollStore
- Commit: `88424f683b2a08f34a3f88985f790f97d84ce1df`
- License: BSD-3-Clause
- Purpose: authoritative install/uninstall/open helper command semantics.
- Integration: no privileged binary is copied; the compatible command boundary
  is implemented against VibeContainers' private guest runtime.
