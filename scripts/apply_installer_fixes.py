#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, marker: str, label: str) -> str:
    if marker in text:
        return text
    if old not in text:
        raise SystemExit(f"installer fix: expected source block not found for {label}")
    return text.replace(old, new, 1)


def write_if_changed(path: Path, text: str, original: str) -> None:
    if text != original:
        path.write_text(text)
        print(f"patched {path.relative_to(ROOT)}")
    else:
        print(f"already fixed {path.relative_to(ROOT)}")


# ---------------------------------------------------------------------------
# PackageStore: keep exact source identity and final redirected source URL.
# ---------------------------------------------------------------------------
path = ROOT / "iOSSim/Model/PackageStore.swift"
text = path.read_text()
original = text

text = replace_once(
    text,
    '''    struct PendingUpdate: Identifiable, Sendable {\n        let installed: InstalledApp\n        let app: AltApp\n        let sourceName: String\n        var id: String { installed.bundleIdentifier }\n    }\n''',
    '''    struct PendingUpdate: Identifiable, Sendable {\n        let installed: InstalledApp\n        let app: AltApp\n        let sourceName: String\n        let sourceID: UUID\n        var id: String { installed.bundleIdentifier }\n    }\n''',
    "let sourceID: UUID",
    "PendingUpdate source identity",
)

text = replace_once(
    text,
    '''    private(set) var catalogs: [UUID: AltSource] = [:]\n    var loading: Set<UUID> = []\n    var failures: [UUID: String] = [:]\n''',
    '''    private(set) var catalogs: [UUID: AltSource] = [:]\n    var loading: Set<UUID> = []\n    var failures: [UUID: String] = [:]\n    // The URL after HTTP redirects is the correct base for relative IPA URLs.\n    @ObservationIgnored private var effectiveSourceURLs: [UUID: URL] = [:]\n''',
    "effectiveSourceURLs",
    "effective source URL cache",
)

text = replace_once(
    text,
    '''            return PendingUpdate(installed: record, app: entry.app, sourceName: entry.sourceName)\n''',
    '''            return PendingUpdate(\n                installed: record,\n                app: entry.app,\n                sourceName: entry.sourceName,\n                sourceID: entry.sourceID\n            )\n''',
    "sourceID: entry.sourceID",
    "pending update source ID",
)

text = replace_once(
    text,
    '''            let catalog = try await Self.fetch(url)\n            // The request may have outlived a source the user removed. Do not\n            // retain a now-unreachable (and potentially enormous) catalogue.\n            guard sources.contains(where: { $0.id == source.id }) else { return }\n            catalogs[source.id] = catalog\n''',
    '''            let (catalog, effectiveURL) = try await Self.fetch(url)\n            // The request may have outlived a source the user removed. Do not\n            // retain a now-unreachable (and potentially enormous) catalogue.\n            guard sources.contains(where: { $0.id == source.id }) else { return }\n            catalogs[source.id] = catalog\n            effectiveSourceURLs[source.id] = effectiveURL\n''',
    "effectiveSourceURLs[source.id] = effectiveURL",
    "refresh effective URL",
)

old_fetch = '''    private nonisolated static func fetch(_ url: URL) async throws -> AltSource {\n        var request = URLRequest(url: url)\n        request.timeoutInterval = 20\n        request.setValue("application/json", forHTTPHeaderField: "Accept")\n\n        let (data, response) = try await URLSession.shared.data(for: request)\n        if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {\n            throw StoreError.badStatus(http.statusCode)\n        }\n        do {\n            return try await Task.detached(priority: .userInitiated) {\n                try JSONDecoder().decode(AltSource.self, from: data)\n            }.value\n        } catch {\n            throw StoreError.notASource\n        }\n    }\n'''
new_fetch = '''    private nonisolated static func fetch(\n        _ url: URL\n    ) async throws -> (catalog: AltSource, effectiveURL: URL) {\n        var request = URLRequest(url: url)\n        request.timeoutInterval = 20\n        request.setValue("application/json", forHTTPHeaderField: "Accept")\n\n        let (data, response) = try await URLSession.shared.data(for: request)\n        if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {\n            throw StoreError.badStatus(http.statusCode)\n        }\n        let catalog: AltSource\n        do {\n            catalog = try await Task.detached(priority: .userInitiated) {\n                try JSONDecoder().decode(AltSource.self, from: data)\n            }.value\n        } catch {\n            throw StoreError.notASource\n        }\n        return (catalog, response.url ?? url)\n    }\n'''
text = replace_once(
    text,
    old_fetch,
    new_fetch,
    "effectiveURL: URL",
    "source fetch redirect URL",
)

