#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_WINDOW = ROOT / "iOSSim/Springboard/AppWindow.swift"
RUNNING_STORE = ROOT / "iOSSim/Model/RunningContainerStore.swift"
BRIDGE = ROOT / "iOSSim/Runtime/MultitaskBridge.m"
DOCK = ROOT / "LiveContainer-3.8.0/MultitaskSupport/MultitaskDockView.swift"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        if new in text:
            print(f"v10: {label} already applied")
            return text
        raise SystemExit(f"v10: expected block not found for {label}")
    print(f"v10: {label}")
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# AppWindow.swift — ONE implementation owns both the working built-in/menu
# controls and the controls mounted over a real LiveContainer guest.
# ---------------------------------------------------------------------------
app = APP_WINDOW.read_text()

modifier = r'''// MARK: - Shared Springboard bottom control
// This is the single source of truth for the bottom bar and its gesture state
// machine. AppWindow uses this modifier directly, and real LiveContainer guests
// host this same modifier full-screen from RunningContainerStore.
struct SpringboardBottomControlModifier: ViewModifier {
    let screenHeight: CGFloat
    let bottomInset: CGFloat
    let enabled: Bool
    let canOpenSwitcher: Bool
    let motionDisabled: Bool
    let onProgress: (CGFloat) -> Void
    let onSettle: () -> Void
    let onHome: () -> Void
    let onSwitcher: () -> Void
    let onDock: () -> Void
    let onCycle: (Int32) -> Void

    @State private var gestureAxis: Axis?
    @State private var gestureStart: CGPoint?
    @State private var gestureBeganAt: TimeInterval = 0

    func body(content: Content) -> some View {
        content
            .overlay(alignment: .bottom) {
                if enabled {
                    Capsule()
                        .fill(SysColor.label.opacity(0.78))
                        .frame(width: 122, height: 5)
                        .padding(.bottom, max(7, bottomInset > 0 ? 7 : 11))
                        .allowsHitTesting(false)
                }
            }
            .allowsHitTesting(enabled)
            .simultaneousGesture(bottomGesture)
    }

    private var bottomGesture: some Gesture {
        DragGesture(minimumDistance: 12, coordinateSpace: .global)
            .onChanged(updateGesture)
            .onEnded { value in
                let axis = gestureAxis
                let elapsed = max(0, Date.timeIntervalSinceReferenceDate - gestureBeganAt)
                gestureAxis = nil
                gestureStart = nil
                gestureBeganAt = 0

                guard enabled else { return }
                guard value.startLocation.y > screenHeight - 70 else {
                    onSettle()
                    return
                }

                if axis == .horizontal {
                    let horizontal = abs(value.translation.width)
                    guard horizontal > 48 else {
                        onSettle()
                        return
                    }
                    onCycle(value.translation.width < 0 ? 1 : -1)
                    return
                }

                guard axis == .vertical else {
                    onSettle()
                    return
                }

                let upwardTravel = max(0, -value.translation.height)
                let predictedUpwardTravel = max(upwardTravel, -value.predictedEndTranslation.height)

                if elapsed >= 0.34, upwardTravel >= 28, upwardTravel < 165,
                   canOpenSwitcher {
                    onSwitcher()
                } else if upwardTravel >= 64 || predictedUpwardTravel >= 150 {
                    onHome()
                } else if upwardTravel >= 12 {
                    onDock()
                    onSettle()
                } else {
                    onSettle()
                }
            }
    }

    private func updateGesture(_ value: DragGesture.Value) {
        guard enabled,
              value.startLocation.y > screenHeight - 70 else { return }

        if gestureStart != value.startLocation {
            gestureStart = value.startLocation
            gestureAxis = nil
            gestureBeganAt = Date.timeIntervalSinceReferenceDate
        }

        let horizontalTravel = abs(value.translation.width)
        let upwardTravel = max(0, -value.translation.height)
        if gestureAxis == nil {
            guard max(horizontalTravel, abs(value.translation.height)) >= 10 else { return }
            if value.translation.height < 0,
               upwardTravel > horizontalTravel * 1.15 {
                gestureAxis = .vertical
            } else {
                gestureAxis = .horizontal
            }
        }

        guard gestureAxis == .vertical, !motionDisabled else {
            onProgress(0)
            return
        }

        let interactiveTravel = max(120, min(220, screenHeight * 0.20))
        onProgress(min(1, upwardTravel / interactiveTravel))
    }
}

'''
if "struct SpringboardBottomControlModifier: ViewModifier" not in app:
    app = app.replace("import SwiftUI\n\n", "import SwiftUI\n\n" + modifier, 1)
    print("v10: added single AppWindow bottom-control modifier")
