import SwiftUI

/// Preinstalled app-management surface for the private NyxPhone environment.
/// It reuses the existing VibeContainers package, container, signing, tweak,
/// and guest-launch implementation instead of maintaining a conflicting copy.
struct TrollStoreApp: View {
    var body: some View {
        PackagesView(
            onBack: {},
            rootTitle: "TrollStore",
            rootBackTitle: "Home"
        )
    }
}