text = replace_once(
    text,
    '''            let catalog = try await Self.fetch(url)\n            let source = Source(url: normalised, name: catalog.name)\n            sources.append(source)\n            catalogs[source.id] = catalog\n''',
    '''            let (catalog, effectiveURL) = try await Self.fetch(url)\n            let source = Source(url: normalised, name: catalog.name)\n            sources.append(source)\n            catalogs[source.id] = catalog\n            effectiveSourceURLs[source.id] = effectiveURL\n''',
    "effectiveSourceURLs[source.id] = effectiveURL",
    "added source effective URL",
)

text = replace_once(
    text,
    '''        catalogs[source.id] = nil\n        failures[source.id] = nil\n        loading.remove(source.id)\n''',
    '''        catalogs[source.id] = nil\n        failures[source.id] = nil\n        effectiveSourceURLs[source.id] = nil\n        loading.remove(source.id)\n''',
    "effectiveSourceURLs[source.id] = nil",
    "remove source URL cache",
)

text = replace_once(
    text,
    '''    func install(_ app: AltApp, from sourceName: String) {\n        let bundleIdentifier = app.bundleIdentifier\n        guard !pendingInstallBundles.contains(bundleIdentifier),\n              !GuestInstaller.shared.isBusy(bundleIdentifier) else { return }\n        pendingInstallBundles.insert(bundleIdentifier)\n\n        let completedRecord = InstalledApp(\n''',
    '''    func install(_ app: AltApp, from sourceName: String, sourceID: UUID? = nil) {\n        let bundleIdentifier = app.bundleIdentifier\n        guard !pendingInstallBundles.contains(bundleIdentifier),\n              !GuestInstaller.shared.isBusy(bundleIdentifier) else { return }\n        pendingInstallBundles.insert(bundleIdentifier)\n\n        // Preserve the exact source chosen by the UI. Guessing later by bundle\n        // identifier/download string can select the wrong repository when the\n        // same app exists in more than one source. Prefer the final redirected\n        // catalogue URL because relative download URLs are based on that URL.\n        let sourceBaseURL: URL? = sourceID.flatMap { id in\n            if let effective = effectiveSourceURLs[id] { return effective }\n            guard let source = sources.first(where: { $0.id == id }) else { return nil }\n            return SourceURL.normalise(source.url)\n        }\n\n        let completedRecord = InstalledApp(\n''',
    "let sourceBaseURL: URL? = sourceID.flatMap",
    "exact source install context",
)

text = replace_once(
    text,
    '''            let succeeded = await GuestInstaller.shared.install(app, into: container)\n''',
    '''            let succeeded = await GuestInstaller.shared.install(\n                app,\n                into: container,\n                sourceBaseURL: sourceBaseURL\n            )\n''',
    "sourceBaseURL: sourceBaseURL",
    "pass source URL to installer",
)

text = replace_once(
    text,
    '''    func update(_ update: PendingUpdate) {\n        install(update.app, from: update.sourceName)\n    }\n''',
    '''    func update(_ update: PendingUpdate) {\n        install(update.app, from: update.sourceName, sourceID: update.sourceID)\n    }\n''',
    "sourceID: update.sourceID",
    "update source identity",
)

write_if_changed(path, text, original)


# ---------------------------------------------------------------------------
# PackagesView: pass source UUID through GET / UPDATE / RETRY actions.
# ---------------------------------------------------------------------------
path = ROOT / "iOSSim/Apps/PackagesView.swift"
text = path.read_text()
original = text

text = replace_once(
    text,
    '''                        action: store.action(\n                            for: pending.app,\n                            sourceName: pending.sourceName\n                        )\n''',
    '''                        action: store.action(\n                            for: pending.app,\n                            sourceName: pending.sourceName,\n                            sourceID: pending.sourceID\n                        )\n''',
    "sourceID: pending.sourceID",
    "updates action source ID",
)