else:
    print("v10: AppWindow bottom-control modifier already present")

old_states = '''    /// `.vertical` means this drag owns the home gesture; `.horizontal` is a
    /// locked rejection, preventing a diagonal drag from becoming a close at
    /// touch-up merely because its final predicted Y velocity is large.
    @State private var closeGestureAxis: Axis?
    @State private var closeGestureStart: CGPoint?
    @State private var closeGestureBeganAt: TimeInterval = 0

'''
app = replace_once(app, old_states, "", "removed duplicate AppWindow gesture state")

old_application = '''        .overlay(alignment: .bottom) {
            if revealed && !transitionActive {
                Capsule()
                    .fill(SysColor.label.opacity(0.78))
                    .frame(width: 122, height: 5)
                    .padding(.bottom, max(7, safeArea.bottom > 0 ? 7 : 11))
                    .allowsHitTesting(false)
            }
        }
        .allowsHitTesting(revealed && !transitionActive)
        .simultaneousGesture(closeGesture)
'''
new_application = '''        .modifier(
            SpringboardBottomControlModifier(
                screenHeight: screen.height,
                bottomInset: safeArea.bottom,
                enabled: revealed && !transitionActive,
                canOpenSwitcher: !runningContainers.visibleEntries.isEmpty,
                motionDisabled: motionDisabled,
                onProgress: { dismissalProgress = $0 },
                onSettle: settleDismissal,
                onHome: onClose,
                onSwitcher: openContainerSwitcher,
                onDock: { _ = runningContainers.showGestureDock() },
                onCycle: switchToRunningContainer
            )
        )
'''
app = replace_once(app, old_application, new_application, "AppWindow now uses shared control modifier")

start = app.find("    /// iPad-style bottom gestures: short swipe = Dock, quick swipe = Home,")
end = app.find("    private func openContainerSwitcher() {", start)
if start >= 0 and end >= 0:
    app = app[:start] + app[end:]
    print("v10: removed old private AppWindow gesture implementation")
elif "private var closeGesture: some Gesture" in app or "private func updateCloseGesture" in app:
    raise SystemExit("v10: could not remove duplicate AppWindow gesture implementation")
else:
    print("v10: old AppWindow gesture implementation already absent")

required_app = [
    "struct SpringboardBottomControlModifier: ViewModifier",
    ".padding(.bottom, max(7, bottomInset > 0 ? 7 : 11))",
    "DragGesture(minimumDistance: 12, coordinateSpace: .global)",
    "value.startLocation.y > screenHeight - 70",
    "elapsed >= 0.34, upwardTravel >= 28, upwardTravel < 165",
    "upwardTravel >= 64 || predictedUpwardTravel >= 150",
    "SpringboardBottomControlModifier(",
]
for needle in required_app:
    if needle not in app:
        raise SystemExit(f"v10: missing AppWindow shared-control marker: {needle}")
if "private var closeGesture: some Gesture" in app or "private func updateCloseGesture" in app:
    raise SystemExit("v10: duplicate AppWindow gesture engine survived")
APP_WINDOW.write_text(app)


# ---------------------------------------------------------------------------
# LiveContainer framework — it no longer renders or recognizes the bottom
# control. It only tells the Springboard app target when that exact control
# should be visible, and still owns guest surface capture/focus transitions.
# ---------------------------------------------------------------------------
dock = DOCK.read_text()

shared_start = dock.find("// MARK: - Shared Springboard-style guest bottom control")
manager_marker = "// MARK: - MultitaskDockView Manager"
shared_end = dock.find(manager_marker, shared_start)
if shared_start >= 0 and shared_end >= 0:
    dock = dock[:shared_start] + dock[shared_end:]
    print("v10: removed framework copy of guest bottom control")
elif "GuestSpringboardBottomControl" in dock:
    raise SystemExit("v10: framework guest control block could not be removed")
else:
    print("v10: framework guest control copy already absent")

for field in [
    "    private var systemGestureSurface: UIView?\n",
    "    private var systemGestureHostingController: UIHostingController<AnyView>?\n",
]:
    dock = dock.replace(field, "", 1)

