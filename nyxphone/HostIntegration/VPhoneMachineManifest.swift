import Foundation

/// Portable host-side representation of the vphone600ap machine.
/// It deliberately does not import Virtualization.framework.
public struct VPhoneMachineManifest: Codable, Sendable, Equatable {
    public struct Screen: Codable, Sendable, Equatable {
        public var width: UInt32
        public var height: UInt32
        public var pixelsPerInch: UInt32
        public var scale: Double

        public static let iPhone = Screen(width: 1290, height: 2796, pixelsPerInch: 460, scale: 3.0)
    }

    public struct Firmware: Codable, Sendable, Equatable {
        public var bootROM: String
        public var sepROM: String
        public var sepStorage: String
        public var nvram: String
        public var disk: String
        public var machineIdentifier: String
    }

    public var platformType: String
    public var cpuCount: UInt32
    public var guestPhysicalMemorySize: UInt64
    public var screen: Screen
    public var firmware: Firmware

    public init(
        platformType: String = "vresearch101",
        cpuCount: UInt32 = 8,
        guestPhysicalMemorySize: UInt64 = 8 * 1024 * 1024 * 1024,
        screen: Screen = .iPhone,
        firmware: Firmware
    ) {
        self.platformType = platformType
        self.cpuCount = cpuCount
        self.guestPhysicalMemorySize = guestPhysicalMemorySize
        self.screen = screen
        self.firmware = firmware
    }
}

public enum VPhoneMachineManifestError: Error, LocalizedError {
    case unsupportedPlatform(String)
    case invalidCPUCount
    case invalidMemorySize
    case missingFirmware(String)

    public var errorDescription: String? {
        switch self {
        case .unsupportedPlatform(let value): "Unsupported virtual-phone platform: \(value)"
        case .invalidCPUCount: "The virtual phone must expose at least one CPU."
        case .invalidMemorySize: "The virtual phone guest-physical memory size is invalid."
        case .missingFirmware(let path): "Required virtual-phone firmware is missing: \(path)"
        }
    }
}

extension VPhoneMachineManifest {
    public func validate(relativeTo root: URL, fileManager: FileManager = .default) throws {
        guard platformType == "vresearch101" else {
            throw VPhoneMachineManifestError.unsupportedPlatform(platformType)
        }
        guard cpuCount > 0 else { throw VPhoneMachineManifestError.invalidCPUCount }
        guard guestPhysicalMemorySize >= 1024 * 1024 * 1024 else {
            throw VPhoneMachineManifestError.invalidMemorySize
        }

        for path in [firmware.bootROM, firmware.sepROM, firmware.sepStorage, firmware.nvram, firmware.disk, firmware.machineIdentifier] {
            guard fileManager.fileExists(atPath: root.appendingPathComponent(path).path) else {
                throw VPhoneMachineManifestError.missingFirmware(path)
            }
        }
    }
}
