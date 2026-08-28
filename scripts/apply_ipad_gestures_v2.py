#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def write(path: Path, text: str) -> None:
    path.write_text(text)
    print(f"normalized {path.relative_to(ROOT)}")


def replace_required(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"gesture v2: expected block not found for {label}")
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# MultitaskDockManager: reuse the existing dock, switcher, focus and hidden
# guest surfaces. No second multitasking implementation is introduced.
# ---------------------------------------------------------------------------
manager = ROOT / "LiveContainer-3.8.0/MultitaskSupport/MultitaskDockView.swift"
text = manager.read_text()
if "private var gestureDockOverride = false" not in text:
    text = replace_required(
        text,
        "    private var dockEdgeGestures: [UIScreenEdgePanGestureRecognizer] = []\n",
        "    private var dockEdgeGestures: [UIScreenEdgePanGestureRecognizer] = []\n"
        "    /// Set only while the bottom gesture explicitly exposes the existing\n"
        "    /// multitasking dock on a phone. Normal launches stay edge-to-edge.\n"
        "    private var gestureDockOverride = false\n",
        "gesture dock state",
    )
if "gestureDockOverride = false\n        guard isVisible" not in text:
    text = replace_required(
        text,
        "    @objc public func hideDock() {\n        guard isVisible, let hostingController = hostingController else { return }\n",
        "    @objc public func hideDock() {\n        gestureDockOverride = false\n        guard isVisible, let hostingController = hostingController else { return }\n",
        "hideDock reset",
    )
if "if gestureDockOverride { return true }" not in text:
    text = replace_required(
        text,
        "    private func isDockEnabled() -> Bool {\n",
        "    private func isDockEnabled() -> Bool {\n        if gestureDockOverride { return true }\n",
        "dock gesture override",
    )

# Remove the old wording if an earlier queued build already persisted it.
text = text.replace(
    "    /// iPad-style bottom-edge and four/five-finger horizontal switching. A\n",
    "    /// iPad-style bottom-edge horizontal switching. A\n",
)

if "@objc public func returnToHostHome()" not in text:
    marker = "    /// Reveals VibeContainers' adaptive app switcher after clearing the guest\n"
    methods = '''    // MARK: - Vibe iPad-style bottom gestures\n\n    /// Reveal VibeContainers' Springboard without terminating guest processes.\n    @objc public func returnToHostHome() {\n        let action = {\n            _ = self.captureAppSwitcherPreviews()\n            _ = self.captureAppSwitcherPreviewViews()\n            self.gestureDockOverride = false\n            self.hideGuestSurfacesForAppSwitcher()\n            self.hideDock()\n            self.raiseHostedSurfaces()\n        }\n        if Thread.isMainThread { action() } else { DispatchQueue.main.async(execute: action) }\n    }\n\n    /// A short upward pull uses LiveContainer's existing multitasking dock.\n    @objc public func showDockForSystemGesture() {\n        let action = {\n            guard !self.apps.isEmpty else { return }\n            self.gestureDockOverride = true\n            self.raiseHostedSurfaces()\n            if self.isVisible {\n                if self.isDockHidden {\n                    self.showDockFromHidden()\n                } else {\n                    self.updateDockFrame()\n                }\n            } else {\n                self.showDock()\n            }\n        }\n        if Thread.isMainThread { action() } else { DispatchQueue.main.async(execute: action) }\n    }\n\n    /// Horizontal travel along the home indicator focuses the adjacent running\n    /// container through the existing focus path.\n    @objc(cycleAppFrom:direction:)\n    public func cycleApp(from currentUUID: String?, direction: Int) -> Bool {\n        dispatchPrecondition(condition: .onQueue(.main))\n        guard !apps.isEmpty else { return false }\n\n        let step = direction >= 0 ? 1 : -1\n        let currentIndex = currentUUID.flatMap { uuid in\n            apps.firstIndex(where: { $0.appUUID == uuid })\n        }\n        let targetIndex: Int\n        if let currentIndex {\n            if apps.count == 1 { return true }\n            targetIndex = (currentIndex + step + apps.count) % apps.count\n        } else {\n            targetIndex = step > 0 ? 0 : apps.count - 1\n        }\n\n        gestureDockOverride = false\n        hideDock()\n        return focusAppResult(apps[targetIndex].appUUID) == 0\n    }\n\n'''
    text = replace_required(text, marker, methods + marker, "multitask gesture actions")