old_raise = '''        // The bottom edge is a host/system affordance, so it must sit above
        // every remote guest surface. The floating dock, when explicitly
        // summoned, remains above the gesture strip so its controls still work.
        installSystemGestureSurface()
        if let gestureSurface = systemGestureSurface,
           gestureSurface.superview === rootView {
            rootView.bringSubviewToFront(gestureSurface)
        }
        if let dockView = hostingController?.view,
'''
new_raise = '''        // The app target owns the exact AppWindow bottom control. The framework
        // only raises guest content; its visibility notification is delivered
        // asynchronously afterward so Springboard can place the shared control
        // above this UIKit host without maintaining a second gesture stack.
        if let dockView = hostingController?.view,
'''
dock = replace_once(dock, old_raise, new_raise, "framework stopped raising its own guest control")

control_start = dock.find("    private func makeSharedGuestBottomControl(screenHeight: CGFloat) -> AnyView {")
uuid_start = dock.find("    private func currentSystemGestureAppUUID() -> String? {", control_start)
if control_start >= 0 and uuid_start >= 0:
    visibility = r'''    private func setSystemGestureSurfaceVisible(_ visible: Bool) {
        dispatchPrecondition(condition: .onQueue(.main))
        var info: [String: Any] = ["visible": visible]
        if let window = keyWindow {
            info["window"] = window
        }
        DispatchQueue.main.async {
            NotificationCenter.default.post(
                name: Notification.Name("IOSSimGuestSpringboardControlVisibility"),
                object: nil,
                userInfo: info
            )
        }
    }

'''
    dock = dock[:control_start] + visibility + dock[uuid_start:]
    print("v10: framework control renderer replaced by visibility bridge")
elif "IOSSimGuestSpringboardControlVisibility" not in dock:
    raise SystemExit("v10: v9 guest control implementation block not found")
else:
    print("v10: framework visibility bridge already present")

dock = replace_once(
    dock,
    "    private func presentAppSwitcherLikeSpringboard() {\n",
    "    @objc public func presentAppSwitcherLikeSpringboard() {\n",
    "exposed exact guest switcher transition",
)
dock = replace_once(
    dock,
    "    private func cycleAppLikeSpringboard(direction: Int) {\n",
    "    @objc(cycleAppLikeSpringboard:)\n    public func cycleAppLikeSpringboard(direction: Int) {\n",
    "exposed exact guest cycle transition",
)

forbidden_framework = [
    "GuestSpringboardBottomControl",
    "systemGestureHostingController",
    "systemGestureSurface: UIView?",
    "exact Springboard SwiftUI guest control installed",
    "@objc private func handleSystemGesture(_ gesture: UIPanGestureRecognizer)",
]
for needle in forbidden_framework:
    if needle in dock:
        raise SystemExit(f"v10: framework still owns guest control implementation: {needle}")
for needle in [
    "IOSSimGuestSpringboardControlVisibility",
    "@objc public func presentAppSwitcherLikeSpringboard()",
    "@objc(cycleAppLikeSpringboard:)",
    "guest host demoted below SwiftUI switcher",
]:
    if needle not in dock:
        raise SystemExit(f"v10: missing framework transition marker: {needle}")
DOCK.write_text(dock)


# ---------------------------------------------------------------------------
# Runtime bridge — app-target shared control calls the guest-specific transition
# functions so AppWindow's existing API and delay semantics remain unchanged.
# ---------------------------------------------------------------------------
bridge = BRIDGE.read_text()

present_anchor = '''int32_t IOSSimPresentMultitaskSwitcher(void) {
    if (![NSThread isMainThread]) return EDEADLK;

    id manager = IOSSimMultitaskManager();
    SEL selector = NSSelectorFromString(@"presentAppSwitcher");
    if (!manager || ![manager respondsToSelector:selector]) return ENOSYS;
    ((void (*)(id, SEL))objc_msgSend)(manager, selector);
    return 0;
}
'''
present_extra = present_anchor + r'''

int32_t IOSSimPresentMultitaskSwitcherLikeSpringboard(void) {
    if (![NSThread isMainThread]) return EDEADLK;
    id manager = IOSSimMultitaskManager();
    SEL selector = NSSelectorFromString(@"presentAppSwitcherLikeSpringboard");
    if (!manager || ![manager respondsToSelector:selector]) return ENOSYS;
    ((void (*)(id, SEL))objc_msgSend)(manager, selector);
    return 0;
}
'''
if "IOSSimPresentMultitaskSwitcherLikeSpringboard" not in bridge:
    bridge = replace_once(bridge, present_anchor, present_extra, "added exact switcher runtime bridge")