old_actions = '''extension PackageStore {\n    func action(for entry: Entry) -> AppRow.Action {\n        action(for: entry.app, sourceName: entry.sourceName)\n    }\n\n    func action(for app: AltApp, sourceName: String) -> AppRow.Action {\n        let bundleIdentifier = app.bundleIdentifier\n        let phase = GuestInstaller.shared.phase(for: bundleIdentifier)\n\n        if pendingInstallBundles.contains(bundleIdentifier) {\n            switch phase {\n            case .downloading(let progress):\n                return .installing("\\(Int((progress * 100).rounded()))%", progress: progress)\n            case .unpacking:\n                return .installing("UNPACKING", progress: nil)\n            case .preparing:\n                return .installing("PREPARING", progress: nil)\n            default:\n                return .installing("STARTING", progress: nil)\n            }\n        }\n\n        switch phase {\n        case .downloading(let progress):\n            return .installing("\\(Int((progress * 100).rounded()))%", progress: progress)\n        case .unpacking:\n            return .installing("UNPACKING", progress: nil)\n        case .preparing:\n            return .installing("PREPARING", progress: nil)\n        case .failed:\n            return .retry { self.install(app, from: sourceName) }\n        case .idle, .ready:\n            break\n        }\n\n        if hasUpdate(app) { return .update { self.install(app, from: sourceName) } }\n        if isInstalled(app) { return .open }\n        return .get { self.install(app, from: sourceName) }\n    }\n}\n'''
new_actions = '''extension PackageStore {\n    func action(for entry: Entry) -> AppRow.Action {\n        action(for: entry.app, sourceName: entry.sourceName, sourceID: entry.sourceID)\n    }\n\n    func action(\n        for app: AltApp,\n        sourceName: String,\n        sourceID: UUID? = nil\n    ) -> AppRow.Action {\n        let bundleIdentifier = app.bundleIdentifier\n        let phase = GuestInstaller.shared.phase(for: bundleIdentifier)\n\n        if pendingInstallBundles.contains(bundleIdentifier) {\n            switch phase {\n            case .downloading(let progress):\n                return .installing("\\(Int((progress * 100).rounded()))%", progress: progress)\n            case .unpacking:\n                return .installing("UNPACKING", progress: nil)\n            case .preparing:\n                return .installing("PREPARING", progress: nil)\n            default:\n                return .installing("STARTING", progress: nil)\n            }\n        }\n\n        switch phase {\n        case .downloading(let progress):\n            return .installing("\\(Int((progress * 100).rounded()))%", progress: progress)\n        case .unpacking:\n            return .installing("UNPACKING", progress: nil)\n        case .preparing:\n            return .installing("PREPARING", progress: nil)\n        case .failed:\n            return .retry { self.install(app, from: sourceName, sourceID: sourceID) }\n        case .idle, .ready:\n            break\n        }\n\n        if hasUpdate(app) {\n            return .update { self.install(app, from: sourceName, sourceID: sourceID) }\n        }\n        if isInstalled(app) { return .open }\n        return .get { self.install(app, from: sourceName, sourceID: sourceID) }\n    }\n}\n'''
text = replace_once(
    text,
    old_actions,
    new_actions,
    "sourceID: entry.sourceID",
    "store action source identity",
)

write_if_changed(path, text, original)


# ---------------------------------------------------------------------------
# GuestInstaller: pure URL resolution + recoverable crash transaction cleanup.
# ---------------------------------------------------------------------------
path = ROOT / "iOSSim/Model/GuestInstaller.swift"
text = path.read_text()
original = text

text = replace_once(
    text,
    '''    private init() {\n        // A killed/terminated import can leave a full extracted app in Staging.\n        // Nothing in this directory is persistent state, so reclaim it before\n        // the next install instead of letting abandoned imports exhaust /User.\n        try? FileManager.default.removeItem(at: Self.stagingRoot)\n    }\n''',
    '''    private init() {\n        // A killed/terminated import can leave a full extracted app in Staging.\n        // Nothing in this directory is persistent state, so reclaim it before\n        // the next install instead of letting abandoned imports consume space.\n        try? FileManager.default.removeItem(at: Self.stagingRoot)\n\n        // Source installs stage inside each app container so the final rename is\n        // guaranteed to stay on one filesystem. Reclaim only transactions that\n        // carry our active marker; recovery copies are explicitly protected.\n        for container in GuestContainerStore.shared.containers.values {\n            Self.cleanupAbandonedTransactions(\n                in: GuestContainerStore.shared.url(for: container)\n            )\n        }\n    }\n''',
    "Self.cleanupAbandonedTransactions(",
    "startup source transaction cleanup",
)

