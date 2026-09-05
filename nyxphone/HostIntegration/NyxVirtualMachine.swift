import Foundation

/// ViPhone-facing Swift owner for one NyxRuntime interpreter instance.
public final class NyxVirtualMachine: @unchecked Sendable {
    private let session: VirtualPhoneSession

    public init(manifest: VPhoneMachineManifest) throws {
        session = try VirtualPhoneSession(manifest: manifest)
    }

    public var state: UInt32 { session.state }
    public var committedGuestBytes: UInt64 { session.committedGuestBytes }
    public var instructionsRetired: UInt64 { session.instructionsRetired }
    public var syscallsHandled: UInt64 { session.syscallsHandled }
    public var syscallsRejected: UInt64 { session.syscallsRejected }

    public func stageBootArtifacts(
        _ artifacts: VPhoneBootArtifacts,
        addresses: VPhoneBootAddresses = .init()
    ) throws {
        try session.stageBootArtifacts(artifacts, addresses: addresses)
    }

    public func boot() throws { try session.boot() }
    public func stop() { session.stop() }
}
