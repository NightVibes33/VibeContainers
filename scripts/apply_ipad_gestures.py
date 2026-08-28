#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str, marker: str) -> None:
    text = path.read_text()
    if marker in text:
        print(f"already patched {path.relative_to(ROOT)}: {marker}")
        return
    if old not in text:
        raise SystemExit(f"gesture patch: expected block not found in {path.relative_to(ROOT)} for {marker}")
    path.write_text(text.replace(old, new, 1))
    print(f"patched {path.relative_to(ROOT)}: {marker}")


def regex_once(path: Path, pattern: str, replacement: str, marker: str) -> None:
    text = path.read_text()
    if marker in text:
        print(f"already patched {path.relative_to(ROOT)}: {marker}")
        return
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"gesture patch: expected regex block not found in {path.relative_to(ROOT)} for {marker}")
    path.write_text(updated)
    print(f"patched {path.relative_to(ROOT)}: {marker}")


# MARK: LiveContainer multitasking manager
manager = ROOT / "LiveContainer-3.8.0/MultitaskSupport/MultitaskDockView.swift"
replace_once(
    manager,
    "    private var dockEdgeGestures: [UIScreenEdgePanGestureRecognizer] = []\n",
    "    private var dockEdgeGestures: [UIScreenEdgePanGestureRecognizer] = []\n"
    "    /// True only while the iPad-style bottom gesture has explicitly exposed\n"
    "    /// the multitasking controls on a phone. Normal launch behavior remains\n"
    "    /// unchanged, so the dock never appears just because a guest started.\n"
    "    private var gestureDockOverride = false\n",
    "gestureDockOverride = false",
)

replace_once(
    manager,
    "    @objc public func hideDock() {\n        guard isVisible, let hostingController = hostingController else { return }\n",
    "    @objc public func hideDock() {\n        gestureDockOverride = false\n        guard isVisible, let hostingController = hostingController else { return }\n",
    "gestureDockOverride = false\n        guard isVisible",
)

replace_once(
    manager,
    "    private func isDockEnabled() -> Bool {\n        // Phones present a single edge-to-edge guest and use the host's\n",
    "    private func isDockEnabled() -> Bool {\n        if gestureDockOverride { return true }\n        // Phones present a single edge-to-edge guest and use the host's\n",
    "if gestureDockOverride { return true }",
)

manager_methods = '''    // MARK: - Vibe iPad-style system gestures\n\n    /// Home gesture: reveal VibeContainers' Springboard without terminating any\n    /// guest process. The current switcher previews are retained for a later\n    /// swipe-up-and-hold.\n    @objc public func returnToHostHome() {\n        let action = {\n            _ = self.captureAppSwitcherPreviews()\n            _ = self.captureAppSwitcherPreviewViews()\n            self.gestureDockOverride = false\n            self.hideGuestSurfacesForAppSwitcher()\n            self.hideDock()\n            self.raiseHostedSurfaces()\n        }\n        if Thread.isMainThread { action() } else { DispatchQueue.main.async(execute: action) }\n    }\n\n    /// A short bottom swipe exposes the existing LiveContainer multitasking\n    /// controls. On phone this is opt-in for the lifetime of that dock reveal;\n    /// normal guest launches still remain edge-to-edge.\n    @objc public func showDockForSystemGesture() {\n        let action = {\n            guard !self.apps.isEmpty else { return }\n            self.gestureDockOverride = true\n            self.raiseHostedSurfaces()\n            if self.isVisible {\n                if self.isDockHidden {\n                    self.showDockFromHidden()\n                } else {\n                    self.updateDockFrame()\n                }\n            } else {\n                self.showDock()\n            }\n        }\n        if Thread.isMainThread { action() } else { DispatchQueue.main.async(execute: action) }\n    }\n\n    /// iPad-style bottom-edge and four/five-finger horizontal switching. A\n    /// negative direction moves toward the previous running container; a\n    /// positive direction moves toward the next one.\n    @objc(cycleAppFrom:direction:)\n    public func cycleApp(from currentUUID: String?, direction: Int) -> Bool {\n        dispatchPrecondition(condition: .onQueue(.main))\n        guard !apps.isEmpty else { return false }\n\n        let step = direction >= 0 ? 1 : -1\n        let currentIndex = currentUUID.flatMap { uuid in\n            apps.firstIndex(where: { $0.appUUID == uuid })\n        }\n        let targetIndex: Int\n        if let currentIndex {\n            if apps.count == 1 { return true }\n            targetIndex = (currentIndex + step + apps.count) % apps.count\n        } else {\n            targetIndex = step > 0 ? 0 : apps.count - 1\n        }\n\n        gestureDockOverride = false\n        hideDock()\n        return focusAppResult(apps[targetIndex].appUUID) == 0\n    }\n\n'''
replace_once(
    manager,
    "    /// Reveals VibeContainers' adaptive app switcher after clearing the guest\n",
    manager_methods + "    /// Reveals VibeContainers' adaptive app switcher after clearing the guest\n",
    "MARK: - Vibe iPad-style system gestures",
)

