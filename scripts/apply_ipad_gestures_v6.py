#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "LiveContainer-3.8.0/MultitaskSupport/MultitaskDockView.swift"
text = PATH.read_text()


def replace_required(old: str, new: str, label: str) -> None:
    global text
    if new in text:
        print(f"gesture v6: {label} already applied")
        return
    if old not in text:
        raise SystemExit(f"gesture v6: expected block not found for {label}")
    text = text.replace(old, new, 1)
    print(f"gesture v6: applied {label}")


replace_required(
    '''    private var systemGestureBeganAt: TimeInterval = 0
    private var systemGestureTriggered = false
''',
    '''    private var systemGestureBeganAt: TimeInterval = 0
    private var systemGestureTriggered = false
    private var systemGestureLastTranslation: CGPoint = .zero
    private var systemGestureLastVelocity: CGPoint = .zero
''',
    "cache last pan vector",
)

# Keep Vibe's gesture strip entirely above the system Home-indicator safe area.
# The previous surface reached the physical screen edge, letting SpringBoard's
# own Home gesture win arbitration and pull the whole host app instead of
# delivering the pan to Vibe.
replace_required(
    '''        let height = max(54, window.safeAreaInsets.bottom + 36)
        let frame = CGRect(
            x: 0,
            y: max(0, rootView.bounds.height - height),
            width: rootView.bounds.width,
            height: height
        )
''',
    '''        let systemBottomInset = max(window.safeAreaInsets.bottom, rootView.safeAreaInsets.bottom)
        let controlHeight: CGFloat = 52
        let gapAboveSystemZone: CGFloat = 6
        let controlBottom = max(0, rootView.bounds.height - systemBottomInset - gapAboveSystemZone)
        let frame = CGRect(
            x: 0,
            y: max(0, controlBottom - controlHeight),
            width: rootView.bounds.width,
            height: controlHeight
        )
        NSLog(
            "VibeContainers: app-owned bottom gesture strip y=%.1f h=%.1f systemInset=%.1f",
            frame.origin.y,
            frame.height,
            systemBottomInset
        )
''',
    "move gesture strip above iOS Home zone",
)

# The v4 cancellation fallback did not actually preserve the drag. UIKit may
# zero a cancelled recognizer before the callback, so cache every changed/ended
# vector and classify a cancellation from those cached values.
replace_required(
    '''        switch gesture.state {
        case .began:
            systemGestureTriggered = false
            systemGestureBeganAt = ProcessInfo.processInfo.systemUptime
            return
        case .cancelled:
            NSLog("VibeContainers: bottom gesture cancelled by UIKit; committing last translation")
            break
        case .failed:
            systemGestureTriggered = false
            systemGestureBeganAt = 0
            return
        case .changed, .ended:
            break
        default:
            return
        }

        guard !systemGestureTriggered else { return }
        let translation = gesture.translation(in: gesture.view)
        let velocity = gesture.velocity(in: gesture.view)
''',
    '''        let translation: CGPoint
        let velocity: CGPoint
        switch gesture.state {
        case .began:
            systemGestureTriggered = false
            systemGestureBeganAt = ProcessInfo.processInfo.systemUptime
            systemGestureLastTranslation = .zero
            systemGestureLastVelocity = .zero
            return
        case .changed:
            translation = gesture.translation(in: gesture.view)
            velocity = gesture.velocity(in: gesture.view)
            systemGestureLastTranslation = translation
            systemGestureLastVelocity = velocity
        case .ended:
            translation = gesture.translation(in: gesture.view)
            velocity = gesture.velocity(in: gesture.view)
            systemGestureLastTranslation = translation
            systemGestureLastVelocity = velocity
        case .cancelled:
            translation = systemGestureLastTranslation
            velocity = systemGestureLastVelocity
            NSLog(
                "VibeContainers: bottom gesture cancelled; using cached translation x=%.1f y=%.1f velocityY=%.1f",
                translation.x,
                translation.y,
                velocity.y
            )
        case .failed:
            systemGestureTriggered = false
            systemGestureBeganAt = 0
            systemGestureLastTranslation = .zero
            systemGestureLastVelocity = .zero
            return
        default:
            return
        }

        guard !systemGestureTriggered else { return }
''',
    "commit cancellation from cached drag",
)

# Make the visible pill sit near the bottom of Vibe's app-owned strip while
# remaining above the protected system safe area.
replace_required(
    '''            pill.bottomAnchor.constraint(equalTo: surface.bottomAnchor, constant: -7),
''',
    '''            pill.bottomAnchor.constraint(equalTo: surface.bottomAnchor, constant: -4),
''',
    "position pill inside app-owned strip",
)

PATH.write_text(text)
print(f"gesture v6: normalized {PATH.relative_to(ROOT)}")