write(manager, text)


# ---------------------------------------------------------------------------
# Real guest scene: the host-owned home-indicator surface receives gestures
# even when the remote app consumes its own normal UIKit touches.
# ---------------------------------------------------------------------------
decorated = ROOT / "LiveContainer-3.8.0/MultitaskSupport/DecoratedAppSceneViewController.m"
text = decorated.read_text()

# Explicitly remove every four/five-finger artifact from an earlier attempt.
text = re.sub(r'^@property\(nonatomic\) UIPanGestureRecognizer \*multitaskSwipeGesture;\n', '', text, flags=re.M)
text = re.sub(r'^@property\(nonatomic\) BOOL multitaskSwipeTriggered;\n', '', text, flags=re.M)
text = re.sub(
    r'\n    // iPadOS also supports four/five-finger horizontal app switching\..*?\n    \[self\.view addGestureRecognizer:self\.multitaskSwipeGesture\];\n',
    '\n', text, flags=re.S,
)
text = re.sub(
    r'\n- \(void\)handleMultitaskSwipeGesture:\(UIPanGestureRecognizer \*\)gesture \{.*?\n\}\n',
    '\n', text, flags=re.S,
)
text = re.sub(
    r'\n    if \(gestureRecognizer == self\.multitaskSwipeGesture\) \{.*?\n    \}',
    '', text, flags=re.S,
)

if "@property(nonatomic) NSTimeInterval appSwitcherGestureBeganAt;" not in text:
    text = replace_required(
        text,
        "@property(nonatomic) BOOL appSwitcherGestureTriggered;\n",
        "@property(nonatomic) BOOL appSwitcherGestureTriggered;\n"
        "@property(nonatomic) NSTimeInterval appSwitcherGestureBeganAt;\n",
        "guest gesture timing state",
    )

text = text.replace(
    'self.appSwitcherGrabber.accessibilityLabel = @"Open VibeContainers app switcher";',
    'self.appSwitcherGrabber.accessibilityLabel = @"VibeContainers multitasking gestures";',
)
text = text.replace(
    'self.appSwitcherGrabber.accessibilityHint = @"Tap or swipe up to switch containers.";',
    'self.appSwitcherGrabber.accessibilityHint = @"Short swipe for Dock, swipe up for Home, hold for the app switcher, or swipe sideways to change apps.";',
)

text = text.replace(
    'NSLog(@"VibeContainers: installed virtual bottom switcher grabber above the guest scene");',
    'NSLog(@"VibeContainers: installed iPad-style bottom gestures above the guest scene");',
)
text = text.replace(
    'NSLog(@"VibeContainers: installed iPad-style Home/Dock/switcher gestures above the guest scene");',
    'NSLog(@"VibeContainers: installed iPad-style bottom gestures above the guest scene");',
)

# Let maximized iPad guest windows use the same host gesture; windowed guests
# retain their normal Stage Manager controls.
text = text.replace(
    "    if (!self.usesPhoneFullscreenPresentation || !self.isMaximized ||\n"
    "        self.view.hidden || self.view.alpha < 0.01 || !self.view.window) {\n",
    "    if (!self.isMaximized ||\n"
    "        self.view.hidden || self.view.alpha < 0.01 || !self.view.window) {\n",
)

start = text.find("- (void)handleAppSwitcherGrabberTap {")
end = text.find("- (BOOL)gestureRecognizerShouldBegin:", start)
if start < 0 or end < 0:
    raise SystemExit("gesture v2: guest bottom gesture handlers not found")
