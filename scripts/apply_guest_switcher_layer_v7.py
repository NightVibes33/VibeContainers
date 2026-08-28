#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANAGER = ROOT / "LiveContainer-3.8.0/MultitaskSupport/MultitaskDockView.swift"
text = MANAGER.read_text()


def replace_required(old: str, new: str, label: str) -> None:
    global text
    if new in text:
        print(f"gesture v7: {label} already applied")
        return
    if old not in text:
        raise SystemExit(f"gesture v7: expected block not found for {label}")
    text = text.replace(old, new, 1)
    print(f"gesture v7: applied {label}")


# The built-in AppWindow switcher works because its SwiftUI app surface is
# removed before the switcher is inserted. A real LiveContainer guest is hosted
# in a UIKit container above SwiftUI. Hiding only the guest child leaves that
# container above ContainerSwitcherView, so the gesture can commit while the
# host overlay remains visually unreachable. Demote the entire guest host for
# host-owned overlays; focus already calls raiseHostedSurfaces() to restore it.
marker = '''    /// Reveals VibeContainers' adaptive app switcher after clearing the guest
    /// windows from the host surface. The processes themselves keep running.
'''
method = '''    /// Moves LiveContainer's UIKit host below the SwiftUI Springboard while a
    /// host-owned overlay (notably ContainerSwitcherView) is presented. Guest
    /// child views stay attached and their processes keep running; selecting a
    /// card restores this host through raiseHostedSurfaces().
    private func demoteHostedSurfacesForHostOverlay() {
        dispatchPrecondition(condition: .onQueue(.main))
        guard let window = keyWindow,
              let rootView = window.rootViewController?.view,
              windowHostingView.superview === rootView else { return }

        windowHostingView.isUserInteractionEnabled = false
        rootView.sendSubviewToBack(windowHostingView)
        NSLog("VibeContainers: guest host demoted below SwiftUI switcher")
    }

'''
if "guest host demoted below SwiftUI switcher" not in text:
    if marker not in text:
        raise SystemExit("gesture v7: switcher marker not found")
    text = text.replace(marker, method + marker, 1)
    print("gesture v7: added host demotion helper")

replace_required(
    '''        hostWindow = window

        if windowHostingView.superview !== rootView {
''',
    '''        hostWindow = window
        // Any route that focuses a guest owns the host again. This reverses
        // demoteHostedSurfacesForHostOverlay() after a switcher card is tapped.
        windowHostingView.isUserInteractionEnabled = true

        if windowHostingView.superview !== rootView {
''',
    "restore host interaction on focus",
)

replace_required(
    '''            self.hideGuestSurfacesForAppSwitcher()
            NotificationCenter.default.post(
''',
    '''            self.hideGuestSurfacesForAppSwitcher()
            self.demoteHostedSurfacesForHostOverlay()
            NotificationCenter.default.post(
''',
    "demote guest host before switcher notification",
)

# Hard validation: a guest-originated switcher must perform both operations.
required = [
    'self.hideGuestSurfacesForAppSwitcher()\n            self.demoteHostedSurfacesForHostOverlay()\n            NotificationCenter.default.post(',
    'rootView.sendSubviewToBack(windowHostingView)',
    'windowHostingView.isUserInteractionEnabled = true',
]
for needle in required:
    if needle not in text:
        raise SystemExit(f"gesture v7: validation missing {needle!r}")

MANAGER.write_text(text)
print(f"gesture v7: normalized {MANAGER.relative_to(ROOT)}")
