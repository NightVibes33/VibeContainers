import Foundation
import LiveContainerSwiftUI
import SwiftUI
import UniformTypeIdentifiers

/// TrollStore-style app management scoped to NyxPhone's private environment.
///
/// Installation and launch deliberately reuse VibeContainers' audited IPA
/// extraction, Mach-O preparation, entitlement mediation, per-app containers,
/// JIT/JIT-less signing, and LiveProcess lifecycle. Nothing is registered with
/// the physical device's SpringBoard or written outside NyxPhone's container.
@MainActor
struct NyxianTrollStoreWorkspace: View {
    @State private var packageStore = PackageStore.shared
    @State private var installer = GuestInstaller.shared
    @State private var importingIPA = false
    @State private var noticeTitle = "Nyxian TrollStore ready"
    @State private var noticeDetail = "Import a decrypted arm64 IPA or install the embedded validation app."
    @State private var exportedIPA: URL?

    var body: some View {
        List {
            Section {
                LabeledContent("Scope", value: "NyxPhone only")
                LabeledContent("Persistence", value: "Per-app containers")
                LabeledContent("Execution", value: "VibeContainers + Nyxian")
                LabeledContent("vphone-aio donor", value: "1db79dcc")
            } header: {
                Text("TrollStore Workspace")
            } footer: {
                Text("This workspace does not modify or register apps with the physical iPhone SpringBoard.")
            }

            Section("Install") {
                Button {
                    importingIPA = true
                } label: {
                    Label("Import TrollStore IPA", systemImage: "square.and.arrow.down")
                }
                .disabled(installer.sideload.isWorking)

                Button {
                    installValidationApp()
                } label: {
                    Label("Install Embedded Validation App", systemImage: "checkmark.seal")
                }
                .disabled(installer.sideload.isWorking || validationIPAURL == nil)

                if installer.sideload.isWorking {
                    ProgressView("Preparing IPA…")
                }
            }

            Section("Installed Apps") {
                if packageStore.installedList.isEmpty {
                    ContentUnavailableView(
                        "No Apps Installed",
                        systemImage: "shippingbox",
                        description: Text("Import a decrypted arm64 IPA to create its persistent NyxPhone container.")
                    )
                } else {
                    ForEach(packageStore.installedList) { app in
                        VStack(alignment: .leading, spacing: 8) {
                            Text(app.name).font(.headline)
                            Text("\(app.bundleIdentifier) · \(app.version)")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .textSelection(.enabled)
                            HStack {
                                Button("Launch") { launch(app) }
                                    .buttonStyle(.borderedProminent)
                                Button("Export") { export(app) }
                                    .buttonStyle(.bordered)
                                Spacer()
                                Button(role: .destructive) {
                                    packageStore.remove(app.bundleIdentifier)
                                    noticeTitle = "App removed"
                                    noticeDetail = "\(app.name) and its NyxPhone container were removed."
                                } label: {
                                    Image(systemName: "trash")
                                }
                                .buttonStyle(.bordered)
                            }
                        }
                        .padding(.vertical, 4)
                    }
                }
            }

            if let exportedIPA {
                Section("Export") {
                    ShareLink(item: exportedIPA) {
                        Label("Share \(exportedIPA.lastPathComponent)", systemImage: "square.and.arrow.up")
                    }
                }
            }

            Section("Last Event") {
                Text(noticeTitle).font(.headline)
                Text(noticeDetail)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
            }
        }
        .navigationTitle("Nyxian TrollStore")
        .fileImporter(
            isPresented: $importingIPA,
            allowedContentTypes: [.item],
            allowsMultipleSelection: false
        ) { result in
            guard case .success(let urls) = result, let url = urls.first else { return }
            guard url.pathExtension.lowercased() == "ipa" else {
                noticeTitle = "Unsupported file"
                noticeDetail = "Choose an .ipa archive."
                return
            }
            Task { await install(url, source: "Imported file") }
        }
    }

    private var validationIPAURL: URL? {
        Bundle.main.url(
            forResource: "NyxValidation",
            withExtension: "ipa",
            subdirectory: "NyxPhoneGuest"
        )
    }

    private func installValidationApp() {
        guard let validationIPAURL else {
            noticeTitle = "Validation IPA missing"
            noticeDetail = "This build does not contain NyxValidation.ipa."
            return
        }
        Task { await install(validationIPAURL, source: "Embedded validation") }
    }

    private func install(_ url: URL, source: String) async {
        noticeTitle = "Installing"
        noticeDetail = source
        await installer.installIPA(at: url)
        switch installer.sideload {
        case .installed(let bundleIdentifier):
            noticeTitle = "Installed"
            noticeDetail = "\(bundleIdentifier) is persistent and ready for launch."
        case .failed(let message):
            noticeTitle = "Install failed"
            noticeDetail = message
        default:
            noticeTitle = "Install incomplete"
            noticeDetail = "The installer returned without a final state."
        }
    }

    private func launch(_ app: PackageStore.InstalledApp) {
        guard let container = GuestContainerStore.shared.container(for: app.bundleIdentifier) else {
            noticeTitle = "Container missing"
            noticeDetail = "Reinstall \(app.name) to recreate its container."
            return
        }
        noticeTitle = "Launching"
        noticeDetail = app.name
        Task {
            let outcome = await installer.launch(container)
            noticeTitle = outcome.headline
            noticeDetail = outcome.detail
        }
    }

    private func export(_ app: PackageStore.InstalledApp) {
        guard let container = GuestContainerStore.shared.container(for: app.bundleIdentifier) else {
            noticeTitle = "Export failed"
            noticeDetail = "The app container is missing."
            return
        }
        let payload = GuestContainerStore.shared.url(for: container)
            .appendingPathComponent("Payload", isDirectory: true)
        guard FileManager.default.fileExists(atPath: payload.path) else {
            noticeTitle = "Export failed"
            noticeDetail = "The installed Payload directory is missing."
            return
        }

        do {
            let root = FileManager.default.temporaryDirectory
                .appendingPathComponent("NyxPhoneExport-\(UUID().uuidString)", isDirectory: true)
            try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
            try FileManager.default.copyItem(
                at: payload,
                to: root.appendingPathComponent("Payload", isDirectory: true)
            )
            guard let archiverType = NSClassFromString("PKZipArchiver") as? NSObject.Type else {
                throw CocoaError(.featureUnsupported)
            }
            let archiver = archiverType.init()
            let selector = NSSelectorFromString("zippedDataForURL:")
            guard archiver.responds(to: selector),
                  let archive = archiver.perform(selector, with: root)?.takeUnretainedValue() as? Data else {
                throw CocoaError(.fileWriteUnknown)
            }
            let safeName = app.name.replacingOccurrences(of: "/", with: "-")
            let destination = FileManager.default.temporaryDirectory
                .appendingPathComponent("\(safeName)-NyxPhone.ipa")
            try archive.write(to: destination, options: .atomic)
            try? FileManager.default.removeItem(at: root)
            exportedIPA = destination
            noticeTitle = "Export ready"
            noticeDetail = destination.lastPathComponent
        } catch {
            noticeTitle = "Export failed"
            noticeDetail = error.localizedDescription
        }
    }
}
