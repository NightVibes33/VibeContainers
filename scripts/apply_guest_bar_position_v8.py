#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANAGER = ROOT / "LiveContainer-3.8.0/MultitaskSupport/MultitaskDockView.swift"
text = MANAGER.read_text()

raised = '''        let systemBottomInset = max(window.safeAreaInsets.bottom, rootView.safeAreaInsets.bottom)\n        let controlHeight: CGFloat = 52\n        let gapAboveSystemZone: CGFloat = 6\n        let controlBottom = max(0, rootView.bounds.height - systemBottomInset - gapAboveSystemZone)\n        let frame = CGRect(\n            x: 0,\n            y: max(0, controlBottom - controlHeight),\n            width: rootView.bounds.width,\n            height: controlHeight\n        )\n        NSLog(\n            "VibeContainers: app-owned bottom gesture strip y=%.1f h=%.1f systemInset=%.1f",\n            frame.origin.y,\n            frame.height,\n            systemBottomInset\n        )\n'''

restored = '''        // Match the working AppWindow/home-indicator placement. v6 moved this\n        // strip above the safe-area zone, which visibly shifted the control.\n        // Keep v6's cached cancellation/action handling, but restore the original\n        // bottom geometry used by the controls that already work correctly.\n        let height = max(54, window.safeAreaInsets.bottom + 36)\n        let frame = CGRect(\n            x: 0,\n            y: max(0, rootView.bounds.height - height),\n            width: rootView.bounds.width,\n            height: height\n        )\n        NSLog(\n            "VibeContainers: guest gesture bar restored to working bottom position y=%.1f h=%.1f",\n            frame.origin.y,\n            frame.height\n        )\n'''

if restored not in text:
    if raised not in text:
        raise SystemExit("gesture v8: raised v6 geometry not found")
    text = text.replace(raised, restored, 1)

# AppWindow's visible pill sits 7pt from the physical bottom. Restore the guest
# pill to that same placement instead of v6's raised -4 inset.
text = text.replace(
    'pill.bottomAnchor.constraint(equalTo: surface.bottomAnchor, constant: -4)',
    'pill.bottomAnchor.constraint(equalTo: surface.bottomAnchor, constant: -7)',
    1,
)

required = [
    'let height = max(54, window.safeAreaInsets.bottom + 36)',
    'pill.bottomAnchor.constraint(equalTo: surface.bottomAnchor, constant: -7)',
    'guest gesture bar restored to working bottom position',
    'systemGestureLastTranslation',
    'guest host demoted below SwiftUI switcher',
]
for needle in required:
    if needle not in text:
        raise SystemExit(f"gesture v8: validation missing {needle!r}")

MANAGER.write_text(text)
print(f"gesture v8: normalized {MANAGER.relative_to(ROOT)}")
