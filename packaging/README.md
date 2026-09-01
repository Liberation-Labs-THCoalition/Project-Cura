# Shipping Cura as something you double-click

The person installing Cura is often in his seventies, caring for a spouse with
dementia, with failing eyesight and ten free minutes at a time. He already tried
and abandoned two installs. Both times the wall was the same: a terminal.

So the target is one file, downloaded, double-clicked, and a window opens. No
Python first. macOS has shipped no usable system Python since 12.3 removed
`/usr/bin/python`, and Apple ships no Python 3 runtime at all, so "he already
has Python" is false on every Mac.

## Build

```
python packaging/build_desktop.py
```

That is the whole interface. It refuses to build with a Python that cannot
import `tkinter`, runs the finished artifact against `--selftest` before calling
it done, and prints a SHA-256.

PyInstaller **cannot cross-compile**. Its documentation is explicit: "If you
need to distribute your application for more than one OS, for example both
Windows and macOS, you must install PyInstaller on each platform and bundle your
app separately on each." Mac artifacts come from a Mac, Windows from Windows.
`.github/workflows/desktop.yml` does that on GitHub-hosted runners.

| Platform | Output | Shape |
|---|---|---|
| macOS | `Cura-Setup-macOS-<ver>.zip` containing `Cura Setup.app` | onedir + BUNDLE, universal2 |
| Windows | `Cura-Setup-Windows-<ver>.exe` | onefile |
| Linux | `cura-setup-linux-<ver>.tar.gz` | onedir; used to verify the spec |

macOS ships zipped because a `.app` *is* a folder. Windows ships as one `.exe`
because a folder of 200 files with the real one buried in it is a terminal by
another name.

## The part that decides whether any of this works

**An unsigned build does not reach him.** This is not a polish item.

### macOS

A downloaded app carries `com.apple.quarantine`. On first launch Gatekeeper
shows:

> Apple could not verify "Cura Setup" is free of malware that may harm your Mac
> or compromise your privacy.

The only two buttons are **Move to Trash** and **Done**. There is no "Open".

To run it anyway he must quit the dialog, open System Settings, go to Privacy &
Security, scroll to the bottom, find a Security section, click **Open Anyway**,
authenticate, return to the app, launch it again, and click **Open Anyway** in a
second dialog. Seven steps, in a settings pane he has no reason to have seen.

The old Control-click → Open shortcut **no longer works**: Apple removed the
Gatekeeper contextual-menu override in macOS 15 Sequoia.

Assume he will click Move to Trash. It is the sensible thing to do when a
computer tells a man caring for his dying wife that software might harm him.

**This is a blocker, not a footnote.**

The fix is a Developer ID signature *and* notarization. Signing alone is not
enough — Gatekeeper looks for a notarization ticket, and a signed-but-unnotarized
app shows the same dialog. Notarization requires Apple Developer Program
membership: **$99/year**.

Note on the fee waiver: Apple offers a membership fee waiver to nonprofits,
accredited educational institutions and government entities, but its stated
scope is free apps on the App Store, and it is not documented as covering
Developer ID distribution outside the App Store. Do not plan around it. Verify
with Apple before relying on it; budget the $99 either way.

Ad-hoc signing (what PyInstaller does when `CURA_CODESIGN_IDENTITY` is unset) is
required for the app to run *at all* on Apple Silicon, but it does nothing for
Gatekeeper.

### Windows

An unsigned `.exe` downloaded from the internet carries the Mark of the Web and
Microsoft Defender SmartScreen shows:

> Windows protected your PC
> Microsoft Defender SmartScreen prevented an unrecognized app from starting.
> Running this app might put your PC at risk.

He must click **More info** — an unemphasised text link, not a button — and then
**Run anyway**. Two steps, and the escape hatch is visible.

Milder than macOS, but still a scam-shaped screen shown to a man whose wife's
companion app is *specifically* built to defend against scams.

