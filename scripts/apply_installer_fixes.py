#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "iOSSim/Model/GuestInstaller.swift"
text = PATH.read_text()
original = text


def replace_once(old: str, new: str, marker: str) -> None:
    global text
    if marker in text:
        return
    if old not in text:
        raise SystemExit(f"installer hotfix: expected source block not found for {marker}")
    text = text.replace(old, new, 1)


replace_once(
    "    static let shared = GuestInstaller()\n    private init() {}\n",
    "    static let shared = GuestInstaller()\n    private init() {\n        // A killed/terminated import can leave a full extracted app in Staging.\n        // Nothing in this directory is persistent state, so reclaim it before\n        // the next install instead of letting abandoned imports exhaust /User.\n        try? FileManager.default.removeItem(at: Self.stagingRoot)\n    }\n",
    "reclaim it before\\n        // the next install",
)

replace_once(
    '''                let session = URLSession(\n                    configuration: .default,\n                    delegate: self,\n                    delegateQueue: nil\n                )\n                self.session = session\n                let task = session.downloadTask(with: url)\n''',
    '''                // IPA payloads can be hundreds of MB. Do not let URLCache\n                // retain another copy of a downloaded archive on the User volume.\n                let configuration = URLSessionConfiguration.ephemeral\n                configuration.urlCache = nil\n                configuration.requestCachePolicy = .reloadIgnoringLocalCacheData\n                configuration.timeoutIntervalForResource = 30 * 60\n\n                let session = URLSession(\n                    configuration: configuration,\n                    delegate: self,\n                    delegateQueue: nil\n                )\n                self.session = session\n\n                var request = URLRequest(url: url)\n                request.timeoutInterval = 120\n                request.cachePolicy = .reloadIgnoringLocalCacheData\n                request.setValue(\n                    "application/octet-stream, application/zip, */*",\n                    forHTTPHeaderField: "Accept"\n                )\n                request.setValue("VibeContainers/1.0 (iOS)", forHTTPHeaderField: "User-Agent")\n                let task = session.downloadTask(with: request)\n''',
    "configuration.timeoutIntervalForResource = 30 * 60",
)

replace_once(
    '''        guard let raw = app.latest?.downloadURL, let url = URL(string: raw) else {\n            phases[bundle] = .failed("This version has no download URL.")\n            return false\n        }\n''',
    '''        guard let raw = app.latest?.downloadURL,\n              let url = Self.resolveDownloadURL(raw, for: app) else {\n            phases[bundle] = .failed("This version has no usable download URL.")\n            return false\n        }\n''',
    "Self.resolveDownloadURL(raw, for: app)",
)

replace_once(
    '''    /// Installs an `.ipa` the user picked in the file browser.\n    ///\n    /// The picked file lives outside the app, so its security scope has to be\n    /// open for the copy — and only for the copy: everything after this works\n    /// on iOSSim's own staging directory.\n    func installIPA(at picked: URL) async {\n        let scoped = picked.startAccessingSecurityScopedResource()\n        defer { if scoped { picked.stopAccessingSecurityScopedResource() } }\n\n        let staging = Self.stagingRoot\n            .appendingPathComponent("import-\\(UUID().uuidString)", isDirectory: true)\n        let copy = staging.appendingPathComponent("import.ipa")\n\n        do {\n            try FileManager.default.createDirectory(at: staging, withIntermediateDirectories: true)\n            try FileManager.default.copyItem(at: picked, to: copy)\n        } catch {\n            try? FileManager.default.removeItem(at: staging)\n            sideload = .failed("Could not read that file: \\(error.localizedDescription)")\n            return\n        }\n        await unpackAndInstall(copy, origin: "Local file")\n    }\n''',
    '''    /// Installs an `.ipa` the user picked in the file browser.\n    ///\n    /// Keep the security scope open while the ZIP reader consumes the selected\n    /// file directly. The old implementation first copied the complete IPA into\n    /// Documents/Staging and then extracted it, requiring compressed IPA + copy\n    /// + expanded app to coexist and causing bogus-looking "volume User is out\n    /// of space" failures whose filename happened to be the guest executable.\n    func installIPA(at picked: URL) async {\n        let scoped = picked.startAccessingSecurityScopedResource()\n        defer { if scoped { picked.stopAccessingSecurityScopedResource() } }\n\n        let staging = Self.stagingRoot\n            .appendingPathComponent("import-\\(UUID().uuidString)", isDirectory: true)\n\n        do {\n            try FileManager.default.createDirectory(at: staging, withIntermediateDirectories: true)\n        } catch {\n            sideload = .failed("Could not create import staging: \\(error.localizedDescription)")\n            return\n        }\n\n        await unpackAndInstall(\n            picked,\n            staging: staging,\n            origin: "Local file",\n            removeArchiveAfterExtraction: false\n        )\n    }\n''',
    "Keep the security scope open while the ZIP reader consumes",
)

replace_once(
    '''        await unpackAndInstall(copy, origin: remote.host() ?? "Link")\n''',
    '''        await unpackAndInstall(\n            copy,\n            staging: staging,\n            origin: remote.host() ?? "Link",\n            removeArchiveAfterExtraction: true\n        )\n''',
    "removeArchiveAfterExtraction: true",
)

