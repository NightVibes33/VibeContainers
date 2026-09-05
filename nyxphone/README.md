# ViPhone

ViPhone is an iPhone/iPad-only native physical-device virtual phone. The native VibeContainers host links a purpose-built NyxRuntime interpreter and integrates the pinned Nyxian userspace-kernel surface. It does not use QEMU, Virtualization.framework, or a companion computer.

Current milestone: M2 EL1-to-EL0 transition and nyxinit userspace execution through the NyxRuntime interpreter.

## Source layout

- `Host/VibeContainers`: pinned native iOS/iPadOS host application.
- `Runtime`: NyxRuntime public ABI and specialized AArch64 interpreter core.
- `Kernel/Nyxian`: pinned Nyxian source and ksurface ABI donor.
- `HostIntegration`: Swift bridge and diagnostics integrated into the host target.
- `VPhoneResearchKit`: metadata-only home for transferable firmware research.

Apple firmware is never stored in this repository. Future firmware preparation accepts only user-supplied IPSWs.

## Nyxian TrollStore workspace

NyxPhone includes a TrollStore-style workspace that is private to the host app.
It uses VibeContainers' real IPA extractor, per-app containers, Mach-O
preparation, entitlement mediation, JIT/JIT-less signing, and launch lifecycle.
It can import, persist, launch, remove, and export supported decrypted arm64
IPAs. A source-built `NyxValidation.ipa` is embedded in every CI artifact so the
same install path can be exercised without an external download.

The workspace is informed by the pinned `34306/vphone-aio` guest image and
launcher. That repository publishes TrollStore only inside its multi-part
prebuilt guest, not as reusable source files, so NyxPhone verifies its pinned
launcher provenance without copying the 12 GB image into this repository.

This does not register TrollStore or guest apps with the physical device's
Apple SpringBoard. Physical-device installation of the unsigned NyxPhone IPA
still requires an authorized signing/install method.
