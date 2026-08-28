import SwiftUI

/// Presents an app through a circular reveal centered on its source icon. The
/// app remains laid out at full size behind the reveal, so no intermediate
/// frame can squash its interface or resemble a page flip.
struct AppWindow: View {
    let item: HomeItem
    let source: CGRect
    let screen: CGSize
    let progress: CGFloat
    /// Drives the icon/app content handoff independently of the geometry spring.
    let revealed: Bool
    /// Direct manipulation from the bottom-edge home gesture. Springboard also
    /// reads this value so its icons can return underneath the retreating app.
    @Binding var dismissalProgress: CGFloat
    /// Kept explicit so the expensive reveal mask is absent while the app is
    /// sitting full-screen and scrolling normally.
    let transitionActive: Bool
    let onClose: () -> Void

    /// `.vertical` means this drag owns the home gesture; `.horizontal` is a
    /// locked rejection, preventing a diagonal drag from becoming a close at
    /// touch-up merely because its final predicted Y velocity is large.
    @State private var closeGestureAxis: Axis?
    @State private var closeGestureStart: CGPoint?
    @State private var closeGestureBeganAt: TimeInterval = 0

    @Environment(\.deviceSafeArea) private var safeArea
    @Environment(\.accessibilityReduceMotion) private var accessibilityReduceMotion

    private var appearance: Appearance { Appearance.shared }
    private var runningContainers: RunningContainerStore { .shared }
    private var motionDisabled: Bool {
        accessibilityReduceMotion || appearance.reduceMotion
    }