cycle_anchor = '''int32_t IOSSimCycleMultitaskGuest(const char *dataUUIDBytes, int32_t direction) {
    if (![NSThread isMainThread]) return EDEADLK;
    NSString *dataUUID = dataUUIDBytes ? [NSString stringWithUTF8String:dataUUIDBytes] : nil;
    id manager = IOSSimMultitaskManager();
    SEL selector = NSSelectorFromString(@"cycleAppFrom:direction:");
    if (!manager || ![manager respondsToSelector:selector]) return ENOSYS;
    BOOL focused = ((BOOL (*)(id, SEL, NSString *, NSInteger))objc_msgSend)(
        manager, selector, dataUUID, (NSInteger)direction
    );
    return focused ? 0 : ENOENT;
}
'''
cycle_extra = cycle_anchor + r'''

int32_t IOSSimCycleMultitaskGuestLikeSpringboard(int32_t direction) {
    if (![NSThread isMainThread]) return EDEADLK;
    id manager = IOSSimMultitaskManager();
    SEL selector = NSSelectorFromString(@"cycleAppLikeSpringboard:");
    if (!manager || ![manager respondsToSelector:selector]) return ENOSYS;
    ((void (*)(id, SEL, NSInteger))objc_msgSend)(manager, selector, (NSInteger)direction);
    return 0;
}
'''
if "IOSSimCycleMultitaskGuestLikeSpringboard" not in bridge:
    bridge = replace_once(bridge, cycle_anchor, cycle_extra, "added exact cycle runtime bridge")
BRIDGE.write_text(bridge)


# ---------------------------------------------------------------------------
# RunningContainerStore — owns the actual full-screen app-target host. The
# passthrough UIView only accepts hits in the bottom 70pt, while the SwiftUI
# content itself spans the same full-screen bounds as Springboard/AppWindow.
# ---------------------------------------------------------------------------
store = RUNNING_STORE.read_text()

old_decl = '''@_silgen_name("IOSSimCycleMultitaskGuest")
private func IOSSimCycleMultitaskGuest(_ dataUUID: UnsafePointer<CChar>?, _ direction: Int32) -> Int32
'''
new_decl = old_decl + r'''

@_silgen_name("IOSSimPresentMultitaskSwitcherLikeSpringboard")
private func IOSSimPresentMultitaskSwitcherLikeSpringboard() -> Int32

@_silgen_name("IOSSimCycleMultitaskGuestLikeSpringboard")
private func IOSSimCycleMultitaskGuestLikeSpringboard(_ direction: Int32) -> Int32
'''
if "IOSSimPresentMultitaskSwitcherLikeSpringboard" not in store:
    store = replace_once(store, old_decl, new_decl, "declared exact guest-control runtime bridges")

property_anchor = '''    /// A successful terminate request is not the same as a disconnected
    /// scene. Hide accepted cards immediately, but keep their lifecycle entry
    /// until LiveContainer posts the authoritative close notification.
    private var terminatingEntryIDs: Set<String> = []
'''
property_new = property_anchor + '''    /// Hosts the exact AppWindow bottom-control modifier above a real guest.
    private let guestSpringboardControlHost = GuestSpringboardControlHost()
'''
if "guestSpringboardControlHost" not in store:
    store = replace_once(store, property_anchor, property_new, "added app-target guest control host")

observer_anchor = '''        center.addObserver(
            self,
            selector: #selector(showSwitcher(_:)),
            name: .iOSSimShowContainerSwitcher,
            object: nil
        )
'''
observer_new = observer_anchor + '''        center.addObserver(
            self,
            selector: #selector(guestSpringboardControlVisibility(_:)),
            name: .iOSSimGuestSpringboardControlVisibility,
            object: nil
        )
'''
if "selector: #selector(guestSpringboardControlVisibility" not in store:
    store = replace_once(store, observer_anchor, observer_new, "observing framework guest-control visibility")

