#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def patch(path: Path, old: str, new: str, marker: str) -> None:
    text = path.read_text()
    if marker in text:
        print(f"already fixed {path.relative_to(ROOT)}: {marker}")
        return
    if old not in text:
        raise SystemExit(f"follow-up fix: expected block not found in {path.relative_to(ROOT)}")
    path.write_text(text.replace(old, new, 1))
    print(f"patched {path.relative_to(ROOT)}: {marker}")


package = ROOT / "iOSSim/Model/PackageStore.swift"
patch(
    package,
    '''    struct PendingUpdate: Identifiable, Sendable {\n        let installed: InstalledApp\n        let app: AltApp\n        let sourceName: String\n        var id: String { installed.bundleIdentifier }\n    }\n''',
    '''    struct PendingUpdate: Identifiable, Sendable {\n        let installed: InstalledApp\n        let app: AltApp\n        let sourceName: String\n        let sourceID: UUID\n        var id: String { installed.bundleIdentifier }\n    }\n''',
    "let sourceName: String\n        let sourceID: UUID\n        var id: String { installed.bundleIdentifier }",
)

patch(
    package,
    '''        do {\n            let catalog = try await Self.fetch(url)\n            let source = Source(url: normalised, name: catalog.name)\n            sources.append(source)\n            catalogs[source.id] = catalog\n            persistSources()\n''',
    '''        do {\n            let (catalog, effectiveURL) = try await Self.fetch(url)\n            let source = Source(url: normalised, name: catalog.name)\n            sources.append(source)\n            catalogs[source.id] = catalog\n            effectiveSourceURLs[source.id] = effectiveURL\n            persistSources()\n''',
    "sources.append(source)\n            catalogs[source.id] = catalog\n            effectiveSourceURLs[source.id] = effectiveURL",
)

guest = ROOT / "iOSSim/Model/GuestInstaller.swift"
patch(
    guest,
    '''            includingPropertiesForKeys: [.isDirectoryKey],\n            options: [.skipsHiddenFiles]\n''',
    '''            includingPropertiesForKeys: [.isDirectoryKey],\n            options: []\n''',
    "includingPropertiesForKeys: [.isDirectoryKey],\n            options: []",
)

# The marker itself must be created with an error-reporting API. If this fails,
# the install transaction is not safe to treat as cleanup-owned state.
patch(
    guest,
    '''            FileManager.default.createFile(\n                atPath: transactionRoot.appendingPathComponent(Self.activeTransactionMarker).path,\n                contents: Data()\n            )\n            phases[bundle] = .downloading(0)\n''',
    '''            try Data().write(\n                to: transactionRoot.appendingPathComponent(Self.activeTransactionMarker),\n                options: .atomic\n            )\n            phases[bundle] = .downloading(0)\n''',
    "to: transactionRoot.appendingPathComponent(Self.activeTransactionMarker)",
)

