# macOS: “damaged”, “broken”, or cannot be opened

These messages do not all mean the same thing. Send the exact message, macOS
version (Apple menu → About This Mac), and whether the Mac says Intel or Apple
chip when reporting a problem. Do not send account credentials.

## Packaging defect addressed in source

The previous build changed `Info.plist` and copied icons **after** PyInstaller
sealed the app. Those changes could invalidate its code signature. The corrected
build now signs the final bundle, strictly verifies it, and checks the signature,
executable permissions and architecture of the app inside the actual DMG. It
refuses to package if these checks fail. This source change does not repair a
previously downloaded v1.1.0 installer; a new verified build is required.

## Integrity is not Apple approval

Without a configured Apple Developer ID the build uses an **ad-hoc signature**.
That protects bundle integrity but does not establish a trusted developer or
satisfy Gatekeeper/notarization. Do not interpret a passing CI signature check as
Apple approval or proof that a downloaded app will open without warnings.

For trusted distribution the maintainer must configure a Developer ID signing
identity and a `notarytool` keychain profile on the macOS build machine. The
packager accepts `CLIPOS_CODESIGN_IDENTITY` and `CLIPOS_NOTARY_PROFILE`. It submits
a ZIP, requires Apple's Accepted result, then staples and validates the app's
ticket before creating the DMG. Manage credentials through secure CI/keychain
configuration, never in chat or source control.

## Safe checks on an existing installation

Only download from the official repository's Releases page. Use the **Intel**
DMG on an Intel Mac. Drag CLIPOS into Applications before opening it. Back up
projects before replacing an existing installation; do not delete the CLIPOS
Application Support data directory.

These Terminal commands are read-only diagnostics:

```sh
sw_vers
uname -m
codesign --verify --deep --strict --verbose=2 /Applications/CLIPOS.app
spctl --assess --type execute --verbose=4 /Applications/CLIPOS.app
lipo -archs /Applications/CLIPOS.app/Contents/MacOS/CLIPOS
```

- `a sealed resource is missing or invalid`: the installed bundle was modified,
  incorrectly packaged, or corrupted. Do not force it open.
- `rejected` / no usable signature: the app has not passed Gatekeeper; valid
  ad-hoc signing alone is insufficient. A trusted/notarized release is needed.
- “not supported on this Mac”: check both CPU architecture and macOS requirements.
- A failure while mounting the DMG is distinct from an app-launch error; include
  the installer filename and exact Finder/DiskImageMounter message in the report.

Do not disable Gatekeeper globally or remove quarantine attributes as a substitute
for correcting signing, notarization or compatibility problems.
