import Foundation
import Compression

/// A ZIP reader specialized for IPA imports.
///
/// The central directory is memory-mapped so metadata stays cheap even for a
/// large IPA, while file payloads are read and decompressed in bounded chunks.
/// We never materialize the whole compressed entry and whole expanded entry at
/// the same time. This keeps large executables/frameworks from causing memory
/// spikes and lets disk-space failures be detected before a partial Payload is
/// written.
enum ZipArchive {
    struct Entry {
        let path: String
        let compressionMethod: UInt16
        let compressedSize: Int
        let uncompressedSize: Int
        let localHeaderOffset: Int
        let isDirectory: Bool
        /// Full Unix mode from ZIP external attributes when present.
        let unixMode: UInt16
    }

    enum ZipError: LocalizedError {
        case notAZip
        case truncated
        case unsupportedMethod(UInt16)
        case inflateFailed
        case unsafePath(String)
        case archiveTooLarge
        case insufficientSpace(required: Int64, available: Int64)
        case cannotCreateOutput(String)

        var errorDescription: String? {
            switch self {
            case .notAZip:
                "The selected file is not a ZIP archive."
            case .truncated:
                "The archive is incomplete or damaged."
            case .unsupportedMethod(let method):
                "The archive uses unsupported compression method \(method)."
            case .inflateFailed:
                "The archive could not be decompressed."
            case .unsafePath:
                "The archive contains an unsafe file path."
            case .archiveTooLarge:
                "The archive is too large to import safely."
            case .insufficientSpace(let required, let available):
                "This IPA needs about \(Self.mb(required)) MB free to unpack; only \(Self.mb(available)) MB is currently available."
            case .cannotCreateOutput(let path):
                "Could not create an extracted file at \(path)."
            }
        }

        private static func mb(_ bytes: Int64) -> Int64 {
            max(0, (bytes + 1_048_575) / 1_048_576)
        }
    }

    private static let ioChunkSize = 256 * 1_024
    private static let minimumFreeReserve: Int64 = 32 * 1_024 * 1_024

    /// Extracts the whole archive under `destination`, returning the executable
    /// bits so the installer can restore them after all files are present.
    @discardableResult
    static func extract(
        _ archiveURL: URL,
        to destination: URL,
        maximumUncompressedBytes: Int? = nil,
        maximumEntries: Int? = nil
    ) throws -> [String: UInt16] {
        // `.mappedIfSafe` maps the archive instead of eagerly copying all IPA
        // bytes into heap memory. Only central-directory/header bytes are read
        // from this Data; actual file payloads stream through FileHandle below.
        let data = try Data(contentsOf: archiveURL, options: .mappedIfSafe)
        let entries = try readCentralDirectory(data)

        if let maximumEntries, entries.count > maximumEntries {
            throw ZipError.archiveTooLarge
        }

        var totalUncompressed: Int64 = 0
        for entry in entries {
            let size = Int64(entry.uncompressedSize)
            guard size >= 0, totalUncompressed <= Int64.max - size else {
                throw ZipError.archiveTooLarge
            }
            totalUncompressed += size
            if let maximumUncompressedBytes,
               totalUncompressed > Int64(maximumUncompressedBytes) {
                throw ZipError.archiveTooLarge
            }
        }

        let manager = FileManager.default
        let root = destination.standardizedFileURL
        try manager.createDirectory(at: root, withIntermediateDirectories: true)
        try preflightFreeSpace(for: totalUncompressed, at: root)

        // Validate every pathname before writing the first archive entry. A bad
        // source cannot leave a partly extracted tree outside/inside staging.
        for entry in entries where !isMobileContainerManagerMetadata(entry.path) {
            _ = try safeOutputURL(for: entry.path, under: root)
        }

        let input = try FileHandle(forReadingFrom: archiveURL)
        defer { try? input.close() }

        var modes: [String: UInt16] = [:]
        for entry in entries {
            // Repackaged IPAs sometimes carry this private container marker.
            // It is not part of the runnable app bundle and iOS can reject it.
            if isMobileContainerManagerMetadata(entry.path) { continue }

            let outURL = try safeOutputURL(for: entry.path, under: root)
            if entry.isDirectory {
                try manager.createDirectory(at: outURL, withIntermediateDirectories: true)
                continue
            }

            try manager.createDirectory(
                at: outURL.deletingLastPathComponent(),
                withIntermediateDirectories: true
            )
            if manager.fileExists(atPath: outURL.path) {
                try manager.removeItem(at: outURL)
            }
            guard manager.createFile(atPath: outURL.path, contents: nil) else {
                throw ZipError.cannotCreateOutput(entry.path)
            }

            do {
                let dataStart = try localDataStart(for: entry, in: data)
                try input.seek(toOffset: UInt64(dataStart))
                let output = try FileHandle(forWritingTo: outURL)
                defer { try? output.close() }

                switch entry.compressionMethod {
                case 0:
                    try copyStored(entry, input: input, output: output)
                case 8:
                    try inflateDeflate(entry, input: input, output: output)
                default:
                    throw ZipError.unsupportedMethod(entry.compressionMethod)
                }
            } catch {
                try? manager.removeItem(at: outURL)
                throw error
            }

            if entry.unixMode != 0 { modes[entry.path] = entry.unixMode }
        }
        return modes
    }

