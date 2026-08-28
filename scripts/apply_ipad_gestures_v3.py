#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_required(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"gesture v3: expected block not found for {label}")
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# The physical bottom edge belongs to the Vibe host, not to one guest window.
# A guest-local recognizer fails whenever the guest is windowed and can also
# lose the touch stream to a remote scene. Put one full-width gesture surface
# on the host root view and keep the existing dock/switcher/focus machinery as
# the actions behind it.
# ---------------------------------------------------------------------------
manager = ROOT / "LiveContainer-3.8.0/MultitaskSupport/MultitaskDockView.swift"
text = manager.read_text()

if "private var systemGestureSurface: UIView?" not in text:
    text = replace_required(
        text,
        "    private var gestureDockOverride = false\n",
        "    private var gestureDockOverride = false\n"
        "    /// Full-width host-owned bottom edge. Unlike a recognizer attached\n"
        "    /// to a guest window, this remains reachable for maximized and\n"
        "    /// windowed virtual guests and cannot be swallowed by the remote scene.\n"
        "    private var systemGestureSurface: UIView?\n"
        "    private var systemGesturePill: UIView?\n"
        "    private var systemGestureRecognizer: UIPanGestureRecognizer?\n"
        "    private var systemGestureBeganAt: TimeInterval = 0\n"
        "    private var systemGestureTriggered = false\n",
        "host gesture state",
    )

raise_old = '''        rootView.bringSubviewToFront(windowHostingView)\n\n        if let dockView = hostingController?.view,\n           let dockSuperview = dockView.superview {\n            dockSuperview.bringSubviewToFront(dockView)\n        }\n'''
raise_new = '''        rootView.bringSubviewToFront(windowHostingView)\n\n        // The bottom edge is a host/system affordance, so it must sit above\n        // every remote guest surface. The floating dock, when explicitly\n        // summoned, remains above the gesture strip so its controls still work.\n        installSystemGestureSurface()\n        if let gestureSurface = systemGestureSurface,\n           gestureSurface.superview === rootView {\n            rootView.bringSubviewToFront(gestureSurface)\n        }\n        if let dockView = hostingController?.view,\n           let dockSuperview = dockView.superview {\n            dockSuperview.bringSubviewToFront(dockView)\n        }\n'''
if "The bottom edge is a host/system affordance" not in text:
    text = replace_required(text, raise_old, raise_new, "raise host gesture surface")