new_handlers = '''- (void)handleAppSwitcherGrabberTap {\n    if (!self.isMaximized || self.view.hidden || self.view.alpha < 0.01 || !self.view.window) return;\n    UIImpactFeedbackGenerator *feedback = [[UIImpactFeedbackGenerator alloc]\n        initWithStyle:UIImpactFeedbackStyleLight];\n    [feedback impactOccurred];\n    [[MultitaskDockManager shared] showDockForSystemGesture];\n}\n\n- (void)handleAppSwitcherGesture:(UIPanGestureRecognizer *)gesture {\n    if (gesture.state == UIGestureRecognizerStateBegan) {\n        self.appSwitcherGestureTriggered = NO;\n        self.appSwitcherGestureBeganAt = NSDate.date.timeIntervalSinceReferenceDate;\n        return;\n    }\n    if (gesture.state == UIGestureRecognizerStateCancelled ||\n        gesture.state == UIGestureRecognizerStateFailed) {\n        self.appSwitcherGestureTriggered = NO;\n        return;\n    }\n    if (gesture.state != UIGestureRecognizerStateChanged &&\n        gesture.state != UIGestureRecognizerStateEnded) return;\n    if (self.appSwitcherGestureTriggered || ![self canHandleAppSwitcherGesture:gesture]) return;\n\n    CGPoint translation = [gesture translationInView:self.view.window];\n    CGPoint velocity = [gesture velocityInView:self.view.window];\n    CGFloat horizontal = fabs(translation.x);\n    CGFloat upward = MAX(0.0, -translation.y);\n    NSTimeInterval elapsed = MAX(0.0, NSDate.date.timeIntervalSinceReferenceDate - self.appSwitcherGestureBeganAt);\n\n    // Slide across the home indicator to move directly between running apps.\n    if (horizontal > 44.0 && horizontal > fabs(translation.y) * 1.25) {\n        self.appSwitcherGestureTriggered = YES;\n        NSInteger direction = translation.x < 0 ? 1 : -1;\n        UIImpactFeedbackGenerator *feedback = [[UIImpactFeedbackGenerator alloc]\n            initWithStyle:UIImpactFeedbackStyleLight];\n        [feedback impactOccurred];\n        [[MultitaskDockManager shared] cycleAppFrom:self.dataUUID direction:direction];\n        return;\n    }\n\n    if (gesture.state == UIGestureRecognizerStateChanged) {\n        // Lift and pause: existing VibeContainers app switcher.\n        if (elapsed >= 0.40 && upward >= 32.0 && upward < 165.0 &&\n            upward > horizontal * 1.15 && fabs(velocity.y) < 900.0) {\n            self.appSwitcherGestureTriggered = YES;\n            UIImpactFeedbackGenerator *feedback = [[UIImpactFeedbackGenerator alloc]\n                initWithStyle:UIImpactFeedbackStyleMedium];\n            [feedback impactOccurred];\n            [[MultitaskDockManager shared] presentAppSwitcher];\n            return;\n        }\n\n        // Fast upward flick: Vibe Home, while the guest remains alive.\n        if (elapsed < 0.30 && upward >= 86.0 && upward > horizontal * 1.10 &&\n            velocity.y < -650.0) {\n            self.appSwitcherGestureTriggered = YES;\n            [[MultitaskDockManager shared] returnToHostHome];\n            return;\n        }\n        return;\n    }\n\n    CGFloat predictedUpward = MAX(upward, -(translation.y + MIN(velocity.y, 0.0) * 0.08));\n    self.appSwitcherGestureTriggered = YES;\n    if (elapsed >= 0.34 && upward >= 28.0 && upward < 165.0) {\n        [[MultitaskDockManager shared] presentAppSwitcher];\n    } else if (upward >= 64.0 || predictedUpward >= 150.0) {\n        [[MultitaskDockManager shared] returnToHostHome];\n    } else if (upward >= 12.0) {\n        [[MultitaskDockManager shared] showDockForSystemGesture];\n    } else {\n        self.appSwitcherGestureTriggered = NO;\n    }\n}\n\n'''
text = text[:start] + new_handlers + text[end:]