SmartScreen is reputation-based. Microsoft's documentation: "If a URL, a file,
an app, or a certificate has an established reputation, users don't see any
warnings. If there's no reputation, the item is marked as a higher risk and
presents a warning to the user."

The cheap route is **Azure Artifact Signing** (formerly Trusted Signing):
Basic is about **$9.99/month** for 5,000 signatures. As of April 2026 the
three-year business-history requirement was dropped and self-employed
individuals can apply, but it remains limited to verified US, Canadian, EU and
UK businesses and individuals. Reputation attaches to the validated identity
rather than to an individual certificate, so a new certificate does not restart
the reputation clock.

Traditional OV code-signing certificates are $200–$600/year and, since the
CA/Browser Forum moved private keys onto FIPS-certified hardware, also require a
token or HSM. For this project that is the worse deal.

### Cost, plainly

| | Per year |
|---|---|
| Apple Developer Program (macOS signing + notarization) | $99 |
| Azure Artifact Signing Basic (Windows) | ~$120 |
| **Both** | **~$219** |

There is no free path that removes both warnings. Distributing through the Mac
App Store still requires the same $99 membership. Homebrew, winget and similar
help technically-comfortable users and do not help this man, because they are
terminals.

**Recommendation: pay for both.** ~$219/year against a project whose entire
premise is reaching people who cannot get past a terminal. Signing is not
overhead here; it is the last mile of the product. Start with macOS if only one
can be funded — its warning is the one with no way through.

## Signing setup

### macOS

Repository secrets:

| Secret | What it is |
|---|---|
| `MACOS_CERT_P12` | base64 of a "Developer ID Application" `.p12` |
| `MACOS_CERT_PASSWORD` | the `.p12` export password |
| `MACOS_SIGN_IDENTITY` | `Developer ID Application: NAME (TEAMID)` |
| `MACOS_NOTARY_APPLE_ID` | Apple ID for notarytool |
| `MACOS_NOTARY_PASSWORD` | app-specific password, not the account password |
| `MACOS_TEAM_ID` | 10-character team ID |

The workflow signs during the PyInstaller build, notarizes the zip, staples the
ticket into the `.app` so the check works offline, re-zips, and then asks
Gatekeeper directly with `spctl --assess`. That last step is the real test: it
is the same question his Mac asks.

Entitlements live in `entitlements.plist`. All three are required because the
hardened runtime otherwise kills a frozen Python app at launch with no message.

### Windows

Repository secrets: `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`,
`AZURE_SIGNING_ENDPOINT`, `AZURE_SIGNING_ACCOUNT`, `AZURE_CERT_PROFILE`.

Both are optional. With no secrets set, the build still succeeds and both jobs
emit a loud warning describing exactly what an unsigned download will show.

## Why PyInstaller

| | Verdict |
|---|---|
| **PyInstaller 6.22.2** (2026-08-17) | Chosen. "Development Status :: 6 - Mature", supports Python 3.8–3.15, both targets from one spec, `codesign_identity` / `entitlements_file` / `target_arch=universal2` built in, Tcl/Tk 9 support since 6.22.0. |
| **Briefcase 0.4.4** (2026-07-08) | Real alternative, and its native installer output (`.msi`, `.dmg`) is arguably friendlier. But it is "Development Status :: 4 - Beta", and it wants its own project layout and `pyproject.toml` section — a migration, not a build script. Revisit when a proper installer is wanted. |
| **py2app 0.28.10** (2026-02-13) | macOS only. Would still leave Windows unsolved and mean maintaining two toolchains for one small app. |

## Known gaps

- Neither artifact has an icon. A generic icon on a downloaded app reads as
  untrustworthy to exactly the person we are worried about. Needs `.icns` and
  `.ico`, which need a designed mark.
- This app does setup and rehearsal. Nothing here yet keeps `cura run` alive
  across a reboot — that wants a LaunchAgent on macOS and a Scheduled Task on
  Windows, and it is a separate piece of work.
- The Linux `.tar.gz` is a verification artifact, not a supported download.
