import Foundation

/// Implements TrollStore's install/uninstall/open command boundary without
/// escaping the VibeContainers sandbox. This replaces the upstream root-persona
/// helper and physical SpringBoard registration with the existing guest runtime.
@MainActor
final class TrollStoreCompatibilityBridge {
    static let shared = TrollStoreCompatibilityBridge()

    enum Command: Equatable {
        case install(URL)
        case uninstall(String)
        case open(String)
    }

    struct Result: Equatable {
        let status: Int32
        let message: String
        var succeeded: Bool { status == 0 }
    }

    private init() {}

    func execute(_ command: Command) async -> Result {
        switch command {
        case .install(let archive):
            let ext = archive.pathExtension.lowercased()
            guard ext == "ipa" || ext == "tipa" else {
                return Result(status: 166, message: "Expected a .ipa or .tipa archive.")
            }
            await GuestInstaller.shared.installIPA(at: archive)
            switch GuestInstaller.shared.sideload {
            case .installed(let identifier):
                return Result(status: 0, message: identifier)
            case .failed(let reason):
                return Result(status: 1, message: reason)
            default:
                return Result(status: 1, message: "Installation did not reach a final state.")
            }

        case .uninstall(let identifier):
            guard GuestContainerStore.shared.container(for: identifier) != nil else {
                return Result(status: 167, message: "No installed container for \(identifier).")
            }
            PackageStore.shared.remove(identifier)
            return Result(status: 0, message: identifier)

        case .open(let identifier):
            guard let container = GuestContainerStore.shared.container(for: identifier) else {
                return Result(status: 167, message: "No installed container for \(identifier).")
            }
            let outcome = await GuestInstaller.shared.launch(container)
            return Result(status: outcome.ok ? 0 : 1,
                          message: "\(outcome.headline): \(outcome.detail)")
        }
    }
}
