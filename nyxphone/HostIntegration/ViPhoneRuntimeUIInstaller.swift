import SwiftUI
import UIKit

@MainActor
private enum ViPhoneRuntimeUIInstaller {
    private static var installed = false
    private static var observer: NSObjectProtocol?
    private static weak var runtimeButton: UIButton?

    static func install() {
        guard !installed else { return }
        installed = true

        observer = NotificationCenter.default.addObserver(
            forName: UIApplication.didBecomeActiveNotification,
            object: nil,
            queue: .main
        ) { _ in
            Task { @MainActor in attachButtonIfPossible() }
        }

        DispatchQueue.main.async {
            Task { @MainActor in attachButtonIfPossible() }
        }
    }

    private static func attachButtonIfPossible() {
        if runtimeButton?.window != nil { return }
        guard let window = foregroundWindow() else { return }

        let button = UIButton(type: .system)
        var configuration = UIButton.Configuration.filled()
        configuration.image = UIImage(systemName: "iphone.gen3")
        configuration.baseForegroundColor = .label
        configuration.baseBackgroundColor = UIColor.secondarySystemBackground.withAlphaComponent(0.88)
        configuration.cornerStyle = .capsule
        configuration.contentInsets = NSDirectionalEdgeInsets(top: 10, leading: 12, bottom: 10, trailing: 12)
        button.configuration = configuration
        button.accessibilityLabel = "Open NyxPhone Runtime"
        button.addAction(UIAction { _ in
            Task { @MainActor in presentRuntimePanel() }
        }, for: .touchUpInside)
        button.translatesAutoresizingMaskIntoConstraints = false
        button.layer.shadowOpacity = 0.18
        button.layer.shadowRadius = 10
        button.layer.shadowOffset = CGSize(width: 0, height: 4)

        window.addSubview(button)
        NSLayoutConstraint.activate([
            button.trailingAnchor.constraint(equalTo: window.safeAreaLayoutGuide.trailingAnchor, constant: -12),
            button.topAnchor.constraint(equalTo: window.safeAreaLayoutGuide.topAnchor, constant: 10),
            button.widthAnchor.constraint(greaterThanOrEqualToConstant: 48),
            button.heightAnchor.constraint(equalToConstant: 44),
        ])
        runtimeButton = button
    }

    private static func presentRuntimePanel() {
        guard let presenter = topPresenter(from: foregroundWindow()?.rootViewController) else { return }
        if presenter is UIHostingController<ViPhoneRuntimePanel> { return }
        let controller = UIHostingController(rootView: ViPhoneRuntimePanel())
        controller.modalPresentationStyle = .pageSheet
        if let sheet = controller.sheetPresentationController {
            sheet.detents = [.medium(), .large()]
            sheet.prefersGrabberVisible = true
        }
        presenter.present(controller, animated: true)
    }

    private static func foregroundWindow() -> UIWindow? {
        let scenes = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
        let foregroundScenes = scenes.filter { scene in
            scene.activationState == .foregroundActive || scene.activationState == .foregroundInactive
        }
        let foregroundWindows = foregroundScenes.flatMap { $0.windows }
        if let keyWindow = foregroundWindows.first(where: { $0.isKeyWindow }) {
            return keyWindow
        }
        let allWindows = scenes.flatMap { $0.windows }
        return allWindows.first(where: { !$0.isHidden })
    }

    private static func topPresenter(from controller: UIViewController?) -> UIViewController? {
        if let presented = controller?.presentedViewController {
            return topPresenter(from: presented)
        }
        if let navigation = controller as? UINavigationController {
            return topPresenter(from: navigation.visibleViewController)
        }
        if let tab = controller as? UITabBarController {
            return topPresenter(from: tab.selectedViewController)
        }
        return controller
    }
}

/// Exported as a C symbol so the force-loaded native runtime can ask the
/// VibeContainers host to install its control surface without modifying the
/// upstream VibeContainers project file or requiring a second app entry point.
@_cdecl("ViPhoneInstallRuntimeUI")
public func ViPhoneInstallRuntimeUI() {
    Task { @MainActor in
        ViPhoneRuntimeUIInstaller.install()
    }
}
