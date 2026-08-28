#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "LiveContainer-3.8.0/MultitaskSupport/MultitaskDockView.swift"
text = PATH.read_text()


def replace_required(old: str, new: str, label: str) -> None:
    global text
    if new in text:
        print(f"gesture v5: {label} already applied")
        return
    if old not in text:
        raise SystemExit(f"gesture v5: expected block not found for {label}")
    text = text.replace(old, new, 1)
    print(f"gesture v5: applied {label}")

# showDock() may call setupDockView() as a repair path. The old implementation
# always queued creation asynchronously, so showDock() immediately re-read nil
# and returned. Make creation synchronous when already on the main thread and
# idempotent so the first short bottom pull always has a real Dock controller.
replace_required(
    '''    private func setupDockView() {
        DispatchQueue.main.async {
            let dockView = AnyView(MultitaskDockSwiftView()
                .environmentObject(self))
            
            self.hostingController = UIHostingController(rootView: dockView)
            self.hostingController?.view.autoresizingMask = [.flexibleTopMargin, .flexibleLeftMargin, .flexibleRightMargin, .flexibleBottomMargin]
            self.hostingController?.view.backgroundColor = .clear
        }
    }
''',
    '''    private func setupDockView() {
        let create = {
            guard self.hostingController == nil else { return }
            let dockView = AnyView(MultitaskDockSwiftView()
                .environmentObject(self))

            let controller = UIHostingController(rootView: dockView)
            controller.view.autoresizingMask = [.flexibleTopMargin, .flexibleLeftMargin, .flexibleRightMargin, .flexibleBottomMargin]
            controller.view.backgroundColor = .clear
            self.hostingController = controller
            NSLog("VibeContainers: Dock hosting controller ready")
        }

        if Thread.isMainThread {
            create()
        } else {
            DispatchQueue.main.async(execute: create)
        }
    }
''',
    "synchronous main-thread Dock setup",
)

# Gesture-surface teardown is independent of whether the floating Dock is
# enabled on this idiom. The old early return on phones could leave the Vibe
# bottom strip active after the last guest closed.
replace_required(
    '''            // Native-window mode still needs lifecycle bookkeeping for the
            // host switcher; only the floating dock UI is mode-specific.
            guard self.isDockEnabled() else { return }
            
            if self.apps.isEmpty {
                self.setSystemGestureSurfaceVisible(false)
                self.hideDock()
            } else if self.isVisible {
                self.updateDockFrame()
            }
''',
    '''            if self.apps.isEmpty {
                self.setSystemGestureSurfaceVisible(false)
                self.hideDock()
                return
            }

            // Dock layout updates remain mode-specific, but lifecycle cleanup
            // above must run on every device idiom.
            guard self.isDockEnabled() else { return }
            if self.isVisible {
                self.updateDockFrame()
            }
''',
    "always tear down gesture surface after last guest",
)

# Home does not need a synchronous render-server snapshot. Capturing before
# hiding can make a valid gesture appear inert if the remote scene is slow to
# provide a frame. The switcher action still captures its foreground preview;
# Home prioritizes immediate navigation and keeps the process alive.
replace_required(
    '''        let action = {
            self.setSystemGestureSurfaceVisible(false)
            _ = self.captureAppSwitcherPreviews()
            _ = self.captureAppSwitcherPreviewViews()
            self.gestureDockOverride = false
            self.hideGuestSurfacesForAppSwitcher()
            self.hideDock()
            self.raiseHostedSurfaces()
        }
''',
    '''        let action = {
            self.setSystemGestureSurfaceVisible(false)
            self.gestureDockOverride = false
            self.hideGuestSurfacesForAppSwitcher()
            self.hideDock()
            self.raiseHostedSurfaces()
            NSLog("VibeContainers: Home gesture committed immediately")
        }
''',
    "make Home navigation immediate",
)

PATH.write_text(text)
print(f"gesture v5: normalized {PATH.relative_to(ROOT)}")
