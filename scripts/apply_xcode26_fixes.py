#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def patch(path: Path, old: str, new: str, marker: str) -> None:
    text = path.read_text()
    if marker in text:
        print(f"already fixed {path.relative_to(ROOT)}: {marker}")
        return
    if old not in text:
        raise SystemExit(f"xcode26 fix: expected block not found in {path.relative_to(ROOT)} for {marker}")
    path.write_text(text.replace(old, new, 1))
    print(f"patched {path.relative_to(ROOT)}: {marker}")


settings_icons = ROOT / "iOSSim/Apps/SettingsIcons.swift"
patch(
    settings_icons,
    '''        let step = Double.pi / Double(points)\n\n        var path = Path()\n        for index in 0..<(points * 2) {\n            let radius = index.isMultiple(of: 2) ? outer : inner\n            let angle = Double(index) * step - .pi / 2\n            let point = CGPoint(x: center.x + cos(angle) * radius,\n                                y: center.y + sin(angle) * radius)\n''',
    '''        let step = CGFloat.pi / CGFloat(points)\n\n        var path = Path()\n        for index in 0..<(points * 2) {\n            let radius = index.isMultiple(of: 2) ? outer : inner\n            let angle = CGFloat(index) * step - .pi / 2\n            let point = CGPoint(x: center.x + CoreGraphics.cos(angle) * radius,\n                                y: center.y + CoreGraphics.sin(angle) * radius)\n''',
    "CoreGraphics.cos(angle)",
)

page_transition = ROOT / "iOSSim/Springboard/PageTransition.swift"
text = page_transition.read_text()
replacements = {
    ".scaleEffect(1 - effectDistance * 0.32)": ".scaleEffect(CGFloat(1) - effectDistance * 0.32)",
    ".scaleEffect(1 - effectDistance * 0.28)": ".scaleEffect(CGFloat(1) - effectDistance * 0.28)",
    ".opacity(1 - effectDistance * 0.55)": ".opacity(CGFloat(1) - effectDistance * 0.55)",
    ".scaleEffect(1 - effectDistance * 0.12)": ".scaleEffect(CGFloat(1) - effectDistance * 0.12)",
    ".opacity(1 - effectDistance)": ".opacity(CGFloat(1) - effectDistance)",
    ".opacity(reducesMotion ? max(0, 1 - distance) : 1)": ".opacity(reducesMotion ? max(CGFloat(0), CGFloat(1) - distance) : CGFloat(1))",
}
changed = False
for old, new in replacements.items():
    if new in text:
        continue
    if old not in text:
        raise SystemExit(f"xcode26 fix: expected PageTransition expression not found: {old}")
    text = text.replace(old, new)
    changed = True
if changed:
    page_transition.write_text(text)
    print(f"patched {page_transition.relative_to(ROOT)}")
else:
    print(f"already fixed {page_transition.relative_to(ROOT)}")

springboard = ROOT / "iOSSim/Springboard/SpringboardView.swift"
text = springboard.read_text()
replacements = {
    "let homeTransitionProgress = openProgress * (1 - dismissalRetreat * 0.16)": "let homeTransitionProgress = openProgress * (CGFloat(1) - dismissalRetreat * 0.16)",
    ".scaleEffect(motionDisabled ? 1 : 1 + homeTransitionProgress * 0.045)": ".scaleEffect(motionDisabled ? CGFloat(1) : CGFloat(1) + homeTransitionProgress * 0.045)",
    ".opacity(1 - homeTransitionProgress * 0.18)": ".opacity(CGFloat(1) - homeTransitionProgress * 0.18)",
    ".scaleEffect(motionDisabled ? 1 : 1 + homeTransitionProgress * 0.05)": ".scaleEffect(motionDisabled ? CGFloat(1) : CGFloat(1) + homeTransitionProgress * 0.05)",
    ".opacity(openRevealed ? dismissalRetreat * 0.72 : 1)": ".opacity(openRevealed ? dismissalRetreat * 0.72 : CGFloat(1))",
}
changed = False
for old, new in replacements.items():
    if new in text:
        continue
    if old not in text:
        raise SystemExit(f"xcode26 fix: expected Springboard expression not found: {old}")
    text = text.replace(old, new)
    changed = True
if changed:
    springboard.write_text(text)
    print(f"patched {springboard.relative_to(ROOT)}")
else:
    print(f"already fixed {springboard.relative_to(ROOT)}")

checks = {
    settings_icons: ["CoreGraphics.cos(angle)", "CoreGraphics.sin(angle)", "CGFloat.pi / CGFloat(points)"],
    page_transition: [".opacity(CGFloat(1) - effectDistance * 0.55)"],
    springboard: [".opacity(CGFloat(1) - homeTransitionProgress * 0.18)"],
}
for path, markers in checks.items():
    content = path.read_text()
    missing = [m for m in markers if m not in content]
    if missing:
        raise SystemExit(f"xcode26 validation failed in {path.relative_to(ROOT)}: {missing}")
