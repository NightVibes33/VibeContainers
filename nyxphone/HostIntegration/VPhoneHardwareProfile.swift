import Foundation

/// Values used by Apple's PV=3 `vresearch101` virtual-iPhone hardware model.
/// These are machine-description metadata, not a claim that iOS exposes
/// Virtualization.framework to third-party apps.
public struct VPhoneHardwareProfile: Codable, Sendable, Equatable {
    public var platformVersion: UInt32
    public var boardID: UInt32
    public var isa: UInt64
    public var chipID: UInt32

    public static let vresearch101 = VPhoneHardwareProfile(
        platformVersion: 3,
        boardID: 0x90,
        isa: 2,
        chipID: 0xFE01
    )
}