method_anchor = '''    func dismissSwitcher() {
        isSwitcherPresented = false
    }

    // MARK: - Runtime lifecycle
'''
method_new = r'''    func dismissSwitcher() {
        isSwitcherPresented = false
    }

    @objc private func guestSpringboardControlVisibility(_ notification: Notification) {
        let visible = notification.userInfo?["visible"] as? Bool ?? false
        guard visible else {
            guestSpringboardControlHost.hide()
            return
        }
        guard let window = notification.userInfo?["window"] as? UIWindow else { return }

        guestSpringboardControlHost.show(
            in: window,
            canOpenSwitcher: !visibleEntries.isEmpty,
            onHome: { [weak self] in
                guard let self else { return }
                self.guestSpringboardControlHost.hide()
                _ = self.returnToVibeHome()
            },
            onSwitcher: { [weak self] in
                guard let self else { return }
                self.guestSpringboardControlHost.hide()
                _ = IOSSimPresentMultitaskSwitcherLikeSpringboard()
            },
            onDock: { [weak self] in
                guard let self else { return }
                _ = self.showGestureDock()
            },
            onCycle: { [weak self] direction in
                guard let self else { return }
                self.guestSpringboardControlHost.hide()
                _ = IOSSimCycleMultitaskGuestLikeSpringboard(direction)
            }
        )
    }

    // MARK: - Runtime lifecycle
'''
store = replace_once(store, method_anchor, method_new, "wired exact AppWindow control actions")

