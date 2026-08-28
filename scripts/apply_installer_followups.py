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

# Validate the exact structural relationships instead of ambiguous substring
# markers that can match another struct or code path.
package_text = package.read_text()
guest_text = guest.read_text()
required = [
    "struct PendingUpdate: Identifiable, Sendable {\n        let installed: InstalledApp\n        let app: AltApp\n        let sourceName: String\n        let sourceID: UUID",
    "let (catalog, effectiveURL) = try await Self.fetch(url)\n            let source = Source(url: normalised, name: catalog.name)",
    "effectiveSourceURLs[source.id] = effectiveURL",
    "options: []",
    "to: transactionRoot.appendingPathComponent(Self.activeTransactionMarker)",
]
combined = package_text + "\n" + guest_text
missing = [item for item in required if item not in combined]
if missing:
    raise SystemExit("follow-up validation failed: " + " | ".join(missing))