# Apple documents that COMPRESSION_STATUS_END is only produced after the final
# input is processed with COMPRESSION_STREAM_FINALIZE. Without this flag, every
# otherwise-valid deflated entry can finish with status OK and then be rejected.
zip_archive = ROOT / "iOSSim/Model/ZipArchive.swift"
patch(
    zip_archive,
    '''    private static func inflateDeflate(\n        _ entry: Entry,\n        input: FileHandle,\n        output: FileHandle\n    ) throws {\n        if entry.uncompressedSize == 0 {\n            // Empty deflate streams still have compressed framing bytes. Feed\n            // them through the decoder so corrupt archives do not silently pass.\n        }\n\n        var stream = compression_stream()\n        guard compression_stream_init(\n            &stream,\n            COMPRESSION_STREAM_DECODE,\n            COMPRESSION_ZLIB\n        ) != COMPRESSION_STATUS_ERROR else {\n            throw ZipError.inflateFailed\n        }\n        defer { compression_stream_destroy(&stream) }\n\n        var remaining = entry.compressedSize\n        var totalWritten = 0\n        var reachedEnd = false\n        var outputBuffer = [UInt8](repeating: 0, count: ioChunkSize)\n        let outputCapacity = outputBuffer.count\n\n        while remaining > 0 && !reachedEnd {\n            let count = min(ioChunkSize, remaining)\n            guard let chunk = try input.read(upToCount: count), !chunk.isEmpty else {\n                throw ZipError.truncated\n            }\n            remaining -= chunk.count\n\n            try chunk.withUnsafeBytes { rawSource in\n                let source = rawSource.bindMemory(to: UInt8.self)\n                guard let sourceBase = source.baseAddress else { return }\n                stream.src_ptr = sourceBase\n                stream.src_size = source.count\n\n                while stream.src_size > 0 {\n                    let before = stream.src_size\n                    var produced = 0\n                    let status = outputBuffer.withUnsafeMutableBytes { rawDestination -> compression_status in\n                        let destination = rawDestination.bindMemory(to: UInt8.self)\n                        stream.dst_ptr = destination.baseAddress!\n                        stream.dst_size = outputCapacity\n                        let result = compression_stream_process(&stream, 0)\n                        produced = outputCapacity - stream.dst_size\n                        return result\n                    }\n\n                    if produced > 0 {\n                        try output.write(contentsOf: Data(outputBuffer.prefix(produced)))\n                        totalWritten += produced\n                        if totalWritten > entry.uncompressedSize {\n                            throw ZipError.inflateFailed\n                        }\n                    }\n\n                    if status == COMPRESSION_STATUS_END {\n                        reachedEnd = true\n                        break\n                    }\n                    if status == COMPRESSION_STATUS_ERROR {\n                        throw ZipError.inflateFailed\n                    }\n                    // A valid decoder call must consume input or emit output.\n                    // Guarding this prevents a malformed stream from spinning.\n                    if stream.src_size == before && produced == 0 {\n                        throw ZipError.inflateFailed\n                    }\n                }\n            }\n        }\n\n        guard reachedEnd,\n              remaining == 0,\n              totalWritten == entry.uncompressedSize else {\n            throw ZipError.inflateFailed\n        }\n    }\n''',
    '''    private static func inflateDeflate(\n        _ entry: Entry,\n        input: FileHandle,\n        output: FileHandle\n    ) throws {\n        var stream = compression_stream()\n        guard compression_stream_init(\n            &stream,\n            COMPRESSION_STREAM_DECODE,\n            COMPRESSION_ZLIB\n        ) != COMPRESSION_STATUS_ERROR else {\n            throw ZipError.inflateFailed\n        }\n        defer { compression_stream_destroy(&stream) }\n\n        var remaining = entry.compressedSize\n        var totalWritten = 0\n        var reachedEnd = false\n        var outputBuffer = [UInt8](repeating: 0, count: ioChunkSize)\n        let outputCapacity = outputBuffer.count\n\n        while remaining > 0 && !reachedEnd {\n            let count = min(ioChunkSize, remaining)\n            guard let chunk = try input.read(upToCount: count), !chunk.isEmpty else {\n                throw ZipError.truncated\n            }\n            remaining -= chunk.count\n            let flags = remaining == 0\n                ? Int32(COMPRESSION_STREAM_FINALIZE.rawValue)\n                : Int32(0)\n\n            try chunk.withUnsafeBytes { rawSource in\n                let source = rawSource.bindMemory(to: UInt8.self)\n                guard let sourceBase = source.baseAddress else { return }\n                stream.src_ptr = sourceBase\n                stream.src_size = source.count\n\n                repeat {\n                    let before = stream.src_size\n                    var produced = 0\n                    let status = outputBuffer.withUnsafeMutableBytes { rawDestination -> compression_status in\n                        let destination = rawDestination.bindMemory(to: UInt8.self)\n                        stream.dst_ptr = destination.baseAddress!\n                        stream.dst_size = outputCapacity\n                        let result = compression_stream_process(&stream, flags)\n                        produced = outputCapacity - stream.dst_size\n                        return result\n                    }\n\n                    if produced > 0 {\n                        try output.write(contentsOf: Data(outputBuffer.prefix(produced)))\n                        totalWritten += produced\n                        if totalWritten > entry.uncompressedSize {\n                            throw ZipError.inflateFailed\n                        }\n                    }\n\n                    if status == COMPRESSION_STATUS_END {\n                        // A decoder that ends before consuming the entry's declared\n                        // compressed bytes indicates a malformed central directory.\n                        guard stream.src_size == 0 else { throw ZipError.inflateFailed }\n                        reachedEnd = true\n                        break\n                    }\n                    if status == COMPRESSION_STATUS_ERROR {\n                        throw ZipError.inflateFailed\n                    }\n                    // With FINALIZE set, a zero-length source may need another\n                    // call to flush output and return END. Any call that neither\n                    // consumes nor produces data cannot make forward progress.\n                    if stream.src_size == before && produced == 0 {\n                        throw ZipError.inflateFailed\n                    }\n                } while stream.src_size > 0 || flags != 0\n            }\n        }\n\n        guard reachedEnd,\n              remaining == 0,\n              totalWritten == entry.uncompressedSize else {\n            throw ZipError.inflateFailed\n        }\n    }\n''',
    "Int32(COMPRESSION_STREAM_FINALIZE.rawValue)",
)

# Validate exact structural relationships instead of ambiguous substring
# markers that can match another struct or code path.
package_text = package.read_text()
guest_text = guest.read_text()
zip_text = zip_archive.read_text()
required = [
    "struct PendingUpdate: Identifiable, Sendable {\n        let installed: InstalledApp\n        let app: AltApp\n        let sourceName: String\n        let sourceID: UUID",
    "let (catalog, effectiveURL) = try await Self.fetch(url)\n            let source = Source(url: normalised, name: catalog.name)",
    "effectiveSourceURLs[source.id] = effectiveURL",
    "options: []",
    "to: transactionRoot.appendingPathComponent(Self.activeTransactionMarker)",
    "Int32(COMPRESSION_STREAM_FINALIZE.rawValue)",
    "stream.src_size > 0 || flags != 0",
]
combined = package_text + "\n" + guest_text + "\n" + zip_text
missing = [item for item in required if item not in combined]
if missing:
    raise SystemExit("follow-up validation failed: " + " | ".join(missing))