# Normalize the recognizer gate after stripping any previous multi-finger branch.
start = text.find("- (BOOL)gestureRecognizerShouldBegin:")
end = text.find("- (BOOL)gestureRecognizer:(UIGestureRecognizer *)gestureRecognizer", start)
if start < 0 or end < 0:
    raise SystemExit("gesture v2: gesture recognizer delegate block not found")
should_begin = '''- (BOOL)gestureRecognizerShouldBegin:(UIGestureRecognizer *)gestureRecognizer {\n    if (gestureRecognizer == self.appSwitcherGesture) {\n        return [self canHandleAppSwitcherGesture:(UIPanGestureRecognizer *)gestureRecognizer];\n    }\n    return YES;\n}\n\n'''
text = text[:start] + should_begin + text[end:]

text = text.replace(
    "    if (self.usesPhoneFullscreenPresentation && self.isMaximized &&\n        !self.view.hidden) {\n",
    "    if (self.isMaximized && !self.view.hidden) {\n",
)

for forbidden in ("minimumNumberOfTouches = 4", "maximumNumberOfTouches = 5", "multitaskSwipeGesture", "handleMultitaskSwipeGesture"):
    if forbidden in text:
        raise SystemExit(f"gesture v2: forbidden multi-finger artifact remains: {forbidden}")
write(decorated, text)


# ---------------------------------------------------------------------------
# C bridge: expose existing multitask manager actions to SwiftUI built-ins.
# ---------------------------------------------------------------------------
bridge = ROOT / "iOSSim/Runtime/MultitaskBridge.m"
text = bridge.read_text()
if "int32_t IOSSimReturnMultitaskHome(void)" not in text:
    marker = "\nint32_t IOSSimTerminateMultitaskGuests(void) {\n"
    methods = '''\nint32_t IOSSimReturnMultitaskHome(void) {\n    if (![NSThread isMainThread]) return EDEADLK;\n    id manager = IOSSimMultitaskManager();\n    SEL selector = NSSelectorFromString(@"returnToHostHome");\n    if (!manager || ![manager respondsToSelector:selector]) return ENOSYS;\n    ((void (*)(id, SEL))objc_msgSend)(manager, selector);\n    return 0;\n}\n\nint32_t IOSSimShowMultitaskDock(void) {\n    if (![NSThread isMainThread]) return EDEADLK;\n    id manager = IOSSimMultitaskManager();\n    SEL selector = NSSelectorFromString(@"showDockForSystemGesture");\n    if (!manager || ![manager respondsToSelector:selector]) return ENOSYS;\n    ((void (*)(id, SEL))objc_msgSend)(manager, selector);\n    return 0;\n}\n\nint32_t IOSSimCycleMultitaskGuest(const char *dataUUIDBytes, int32_t direction) {\n    if (![NSThread isMainThread]) return EDEADLK;\n    NSString *dataUUID = dataUUIDBytes ? [NSString stringWithUTF8String:dataUUIDBytes] : nil;\n    id manager = IOSSimMultitaskManager();\n    SEL selector = NSSelectorFromString(@"cycleAppFrom:direction:");\n    if (!manager || ![manager respondsToSelector:selector]) return ENOSYS;\n    BOOL focused = ((BOOL (*)(id, SEL, NSString *, NSInteger))objc_msgSend)(\n        manager, selector, dataUUID, (NSInteger)direction\n    );\n    return focused ? 0 : ENOENT;\n}\n'''
    text = replace_required(text, marker, methods + marker, "multitask C bridge")
write(bridge, text)