    var body: some View {
        let launchRect = validSource
        let revealCenter = launchRect.map {
            CGPoint(x: $0.midX, y: $0.midY)
        } ?? CGPoint(x: screen.width / 2, y: screen.height / 2)
        let initialRadius = launchRect.map { $0.width / 2 } ?? 1
        let finalRadius = maximumRevealRadius(from: revealCenter)
        // These target values are deliberately not capped above 1: the spring
        // is free to contribute a very small radius/content-scale overshoot.
        let revealRadius = lerp(initialRadius, finalRadius, progress)
        let contentScale = motionDisabled ? 1 : 0.98 + progress * 0.02
        let swipeInfluence = motionDisabled
            ? 0
            : dismissalProgress * min(1, max(0, progress))
        let usesCircularReveal = transitionActive && !motionDisabled

        let surface = ZStack {
            SysColor.groupedBackground

            guestContent
                .environment(\.deviceSafeArea, safeArea)
                .frame(width: screen.width, height: screen.height)
                .scaleEffect(contentScale)
                .opacity(motionDisabled || revealed ? 1 : 0)
        }
        .frame(width: screen.width, height: screen.height)

        surface
        // Keep one stable modifier topology for the lifetime of guestContent.
        // At rest the shape returns the input rect, which is a cheap clip and
        // cannot recreate/reset an app's navigation or scroll state.
        .clipShape(
            CircularRevealShape(
                center: revealCenter,
                radius: revealRadius,
                revealsCircle: usesCircularReveal
            )
        )
        // The live home gesture is a restrained lift. The circular mask only
        // enters once close commits, avoiding masked full-screen rendering (or
        // view identity churn) on every tentative and cancelled swipe.
        .scaleEffect(1 - swipeInfluence * 0.025)
        .offset(y: -swipeInfluence * 12)
        .overlay {
            if usesCircularReveal, let launchRect {
                launchArtwork(size: launchRect.width)
                    .shadow(color: .black.opacity(0.28), radius: 4, y: 2)
                    .scaleEffect(revealed ? 1.04 : 1)
                    .opacity(revealed ? 0 : 1)
                    .position(x: launchRect.midX, y: launchRect.midY)
            }
        }
        // Reduce Motion keeps the surface full-screen and cross-fades it as a
        // unit; normal motion keeps the background opaque during the morph.
        .opacity(motionDisabled ? (revealed ? 1 : 0) : 1)
        .overlay(alignment: .bottom) {
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
    }

    /// Clamp stale frames after rotation or search dismissal to the current
    /// canvas so the expanding mask never starts off-screen.
    private var validSource: CGRect? {
        guard screen.width > 1, screen.height > 1,
              source.minX.isFinite, source.minY.isFinite,
              source.width.isFinite, source.height.isFinite,
              !source.isEmpty else { return nil }

        let side = min(min(source.width, source.height), min(screen.width, screen.height))
        guard side > 1 else { return nil }
        let half = side / 2
        let x = min(max(source.midX, half), screen.width - half)
        let y = min(max(source.midY, half), screen.height - half)
        return CGRect(x: x - half, y: y - half, width: side, height: side)
    }

    private func maximumRevealRadius(from center: CGPoint) -> CGFloat {
        let horizontal = max(center.x, screen.width - center.x)
        let vertical = max(center.y, screen.height - center.y)
        let cornerDistance = (horizontal * horizontal + vertical * vertical).squareRoot()
        // Overscan keeps the corners covered while the lightly under-damped
        // spring completes its final sub-pixel settle.
        return cornerDistance + max(screen.width, screen.height) * 0.06
    }

    @ViewBuilder private var guestContent: some View {
        if let app = item.builtinApp {
            app.screen
        } else if let bundle = item.guestBundle {
            GuestContainerView(bundleIdentifier: bundle)
        }
    }

    @ViewBuilder
    private func launchArtwork(size: CGFloat) -> some View {
        if let app = item.builtinApp {
            IconArtwork(app: app, size: size)
        } else if let bundle = item.guestBundle {
            PackageIcon(
                url: PackageStore.shared.installed[bundle]?.iconURL,
                tint: nil,
                size: size
            )
        }
    }

    /// iPad-style bottom gestures: short swipe = Dock, quick swipe = Home,
    /// swipe-and-hold = app switcher, horizontal = adjacent running app.
    private var closeGesture: some Gesture {
        DragGesture(minimumDistance: 12, coordinateSpace: .global)
            .onChanged(updateCloseGesture)
            .onEnded { value in
                let axis = closeGestureAxis
                let elapsed = max(0, Date.timeIntervalSinceReferenceDate - closeGestureBeganAt)
                closeGestureAxis = nil
                closeGestureStart = nil
                closeGestureBeganAt = 0

                guard value.startLocation.y > screen.height - 70 else {
                    settleDismissal()
                    return
                }

                if axis == .horizontal {
                    let horizontal = abs(value.translation.width)
                    guard horizontal > 48 else {
                        settleDismissal()
                        return
                    }
                    switchToRunningContainer(direction: value.translation.width < 0 ? 1 : -1)
                    return
                }

                guard axis == .vertical else {
                    settleDismissal()
                    return
                }

                let upwardTravel = max(0, -value.translation.height)
                let predictedUpwardTravel = max(upwardTravel, -value.predictedEndTranslation.height)

                if elapsed >= 0.34, upwardTravel >= 28, upwardTravel < 165,
                   !runningContainers.visibleEntries.isEmpty {
                    openContainerSwitcher()
                } else if upwardTravel >= 64 || predictedUpwardTravel >= 150 {
                    onClose()
                } else if upwardTravel >= 12 {
                    _ = runningContainers.showGestureDock()
                    settleDismissal()
                } else {
                    settleDismissal()
                }
            }
    }

    private func updateCloseGesture(_ value: DragGesture.Value) {
        guard revealed, !transitionActive,
              value.startLocation.y > screen.height - 70 else { return }

        if closeGestureStart != value.startLocation {
            closeGestureStart = value.startLocation
            closeGestureAxis = nil
            closeGestureBeganAt = Date.timeIntervalSinceReferenceDate
        }

        let horizontalTravel = abs(value.translation.width)
        let upwardTravel = max(0, -value.translation.height)
        if closeGestureAxis == nil {
            guard max(horizontalTravel, abs(value.translation.height)) >= 10 else { return }
            if value.translation.height < 0,
               upwardTravel > horizontalTravel * 1.15 {
                closeGestureAxis = .vertical
            } else {
                closeGestureAxis = .horizontal
            }
        }

        guard closeGestureAxis == .vertical else {
            dismissalProgress = 0
            return
        }
        guard !motionDisabled else {
            dismissalProgress = 0
            return
        }

        let interactiveTravel = max(120, min(220, screen.height * 0.20))
        dismissalProgress = min(1, upwardTravel / interactiveTravel)
    }

    private func openContainerSwitcher() {
        dismissalProgress = 0
        onClose()
        Task { @MainActor in
            try? await Task.sleep(for: .milliseconds(230))
            _ = runningContainers.presentCapturedSwitcher()
        }
    }

    private func switchToRunningContainer(direction: Int32) {
        guard !runningContainers.activeEntries.isEmpty else {
            settleDismissal()
            return
        }
        dismissalProgress = 0
        onClose()
        Task { @MainActor in
            try? await Task.sleep(for: .milliseconds(230))
            _ = runningContainers.cycleFromHost(direction: direction)
        }
    }

    private func settleDismissal() {
        guard dismissalProgress != 0 else { return }
        withAnimation(motionDisabled ? .reducedMotionFade : .gestureSettle) {
            dismissalProgress = 0
        }
    }
}

/// A stable clip topology whose active path is a source-centered circle and
/// whose settled path is the container rect. Only radius animates; the source
/// center stays fixed for one launch/close transition.
private struct CircularRevealShape: Shape {
    let center: CGPoint
    var radius: CGFloat
    let revealsCircle: Bool

    var animatableData: CGFloat {
        get { radius }
        set { radius = newValue }
    }

    func path(in rect: CGRect) -> Path {
        guard revealsCircle else { return Path(rect) }
        let radius = max(0.5, radius)
        return Path(ellipseIn: CGRect(
            x: center.x - radius,
            y: center.y - radius,
            width: radius * 2,
            height: radius * 2
        ))
    }
}