marker = "    // MARK: - Vibe iPad-style bottom gestures\n"
if "VibeContainers.SystemGestureSurface" not in text:
    methods = '''    // MARK: - Host-owned iPad-style system gesture surface\n\n    private func installSystemGestureSurface() {\n        dispatchPrecondition(condition: .onQueue(.main))\n        guard let window = keyWindow,\n              let rootView = window.rootViewController?.view else { return }\n\n        let height = max(54, window.safeAreaInsets.bottom + 36)\n        let frame = CGRect(\n            x: 0,\n            y: max(0, rootView.bounds.height - height),\n            width: rootView.bounds.width,\n            height: height\n        )\n\n        if let surface = systemGestureSurface {\n            if surface.superview !== rootView {\n                surface.removeFromSuperview()\n                rootView.addSubview(surface)\n            }\n            surface.frame = frame\n            rootView.bringSubviewToFront(surface)\n            return\n        }\n\n        let surface = UIView(frame: frame)\n        surface.autoresizingMask = [.flexibleWidth, .flexibleTopMargin]\n        surface.backgroundColor = .clear\n        surface.isUserInteractionEnabled = true\n        surface.isMultipleTouchEnabled = false\n        surface.isHidden = true\n        surface.accessibilityIdentifier = \"VibeContainers.SystemGestureSurface\"\n        surface.accessibilityLabel = \"VibeContainers system gestures\"\n        surface.accessibilityHint = \"Swipe up for Home, pull slightly for Dock, pause for the app switcher, or swipe sideways to change apps.\"\n\n        let pill = UIView(frame: .zero)\n        pill.translatesAutoresizingMaskIntoConstraints = false\n        pill.isUserInteractionEnabled = false\n        pill.backgroundColor = UIColor.label.withAlphaComponent(0.82)\n        pill.layer.cornerRadius = 2.5\n        pill.layer.shadowColor = UIColor.systemBackground.cgColor\n        pill.layer.shadowOpacity = 0.65\n        pill.layer.shadowRadius = 1.5\n        pill.layer.shadowOffset = .zero\n        surface.addSubview(pill)\n        NSLayoutConstraint.activate([\n            pill.centerXAnchor.constraint(equalTo: surface.centerXAnchor),\n            pill.bottomAnchor.constraint(equalTo: surface.bottomAnchor, constant: -7),\n            pill.widthAnchor.constraint(equalToConstant: 122),\n            pill.heightAnchor.constraint(equalToConstant: 5),\n        ])\n\n        let pan = UIPanGestureRecognizer(target: self, action: #selector(handleSystemGesture(_:)))\n        pan.minimumNumberOfTouches = 1\n        pan.maximumNumberOfTouches = 1\n        pan.cancelsTouchesInView = true\n        pan.delaysTouchesBegan = false\n        pan.delaysTouchesEnded = false\n        surface.addGestureRecognizer(pan)\n\n        rootView.addSubview(surface)\n        rootView.bringSubviewToFront(surface)\n        systemGestureSurface = surface\n        systemGesturePill = pill\n        systemGestureRecognizer = pan\n        NSLog(\"VibeContainers: host bottom gesture surface installed\")\n    }\n\n    private func setSystemGestureSurfaceVisible(_ visible: Bool) {\n        dispatchPrecondition(condition: .onQueue(.main))\n        installSystemGestureSurface()\n        systemGestureSurface?.isHidden = !visible\n        if visible,\n           let surface = systemGestureSurface,\n           let rootView = surface.superview {\n            rootView.bringSubviewToFront(surface)\n            if let dockView = hostingController?.view,\n               dockView.superview === rootView {\n                rootView.bringSubviewToFront(dockView)\n            }\n        }\n    }\n\n    private func currentSystemGestureAppUUID() -> String? {\n        // Prefer the actual visible virtual surface. Falling back to the last\n        // registry entry keeps horizontal switching deterministic for a native\n        // scene whose UIView is not hosted in windowHostingView.\n        for app in apps.reversed() {\n            if let view = app.view,\n               view.window != nil,\n               !view.isHidden,\n               view.alpha > 0.01 {\n                return app.appUUID\n            }\n        }\n        return apps.last?.appUUID\n    }\n\n    @objc private func handleSystemGesture(_ gesture: UIPanGestureRecognizer) {\n        guard !apps.isEmpty else { return }\n\n        switch gesture.state {\n        case .began:\n            systemGestureTriggered = false\n            systemGestureBeganAt = ProcessInfo.processInfo.systemUptime\n            return\n        case .cancelled, .failed:\n            systemGestureTriggered = false\n            systemGestureBeganAt = 0\n            return\n        case .changed, .ended:\n            break\n        default:\n            return\n        }\n\n        guard !systemGestureTriggered else { return }\n        let translation = gesture.translation(in: gesture.view)\n        let velocity = gesture.velocity(in: gesture.view)\n        let horizontal = abs(translation.x)\n        let upward = max(0, -translation.y)\n        let elapsed = max(0, ProcessInfo.processInfo.systemUptime - systemGestureBeganAt)\n\n        // iPad-style home-indicator scrub: directly focus the adjacent running\n        // container through the existing focus path.\n        if horizontal >= 46, horizontal > abs(translation.y) * 1.20 {\n            systemGestureTriggered = true\n            let direction = translation.x < 0 ? 1 : -1\n            let feedback = UIImpactFeedbackGenerator(style: .light)\n            feedback.impactOccurred()\n            _ = cycleApp(from: currentSystemGestureAppUUID(), direction: direction)\n            return\n        }\n\n        if gesture.state == .changed {\n            // Lift and pause: use VibeContainers' existing captured-preview\n            // app switcher. Keep the threshold forgiving enough to feel like\n            // iPadOS rather than requiring a precisely measured drag.\n            if elapsed >= 0.38, upward >= 30, upward < 170,\n               upward > horizontal * 1.10, abs(velocity.y) < 950 {\n                systemGestureTriggered = true\n                UIImpactFeedbackGenerator(style: .medium).impactOccurred()\n                presentAppSwitcher()\n                return\n            }\n\n            // A decisive upward flick returns to Vibe Home immediately while\n            // retaining every guest process for later focus/resume.\n            if elapsed < 0.32, upward >= 78, upward > horizontal * 1.05,\n               velocity.y < -550 {\n                systemGestureTriggered = true\n                returnToHostHome()\n                return\n            }\n            return\n        }\n\n        let predictedUpward = max(upward, upward + max(0, -velocity.y) * 0.08)\n        systemGestureTriggered = true\n        systemGestureBeganAt = 0\n        if elapsed >= 0.34, upward >= 28, upward < 170 {\n            presentAppSwitcher()\n        } else if upward >= 58 || predictedUpward >= 135 {\n            returnToHostHome()\n        } else if upward >= 10 {\n            showDockForSystemGesture()\n        } else {\n            systemGestureTriggered = false\n        }\n    }\n\n'''
    text = replace_required(text, marker, methods + marker, "host gesture methods")

