#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANAGER = ROOT / "LiveContainer-3.8.0/MultitaskSupport/MultitaskDockView.swift"
text = MANAGER.read_text()


def replace_required(old: str, new: str, label: str) -> None:
    global text
    if new in text:
        print(f"gesture v4: {label} already applied")
        return
    if old not in text:
        raise SystemExit(f"gesture v4: expected block not found for {label}")
    text = text.replace(old, new, 1)
    print(f"gesture v4: applied {label}")


# A lifecycle entry can be created before the real DecoratedAppSceneViewController
# hands the manager its UIView. The old code permanently kept the first entry and
# discarded the later non-nil view. That leaves the gesture surface active while
# Home/focus/switching have no concrete guest surface to control.
replace_required(
    '''        DispatchQueue.main.async {
            self.raiseHostedSurfaces()
            guard !self.apps.contains(where: { $0.appUUID == appUUID }) else { return }
            self.apps.append(appModel)
            if UIDevice.current.userInterfaceIdiom == .phone,
''',
    '''        DispatchQueue.main.async {
            self.raiseHostedSurfaces()
            if let existingIndex = self.apps.firstIndex(where: { $0.appUUID == appUUID }) {
                if let view, self.apps[existingIndex].view !== view {
                    self.apps[existingIndex] = DockAppModel(
                        appName: appName,
                        appUUID: appUUID,
                        appInfo: appInfo ?? self.apps[existingIndex].appInfo,
                        view: view
                    )
                    NSLog("VibeContainers: rebound guest UIView for %@", appUUID)
                }
            } else {
                self.apps.append(appModel)
            }
            if UIDevice.current.userInterfaceIdiom == .phone,
''',
    "rebind real guest UIView",
)

# Do not throw away an edge pan merely because UIKit cancels it while arbitrating
# the physical Home-indicator edge. A cancelled gesture still has valid movement
# and should commit using the same final classifier as .ended.
replace_required(
    '''        case .cancelled, .failed:
            systemGestureTriggered = false
            systemGestureBeganAt = 0
            return
''',
    '''        case .cancelled:
            NSLog("VibeContainers: bottom gesture cancelled by UIKit; committing last translation")
            break
        case .failed:
            systemGestureTriggered = false
            systemGestureBeganAt = 0
            return
''',
    "commit cancelled system gesture",
)

# Make the live changed-state classifier iPad-like and forgiving. The previous
# thresholds required a fairly long/high-velocity pull before anything happened,
# which felt interactive without ever crossing an action boundary on some devices.
replace_required(
    '''            if elapsed >= 0.38, upward >= 30, upward < 170,
               upward > horizontal * 1.10, abs(velocity.y) < 950 {
''',
    '''            if elapsed >= 0.30, upward >= 22, upward < 190,
               upward > horizontal * 1.05, abs(velocity.y) < 1200 {
''',
    "forgiving switcher threshold",
)
replace_required(
    '''            if elapsed < 0.32, upward >= 78, upward > horizontal * 1.05,
               velocity.y < -550 {
''',
    '''            if elapsed < 0.45, upward >= 46, upward > horizontal * 1.02,
               velocity.y < -260 {
''',
    "forgiving Home flick threshold",
)
replace_required(
    '''        if elapsed >= 0.34, upward >= 28, upward < 170 {
            presentAppSwitcher()
        } else if upward >= 58 || predictedUpward >= 135 {
            returnToHostHome()
        } else if upward >= 10 {
            showDockForSystemGesture()
''',
    '''        if elapsed >= 0.30, upward >= 22, upward < 190 {
            presentAppSwitcher()
        } else if upward >= 40 || predictedUpward >= 88 {
            returnToHostHome()
        } else if upward >= 6 {
            showDockForSystemGesture()
''',
    "forgiving final classifier",
)

# The registry is authoritative when healthy, but Home must not depend on it.
# Scan the actual virtual-host hierarchy as a fallback so every decorated guest
# surface is hidden even if lifecycle bookkeeping arrived out of order.
replace_required(
    '''    private func hideGuestSurfacesForAppSwitcher() {
        dispatchPrecondition(condition: .onQueue(.main))
        apps.forEach { app in
            guard let view = app.view else { return }
            view.layer.removeAllAnimations()
            view.transform = .identity
            view.alpha = 0
            view.isHidden = true
            view.superview?.sendSubviewToBack(view)
        }
    }
''',
    '''    private func hideGuestSurfacesForAppSwitcher() {
        dispatchPrecondition(condition: .onQueue(.main))

        var guestViews: [UIView] = apps.compactMap { $0.view }
        for hostedView in windowHostingView.subviews {
            guard hostedView._viewDelegate() is DecoratedAppSceneViewController else { continue }
            if !guestViews.contains(where: { $0 === hostedView }) {
                guestViews.append(hostedView)
            }
        }

        NSLog(
            "VibeContainers: hiding guest surfaces registered=%ld concrete=%ld hosted=%ld",
            apps.count,
            guestViews.count,
            windowHostingView.subviews.count
        )
        guestViews.forEach { view in
            view.layer.removeAllAnimations()
            view.transform = .identity
            view.alpha = 0
            view.isHidden = true
            view.superview?.sendSubviewToBack(view)
        }
    }
''',
    "hide concrete hosted guest views",
)

# The singleton may be initialized before SwiftUI has a usable host window. In
# that case setupDockView() can leave hostingController nil forever. Recreate it
# lazily when the user actually asks for the Dock.
replace_required(
    '''    @objc public func showDock() {
        guard isDockEnabled() else { return }
        guard !isVisible, let hostingController = hostingController else { return }
''',
    '''    @objc public func showDock() {
        guard isDockEnabled() else { return }
        if hostingController == nil {
            setupDockView()
        }
        guard !isVisible, let hostingController = hostingController else {
            NSLog("VibeContainers: Dock action could not create hosting controller")
            return
        }
''',
    "lazy Dock hosting controller",
)

MANAGER.write_text(text)
print(f"gesture v4: normalized {MANAGER.relative_to(ROOT)}")
