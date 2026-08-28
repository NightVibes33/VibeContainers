import Foundation

/// Preferences shared with LiveContainer's in-process multitasking UI.
///
/// This VibeContainers build deliberately has no app-group entitlement. In
/// that configuration LiveContainer falls back to the host's standard domain,
/// so the Settings page writes to that same store without probing an
/// unavailable app-group container.
enum MultitaskPreferences {
    static let sharedDefaults = UserDefaults.standard

    static var isEnabled: Bool {
        UserDefaults.standard.object(forKey: "IOSSimMultitaskingEnabled") == nil
            ? true
            : UserDefaults.standard.bool(forKey: "IOSSimMultitaskingEnabled")
    }

    static func configureDefaults() {
        UserDefaults.standard.register(defaults: [
            "IOSSimMultitaskingEnabled": true,
            "LCLaunchMultitaskMaximized": true
        ])
        sharedDefaults.register(defaults: [
            "LCMultitaskMode": 0,
            "LCMultitaskOverlayMode": true,
            "LCMultitaskBottomWindowBar": false,
            "LCDockWidth": 80.0,
            "LCSkipTerminatedScreen": true,
            "LCHideCollapsedDock": false,
            "LCMaxOneAppOnStage": false
        ])

        // register(defaults:) does not override a value saved by an older
        // LiveContainer/VibeContainers build. Mode 1 launches a separate native
        // UIWindowScene and therefore cannot be controlled by Vibe's host-owned
        // bottom edge. Migrate it on every host start; LCUtils also enforces the
        // same invariant immediately before each guest launch.
        let savedMode = sharedDefaults.integer(forKey: "LCMultitaskMode")
        if savedMode != 0 {
            NSLog("VibeContainers: migrating saved multitask mode %d to virtual host", savedMode)
        }
        sharedDefaults.set(0, forKey: "LCMultitaskMode")
        UserDefaults.standard.set(true, forKey: "LCLaunchMultitaskMaximized")
    }
}