# ---------------------------------------------------------------------------
# RunningContainerStore: lightweight Swift entry points for built-in screens.
# ---------------------------------------------------------------------------
running = ROOT / "iOSSim/Model/RunningContainerStore.swift"
text = running.read_text()
if "IOSSimReturnMultitaskHome" not in text:
    marker = '@_silgen_name("IOSSimPresentMultitaskSwitcher")\nprivate func IOSSimPresentMultitaskSwitcher() -> Int32\n'
    declarations = marker + '''\n@_silgen_name("IOSSimReturnMultitaskHome")\nprivate func IOSSimReturnMultitaskHome() -> Int32\n\n@_silgen_name("IOSSimShowMultitaskDock")\nprivate func IOSSimShowMultitaskDock() -> Int32\n\n@_silgen_name("IOSSimCycleMultitaskGuest")\nprivate func IOSSimCycleMultitaskGuest(_ dataUUID: UnsafePointer<CChar>?, _ direction: Int32) -> Int32\n'''
    text = replace_required(text, marker, declarations, "Swift bridge declarations")
if "func showGestureDock()" not in text:
    marker = "    func presentSwitcher() {\n"
    methods = '''    @discardableResult\n    func returnToVibeHome() -> Bool {\n        IOSSimReturnMultitaskHome() == 0\n    }\n\n    @discardableResult\n    func showGestureDock() -> Bool {\n        IOSSimShowMultitaskDock() == 0\n    }\n\n    @discardableResult\n    func cycleFromHost(direction: Int32) -> Bool {\n        IOSSimCycleMultitaskGuest(nil, direction) == 0\n    }\n\n'''
    text = replace_required(text, marker, methods + marker, "Swift gesture actions")
write(running, text)


# ---------------------------------------------------------------------------
# Built-in apps and Settings: same bottom gesture language as real guests.
# ---------------------------------------------------------------------------
app_window = ROOT / "iOSSim/Springboard/AppWindow.swift"
text = app_window.read_text()
if "@State private var closeGestureBeganAt" not in text:
    text = replace_required(
        text,
        "    @State private var closeGestureStart: CGPoint?\n",
        "    @State private var closeGestureStart: CGPoint?\n"
        "    @State private var closeGestureBeganAt: TimeInterval = 0\n",
        "AppWindow gesture timing",
    )
if "private var runningContainers: RunningContainerStore" not in text:
    text = replace_required(
        text,
        "    private var appearance: Appearance { Appearance.shared }\n",
        "    private var appearance: Appearance { Appearance.shared }\n"
        "    private var runningContainers: RunningContainerStore { .shared }\n",
        "AppWindow runtime store",
    )
if "frame(width: 122, height: 5)" not in text:
    marker = "        .opacity(motionDisabled ? (revealed ? 1 : 0) : 1)\n        .allowsHitTesting(revealed && !transitionActive)\n"
    replacement = '''        .opacity(motionDisabled ? (revealed ? 1 : 0) : 1)\n        .overlay(alignment: .bottom) {\n            if revealed && !transitionActive {\n                Capsule()\n                    .fill(SysColor.label.opacity(0.78))\n                    .frame(width: 122, height: 5)\n                    .padding(.bottom, max(7, safeArea.bottom > 0 ? 7 : 11))\n                    .allowsHitTesting(false)\n            }\n        }\n        .allowsHitTesting(revealed && !transitionActive)\n'''
    text = replace_required(text, marker, replacement, "AppWindow home indicator")

start = text.find("    /// Swipe up from the bottom edge to go home.\n")
if start < 0:
    start = text.find("    /// iPad-style bottom gestures:")
end = text.find("    private func updateCloseGesture", start)
if start < 0 or end < 0:
    raise SystemExit("gesture v2: AppWindow close gesture block not found")
