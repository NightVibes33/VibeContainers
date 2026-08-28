import SwiftUI

// MARK: - Shared Springboard bottom control
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
        .modifier(
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
