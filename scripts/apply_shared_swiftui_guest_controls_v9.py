#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "LiveContainer-3.8.0/MultitaskSupport/MultitaskDockView.swift"
text = PATH.read_text()

# Add the exact same SwiftUI DragGesture state machine used by Springboard's
# AppWindow. The old guest control was a UIKit UIPanGestureRecognizer with a
# separate classifier; keeping two gesture engines is why built-in apps worked
# while real LiveContainer guests did not.
anchor = '''// MARK: - MultitaskDockView Manager
@available(iOS 16.0, *)
@objc public class MultitaskDockManager: NSObject, ObservableObject {
'''
overlay = r'''// MARK: - Shared Springboard-style guest bottom control
@available(iOS 16.0, *)
private struct GuestSpringboardBottomControl: View {
    let screenHeight: CGFloat
    let onHome: () -> Void
    let onSwitcher: () -> Void
    let onDock: () -> Void
    let onCycle: (Int) -> Void

    @State private var gestureAxis: Axis?
    @State private var gestureStart: CGPoint?
    @State private var gestureBeganAt: TimeInterval = 0

    var body: some View {
        ZStack(alignment: .bottom) {
            Color.clear
                .contentShape(Rectangle())

            // Keep the visual affordance identical to AppWindow.
            Capsule()
                .fill(Color.primary.opacity(0.78))
                .frame(width: 122, height: 5)
                .padding(.bottom, 7)
                .allowsHitTesting(false)
        }
        .contentShape(Rectangle())
        .simultaneousGesture(bottomGesture)
        .accessibilityIdentifier("VibeContainers.SharedSpringboardGuestControl")
        .accessibilityLabel("VibeContainers system gestures")
        .accessibilityHint("Swipe up for Home, pull slightly for Dock, pause for the app switcher, or swipe sideways to change apps.")
    }

    // This is intentionally the same state machine and thresholds as
    // iOSSim/Springboard/AppWindow.swift's closeGesture.
    private var bottomGesture: some Gesture {
        DragGesture(minimumDistance: 12, coordinateSpace: .global)
            .onChanged(updateGesture)
            .onEnded { value in
                let axis = gestureAxis
                let elapsed = max(0, Date.timeIntervalSinceReferenceDate - gestureBeganAt)
                gestureAxis = nil
                gestureStart = nil
                gestureBeganAt = 0

                guard value.startLocation.y > screenHeight - 70 else { return }

                if axis == .horizontal {
                    let horizontal = abs(value.translation.width)
                    guard horizontal > 48 else { return }
                    onCycle(value.translation.width < 0 ? 1 : -1)
                    return
                }

                guard axis == .vertical else { return }

                let upwardTravel = max(0, -value.translation.height)
                let predictedUpwardTravel = max(upwardTravel, -value.predictedEndTranslation.height)

                if elapsed >= 0.34, upwardTravel >= 28, upwardTravel < 165 {
                    onSwitcher()
                } else if upwardTravel >= 64 || predictedUpwardTravel >= 150 {
                    onHome()
                } else if upwardTravel >= 12 {
                    onDock()
                }
            }
    }

    private func updateGesture(_ value: DragGesture.Value) {
        guard value.startLocation.y > screenHeight - 70 else { return }

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
    }
}

// MARK: - MultitaskDockView Manager
@available(iOS 16.0, *)
@objc public class MultitaskDockManager: NSObject, ObservableObject {
'''
if "VibeContainers.SharedSpringboardGuestControl" not in text:
    if anchor not in text:
        raise SystemExit("v9: manager anchor not found")
    text = text.replace(anchor, overlay, 1)
    print("v9: added shared SwiftUI guest control")
else:
    print("v9: shared SwiftUI guest control already present")

old_vars = '''    private var systemGestureSurface: UIView?
    private var systemGesturePill: UIView?
    private var systemGestureRecognizer: UIPanGestureRecognizer?
    private var systemGestureBeganAt: TimeInterval = 0
    private var systemGestureTriggered = false
    private var systemGestureLastTranslation: CGPoint = .zero
    private var systemGestureLastVelocity: CGPoint = .zero
'''
new_vars = '''    private var systemGestureSurface: UIView?
    private var systemGestureHostingController: UIHostingController<AnyView>?
'''
if old_vars in text:
    text = text.replace(old_vars, new_vars, 1)
    print("v9: removed separate UIKit pan state")
elif new_vars not in text:
    raise SystemExit("v9: gesture variable block not found")

start = text.find("    private func installSystemGestureSurface() {")
end_marker = "    // MARK: - Vibe iPad-style bottom gestures\n"
end = text.find(end_marker, start)
if start < 0 or end < 0:
    raise SystemExit("v9: system gesture implementation block not found")

