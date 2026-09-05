import Foundation
import VPhoneRuntimeCore

public enum VirtualPhoneSessionError: Error, LocalizedError {
    case runtimeCreationFailed
    case kernelSurfaceCreationFailed
    case invalidBootSet
    case runtimeFailure(Int32)

    public var errorDescription: String? {
        switch self {
        case .runtimeCreationFailed:
            "Could not create the native virtual-phone runtime."
        case .kernelSurfaceCreationFailed:
            "Could not attach the Nyxian-compatible userspace kernel surface."
        case .invalidBootSet:
            "The imported boot set is incomplete."
        case .runtimeFailure(let code):
            "Virtual-phone runtime failed with status \(code)."
        }
    }
}

public struct VPhoneBootAddresses: Sendable, Equatable {
    /// vresearch101 decoded iBoot base from the pinned vphone-cli research.
    public var iBoot: UInt64 = 0x7006_C000
    public var kernelcache: UInt64 = 0x8000_0000
    public var deviceTree: UInt64 = 0x9000_0000
    public var trustCache: UInt64 = 0x9100_0000
    public var ramdisk: UInt64 = 0xA000_0000
    public var entry: UInt64 = 0x7006_C000

    public init() {}
}

public struct VPhoneBootArtifacts: Sendable {
    public var iBoot: Data
    public var kernelcache: Data?
    public var deviceTree: Data?
    public var trustCache: Data?
    public var ramdisk: Data?

    public init(
        iBoot: Data,
        kernelcache: Data? = nil,
        deviceTree: Data? = nil,
        trustCache: Data? = nil,
        ramdisk: Data? = nil
    ) {
        self.iBoot = iBoot
        self.kernelcache = kernelcache
        self.deviceTree = deviceTree
        self.trustCache = trustCache
        self.ramdisk = ramdisk
    }
}

/// VibeContainers-facing owner for one standalone virtual phone.
///
/// Guest AArch64 executes in the custom interpreter and SVC instructions are
/// intercepted by the attached Nyxian-compatible userspace microkernel. The
/// session does not launch a patched guest Mach-O through LiveContainer and it
/// has no QEMU, macOS Virtualization.framework or companion-PC dependency.
public final class VirtualPhoneSession: @unchecked Sendable {
    public let manifest: VPhoneMachineManifest
    var runtime: OpaquePointer?
    private var kernelSurface: OpaquePointer?

    public init(manifest: VPhoneMachineManifest) throws {
        self.manifest = manifest
        var config = VPMachineConfig(
            cpu_count: manifest.cpuCount,
            guest_physical_memory_size: manifest.guestPhysicalMemorySize,
            screen_width: manifest.screen.width,
            screen_height: manifest.screen.height,
            pixels_per_inch: manifest.screen.pixelsPerInch,
            screen_scale: manifest.screen.scale
        )
        guard let handle = vp_runtime_create(&config) else {
            throw VirtualPhoneSessionError.runtimeCreationFailed
        }
        runtime = handle
        guard let surface = vp_ksurface_attach(handle) else {
            vp_runtime_destroy(handle)
            runtime = nil
            throw VirtualPhoneSessionError.kernelSurfaceCreationFailed
        }
        kernelSurface = surface
    }

    deinit {
        if let kernelSurface { vp_ksurface_destroy(kernelSurface) }
        if let runtime { vp_runtime_destroy(runtime) }
    }

    public var state: UInt32 {
        guard let runtime else { return UInt32(VP_RUNTIME_FAILED.rawValue) }
        return UInt32(vp_runtime_state(runtime).rawValue)
    }

    public var isWaiting: Bool {
        state == UInt32(VP_RUNTIME_WAITING.rawValue)
    }

    public var isPaused: Bool {
        state == UInt32(VP_RUNTIME_PAUSED.rawValue)
    }

    public var committedGuestBytes: UInt64 {
        guard let runtime else { return 0 }
        return vp_runtime_committed_bytes(runtime)
    }

    public var instructionsRetired: UInt64 {
        guard let runtime else { return 0 }
        return vp_runtime_instructions_retired(runtime)
    }

    public var syscallsHandled: UInt64 {
        guard let kernelSurface else { return 0 }
        return vp_ksurface_syscalls_handled(kernelSurface)
    }

    public var syscallsRejected: UInt64 {
        guard let kernelSurface else { return 0 }
        return vp_ksurface_syscalls_rejected(kernelSurface)
    }

    public func writeGuestPhysicalMemory(address: UInt64, data: Data) throws {
        guard let runtime else { throw VirtualPhoneSessionError.runtimeCreationFailed }
        let status = data.withUnsafeBytes { bytes in
            vp_runtime_memory_write(runtime, address, bytes.baseAddress, bytes.count)
        }
        guard status == VP_STATUS_OK else {
            throw VirtualPhoneSessionError.runtimeFailure(Int32(status.rawValue))
        }
    }