# MARK: Guest scene gesture layer
decorated = ROOT / "LiveContainer-3.8.0/MultitaskSupport/DecoratedAppSceneViewController.m"
replace_once(
    decorated,
    "@property(nonatomic) BOOL appSwitcherGestureTriggered;\n@property(nonatomic, readonly) BOOL usesPhoneFullscreenPresentation;\n",
    "@property(nonatomic) BOOL appSwitcherGestureTriggered;\n"
    "@property(nonatomic) NSTimeInterval appSwitcherGestureBeganAt;\n"
    "@property(nonatomic) UIPanGestureRecognizer *multitaskSwipeGesture;\n"
    "@property(nonatomic) BOOL multitaskSwipeTriggered;\n"
    "@property(nonatomic, readonly) BOOL usesPhoneFullscreenPresentation;\n",
    "multitaskSwipeGesture",
)

replace_once(
    decorated,
    "    self.appSwitcherGrabber.accessibilityLabel = @\"Open VibeContainers app switcher\";\n"
    "    self.appSwitcherGrabber.accessibilityHint = @\"Tap or swipe up to switch containers.\";\n",
    "    self.appSwitcherGrabber.accessibilityLabel = @\"VibeContainers multitasking gestures\";\n"
    "    self.appSwitcherGrabber.accessibilityHint = @\"Short swipe for Dock, swipe up for Home, hold for the app switcher, or swipe sideways to change apps.\";\n",
    "Short swipe for Dock",
)

replace_once(
    decorated,
    "    [self.appSwitcherGrabber addGestureRecognizer:self.appSwitcherGesture];\n"
    "    NSLog(@\"VibeContainers: installed virtual bottom switcher grabber above the guest scene\");\n",
    "    [self.appSwitcherGrabber addGestureRecognizer:self.appSwitcherGesture];\n\n"
    "    // iPadOS also supports four/five-finger horizontal app switching. Keep\n"
    "    // this recognizer simultaneous so ordinary guest touches still flow.\n"
    "    self.multitaskSwipeGesture = [[UIPanGestureRecognizer alloc]\n"
    "        initWithTarget:self action:@selector(handleMultitaskSwipeGesture:)];\n"
    "    self.multitaskSwipeGesture.minimumNumberOfTouches = 4;\n"
    "    self.multitaskSwipeGesture.maximumNumberOfTouches = 5;\n"
    "    self.multitaskSwipeGesture.cancelsTouchesInView = NO;\n"
    "    self.multitaskSwipeGesture.delegate = self;\n"
    "    [self.view addGestureRecognizer:self.multitaskSwipeGesture];\n"
    "    NSLog(@\"VibeContainers: installed iPad-style Home/Dock/switcher gestures above the guest scene\");\n",
    "installed iPad-style Home/Dock/switcher gestures",
)

replace_once(
    decorated,
    "    if (!self.usesPhoneFullscreenPresentation || !self.isMaximized ||\n        self.view.hidden || self.view.alpha < 0.01 || !self.view.window) {\n",
    "    if (!self.isMaximized ||\n        self.view.hidden || self.view.alpha < 0.01 || !self.view.window) {\n",
    "if (!self.isMaximized ||",
)