close_gesture = '''    /// iPad-style bottom gestures: short swipe = Dock, quick swipe = Home,\n    /// swipe-and-hold = app switcher, horizontal = adjacent running app.\n    private var closeGesture: some Gesture {\n        DragGesture(minimumDistance: 12, coordinateSpace: .global)\n            .onChanged(updateCloseGesture)\n            .onEnded { value in\n                let axis = closeGestureAxis\n                let elapsed = max(0, Date.timeIntervalSinceReferenceDate - closeGestureBeganAt)\n                closeGestureAxis = nil\n                closeGestureStart = nil\n                closeGestureBeganAt = 0\n\n                guard value.startLocation.y > screen.height - 70 else {\n                    settleDismissal()\n                    return\n                }\n\n                if axis == .horizontal {\n                    let horizontal = abs(value.translation.width)\n                    guard horizontal > 48 else {\n                        settleDismissal()\n                        return\n                    }\n                    switchToRunningContainer(direction: value.translation.width < 0 ? 1 : -1)\n                    return\n                }\n\n                guard axis == .vertical else {\n                    settleDismissal()\n                    return\n                }\n\n                let upwardTravel = max(0, -value.translation.height)\n                let predictedUpwardTravel = max(upwardTravel, -value.predictedEndTranslation.height)\n\n                if elapsed >= 0.34, upwardTravel >= 28, upwardTravel < 165,\n                   !runningContainers.visibleEntries.isEmpty {\n                    openContainerSwitcher()\n                } else if upwardTravel >= 64 || predictedUpwardTravel >= 150 {\n                    onClose()\n                } else if upwardTravel >= 12 {\n                    _ = runningContainers.showGestureDock()\n                    settleDismissal()\n                } else {\n                    settleDismissal()\n                }\n            }\n    }\n\n'''
text = text[:start] + close_gesture + text[end:]

if "closeGestureBeganAt = Date.timeIntervalSinceReferenceDate" not in text:
    text = replace_required(
        text,
        "        if closeGestureStart != value.startLocation {\n            closeGestureStart = value.startLocation\n            closeGestureAxis = nil\n        }\n",
        "        if closeGestureStart != value.startLocation {\n            closeGestureStart = value.startLocation\n            closeGestureAxis = nil\n            closeGestureBeganAt = Date.timeIntervalSinceReferenceDate\n        }\n",
        "AppWindow gesture start time",
    )

if "private func switchToRunningContainer" not in text:
    marker = "    private func settleDismissal() {\n"
    helpers = '''    private func openContainerSwitcher() {\n        interactiveDismissal = 0\n        onClose()\n        Task { @MainActor in\n            try? await Task.sleep(for: .milliseconds(230))\n            _ = runningContainers.presentCapturedSwitcher()\n        }\n    }\n\n    private func switchToRunningContainer(direction: Int32) {\n        guard !runningContainers.activeEntries.isEmpty else {\n            settleDismissal()\n            return\n        }\n        interactiveDismissal = 0\n        onClose()\n        Task { @MainActor in\n            try? await Task.sleep(for: .milliseconds(230))\n            _ = runningContainers.cycleFromHost(direction: direction)\n        }\n    }\n\n'''
    text = replace_required(text, marker, helpers + marker, "AppWindow gesture helpers")
write(app_window, text)


# Hard validation: only bottom-edge gestures are allowed by this patch.
checks = {
    manager: ["returnToHostHome()", "showDockForSystemGesture()", "cycleApp(from currentUUID"],
    decorated: ["appSwitcherGestureBeganAt", "showDockForSystemGesture", "returnToHostHome", "cycleAppFrom:self.dataUUID"],
    bridge: ["IOSSimReturnMultitaskHome", "IOSSimShowMultitaskDock", "IOSSimCycleMultitaskGuest"],
    running: ["func showGestureDock()", "func cycleFromHost(direction: Int32)"],
    app_window: ["iPad-style bottom gestures", "frame(width: 122, height: 5)"],
}
for path, markers in checks.items():
    content = path.read_text()
    missing = [marker for marker in markers if marker not in content]
    if missing:
        raise SystemExit(f"gesture v2 validation failed in {path.relative_to(ROOT)}: {missing}")

for path in (decorated, app_window):
    content = path.read_text()
    forbidden = [token for token in (
        "minimumNumberOfTouches = 4",
        "maximumNumberOfTouches = 5",
        "multitaskSwipeGesture",
        "handleMultitaskSwipeGesture",
        "MagnificationGesture",
    ) if token in content]
    if forbidden:
        raise SystemExit(f"multi-finger/pinch gesture unexpectedly present in {path.relative_to(ROOT)}: {forbidden}")
