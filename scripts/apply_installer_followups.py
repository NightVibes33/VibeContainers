#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"follow-up fix: expected block not found for {label}")
    return text.replace(old, new, 1)


def update(path: Path, transform) -> None:
    original = path.read_text()
    changed = transform(original)
    if changed != original:
        path.write_text(changed)
        print(f"patched {path.relative_to(ROOT)}")
    else:
        print(f"already fixed {path.relative_to(ROOT)}")


def fix_package(text: str) -> str:
    installed_source_fixed = '''        var version: String\n        var sourceName: String\n        var sourceID: UUID?\n        var iconURL: String?\n'''
    if installed_source_fixed not in text:
        text = replace_once(
            text,
            '''        var version: String\n        var sourceName: String\n        var iconURL: String?\n''',
            installed_source_fixed,
            "InstalledApp sourceID",
        )

    pending_fixed = '''    struct PendingUpdate: Identifiable, Sendable {\n        let installed: InstalledApp\n        let app: AltApp\n        let sourceName: String\n        let sourceID: UUID\n        var id: String { installed.bundleIdentifier }\n    }\n'''
    if pending_fixed not in text:
        text = replace_once(
            text,
            '''    struct PendingUpdate: Identifiable, Sendable {\n        let installed: InstalledApp\n        let app: AltApp\n        let sourceName: String\n        var id: String { installed.bundleIdentifier }\n    }\n''',
            pending_fixed,
            "PendingUpdate sourceID",
        )

    add_source_fixed = '''        do {\n            let (catalog, effectiveURL) = try await Self.fetch(url)\n            let source = Source(url: normalised, name: catalog.name)\n            sources.append(source)\n            catalogs[source.id] = catalog\n            effectiveSourceURLs[source.id] = effectiveURL\n            persistSources()\n'''
    if add_source_fixed not in text:
        text = replace_once(
            text,
            '''        do {\n            let catalog = try await Self.fetch(url)\n            let source = Source(url: normalised, name: catalog.name)\n            sources.append(source)\n            catalogs[source.id] = catalog\n            persistSources()\n''',
            add_source_fixed,
            "addSource effective URL",
        )

    exact_update_lookup = '''            guard hasReadyPayload(record.bundleIdentifier),\n                  let entry = catalogEntry(for: record),\n                  SemVer.isNewer(entry.app.latestVersion, than: record.version) else { return nil }\n'''
    if exact_update_lookup not in text:
        text = replace_once(
            text,
            '''            guard hasReadyPayload(record.bundleIdentifier),\n                  let entry = catalogIndex.entriesByBundle[record.bundleIdentifier],\n                  SemVer.isNewer(entry.app.latestVersion, than: record.version) else { return nil }\n''',
            exact_update_lookup,
            "exact installed-source update lookup",
        )

    catalog_lookup_helper = '''    private func catalogEntry(for record: InstalledApp) -> Entry? {\n        if let sourceID = record.sourceID,\n           let entry = catalogIndex.entriesBySource[sourceID]?.first(where: {\n               $0.app.bundleIdentifier == record.bundleIdentifier\n           }) {\n            return entry\n        }\n\n        // Existing records from builds before source IDs were persisted still\n        // prefer the source name they were installed from before falling back\n        // to the first repository that publishes the same bundle identifier.\n        if let entry = catalogIndex.allApps.first(where: {\n            $0.app.bundleIdentifier == record.bundleIdentifier\n                && $0.sourceName == record.sourceName\n        }) {\n            return entry\n        }\n        return catalogIndex.entriesByBundle[record.bundleIdentifier]\n    }\n\n'''
    if "private func catalogEntry(for record: InstalledApp)" not in text:
        text = replace_once(
            text,
            '''    private nonisolated static func entryNameOrder(_ lhs: Entry, _ rhs: Entry) -> Bool {\n''',
            catalog_lookup_helper + '''    private nonisolated static func entryNameOrder(_ lhs: Entry, _ rhs: Entry) -> Bool {\n''',
            "catalogEntry helper",
        )

    completed_record_fixed = '''            version: app.latestVersion,\n            sourceName: sourceName,\n            sourceID: sourceID,\n            iconURL: app.iconURL,\n'''
    if completed_record_fixed not in text:
        text = replace_once(
            text,
            '''            version: app.latestVersion,\n            sourceName: sourceName,\n            iconURL: app.iconURL,\n''',
            completed_record_fixed,
            "persist installed sourceID",
        )

    sideload_record_fixed = '''            version: version,\n            sourceName: sourceName,\n            sourceID: nil,\n            iconURL: iconURL,\n'''
    if sideload_record_fixed not in text:
        text = replace_once(
            text,
            '''            version: version,\n            sourceName: sourceName,\n            iconURL: iconURL,\n''',
            sideload_record_fixed,
            "sideload sourceID nil",
        )
    return text