regex_once(
    decorated,
    r'- \(void\)handleAppSwitcherGrabberTap \{.*?\n\}\n\n- \(void\)handleAppSwitcherGesture:\(UIPanGestureRecognizer \*\)gesture \{.*?\n\}\n\n(?=- \(BOOL\)gestureRecognizerShouldBegin:)',
    '''- (void)handleAppSwitcherGrabberTap {\n    if (!self.isMaximized || self.view.hidden || self.view.alpha < 0.01 || !self.view.window) {\n        return;\n    }\n    UIImpactFeedbackGenerator *feedback = [[UIImpactFeedbackGenerator alloc]\n        initWithStyle:UIImpactFeedbackStyleLight];\n    [feedback impactOccurred];\n    [[MultitaskDockManager shared] showDockForSystemGesture];\n}\n\n- (void)handleAppSwitcherGesture:(UIPanGestureRecognizer *)gesture {\n    if (gesture.state == UIGestureRecognizerStateBegan) {\n        self.appSwitcherGestureTriggered = NO;\n        self.appSwitcherGestureBeganAt = NSDate.date.timeIntervalSinceReferenceDate;\n        return;\n    }\n    if (gesture.state == UIGestureRecognizerStateCancelled ||\n        gesture.state == UIGestureRecognizerStateFailed) {\n        self.appSwitcherGestureTriggered = NO;\n        return;\n    }\n    if (gesture.state != UIGestureRecognizerStateChanged &&\n        gesture.state != UIGestureRecognizerStateEnded) return;\n    if (self.appSwitcherGestureTriggered || ![self canHandleAppSwitcherGesture:gesture]) return;\n\n    CGPoint translation = [gesture translationInView:self.view.window];\n    CGPoint velocity = [gesture velocityInView:self.view.window];\n    CGFloat horizontal = fabs(translation.x);\n    CGFloat upward = MAX(0.0, -translation.y);\n    NSTimeInterval elapsed = MAX(0.0, NSDate.date.timeIntervalSinceReferenceDate - self.appSwitcherGestureBeganAt);\n\n    // Horizontal travel along the home indicator changes apps without opening\n    // the switcher, matching iPadOS' quick app-to-app gesture.\n    if (horizontal > 44.0 && horizontal > fabs(translation.y) * 1.25) {\n        self.appSwitcherGestureTriggered = YES;\n        NSInteger direction = translation.x < 0 ? 1 : -1;\n        UIImpactFeedbackGenerator *feedback = [[UIImpactFeedbackGenerator alloc]\n            initWithStyle:UIImpactFeedbackStyleLight];\n        [feedback impactOccurred];\n        [[MultitaskDockManager shared] cycleAppFrom:self.dataUUID direction:direction];\n        return;\n    }\n\n    if (gesture.state == UIGestureRecognizerStateChanged) {\n        // A deliberate pause after lifting the app opens the switcher.\n        if (elapsed >= 0.40 && upward >= 32.0 && upward < 165.0 &&\n            upward > horizontal * 1.15 && fabs(velocity.y) < 900.0) {\n            self.appSwitcherGestureTriggered = YES;\n            UIImpactFeedbackGenerator *feedback = [[UIImpactFeedbackGenerator alloc]\n                initWithStyle:UIImpactFeedbackStyleMedium];\n            [feedback impactOccurred];\n            [[MultitaskDockManager shared] presentAppSwitcher];\n            return;\n        }\n\n        // Commit a fast Home flick before the real system gesture gets a chance\n        // to cancel this first-level nested gesture.\n        if (elapsed < 0.30 && upward >= 86.0 && upward > horizontal * 1.10 &&\n            velocity.y < -650.0) {\n            self.appSwitcherGestureTriggered = YES;\n            [[MultitaskDockManager shared] returnToHostHome];\n            return;\n        }\n        return;\n    }\n\n    CGFloat predictedUpward = MAX(upward, -(translation.y + MIN(velocity.y, 0.0) * 0.08));\n    self.appSwitcherGestureTriggered = YES;\n    if (elapsed >= 0.34 && upward >= 28.0 && upward < 165.0) {\n        [[MultitaskDockManager shared] presentAppSwitcher];\n    } else if (upward >= 64.0 || predictedUpward >= 150.0) {\n        [[MultitaskDockManager shared] returnToHostHome];\n    } else if (upward >= 12.0) {\n        [[MultitaskDockManager shared] showDockForSystemGesture];\n    } else {\n        self.appSwitcherGestureTriggered = NO;\n    }\n}\n\n- (void)handleMultitaskSwipeGesture:(UIPanGestureRecognizer *)gesture {\n    if (gesture.state == UIGestureRecognizerStateBegan) {\n        self.multitaskSwipeTriggered = NO;\n        return;\n    }\n    if (gesture.state == UIGestureRecognizerStateCancelled ||\n        gesture.state == UIGestureRecognizerStateFailed) {\n        self.multitaskSwipeTriggered = NO;\n        return;\n    }\n    if (self.multitaskSwipeTriggered || !self.isMaximized || self.view.hidden || !self.view.window) return;\n    if (gesture.state != UIGestureRecognizerStateChanged && gesture.state != UIGestureRecognizerStateEnded) return;\n\n    CGPoint translation = [gesture translationInView:self.view.window];\n    CGFloat horizontal = fabs(translation.x);\n    if (horizontal >= 58.0 && horizontal > fabs(translation.y) * 1.30) {\n        self.multitaskSwipeTriggered = YES;\n        NSInteger direction = translation.x < 0 ? 1 : -1;\n        UIImpactFeedbackGenerator *feedback = [[UIImpactFeedbackGenerator alloc]\n            initWithStyle:UIImpactFeedbackStyleLight];\n        [feedback impactOccurred];\n        [[MultitaskDockManager shared] cycleAppFrom:self.dataUUID direction:direction];\n    }\n}\n\n''',
    "handleMultitaskSwipeGesture",
)