text = replace_once(
    text,
    '''    func install(_ app: AltApp, into container: GuestContainerStore.Container) async -> Bool {\n''',
    '''    func install(\n        _ app: AltApp,\n        into container: GuestContainerStore.Container,\n        sourceBaseURL: URL? = nil\n    ) async -> Bool {\n''',
    "sourceBaseURL: URL? = nil",
    "installer source base parameter",
)

text = replace_once(
    text,
    '''        guard let raw = app.latest?.downloadURL,\n              let url = Self.resolveDownloadURL(raw, for: app) else {\n''',
    '''        guard let raw = app.latest?.downloadURL,\n              let url = Self.resolveDownloadURL(raw, relativeTo: sourceBaseURL) else {\n''',
    "Self.resolveDownloadURL(raw, relativeTo: sourceBaseURL)",
    "pure download URL resolution",
)

text = replace_once(
    text,
    '''        let base = GuestContainerStore.shared.url(for: container)\n        let transactionRoot = base\n''',
    '''        let base = GuestContainerStore.shared.url(for: container)\n        Self.cleanupAbandonedTransactions(in: base)\n        let transactionRoot = base\n''',
    "Self.cleanupAbandonedTransactions(in: base)",
    "preinstall transaction cleanup",
)

text = replace_once(
    text,
    '''            try FileManager.default.createDirectory(\n                at: transactionRoot,\n                withIntermediateDirectories: true\n            )\n            phases[bundle] = .downloading(0)\n''',
    '''            try FileManager.default.createDirectory(\n                at: transactionRoot,\n                withIntermediateDirectories: true\n            )\n            FileManager.default.createFile(\n                atPath: transactionRoot.appendingPathComponent(Self.activeTransactionMarker).path,\n                contents: Data()\n            )\n            phases[bundle] = .downloading(0)\n''',
    "Self.activeTransactionMarker",
    "active source transaction marker",
)

text = replace_once(
    text,
    '''            preserveTransactionForRecovery = error.preserveStaging\n            phases[bundle] = .failed(error.localizedDescription)\n''',
    '''            preserveTransactionForRecovery = error.preserveStaging\n            if preserveTransactionForRecovery {\n                Self.markRecoveryTransaction(transactionRoot)\n            }\n            phases[bundle] = .failed(error.localizedDescription)\n''',
    "Self.markRecoveryTransaction(transactionRoot)",
    "protect recovery transaction",
)

