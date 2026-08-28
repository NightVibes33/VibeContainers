#!/bin/bash
set -euo pipefail

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/vibe-zip-smoke.XXXXXX")
trap 'rm -rf "$TMP"' EXIT

python3 - "$TMP/input.ipa" "$TMP/malicious.ipa" <<'PY'
import sys
import zipfile

normal, malicious = sys.argv[1:]

with zipfile.ZipFile(normal, "w") as archive:
    info = zipfile.ZipInfo("Payload/Test.app/Info.plist")
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (0o100644 << 16)
    archive.writestr(info, b"plist-data-" + (b"A" * 700000))

    executable = zipfile.ZipInfo("Payload/Test.app/Test")
    executable.compress_type = zipfile.ZIP_DEFLATED
    executable.external_attr = (0o100755 << 16)
    archive.writestr(executable, (b"guest-binary-" * 90000) + b"END")

    stored = zipfile.ZipInfo("Payload/Test.app/stored.bin")
    stored.compress_type = zipfile.ZIP_STORED
    stored.external_attr = (0o100644 << 16)
    archive.writestr(stored, bytes(range(256)) * 4096)

with zipfile.ZipFile(malicious, "w") as archive:
    archive.writestr("../escaped.txt", b"must-not-write")
    archive.writestr("Payload/Test.app/Info.plist", b"ok")
PY

cat > "$TMP/main.swift" <<'SWIFT'
import Foundation

private func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data(("zip smoke test: " + message + "\n").utf8))
    exit(1)
}

let arguments = CommandLine.arguments
if arguments.count != 5 { fail("bad arguments") }

let normal = URL(fileURLWithPath: arguments[1])
let malicious = URL(fileURLWithPath: arguments[2])
let output = URL(fileURLWithPath: arguments[3], isDirectory: true)
let maliciousOutput = URL(fileURLWithPath: arguments[4], isDirectory: true)

let modes = try ZipArchive.extract(normal, to: output)

let plist = output.appendingPathComponent("Payload/Test.app/Info.plist")
let executable = output.appendingPathComponent("Payload/Test.app/Test")
let stored = output.appendingPathComponent("Payload/Test.app/stored.bin")

guard let plistData = try? Data(contentsOf: plist),
      plistData == Data("plist-data-".utf8) + Data(repeating: 65, count: 700000) else {
    fail("deflated plist bytes mismatch")
}

var expectedExecutable = Data()
for _ in 0..<90000 { expectedExecutable.append(Data("guest-binary-".utf8)) }
expectedExecutable.append(Data("END".utf8))
guard let executableData = try? Data(contentsOf: executable),
      executableData == expectedExecutable else {
    fail("multi-chunk deflated executable bytes mismatch")
}

guard let storedData = try? Data(contentsOf: stored),
      storedData.count == 256 * 4096,
      storedData.prefix(256) == Data((0...255).map(UInt8.init)) else {
    fail("stored entry bytes mismatch")
}

guard let executableMode = modes["Payload/Test.app/Test"],
      executableMode & 0o111 != 0 else {
    fail("executable mode was not preserved")
}

let escaped = maliciousOutput.deletingLastPathComponent().appendingPathComponent("escaped.txt")
try? FileManager.default.removeItem(at: escaped)
do {
    _ = try ZipArchive.extract(malicious, to: maliciousOutput)
    fail("unsafe path was accepted")
} catch ZipArchive.ZipError.unsafePath {
    // expected
}
guard !FileManager.default.fileExists(atPath: escaped.path) else {
    fail("unsafe path escaped extraction root")
}

print("ZIP extraction smoke test passed")
SWIFT

mkdir -p "$TMP/output" "$TMP/malicious-output"
xcrun swiftc \
    "$ROOT/iOSSim/Model/ZipArchive.swift" \
    "$TMP/main.swift" \
    -o "$TMP/zip-smoke"

"$TMP/zip-smoke" \
    "$TMP/input.ipa" \
    "$TMP/malicious.ipa" \
    "$TMP/output" \
    "$TMP/malicious-output"