regex_once(
    decorated,
    r'- \(BOOL\)gestureRecognizerShouldBegin:\(UIGestureRecognizer \*\)gestureRecognizer \{.*?\n\}\n\n- \(BOOL\)gestureRecognizer:',
    '''- (BOOL)gestureRecognizerShouldBegin:(UIGestureRecognizer *)gestureRecognizer {\n    if (gestureRecognizer == self.appSwitcherGesture) {\n        return [self canHandleAppSwitcherGesture:(UIPanGestureRecognizer *)gestureRecognizer];\n    }\n    if (gestureRecognizer == self.multitaskSwipeGesture) {\n        return self.isMaximized && !self.view.hidden && self.view.alpha > 0.01 && self.view.window != nil;\n    }\n    return YES;\n}\n\n- (BOOL)gestureRecognizer:''',
    "gestureRecognizer == self.multitaskSwipeGesture",
)

replace_once(
    decorated,
    "    if (self.usesPhoneFullscreenPresentation && self.isMaximized &&\n        !self.view.hidden) {\n",
    "    if (self.isMaximized && !self.view.hidden) {\n",
    "if (self.isMaximized && !self.view.hidden)",
)

# MARK: C bridge for built-in SwiftUI surfaces
bridge = ROOT / "iOSSim/Runtime/MultitaskBridge.m"
bridge_methods = '''\nint32_t IOSSimReturnMultitaskHome(void) {\n    if (![NSThread isMainThread]) return EDEADLK;\n    id manager = IOSSimMultitaskManager();\n    SEL selector = NSSelectorFromString(@"returnToHostHome");\n    if (!manager || ![manager respondsToSelector:selector]) return ENOSYS;\n    ((void (*)(id, SEL))objc_msgSend)(manager, selector);\n    return 0;\n}\n\nint32_t IOSSimShowMultitaskDock(void) {\n    if (![NSThread isMainThread]) return EDEADLK;\n    id manager = IOSSimMultitaskManager();\n    SEL selector = NSSelectorFromString(@"showDockForSystemGesture");\n    if (!manager || ![manager respondsToSelector:selector]) return ENOSYS;\n    ((void (*)(id, SEL))objc_msgSend)(manager, selector);\n    return 0;\n}\n\nint32_t IOSSimCycleMultitaskGuest(const char *dataUUIDBytes, int32_t direction) {\n    if (![NSThread isMainThread]) return EDEADLK;\n    NSString *dataUUID = dataUUIDBytes ? [NSString stringWithUTF8String:dataUUIDBytes] : nil;\n    id manager = IOSSimMultitaskManager();\n    SEL selector = NSSelectorFromString(@"cycleAppFrom:direction:");\n    if (!manager || ![manager respondsToSelector:selector]) return ENOSYS;\n    BOOL focused = ((BOOL (*)(id, SEL, NSString *, NSInteger))objc_msgSend)(\n        manager, selector, dataUUID, (NSInteger)direction\n    );\n    return focused ? 0 : ENOENT;\n}\n'''
replace_once(
    bridge,
    "\nint32_t IOSSimTerminateMultitaskGuests(void) {\n",
    bridge_methods + "\nint32_t IOSSimTerminateMultitaskGuests(void) {\n",
    "IOSSimReturnMultitaskHome",
)

