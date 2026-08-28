#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "iOSSim/Model/HomeLayoutStore.swift"
text = PATH.read_text()


def replace_required(old: str, new: str, label: str) -> None:
    global text
    if new in text:
        print(f"home layout: {label} already applied")
        return
    if old not in text:
        raise SystemExit(f"home layout: expected block not found for {label}")
    text = text.replace(old, new, 1)
    print(f"home layout: applied {label}")

# A saved Dock is user-owned state, including intentionally empty slots. The
# previous startup path treated an under-full Dock as incomplete and pulled
# arbitrary page icons into it on every relaunch, undoing drag-and-drop edits.
replace_required(
    '''        migrateInstalledBuiltinsIfNeeded(defaults)
        adoptNewBuiltins()
        if fillDockFromPages() { persist() }
''',
    '''        migrateInstalledBuiltinsIfNeeded(defaults)
        adoptNewBuiltins()
        // Never auto-fill a restored Dock. Empty Dock capacity is intentional
        // user layout state and must survive a process relaunch unchanged.
''',
    "stop launch-time Dock refill",
)

# Installing/removing packages should reconcile membership only. It must not
# reinterpret the user's current Dock as a request to repopulate it.
replace_required(
    '''        let placed = Set(allApps.compactMap(\\.guestBundle))
        for bundle in installed where !placed.contains(bundle) {
            placeInFirstFreeSlot(.guest(bundle), preferring: 0, columns: columns)
        }
        fillDockFromPages()
        persist()
''',
    '''        let placed = Set(allApps.compactMap(\\.guestBundle))
        for bundle in installed where !placed.contains(bundle) {
            // New guest apps land on a page. Dock membership changes only by
            // explicit user drag/drop, exactly like SpringBoard.
            placeInFirstFreeSlot(.guest(bundle), preferring: 0, columns: columns)
        }
        persist()
''',
    "stop guest-sync Dock refill",
)

PATH.write_text(text)
print(f"home layout: normalized {PATH.relative_to(ROOT)}")