# Home/switcher hide the Vibe gesture strip; focusing a guest restores it.
if "self.setSystemGestureSurfaceVisible(false)\n            _ = self.captureAppSwitcherPreviews()" not in text:
    text = replace_required(
        text,
        "        let action = {\n            _ = self.captureAppSwitcherPreviews()\n",
        "        let action = {\n            self.setSystemGestureSurfaceVisible(false)\n            _ = self.captureAppSwitcherPreviews()\n",
        "hide gesture strip on Home",
    )

if "self.setSystemGestureSurfaceVisible(true)\n            guard !self.apps.isEmpty" not in text:
    text = replace_required(
        text,
        "        let action = {\n            guard !self.apps.isEmpty else { return }\n            self.gestureDockOverride = true\n",
        "        let action = {\n            self.setSystemGestureSurfaceVisible(true)\n            guard !self.apps.isEmpty else { return }\n            self.gestureDockOverride = true\n",
        "show gesture strip with dock",
    )

cycle_old = '''        gestureDockOverride = false\n        hideDock()\n        return focusAppResult(apps[targetIndex].appUUID) == 0\n'''
cycle_new = '''        gestureDockOverride = false\n        hideDock()\n        let focused = focusAppResult(apps[targetIndex].appUUID) == 0\n        if focused { setSystemGestureSurfaceVisible(true) }\n        return focused\n'''
if "let focused = focusAppResult(apps[targetIndex].appUUID) == 0" not in text:
    text = replace_required(text, cycle_old, cycle_new, "cycle keeps gesture surface")

if "self.setSystemGestureSurfaceVisible(false)\n            let startedAt" not in text:
    text = replace_required(
        text,
        "        let present = {\n            let startedAt = ProcessInfo.processInfo.systemUptime\n",
        "        let present = {\n            self.setSystemGestureSurfaceVisible(false)\n            let startedAt = ProcessInfo.processInfo.systemUptime\n",
        "hide strip for switcher",
    )

# Do not auto-present LiveContainer's old floating rail on first launch. The
# same dock still exists and is exposed by a short bottom pull.
auto_dock_old = '''            // Keep native scenes in the lifecycle registry without displaying\n            // LiveContainer's floating virtual-window dock for them.\n            guard self.isDockEnabled() else { return }\n            \n            if self.apps.count == 1 {\n                self.showDock()\n            } else if self.isVisible {\n                self.updateDockFrame()\n            }\n'''
auto_dock_new = '''            self.setSystemGestureSurfaceVisible(true)\n\n            // Keep the existing multitasking dock as the Dock action, but do\n            // not leave LiveContainer's old floating rail permanently visible.\n            // A short bottom pull summons it; Home/switcher hide it again.\n            guard self.isDockEnabled() else { return }\n            if self.isVisible {\n                self.updateDockFrame()\n            }\n'''
if "A short bottom pull summons it" not in text:
    text = replace_required(text, auto_dock_old, auto_dock_new, "stop automatic floating dock")

# If every running app closes, the synthetic home indicator must disappear.
if "self.setSystemGestureSurfaceVisible(false)\n                self.hideDock()" not in text:
    text = replace_required(
        text,
        "            if self.apps.isEmpty {\n                self.hideDock()\n",
        "            if self.apps.isEmpty {\n                self.setSystemGestureSurfaceVisible(false)\n                self.hideDock()\n",
        "hide strip after last close",
    )

