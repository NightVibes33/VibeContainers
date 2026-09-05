import Foundation
import VPhoneRuntimeCore

/// The Apple boot artifacts resolved from a user-imported IPSW after the
/// vphone-derived patch pipeline has produced bootable copies. No Apple bytes
/// are compiled into ViPhone; every Data value is supplied at runtime.
public struct VPhoneBootSet: Sendable {
    public struct Artifact: Sendable {
        public let data: Data
        public let guestAddress: UInt64

        public init(data: Data, guestAddress: UInt64) {
            self.data = data
            self.guestAddress = guestAddress
        }
    }

    public let iBoot: Artifact
    public let kernelcache: Artifact
    public let deviceTree: Artifact
    public let trustCache: Artifact
    public let ramdisk: Artifact
    public let entryAddress: UInt64

    public init(
        iBoot: Artifact,
        kernelcache: Artifact,
        deviceTree: Artifact,
        trustCache: Artifact,
        ramdisk: Artifact,
        entryAddress: UInt64
    ) {
        self.iBoot = iBoot
        self.kernelcache = kernelcache
        self.deviceTree = deviceTree
        self.trustCache = trustCache
        self.ramdisk = ramdisk
        self.entryAddress = entryAddress
    }
}

extension VirtualPhoneSession {
    /// Copies a complete patched Apple boot set into guest-physical memory and
    /// selects its entry point. `vp_runtime_stage_boot_images` consumes all
    /// pointers synchronously, so the Data backing stores only need to remain
    /// pinned for the duration of this call.
    public func stageBootSet(_ bootSet: VPhoneBootSet) throws {
        guard let runtime else {
            throw VirtualPhoneSessionError.runtimeCreationFailed
        }
        guard !bootSet.iBoot.data.isEmpty,
              !bootSet.kernelcache.data.isEmpty,
              !bootSet.deviceTree.data.isEmpty,
              !bootSet.trustCache.data.isEmpty,
              !bootSet.ramdisk.data.isEmpty else {
            throw VirtualPhoneSessionError.invalidBootSet
        }

        let status: VPStatus = bootSet.iBoot.data.withUnsafeBytes { iBootBytes in
            bootSet.kernelcache.data.withUnsafeBytes { kernelBytes in
                bootSet.deviceTree.data.withUnsafeBytes { deviceTreeBytes in
                    bootSet.trustCache.data.withUnsafeBytes { trustCacheBytes in
                        bootSet.ramdisk.data.withUnsafeBytes { ramdiskBytes in
                            var layout = VPBootImageLayout(
                                iboot: VPBootImage(
                                    bytes: iBootBytes.baseAddress,
                                    length: iBootBytes.count,
                                    guest_address: bootSet.iBoot.guestAddress
                                ),
                                kernelcache: VPBootImage(
                                    bytes: kernelBytes.baseAddress,
                                    length: kernelBytes.count,
                                    guest_address: bootSet.kernelcache.guestAddress
                                ),
                                device_tree: VPBootImage(
                                    bytes: deviceTreeBytes.baseAddress,
                                    length: deviceTreeBytes.count,
                                    guest_address: bootSet.deviceTree.guestAddress
                                ),
                                trust_cache: VPBootImage(
                                    bytes: trustCacheBytes.baseAddress,
                                    length: trustCacheBytes.count,
                                    guest_address: bootSet.trustCache.guestAddress
                                ),
                                ramdisk: VPBootImage(
                                    bytes: ramdiskBytes.baseAddress,
                                    length: ramdiskBytes.count,
                                    guest_address: bootSet.ramdisk.guestAddress
                                ),
                                entry_address: bootSet.entryAddress
                            )
                            return vp_runtime_stage_boot_images(runtime, &layout)
                        }
                    }
                }
            }
        }

        guard status == VP_STATUS_OK else {
            throw VirtualPhoneSessionError.runtimeFailure(Int32(status.rawValue))
        }
    }
}
