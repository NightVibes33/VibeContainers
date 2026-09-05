import SwiftUI

/// The preinstalled TrollStore application entry point for NyxPhone.
///
/// This is a distinct app screen, not a shortcut into PackagesView. Its
/// install/list/launch/remove actions live in NyxianTrollStoreWorkspace and
/// cross the TrollStoreCompatibilityBridge command boundary.
struct TrollStoreApp: View {
    var body: some View {
        NyxianTrollStoreWorkspace()
    }
}
