#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    if new in text:
        print(f"{path}: already patched")
        return
    if old not in text:
        raise SystemExit(f"{path}: expected source block not found")
    path.write_text(text.replace(old, new, 1))
    print(f"{path}: patched")


lcutils = ROOT / "LiveContainer-3.8.0/LiveContainerSwiftUI/Utilities/LCUtils.m"
replace_once(
    lcutils,
    '''        if (@available(iOS 16.1, *)) {
            if(UIApplication.sharedApplication.supportsMultipleScenes && [NSUserDefaults.lcSharedDefaults integerForKey:@"LCMultitaskMode"] == 1) {
                [MultitaskWindowManager openAppWindowWithDisplayName:displayName dataUUID:dataUUID bundleId:bundleId pidCallback:completionHandler];
                MultitaskDockManager *dock = [MultitaskDockManager shared];
                [dock addRunningApp:displayName appUUID:dataUUID view:nil];
                return;
            }
        }
        
        MultitaskDockManager *dock = MultitaskDockManager.shared;
''',
    '''        // VibeContainers' Home/Dock/switcher contract requires the guest to
        // stay inside the host window hierarchy. A saved upstream LiveContainer
        // native-window preference (mode 1) creates a separate UIWindowScene,
        // which bypasses every host-owned bottom gesture and preserves the old
        // controls. Migrate that state here at the final launch decision so an
        // existing installation cannot silently select the incompatible path.
        NSUserDefaults *sharedDefaults = NSUserDefaults.lcSharedDefaults;
        NSInteger savedMode = [sharedDefaults integerForKey:@"LCMultitaskMode"];
        if (savedMode != 0) {
            [sharedDefaults setInteger:0 forKey:@"LCMultitaskMode"];
            [sharedDefaults synchronize];
        }
        NSLog(@"VibeContainers: FORCED virtual-window guest host (saved mode=%ld)", (long)savedMode);

        MultitaskDockManager *dock = MultitaskDockManager.shared;
'''
)

prefs = ROOT / "iOSSim/Model/MultitaskPreferences.swift"
replace_once(
    prefs,
    '''        sharedDefaults.register(defaults: [
            "LCMultitaskMode": 0,
            "LCMultitaskOverlayMode": true,
            "LCMultitaskBottomWindowBar": false,
            "LCDockWidth": 80.0,
            "LCSkipTerminatedScreen": true,
            "LCHideCollapsedDock": false,
            "LCMaxOneAppOnStage": false
        ])
''',
    '''        sharedDefaults.register(defaults: [
            "LCMultitaskMode": 0,
            "LCMultitaskOverlayMode": true,
            "LCMultitaskBottomWindowBar": false,
            "LCDockWidth": 80.0,
            "LCSkipTerminatedScreen": true,
            "LCHideCollapsedDock": false,
            "LCMaxOneAppOnStage": false
        ])

        // register(defaults:) does not override a value saved by an older
        // LiveContainer/VibeContainers build. Mode 1 launches a separate native
        // UIWindowScene and therefore cannot be controlled by Vibe's host-owned
        // bottom edge. Migrate it on every host start; LCUtils also enforces the
        // same invariant immediately before each guest launch.
        let savedMode = sharedDefaults.integer(forKey: "LCMultitaskMode")
        if savedMode != 0 {
            NSLog("VibeContainers: migrating saved multitask mode %d to virtual host", savedMode)
        }
        sharedDefaults.set(0, forKey: "LCMultitaskMode")
        UserDefaults.standard.set(true, forKey: "LCLaunchMultitaskMaximized")
'''
)

print("VibeContainers virtual-host lock applied")