replacement = r'''    private func makeSharedGuestBottomControl(screenHeight: CGFloat) -> AnyView {
        AnyView(
            GuestSpringboardBottomControl(
                screenHeight: screenHeight,
                onHome: { [weak self] in
                    self?.returnToHostHome()
                },
                onSwitcher: { [weak self] in
                    self?.presentAppSwitcherLikeSpringboard()
                },
                onDock: { [weak self] in
                    self?.showDockForSystemGesture()
                },
                onCycle: { [weak self] direction in
                    self?.cycleAppLikeSpringboard(direction: direction)
                }
            )
        )
    }

    private func installSystemGestureSurface() {
        dispatchPrecondition(condition: .onQueue(.main))
        guard let window = keyWindow,
              let rootViewController = window.rootViewController else { return }
        let rootView = rootViewController.view!

        // AppWindow accepts a gesture only when it begins in the bottom 70pt.
        // Host the exact SwiftUI DragGesture in that same physical region.
        let height: CGFloat = 70
        let frame = CGRect(
            x: 0,
            y: max(0, rootView.bounds.height - height),
            width: rootView.bounds.width,
            height: height
        )

        if let controller = systemGestureHostingController {
            controller.rootView = makeSharedGuestBottomControl(screenHeight: rootView.bounds.height)
            if controller.parent !== rootViewController {
                controller.willMove(toParent: nil)
                controller.view.removeFromSuperview()
                controller.removeFromParent()
                rootViewController.addChild(controller)
                rootView.addSubview(controller.view)
                controller.didMove(toParent: rootViewController)
            } else if controller.view.superview !== rootView {
                rootView.addSubview(controller.view)
            }
            controller.view.frame = frame
            rootView.bringSubviewToFront(controller.view)
            systemGestureSurface = controller.view
            return
        }

        let controller = UIHostingController(
            rootView: makeSharedGuestBottomControl(screenHeight: rootView.bounds.height)
        )
        controller.view.frame = frame
        controller.view.autoresizingMask = [.flexibleWidth, .flexibleTopMargin]
        controller.view.backgroundColor = .clear
        controller.view.isOpaque = false
        controller.view.isHidden = true

        rootViewController.addChild(controller)
        rootView.addSubview(controller.view)
        controller.didMove(toParent: rootViewController)
        rootView.bringSubviewToFront(controller.view)

        systemGestureHostingController = controller
        systemGestureSurface = controller.view
        NSLog("VibeContainers: exact Springboard SwiftUI guest control installed")
    }

    private func setSystemGestureSurfaceVisible(_ visible: Bool) {
        dispatchPrecondition(condition: .onQueue(.main))
        installSystemGestureSurface()
        systemGestureSurface?.isHidden = !visible
        if visible,
           let surface = systemGestureSurface,
           let rootView = surface.superview {
            rootView.bringSubviewToFront(surface)
            if let dockView = hostingController?.view,
               dockView.superview === rootView {
                rootView.bringSubviewToFront(dockView)
            }
        }
    }

    private func currentSystemGestureAppUUID() -> String? {
        for app in apps.reversed() {
            if let view = app.view,
               view.window != nil,
               !view.isHidden,
               view.alpha > 0.01 {
                return app.appUUID
            }
        }
        return apps.last?.appUUID
    }

    /// AppWindow's switcher path closes its app surface first, waits 230 ms,
    /// then asks RunningContainerStore to present the captured switcher. Do the
    /// same for a real guest instead of presenting from inside the live host.
    private func presentAppSwitcherLikeSpringboard() {
        dispatchPrecondition(condition: .onQueue(.main))
        setSystemGestureSurfaceVisible(false)

        let previews = captureAppSwitcherPreviews()
        let previewViews = captureAppSwitcherPreviewViews()
        hideGuestSurfacesForAppSwitcher()
        demoteHostedSurfacesForHostOverlay()

        DispatchQueue.main.asyncAfter(deadline: .now() + 0.230) { [weak self] in
            guard let self else { return }
            NotificationCenter.default.post(
                name: Notification.Name("IOSSimShowContainerSwitcher"),
                object: nil,
                userInfo: [
                    "previews": previews,
                    "previewViews": previewViews,
                    "animated": true,
                ]
            )
            NSLog("VibeContainers: Springboard-matched guest switcher committed after 230 ms")
        }
    }

    /// AppWindow closes first and changes apps after the same 230 ms handoff.
    private func cycleAppLikeSpringboard(direction: Int) {
        dispatchPrecondition(condition: .onQueue(.main))
        let currentUUID = currentSystemGestureAppUUID()
        setSystemGestureSurfaceVisible(false)
        hideGuestSurfacesForAppSwitcher()

        DispatchQueue.main.asyncAfter(deadline: .now() + 0.230) { [weak self] in
            guard let self else { return }
            _ = self.cycleApp(from: currentUUID, direction: direction)
            NSLog("VibeContainers: Springboard-matched guest cycle committed after 230 ms")
        }
    }

'''
text = text[:start] + replacement + text[end:]
print("v9: replaced UIKit guest pan with Springboard-style SwiftUI DragGesture")

# Validate the old guest-only recognizer no longer exists in the manager source.
forbidden = [
    "@objc private func handleSystemGesture(_ gesture: UIPanGestureRecognizer)",
    "systemGestureRecognizer = pan",
    "systemGestureLastTranslation",
    "systemGestureLastVelocity",
]
for needle in forbidden:
    if needle in text:
        raise SystemExit(f"v9: old guest pan path still present: {needle}")

required = [
    'VibeContainers.SharedSpringboardGuestControl',
    'DragGesture(minimumDistance: 12, coordinateSpace: .global)',
    'value.startLocation.y > screenHeight - 70',
    'elapsed >= 0.34, upwardTravel >= 28, upwardTravel < 165',
    'upwardTravel >= 64 || predictedUpwardTravel >= 150',
    'upwardTravel >= 12',
    '.now() + 0.230',
    'exact Springboard SwiftUI guest control installed',
]
for needle in required:
    if needle not in text:
        raise SystemExit(f"v9: required shared-control marker missing: {needle}")

PATH.write_text(text)
print(f"v9: normalized {PATH.relative_to(ROOT)}")