def fix_packages_view(text: str) -> str:
    installed_update_fixed = '''                                last: pending.id == store.updates.last?.id,\n                                action: store.action(\n                                    for: pending.app,\n                                    sourceName: pending.sourceName,\n                                    sourceID: pending.sourceID\n                                )\n'''
    if installed_update_fixed not in text:
        text = replace_once(
            text,
            '''                                last: pending.id == store.updates.last?.id,\n                                action: store.action(\n                                    for: pending.app,\n                                    sourceName: pending.sourceName\n                                )\n''',
            installed_update_fixed,
            "Installed updates sourceID",
        )
    return text


def fix_guest(text: str) -> str:
    visible_hidden_transactions = '''            includingPropertiesForKeys: [.isDirectoryKey],\n            options: []\n'''
    if visible_hidden_transactions not in text:
        text = replace_once(
            text,
            '''            includingPropertiesForKeys: [.isDirectoryKey],\n            options: [.skipsHiddenFiles]\n''',
            visible_hidden_transactions,
            "hidden transaction cleanup",
        )

    checked_marker = '''            try Data().write(\n                to: transactionRoot.appendingPathComponent(Self.activeTransactionMarker),\n                options: .atomic\n            )\n            phases[bundle] = .downloading(0)\n'''
    if checked_marker not in text:
        text = replace_once(
            text,
            '''            FileManager.default.createFile(\n                atPath: transactionRoot.appendingPathComponent(Self.activeTransactionMarker).path,\n                contents: Data()\n            )\n            phases[bundle] = .downloading(0)\n''',
            checked_marker,
            "checked transaction marker",
        )
    return text