# Replace the old source-guessing resolver as one block.
resolver_start = "    /// Resolves the forms found in real AltStore-compatible sources: absolute\n"
resolver_end = "    /// Lifts the app's own icon out of the bundle so the home screen shows it\n"
resolver_marker = "private static func resolveDownloadURL(_ raw: String, relativeTo sourceBase: URL?)"
if resolver_marker not in text:
    try:
        start = text.index(resolver_start)
        end = text.index(resolver_end, start)
    except ValueError as exc:
        raise SystemExit("installer fix: download URL resolver block not found") from exc
    resolver = '''    private static let activeTransactionMarker = ".vibe-install-active"\n    private static let recoveryTransactionMarker = ".vibe-install-recovery"\n\n    /// A normal process death skips Swift `defer`, so unfinished source installs\n    /// can otherwise leave a downloaded IPA plus a partially expanded Payload.\n    /// Only directories carrying our explicit active marker are reclaimed. A\n    /// transaction containing the previous version after a rollback failure is\n    /// protected by a recovery marker and is never auto-deleted.\n    private static func cleanupAbandonedTransactions(in base: URL) {\n        let manager = FileManager.default\n        guard let children = try? manager.contentsOfDirectory(\n            at: base,\n            includingPropertiesForKeys: [.isDirectoryKey],\n            options: [.skipsHiddenFiles]\n        ) else { return }\n\n        for child in children where child.lastPathComponent.hasPrefix(".install-") {\n            let active = child.appendingPathComponent(activeTransactionMarker)\n            let recovery = child.appendingPathComponent(recoveryTransactionMarker)\n            guard manager.fileExists(atPath: active.path),\n                  !manager.fileExists(atPath: recovery.path) else { continue }\n            try? manager.removeItem(at: child)\n        }\n    }\n\n    private static func markRecoveryTransaction(_ transaction: URL) {\n        let manager = FileManager.default\n        let marker = transaction.appendingPathComponent(recoveryTransactionMarker)\n        if !manager.createFile(atPath: marker.path, contents: Data()) {\n            // If the disk is so full that the protection marker cannot be made,\n            // remove the active marker. Cleanup only targets active transactions,\n            // so the recovery payload remains preserved across the next launch.\n            try? manager.removeItem(\n                at: transaction.appendingPathComponent(activeTransactionMarker)\n            )\n        }\n    }\n\n    /// Resolves absolute, scheme-relative and source-relative IPA URLs. The\n    /// caller supplies the exact source URL that produced this catalogue entry;\n    /// no bundle-ID scan or repository guessing occurs here.\n    private static func resolveDownloadURL(_ raw: String, relativeTo sourceBase: URL?) -> URL? {\n        let value = raw.trimmingCharacters(in: .whitespacesAndNewlines)\n        guard !value.isEmpty else { return nil }\n\n        let candidate: URL?\n        if value.hasPrefix("//") {\n            candidate = URL(string: "https:" + value)\n        } else if let direct = URL(string: value), direct.scheme != nil {\n            candidate = direct\n        } else if let sourceBase {\n            candidate = URL(string: value, relativeTo: sourceBase)?.absoluteURL\n        } else {\n            candidate = nil\n        }\n\n        guard var resolved = candidate,\n              let scheme = resolved.scheme?.lowercased(),\n              scheme == "https" || scheme == "http" else { return nil }\n\n        // A copied GitHub file-page URL serves HTML. Convert only the canonical\n        // /blob/<ref>/ form; release/download and other direct URLs stay intact.\n        if resolved.host?.lowercased() == "github.com" {\n            var parts = resolved.path.split(separator: "/").map(String.init)\n            if let blob = parts.firstIndex(of: "blob"), parts.count > blob + 1 {\n                parts.remove(at: blob)\n                if let rawURL = URL(\n                    string: "https://raw.githubusercontent.com/" + parts.joined(separator: "/")\n                ) {\n                    resolved = rawURL\n                }\n            }\n        }\n        return resolved\n    }\n\n'''
    text = text[:start] + resolver + text[end:]

# Correct the earlier explanatory wording: the filename in an ENOSPC error is
# simply the file that happened to be written when capacity ran out.
text = text.replace(
    '''        // file directly. The old implementation first copied the complete IPA into\n        // Documents/Staging and then extracted it, requiring compressed IPA + copy\n        // + expanded app to coexist and causing bogus-looking "volume User is out\n        // of space" failures whose filename happened to be the guest executable.\n''',
    '''        // file directly. The old implementation first copied the complete IPA into\n        // Documents/Staging and then extracted it, requiring the original IPA, a\n        // second full IPA copy and the expanded app to coexist. The filename in an\n        // out-of-space error is simply whichever guest file was being written then.\n''',
)

write_if_changed(path, text, original)


# ---------------------------------------------------------------------------
# Structural assertions: fail CI before spending time on Xcode if a regression
# silently drops one of the critical install fixes.
# ---------------------------------------------------------------------------
checks = {
    ROOT / "iOSSim/Model/GuestInstaller.swift": [
        "URLSessionConfiguration.ephemeral",
        "removeArchiveAfterExtraction: false",
        "resolveDownloadURL(_ raw: String, relativeTo sourceBase: URL?)",
        "cleanupAbandonedTransactions(in base: URL)",
        "recoveryTransactionMarker",
    ],
    ROOT / "iOSSim/Model/PackageStore.swift": [
        "effectiveSourceURLs",
        "sourceID: UUID",
        "sourceBaseURL: sourceBaseURL",
        "response.url ?? url",
    ],
    ROOT / "iOSSim/Apps/PackagesView.swift": [
        "sourceID: entry.sourceID",
        "sourceID: pending.sourceID",
    ],
    ROOT / "iOSSim/Model/ZipArchive.swift": [
        "volumeAvailableCapacityForImportantUsageKey",
        "inflateDeflate(",
        "ioChunkSize = 256 * 1_024",
        "try manager.createDirectory(",
    ],
}

missing = []
for check_path, markers in checks.items():
    content = check_path.read_text()
    for marker in markers:
        if marker not in content:
            missing.append(f"{check_path.relative_to(ROOT)}: {marker}")

if missing:
    print("missing expected installer fixes:", file=sys.stderr)
    for item in missing:
        print(f"  - {item}", file=sys.stderr)
    raise SystemExit(1)