# MARK: Host-side Swift bridge
running = ROOT / "iOSSim/Model/RunningContainerStore.swift"
replace_once(
    running,
    "@_silgen_name(\"IOSSimPresentMultitaskSwitcher\")\nprivate func IOSSimPresentMultitaskSwitcher() -> Int32\n",
    "@_silgen_name(\"IOSSimPresentMultitaskSwitcher\")\nprivate func IOSSimPresentMultitaskSwitcher() -> Int32\n\n"
    "@_silgen_name(\"IOSSimReturnMultitaskHome\")\nprivate func IOSSimReturnMultitaskHome() -> Int32\n\n"
    "@_silgen_name(\"IOSSimShowMultitaskDock\")\nprivate func IOSSimShowMultitaskDock() -> Int32\n\n"
    "@_silgen_name(\"IOSSimCycleMultitaskGuest\")\nprivate func IOSSimCycleMultitaskGuest(_ dataUUID: UnsafePointer<CChar>?, _ direction: Int32) -> Int32\n",
    "IOSSimShowMultitaskDock",
)

running_methods = '''    @discardableResult\n    func returnToVibeHome() -> Bool {\n        IOSSimReturnMultitaskHome() == 0\n    }\n\n    @discardableResult\n    func showGestureDock() -> Bool {\n        IOSSimShowMultitaskDock() == 0\n    }\n\n    @discardableResult\n    func cycleFromHost(direction: Int32) -> Bool {\n        IOSSimCycleMultitaskGuest(nil, direction) == 0\n    }\n\n'''
replace_once(
    running,
    "    func presentSwitcher() {\n",
    running_methods + "    func presentSwitcher() {\n",
    "func showGestureDock()",
)

# MARK: Built-in apps / Settings gesture semantics
app_window = ROOT / "iOSSim/Springboard/AppWindow.swift"
replace_once(
    app_window,
    "    @State private var closeGestureStart: CGPoint?\n",
    "    @State private var closeGestureStart: CGPoint?\n"
    "    @State private var closeGestureBeganAt: TimeInterval = 0\n",
    "closeGestureBeganAt",
)

replace_once(
    app_window,
    "    private var appearance: Appearance { Appearance.shared }\n",
    "    private var appearance: Appearance { Appearance.shared }\n"
    "    private var runningContainers: RunningContainerStore { .shared }\n",
    "private var runningContainers",
)

replace_once(
    app_window,
    "        .opacity(motionDisabled ? (revealed ? 1 : 0) : 1)\n"
    "        .allowsHitTesting(revealed && !transitionActive)\n"
    "        .simultaneousGesture(closeGesture)\n",
    "        .opacity(motionDisabled ? (revealed ? 1 : 0) : 1)\n"
    "        .overlay(alignment: .bottom) {\n"
    "            if revealed && !transitionActive {\n"
    "                Capsule()\n"
    "                    .fill(SysColor.label.opacity(0.78))\n"
    "                    .frame(width: 122, height: 5)\n"
    "                    .padding(.bottom, max(7, safeArea.bottom > 0 ? 7 : 11))\n"
    "                    .allowsHitTesting(false)\n"
    "            }\n"
    "        }\n"
    "        .allowsHitTesting(revealed && !transitionActive)\n"
    "        .simultaneousGesture(closeGesture)\n",
    "frame(width: 122, height: 5)",
)