def fix_zip(text: str) -> str:
    # COMPRESSION_STATUS_END is only produced after the last input is processed
    # with COMPRESSION_STREAM_FINALIZE. The first streaming implementation did
    # not pass that flag.
    if "Int32(COMPRESSION_STREAM_FINALIZE.rawValue)" not in text:
        text = replace_once(
            text,
            '''            remaining -= chunk.count\n\n            try chunk.withUnsafeBytes { rawSource in\n''',
            '''            remaining -= chunk.count\n            let flags = remaining == 0\n                ? Int32(COMPRESSION_STREAM_FINALIZE.rawValue)\n                : Int32(0)\n\n            try chunk.withUnsafeBytes { rawSource in\n''',
            "Compression finalize flag",
        )
        text = text.replace(
            "compression_stream_process(&stream, 0)",
            "compression_stream_process(&stream, flags)",
        )
        text = text.replace(
            "                while stream.src_size > 0 {",
            "                repeat {",
            1,
        )
        text = text.replace(
            '''                    if stream.src_size == before && produced == 0 {\n                        throw ZipError.inflateFailed\n                    }\n                }\n''',
            '''                    if stream.src_size == before && produced == 0 {\n                        throw ZipError.inflateFailed\n                    }\n                } while stream.src_size > 0 || flags != 0\n''',
            1,
        )

    # Swift 6.2 no longer provides a zero-argument imported initializer for the
    # C compression_stream struct. Allocate the C struct exactly as Apple's
    # streaming sample does and let compression_stream_init initialize it.
    if "UnsafeMutablePointer<compression_stream>.allocate(capacity: 1)" not in text:
        text = replace_once(
            text,
            '''        var stream = compression_stream()\n        guard compression_stream_init(\n            &stream,\n            COMPRESSION_STREAM_DECODE,\n            COMPRESSION_ZLIB\n        ) != COMPRESSION_STATUS_ERROR else {\n            throw ZipError.inflateFailed\n        }\n        defer { compression_stream_destroy(&stream) }\n''',
            '''        let stream = UnsafeMutablePointer<compression_stream>.allocate(capacity: 1)\n        guard compression_stream_init(\n            stream,\n            COMPRESSION_STREAM_DECODE,\n            COMPRESSION_ZLIB\n        ) != COMPRESSION_STATUS_ERROR else {\n            stream.deallocate()\n            throw ZipError.inflateFailed\n        }\n        defer {\n            compression_stream_destroy(stream)\n            stream.deallocate()\n        }\n''',
            "Compression stream allocation",
        )
        text = text.replace("stream.src_ptr", "stream.pointee.src_ptr")
        text = text.replace("stream.src_size", "stream.pointee.src_size")
        text = text.replace("stream.dst_ptr", "stream.pointee.dst_ptr")
        text = text.replace("stream.dst_size", "stream.pointee.dst_size")
        text = text.replace(
            "compression_stream_process(&stream, flags)",
            "compression_stream_process(stream, flags)",
        )
    return text


package = ROOT / "iOSSim/Model/PackageStore.swift"
packages_view = ROOT / "iOSSim/Apps/PackagesView.swift"
guest = ROOT / "iOSSim/Model/GuestInstaller.swift"
zip_archive = ROOT / "iOSSim/Model/ZipArchive.swift"

update(package, fix_package)
update(packages_view, fix_packages_view)
update(guest, fix_guest)
update(zip_archive, fix_zip)

package_text = package.read_text()
packages_view_text = packages_view.read_text()
guest_text = guest.read_text()
zip_text = zip_archive.read_text()

required = [
    (
        package_text,
        "var sourceName: String\n        var sourceID: UUID?\n        var iconURL: String?",
    ),
    (
        package_text,
        "struct PendingUpdate: Identifiable, Sendable {\n        let installed: InstalledApp\n        let app: AltApp\n        let sourceName: String\n        let sourceID: UUID",
    ),
    (
        package_text,
        "let (catalog, effectiveURL) = try await Self.fetch(url)\n            let source = Source(url: normalised, name: catalog.name)",
    ),
    (package_text, "effectiveSourceURLs[source.id] = effectiveURL"),
    (package_text, "private func catalogEntry(for record: InstalledApp)"),
    (package_text, "sourceID: sourceID,\n            iconURL: app.iconURL"),
    (package_text, "sourceID: nil,\n            iconURL: iconURL"),
    (
        packages_view_text,
        "last: pending.id == store.updates.last?.id,\n                                action: store.action(\n                                    for: pending.app,\n                                    sourceName: pending.sourceName,\n                                    sourceID: pending.sourceID",
    ),
    (guest_text, "includingPropertiesForKeys: [.isDirectoryKey],\n            options: []"),
    (guest_text, "to: transactionRoot.appendingPathComponent(Self.activeTransactionMarker)"),
    (zip_text, "Int32(COMPRESSION_STREAM_FINALIZE.rawValue)"),
    (zip_text, "UnsafeMutablePointer<compression_stream>.allocate(capacity: 1)"),
    (zip_text, "stream.pointee.src_size > 0 || flags != 0"),
    (zip_text, "compression_stream_process(stream, flags)"),
]
missing = [marker for content, marker in required if marker not in content]
if missing:
    raise SystemExit("follow-up validation failed: " + " | ".join(missing))