    private static func preflightFreeSpace(for expandedBytes: Int64, at root: URL) throws {
        guard expandedBytes > 0 else { return }
        let values = try? root.resourceValues(forKeys: [.volumeAvailableCapacityForImportantUsageKey])
        guard let available = values?.volumeAvailableCapacityForImportantUsage,
              available >= 0 else { return }

        // Keep a modest reserve for metadata, code signing and plist writes.
        // Five percent scales for large apps; 32 MiB avoids running the volume
        // completely dry for smaller imports.
        let reserve = max(minimumFreeReserve, expandedBytes / 20)
        guard expandedBytes <= Int64.max - reserve else { throw ZipError.archiveTooLarge }
        let required = expandedBytes + reserve
        guard available >= required else {
            throw ZipError.insufficientSpace(required: required, available: available)
        }
    }

    private static func isMobileContainerManagerMetadata(_ path: String) -> Bool {
        path.split(separator: "/", omittingEmptySubsequences: true).last
            == ".com.apple.mobile_container_manager.metadata.plist"
    }

    /// ZIP paths are attacker-controlled. Keep every entry beneath the chosen
    /// extraction directory so a crafted IPA cannot write outside staging.
    private static func safeOutputURL(for path: String, under root: URL) throws -> URL {
        guard !path.isEmpty,
              !path.hasPrefix("/"),
              !path.hasPrefix("\\"),
              !path.contains("\\"),
              !path.split(separator: "/", omittingEmptySubsequences: false).contains("..") else {
            throw ZipError.unsafePath(path)
        }

        let candidate = root.appendingPathComponent(path).standardizedFileURL
        let rootPath = root.path.hasSuffix("/") ? root.path : root.path + "/"
        guard candidate.path == root.path || candidate.path.hasPrefix(rootPath) else {
            throw ZipError.unsafePath(path)
        }
        return candidate
    }

    // MARK: - Central directory

    private static func readCentralDirectory(_ data: Data) throws -> [Entry] {
        let eocdSignature: UInt32 = 0x0605_4b50
        guard data.count >= 22 else { throw ZipError.truncated }

        var eocd = -1
        let lowerBound = max(0, data.count - 22 - 0xFFFF)
        var index = data.count - 22
        while index >= lowerBound {
            if data.u32(index) == eocdSignature { eocd = index; break }
            index -= 1
        }
        guard eocd >= 0 else { throw ZipError.notAZip }

        let entryCount = Int(data.u16(eocd + 10))
        var offset = Int(data.u32(eocd + 16))

        // Classic IPA ZIPs fit in 32-bit central-directory fields. Reject a
        // Zip64 sentinel explicitly instead of mis-parsing offsets as 4 GiB.
        if entryCount == 0xFFFF || data.u32(eocd + 16) == 0xFFFF_FFFF {
            throw ZipError.archiveTooLarge
        }

        let cdSignature: UInt32 = 0x0201_4b50
        var entries: [Entry] = []
        entries.reserveCapacity(entryCount)

        for _ in 0..<entryCount {
            guard offset >= 0,
                  offset + 46 <= data.count,
                  data.u32(offset) == cdSignature else {
                throw ZipError.truncated
            }

            let method = data.u16(offset + 10)
            let compressedRaw = data.u32(offset + 20)
            let uncompressedRaw = data.u32(offset + 24)
            let localHeaderRaw = data.u32(offset + 42)
            if compressedRaw == 0xFFFF_FFFF
                || uncompressedRaw == 0xFFFF_FFFF
                || localHeaderRaw == 0xFFFF_FFFF {
                throw ZipError.archiveTooLarge
            }

            let compressed = Int(compressedRaw)
            let uncompressed = Int(uncompressedRaw)
            let nameLen = Int(data.u16(offset + 28))
            let extraLen = Int(data.u16(offset + 30))
            let commentLen = Int(data.u16(offset + 32))
            let localHeader = Int(localHeaderRaw)
            let externalAttrs = data.u32(offset + 38)
            let unixMode = UInt16((externalAttrs >> 16) & 0xFFFF)

            let nameStart = offset + 46
            guard nameStart <= data.count,
                  nameLen <= data.count - nameStart,
                  extraLen <= data.count - nameStart - nameLen,
                  commentLen <= data.count - nameStart - nameLen - extraLen else {
                throw ZipError.truncated
            }
            let name = String(decoding: data[nameStart..<nameStart + nameLen], as: UTF8.self)

            entries.append(Entry(
                path: name,
                compressionMethod: method,
                compressedSize: compressed,
                uncompressedSize: uncompressed,
                localHeaderOffset: localHeader,
                isDirectory: name.hasSuffix("/"),
                unixMode: unixMode
            ))
            offset = nameStart + nameLen + extraLen + commentLen
        }
        return entries
    }