    public func readGuestPhysicalMemory(address: UInt64, count: Int) throws -> Data {
        guard let runtime else { throw VirtualPhoneSessionError.runtimeCreationFailed }
        var data = Data(count: count)
        let status = data.withUnsafeMutableBytes { bytes in
            vp_runtime_memory_read(runtime, address, bytes.baseAddress, bytes.count)
        }
        guard status == VP_STATUS_OK else {
            throw VirtualPhoneSessionError.runtimeFailure(Int32(status.rawValue))
        }
        return data
    }

    public func loadImage(_ image: Data, at guestAddress: UInt64) throws {
        try writeGuestPhysicalMemory(address: guestAddress, data: image)
    }

    /// Stages a complete Apple boot set using runtime ABI v3. Optional images
    /// are represented as empty C descriptors; iBoot is mandatory and contains
    /// the reset vector by default.
    public func stageBootArtifacts(
        _ artifacts: VPhoneBootArtifacts,
        addresses: VPhoneBootAddresses = .init()
    ) throws {
        guard let runtime else { throw VirtualPhoneSessionError.runtimeCreationFailed }
        let kernelcache = artifacts.kernelcache ?? Data()
        let deviceTree = artifacts.deviceTree ?? Data()
        let trustCache = artifacts.trustCache ?? Data()
        let ramdisk = artifacts.ramdisk ?? Data()

        let status: VPStatus = artifacts.iBoot.withUnsafeBytes { ibootBytes in
            kernelcache.withUnsafeBytes { kernelBytes in
                deviceTree.withUnsafeBytes { deviceTreeBytes in
                    trustCache.withUnsafeBytes { trustBytes in
                        ramdisk.withUnsafeBytes { ramdiskBytes in
                            var layout = VPBootImageLayout(
                                iboot: VPBootImage(
                                    bytes: ibootBytes.baseAddress,
                                    length: ibootBytes.count,
                                    guest_address: addresses.iBoot
                                ),
                                kernelcache: VPBootImage(
                                    bytes: kernelBytes.baseAddress,
                                    length: kernelBytes.count,
                                    guest_address: addresses.kernelcache
                                ),
                                device_tree: VPBootImage(
                                    bytes: deviceTreeBytes.baseAddress,
                                    length: deviceTreeBytes.count,
                                    guest_address: addresses.deviceTree
                                ),
                                trust_cache: VPBootImage(
                                    bytes: trustBytes.baseAddress,
                                    length: trustBytes.count,
                                    guest_address: addresses.trustCache
                                ),
                                ramdisk: VPBootImage(
                                    bytes: ramdiskBytes.baseAddress,
                                    length: ramdiskBytes.count,
                                    guest_address: addresses.ramdisk
                                ),
                                entry_address: addresses.entry
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

    public func setEntryPoint(_ guestAddress: UInt64) throws {
        guard let runtime else { throw VirtualPhoneSessionError.runtimeCreationFailed }
        let status = vp_runtime_set_boot_vector(runtime, guestAddress)
        guard status == VP_STATUS_OK else {
            throw VirtualPhoneSessionError.runtimeFailure(Int32(status.rawValue))
        }
    }

    public func setInstructionBudget(_ count: UInt64) {
        guard let runtime else { return }
        vp_runtime_set_instruction_budget(runtime, count)
    }

    /// Runs synchronously; callers should dispatch guest execution away from
    /// the main actor. Budget exhaustion and WFI/WFE are cooperative yields,
    /// not crashes. Both preserve the guest CPU state for the next run.
    public func boot() throws {
        guard let runtime else { throw VirtualPhoneSessionError.runtimeCreationFailed }
        let status = vp_runtime_boot(runtime)
        guard status == VP_STATUS_OK ||
              status == VP_STATUS_BUDGET_EXHAUSTED ||
              status == VP_STATUS_GUEST_WAITING else {
            throw VirtualPhoneSessionError.runtimeFailure(Int32(status.rawValue))
        }
    }

    /// Delivers the host-side event used to wake WFI/WFE. Interrupt-controller
    /// devices will call the same runtime primitive once their IRQ model lands.
    public func signalEvent() throws {
        guard let runtime else { throw VirtualPhoneSessionError.runtimeCreationFailed }
        let status = vp_runtime_signal_event(runtime)
        guard status == VP_STATUS_OK else {
            throw VirtualPhoneSessionError.runtimeFailure(Int32(status.rawValue))
        }
    }

    public func stop() {
        guard let runtime else { return }
        _ = vp_runtime_stop(runtime)
    }
}