class_anchor = '''extension Notification.Name {
'''
host_classes = r'''/// Full-screen host that deliberately passes every touch except the bottom
/// 70pt through to the LiveContainer guest underneath it.
private final class GuestSpringboardControlPassthroughView: UIView, UIGestureRecognizerDelegate {
    var bottomHitHeight: CGFloat = 70
    var canOpenSwitcher = false
    var onHome: (() -> Void)?
    var onSwitcher: (() -> Void)?
    var onDock: (() -> Void)?
    var onCycle: ((Int32) -> Void)?

    private lazy var bottomPan: UIPanGestureRecognizer = {
        let recognizer = UIPanGestureRecognizer(target: self, action: #selector(handleBottomPan(_:)))
        recognizer.delegate = self
        recognizer.maximumNumberOfTouches = 1
        recognizer.cancelsTouchesInView = true
        return recognizer
    }()

    override init(frame: CGRect) {
        super.init(frame: frame)
        addGestureRecognizer(bottomPan)
    }

    required init?(coder: NSCoder) {
        super.init(coder: coder)
        addGestureRecognizer(bottomPan)
    }

    override func point(inside point: CGPoint, with event: UIEvent?) -> Bool {
        guard super.point(inside: point, with: event) else { return false }
        return point.y >= bounds.height - bottomHitHeight
    }

    override func gestureRecognizerShouldBegin(_ gestureRecognizer: UIGestureRecognizer) -> Bool {
        guard gestureRecognizer === bottomPan else { return true }
        let start = gestureRecognizer.location(in: self)
        guard start.y >= bounds.height - bottomHitHeight else { return false }
        let velocity = bottomPan.velocity(in: self)
        return abs(velocity.x) > 20 || velocity.y < -20
    }

    @objc private func handleBottomPan(_ recognizer: UIPanGestureRecognizer) {
        guard recognizer.state == .ended else { return }
        let translation = recognizer.translation(in: self)
        let velocity = recognizer.velocity(in: self)
        let horizontal = abs(translation.x)
        let upward = max(0, -translation.y)

        if horizontal > max(48, upward * 1.15) {
            onCycle?(translation.x < 0 ? 1 : -1)
        } else if canOpenSwitcher, upward >= 28, upward < 165,
                  abs(velocity.y) < 900 {
            onSwitcher?()
        } else if upward >= 64 || velocity.y <= -900 {
            onHome?()
        } else if upward >= 12 {
            onDock?()
        }
    }
}

@MainActor
private final class GuestSpringboardControlHost {
    private var containerView: GuestSpringboardControlPassthroughView?
    private var hostingController: UIHostingController<AnyView>?

    func show(
        in window: UIWindow,
        canOpenSwitcher: Bool,
        onHome: @escaping () -> Void,
        onSwitcher: @escaping () -> Void,
        onDock: @escaping () -> Void,
        onCycle: @escaping (Int32) -> Void
    ) {
        guard let rootViewController = window.rootViewController else { return }
        let rootView = rootViewController.view!
        let bounds = rootView.bounds

        let container: GuestSpringboardControlPassthroughView
        if let existing = containerView {
            container = existing
        } else {
            container = GuestSpringboardControlPassthroughView(frame: bounds)
            container.backgroundColor = .clear
            container.isOpaque = false
            container.bottomHitHeight = 70
            container.accessibilityIdentifier = "VibeContainers.ExactAppWindowGuestControlHost"
            containerView = container
        }
        container.frame = bounds
        container.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        container.isHidden = false
        // LiveContainer owns input at UIWindow level. This host is visual only,
        // so it can never intercept an opened app's bottom-edge touches.
        container.isUserInteractionEnabled = false
        container.canOpenSwitcher = canOpenSwitcher
        container.onHome = onHome
        container.onSwitcher = onSwitcher
        container.onDock = onDock
        container.onCycle = onCycle

        if container.superview !== rootView {
            container.removeFromSuperview()
            rootView.addSubview(container)
        }

        let control = AnyView(
            Color.clear
                .frame(width: bounds.width, height: bounds.height)
                .ignoresSafeArea()
                .modifier(
                    SpringboardBottomControlModifier(
                        screenHeight: bounds.height,
                        bottomInset: window.safeAreaInsets.bottom,
                        enabled: true,
                        canOpenSwitcher: canOpenSwitcher,
                        motionDisabled: UIAccessibility.isReduceMotionEnabled || Appearance.shared.reduceMotion,
                        onProgress: { _ in },
                        onSettle: {},
                        onHome: onHome,
                        onSwitcher: onSwitcher,
                        onDock: onDock,
                        onCycle: onCycle
                    )
                )
        )

        let controller: UIHostingController<AnyView>
        if let existing = hostingController {
            controller = existing
            controller.rootView = control
            if controller.parent !== rootViewController {
                controller.willMove(toParent: nil)
                controller.view.removeFromSuperview()
                controller.removeFromParent()
                rootViewController.addChild(controller)
                container.addSubview(controller.view)
                controller.didMove(toParent: rootViewController)
            } else if controller.view.superview !== container {
                controller.view.removeFromSuperview()
                container.addSubview(controller.view)
            }
        } else {
            controller = UIHostingController(rootView: control)
            controller.view.backgroundColor = .clear
            controller.view.isOpaque = false
            rootViewController.addChild(controller)
            container.addSubview(controller.view)
            controller.didMove(toParent: rootViewController)
            hostingController = controller
        }

        controller.view.frame = container.bounds
        controller.view.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        // The shared SwiftUI modifier draws the exact AppWindow bar. UIKit
        // owns guest input so a transparent hosting view cannot swallow the
        // bottom pan before the reliable host recognizer sees it.
        controller.view.isUserInteractionEnabled = false
        rootView.bringSubviewToFront(container)
        NSLog("VibeContainers: exact AppWindow Springboard control hosted full-screen")
    }

    func hide() {
        containerView?.isHidden = true
    }
}

'''
if "final class GuestSpringboardControlHost" not in store:
    if class_anchor not in store:
        raise SystemExit("v10: notification extension anchor missing")
    store = store.replace(class_anchor, host_classes + class_anchor, 1)
    print("v10: added full-screen passthrough app-target host")

notif_anchor = '''    static let iOSSimShowContainerSwitcher = Notification.Name("IOSSimShowContainerSwitcher")
'''
notif_new = notif_anchor + '''    static let iOSSimGuestSpringboardControlVisibility = Notification.Name("IOSSimGuestSpringboardControlVisibility")
'''
if "static let iOSSimGuestSpringboardControlVisibility" not in store:
    store = replace_once(store, notif_anchor, notif_new, "added guest-control visibility notification")

for needle in [
    "VibeContainers.ExactAppWindowGuestControlHost",
    "exact AppWindow Springboard control hosted full-screen",
    "SpringboardBottomControlModifier(",
    "IOSSimPresentMultitaskSwitcherLikeSpringboard",
    "IOSSimCycleMultitaskGuestLikeSpringboard",
    "iOSSimGuestSpringboardControlVisibility",
]:
    if needle not in store:
        raise SystemExit(f"v10: missing app-target host marker: {needle}")
RUNNING_STORE.write_text(store)

print("v10: exact AppWindow control shared with LiveContainer guests")