regex_once(
    app_window,
    r'    /// Swipe up from the bottom edge to go home\.\n    private var closeGesture: some Gesture \{.*?\n    \}\n\n    private func updateCloseGesture',
    '''    /// iPad-style bottom gestures: short swipe = Dock, quick swipe = Home,\n    /// swipe-and-hold = app switcher, horizontal = adjacent running app.\n    private var closeGesture: some Gesture {\n        DragGesture(minimumDistance: 12, coordinateSpace: .global)\n            .onChanged(updateCloseGesture)\n            .onEnded { value in\n                let axis = closeGestureAxis\n                let elapsed = max(0, Date.timeIntervalSinceReferenceDate - closeGestureBeganAt)\n                closeGestureAxis = nil\n                closeGestureStart = nil\n                closeGestureBeganAt = 0\n\n                guard value.startLocation.y > screen.height - 70 else {\n                    settleDismissal()\n                    return\n                }\n\n                if axis == .horizontal {\n                    let horizontal = abs(value.translation.width)\n                    guard horizontal > 48 else {\n                        settleDismissal()\n                        return\n                    }\n                    switchToRunningContainer(direction: value.translation.width < 0 ? 1 : -1)\n                    return\n                }\n\n                guard axis == .vertical else {\n                    settleDismissal()\n                    return\n                }\n\n                let upwardTravel = max(0, -value.translation.height)\n                let predictedUpwardTravel = max(upwardTravel, -value.predictedEndTranslation.height)\n\n                if elapsed >= 0.34, upwardTravel >= 28, upwardTravel < 165,\n                   !runningContainers.visibleEntries.isEmpty {\n                    openContainerSwitcher()\n                } else if upwardTravel >= 64 || predictedUpwardTravel >= 150 {\n                    onClose()\n                } else if upwardTravel >= 12 {\n                    _ = runningContainers.showGestureDock()\n                    settleDismissal()\n                } else {\n                    settleDismissal()\n                }\n            }\n    }\n\n    private func updateCloseGesture''',
    "iPad-style bottom gestures",
)

replace_once(
    app_window,
    "        if closeGestureStart != value.startLocation {\n            closeGestureStart = value.startLocation\n            closeGestureAxis = nil\n        }\n",
    "        if closeGestureStart != value.startLocation {\n            closeGestureStart = value.startLocation\n            closeGestureAxis = nil\n            closeGestureBeganAt = Date.timeIntervalSinceReferenceDate\n        }\n",
    "closeGestureBeganAt = Date.timeIntervalSinceReferenceDate",
)

helpers = '''    private func openContainerSwitcher() {\n        interactiveDismissal = 0\n        onClose()\n        Task { @MainActor in\n            try? await Task.sleep(for: .milliseconds(230))\n            _ = runningContainers.presentCapturedSwitcher()\n        }\n    }\n\n    private func switchToRunningContainer(direction: Int32) {\n        guard !runningContainers.activeEntries.isEmpty else {\n            settleDismissal()\n            return\n        }\n        interactiveDismissal = 0\n        onClose()\n        Task { @MainActor in\n            try? await Task.sleep(for: .milliseconds(230))\n            _ = runningContainers.cycleFromHost(direction: direction)\n        }\n    }\n\n'''
replace_once(
    app_window,
    "    private func settleDismissal() {\n",
    helpers + "    private func settleDismissal() {\n",
    "private func switchToRunningContainer",
)

# Validation markers
checks = {
    manager: ["returnToHostHome()", "showDockForSystemGesture()", "cycleApp(from currentUUID"],
    decorated: ["handleMultitaskSwipeGesture", "showDockForSystemGesture", "returnToHostHome"],
    bridge: ["IOSSimReturnMultitaskHome", "IOSSimShowMultitaskDock", "IOSSimCycleMultitaskGuest"],
    running: ["func showGestureDock()", "func cycleFromHost(direction: Int32)"],
    app_window: ["iPad-style bottom gestures", "frame(width: 122, height: 5)"],
}
for path, markers in checks.items():
    content = path.read_text()
    missing = [marker for marker in markers if marker not in content]
    if missing:
        raise SystemExit(f"gesture validation failed in {path.relative_to(ROOT)}: {missing}")