# Virtual focus is the common route used by switcher cards and horizontal scrub.
if "if focused { setSystemGestureSurfaceVisible(true) }\n        NSLog(" not in text:
    text = replace_required(
        text,
        "        NSLog(\n            \"VibeContainers: virtual focus %@ %@ (surface=%@ top=%@ hostWindow=%@)\",\n",
        "        if focused { setSystemGestureSurfaceVisible(true) }\n        NSLog(\n            \"VibeContainers: virtual focus %@ %@ (surface=%@ top=%@ hostWindow=%@)\",\n",
        "restore strip after virtual focus",
    )

# Native focus still updates host state when that mode is selected.
if "if focused {\n                setSystemGestureSurfaceVisible(true)\n                return 0\n            }" not in text:
    text = replace_required(
        text,
        "            if focused { return 0 }\n",
        "            if focused {\n                setSystemGestureSurfaceVisible(true)\n                return 0\n            }\n",
        "restore strip after native focus",
    )

manager.write_text(text)
print(f"normalized {manager.relative_to(ROOT)}")


# ---------------------------------------------------------------------------
# The old per-window 180pt grabber is precisely what made the new gestures
# unreachable in windowed mode. Leave its compatibility code compiled, but
# remove it from hit testing and visuals; the host-wide surface above replaces
# it for actual interaction.
# ---------------------------------------------------------------------------
decorated = ROOT / "LiveContainer-3.8.0/MultitaskSupport/DecoratedAppSceneViewController.m"
text = decorated.read_text()
old_log = '    NSLog(@"VibeContainers: installed iPad-style bottom gestures above the guest scene");\n'
new_log = '''    self.appSwitcherGrabber.hidden = YES;\n    self.appSwitcherGrabber.userInteractionEnabled = NO;\n    NSLog(@"VibeContainers: per-window bottom grabber disabled; host owns bottom gestures");\n'''
if "per-window bottom grabber disabled" not in text:
    text = replace_required(text, old_log, new_log, "disable guest-local grabber")
decorated.write_text(text)
print(f"normalized {decorated.relative_to(ROOT)}")


# ---------------------------------------------------------------------------
# Built-in SwiftUI apps use the same gesture semantics. Repair the stale name
# from the first v2 attempt if it ever gets reintroduced before this script.
# ---------------------------------------------------------------------------
app_window = ROOT / "iOSSim/Springboard/AppWindow.swift"
text = app_window.read_text().replace("interactiveDismissal = 0", "dismissalProgress = 0")
app_window.write_text(text)
print(f"normalized {app_window.relative_to(ROOT)}")


# Make the launch result describe the actual interaction instead of directing
# users back to the always-visible floating rail we intentionally removed.
installer = ROOT / "iOSSim/Model/GuestInstaller.swift"
text = installer.read_text().replace(
    "Running in its own app process. Use the floating dock to switch, resize, minimize or close it.",
    "Running in its own app process. Use the bottom edge for Dock, Home, the app switcher, or app-to-app switching.",
)
installer.write_text(text)
print(f"normalized {installer.relative_to(ROOT)}")


# Artifact/source-level assertions: no multi-finger or pinch implementation,
# no stale AppWindow binding, and no auto-show of the legacy dock.
checks = {
    manager: [
        "VibeContainers.SystemGestureSurface",
        "host bottom gesture surface installed",
        "handleSystemGesture(_ gesture:",
        "A short bottom pull summons it",
    ],
    decorated: ["per-window bottom grabber disabled; host owns bottom gestures"],
    installer: ["Use the bottom edge for Dock, Home"],
}
for path, markers in checks.items():
    content = path.read_text()
    missing = [marker for marker in markers if marker not in content]
    if missing:
        raise SystemExit(f"gesture v3 validation failed in {path.relative_to(ROOT)}: {missing}")

for path in (manager, decorated, app_window):
    content = path.read_text()
    forbidden = [token for token in (
        "minimumNumberOfTouches = 4",
        "maximumNumberOfTouches = 5",
        "multitaskSwipeGesture",
        "handleMultitaskSwipeGesture",
        "MagnificationGesture",
        "interactiveDismissal = 0",
    ) if token in content]
    if forbidden:
        raise SystemExit(f"forbidden gesture artifact in {path.relative_to(ROOT)}: {forbidden}")

if "if self.apps.count == 1 {\n                self.showDock()" in manager.read_text():
    raise SystemExit("gesture v3: legacy floating dock still auto-shows on first app")