    private static func localDataStart(for entry: Entry, in data: Data) throws -> Int {
        let local = entry.localHeaderOffset
        guard local >= 0,
              local + 30 <= data.count,
              data.u32(local) == 0x0403_4b50 else {
            throw ZipError.truncated
        }
        let nameLen = Int(data.u16(local + 26))
        let extraLen = Int(data.u16(local + 28))
        let dataStart = local + 30 + nameLen + extraLen
        guard dataStart >= 0,
              dataStart <= data.count,
              entry.compressedSize >= 0,
              entry.compressedSize <= data.count - dataStart else {
            throw ZipError.truncated
        }
        return dataStart
    }

    // MARK: - Streaming payload extraction

    private static func copyStored(
        _ entry: Entry,
        input: FileHandle,
        output: FileHandle
    ) throws {
        var remaining = entry.compressedSize
        var written = 0

        while remaining > 0 {
            let count = min(ioChunkSize, remaining)
            guard let chunk = try input.read(upToCount: count), !chunk.isEmpty else {
                throw ZipError.truncated
            }
            try output.write(contentsOf: chunk)
            remaining -= chunk.count
            written += chunk.count
        }

        guard written == entry.uncompressedSize else {
            throw ZipError.truncated
        }
    }

    private static func inflateDeflate(
        _ entry: Entry,
        input: FileHandle,
        output: FileHandle
    ) throws {
        let stream = UnsafeMutablePointer<compression_stream>.allocate(capacity: 1)
        guard compression_stream_init(
            stream,
            COMPRESSION_STREAM_DECODE,
            COMPRESSION_ZLIB
        ) != COMPRESSION_STATUS_ERROR else {
            stream.deallocate()
            throw ZipError.inflateFailed
        }
        defer {
            compression_stream_destroy(stream)
            stream.deallocate()
        }

        var remaining = entry.compressedSize
        var totalWritten = 0
        var reachedEnd = false
        var outputBuffer = [UInt8](repeating: 0, count: ioChunkSize)
        let outputCapacity = outputBuffer.count

        while remaining > 0 && !reachedEnd {
            let count = min(ioChunkSize, remaining)
            guard let chunk = try input.read(upToCount: count), !chunk.isEmpty else {
                throw ZipError.truncated
            }
            remaining -= chunk.count
            let flags = remaining == 0
                ? Int32(COMPRESSION_STREAM_FINALIZE.rawValue)
                : Int32(0)

            try chunk.withUnsafeBytes { rawSource in
                let source = rawSource.bindMemory(to: UInt8.self)
                guard let sourceBase = source.baseAddress else { return }
                stream.pointee.src_ptr = sourceBase
                stream.pointee.src_size = source.count

                repeat {
                    let before = stream.pointee.src_size
                    var produced = 0
                    let status = outputBuffer.withUnsafeMutableBytes { rawDestination -> compression_status in
                        let destination = rawDestination.bindMemory(to: UInt8.self)
                        stream.pointee.dst_ptr = destination.baseAddress!
                        stream.pointee.dst_size = outputCapacity
                        let result = compression_stream_process(stream, flags)
                        produced = outputCapacity - stream.pointee.dst_size
                        return result
                    }

                    if produced > 0 {
                        try output.write(contentsOf: Data(outputBuffer.prefix(produced)))
                        totalWritten += produced
                        if totalWritten > entry.uncompressedSize {
                            throw ZipError.inflateFailed
                        }
                    }

                    if status == COMPRESSION_STATUS_END {
                        // A decoder that ends before consuming the entry's declared
                        // compressed bytes indicates a malformed central directory.
                        guard stream.pointee.src_size == 0 else { throw ZipError.inflateFailed }
                        reachedEnd = true
                        break
                    }
                    if status == COMPRESSION_STATUS_ERROR {
                        throw ZipError.inflateFailed
                    }
                    // With FINALIZE set, a zero-length source may need another
                    // call to flush output and return END. Any call that neither
                    // consumes nor produces data cannot make forward progress.
                    if stream.pointee.src_size == before && produced == 0 {
                        throw ZipError.inflateFailed
                    }
                } while stream.pointee.src_size > 0 || flags != 0
            }
        }

        guard reachedEnd,
              remaining == 0,
              totalWritten == entry.uncompressedSize else {
            throw ZipError.inflateFailed
        }
    }
}

// MARK: - Little-endian readers

private extension Data {
    func u16(_ offset: Int) -> UInt16 {
        UInt16(self[offset]) | (UInt16(self[offset + 1]) << 8)
    }

    func u32(_ offset: Int) -> UInt32 {
        UInt32(self[offset]) | (UInt32(self[offset + 1]) << 8)
            | (UInt32(self[offset + 2]) << 16) | (UInt32(self[offset + 3]) << 24)
    }
}