replace_once(
    '''    private func unpackAndInstall(_ ipa: URL, origin: String) async {\n        let staging = ipa.deletingLastPathComponent()\n        let payload = staging.appendingPathComponent("Payload", isDirectory: true)\n''',
    '''    private func unpackAndInstall(\n        _ ipa: URL,\n        staging: URL,\n        origin: String,\n        removeArchiveAfterExtraction: Bool\n    ) async {\n        let payload = staging.appendingPathComponent("Payload", isDirectory: true)\n''',
    "removeArchiveAfterExtraction: Bool",
)

replace_once(
    '''            let modes = try await Task.detached(priority: .userInitiated) {\n                try ZipArchive.extract(ipa, to: staging)\n            }.value\n            restoreExecutableBits(modes, under: staging)\n''',
    '''            let modes = try await Task.detached(priority: .userInitiated) {\n                try ZipArchive.extract(ipa, to: staging)\n            }.value\n            // Remote/link imports own their staged archive. Delete it as soon\n            // as extraction succeeds so signing/patching does not keep both the\n            // compressed IPA and expanded Payload on disk at the same time.\n            if removeArchiveAfterExtraction {\n                try? FileManager.default.removeItem(at: ipa)\n            }\n            restoreExecutableBits(modes, under: staging)\n''',
    "Remote/link imports own their staged archive",
)

replace_once(
    '''    private static var stagingRoot: URL {\n        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]\n            .appendingPathComponent("Staging", isDirectory: true)\n    }\n''',
    '''    private static var stagingRoot: URL {\n        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]\n            .appendingPathComponent("Staging", isDirectory: true)\n    }\n\n    /// Resolves the forms found in real AltStore-compatible sources: absolute\n    /// URLs, scheme-relative URLs, paths relative to the source JSON, and GitHub\n    /// `blob` links that otherwise download an HTML page instead of an IPA.\n    private static func resolveDownloadURL(_ raw: String, for app: AltApp) -> URL? {\n        let value = raw.trimmingCharacters(in: .whitespacesAndNewlines)\n        guard !value.isEmpty else { return nil }\n\n        var sourceBase: URL?\n        for source in PackageStore.shared.sources {\n            let matches = PackageStore.shared.apps(for: source).contains { candidate in\n                candidate.bundleIdentifier == app.bundleIdentifier\n                    && candidate.latest?.downloadURL == raw\n            }\n            if matches {\n                sourceBase = SourceURL.normalise(source.url)\n                break\n            }\n        }\n\n        let candidate: URL?\n        if value.hasPrefix("//") {\n            candidate = URL(string: "https:" + value)\n        } else if let direct = URL(string: value), direct.scheme != nil {\n            candidate = direct\n        } else if let sourceBase {\n            candidate = URL(string: value, relativeTo: sourceBase)?.absoluteURL\n        } else {\n            candidate = nil\n        }\n\n        guard var resolved = candidate,\n              let scheme = resolved.scheme?.lowercased(),\n              scheme == "https" || scheme == "http" else { return nil }\n\n        if resolved.host?.lowercased() == "github.com" {\n            var parts = resolved.path.split(separator: "/").map(String.init)\n            if let blob = parts.firstIndex(of: "blob"), parts.count > blob + 1 {\n                parts.remove(at: blob)\n                if let rawURL = URL(\n                    string: "https://raw.githubusercontent.com/" + parts.joined(separator: "/")\n                ) {\n                    resolved = rawURL\n                }\n            }\n        }\n        return resolved\n    }\n''',
    "private static func resolveDownloadURL(_ raw: String, for app: AltApp)",
)

replace_once(
    '''            if ns.code == NSURLErrorNotConnectedToInternet { return "No internet connection." }\n            if ns.code == NSURLErrorTimedOut { return "The download timed out." }\n            return ns.localizedDescription\n''',
    '''            if ns.code == NSURLErrorNotConnectedToInternet { return "No internet connection." }\n            if ns.code == NSURLErrorTimedOut { return "The download timed out." }\n            if (ns.domain == NSCocoaErrorDomain && ns.code == NSFileWriteOutOfSpaceError)\n                || (ns.domain == NSPOSIXErrorDomain && ns.code == Int(ENOSPC)) {\n                return "Not enough free device storage to unpack this IPA."\n            }\n            return ns.localizedDescription\n''',
    "Not enough free device storage to unpack this IPA.",
)

if text != original:
    PATH.write_text(text)
    print(f"patched {PATH.relative_to(ROOT)}")
else:
    print("installer fixes already applied")

# Cheap structural checks so CI fails here rather than producing a subtly old IPA.
required = [
    "URLSessionConfiguration.ephemeral",
    "Self.resolveDownloadURL(raw, for: app)",
    "removeArchiveAfterExtraction: false",
    "removeArchiveAfterExtraction: true",
    "raw.githubusercontent.com",
]
missing = [item for item in required if item not in text]
if missing:
    print("missing expected installer fixes:", ", ".join(missing), file=sys.stderr)
    raise SystemExit(1)
