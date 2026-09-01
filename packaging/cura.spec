# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the double-clickable Cura Setup app.

Build with:   pyinstaller --clean --noconfirm packaging/cura.spec
or better:    python packaging/build_desktop.py

PyInstaller cannot cross-compile. Per its own docs: "If you need to distribute
your application for more than one OS ... you must install PyInstaller on each
platform and bundle your app separately on each." So this one spec is driven by
three different runners, and every platform branch below is reached on exactly
one of them.

Shape of the output, and why:

  macOS   one .app bundle (onedir + BUNDLE). A .app IS a folder, so it cannot
          be onefile in any useful sense, and stapled notarization tickets
          attach to bundles, not to self-extracting stubs. Ships zipped.
  Windows one .exe (onefile). He downloads one file and double-clicks it. A
          onedir zip would make him unpack a folder and find the right file
          among two hundred -- that is a terminal by another name.
  Linux    onedir, used here only to prove this spec is valid.

Environment variables, all optional:

  CURA_VERSION            version string baked into the bundle (default 0.1.0)
  CURA_TARGET_ARCH        macOS only: x86_64 | arm64 | universal2
  CURA_CODESIGN_IDENTITY  macOS only: Developer ID Application: ... (see README)
"""
import os
import sys
from pathlib import Path

# SPECPATH is injected by PyInstaller and points at this file's directory.
ROOT = Path(SPECPATH).parent            # noqa: F821  (repo root)

VERSION = os.environ.get("CURA_VERSION", "0.1.0")
TARGET_ARCH = os.environ.get("CURA_TARGET_ARCH") or None
CODESIGN_IDENTITY = os.environ.get("CURA_CODESIGN_IDENTITY") or None
ENTITLEMENTS = str(ROOT / "packaging" / "entitlements.plist")

IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"

# Ad-hoc-signed-only builds get no entitlements file: entitlements are only
# meaningful under a real signing identity with the hardened runtime.
entitlements_file = ENTITLEMENTS if (IS_MAC and CODESIGN_IDENTITY) else None

# Windows resource block. Without it the SmartScreen "More info" panel shows a
# bare filename; with it, at least the app names itself. It does not remove the
# warning -- only a signature does that. See packaging/README.md.
version_file = None
if IS_WIN:
    candidate = ROOT / "packaging" / "windows_version_info.txt"
    if candidate.exists():
        version_file = str(candidate)

def _loose_tcltk_libs():
    """Linux fallback: hand PyInstaller the Tcl/Tk shared objects by hand.

    On macOS and Windows the Tcl/Tk libraries live where PyInstaller's own hooks
    already look -- a framework inside the Python framework, or DLLs/ next to
    python.exe -- and this returns nothing.

    On Linux, some CPython distributions (python-build-standalone, which is what
    uv and the astral toolchain install) put libtcl9.0.so in <prefix>/lib and
    rely on an RPATH that PyInstaller's dependency scan cannot follow. It then
    warns "Library not found: could not resolve libtcl9.0.so" and builds an app
    that fails on `import tkinter`. That warning is easy to scroll past, which is
    why build_desktop.py runs the artifact afterwards rather than trusting it.
    """
    import glob
    if sys.platform not in ("linux", "linux2"):
        return []
    found = []
    for base in {sys.base_prefix, sys.prefix}:
        for pattern in ("libtcl*.so*", "libtk*.so*"):
            for hit in glob.glob(os.path.join(base, "lib", pattern)):
                if os.path.isfile(hit):
                    found.append((hit, "."))
    return sorted(set(found))


a = Analysis(
    [str(ROOT / "packaging" / "cura_setup_app.py")],
    pathex=[str(ROOT)],
    binaries=_loose_tcltk_libs(),
    datas=[],
    # gui.py imports tkinter inside run() so the window code never runs on a
    # machine without it. PyInstaller does follow function-level imports, but
    # naming them here means a missing Tcl/Tk is a loud build warning rather
    # than a quiet runtime failure on his Mac.
    hiddenimports=[
        "tkinter",
        "tkinter.font",
        "cura.setup.gui",
        "cura.setup.preview",
        "cura.setup.wizard",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Conservative on purpose: excluding something that turns out to be needed
    # fails in his kitchen, not here. Only dev/test and known-absent libraries.
    excludes=[
        "pytest", "_pytest", "pytest_asyncio",
        "numpy", "matplotlib", "scipy", "pandas",
        "IPython", "notebook",
        "PIL",
        "test", "tkinter.test", "unittest.test",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)                       # noqa: F821

if IS_WIN:
    # One file. One double-click.
    exe = EXE(                          # noqa: F821
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name="Cura-Setup",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,                      # UPX-packed binaries trip antivirus
        runtime_tmpdir=None,
        console=False,                  # no console window, ever
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=None,
        version=version_file,
    )
else:
    exe = EXE(                          # noqa: F821
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="Cura Setup" if IS_MAC else "cura-setup",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        # argv_emulation turns a double-clicked Finder open into argv. This app
        # takes no arguments and enabling it costs a visible startup delay on
        # first launch, so it stays off.
        argv_emulation=False,
        target_arch=TARGET_ARCH,
        codesign_identity=CODESIGN_IDENTITY,
        entitlements_file=entitlements_file,
        icon=None,
    )

    coll = COLLECT(                     # noqa: F821
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name="Cura Setup" if IS_MAC else "cura-setup",
    )

    if IS_MAC:
        app = BUNDLE(                   # noqa: F821
            coll,
            name="Cura Setup.app",
            icon=None,
            bundle_identifier="org.liberationlabs.cura.setup",
            version=VERSION,
            info_plist={
                "CFBundleName": "Cura Setup",
                "CFBundleDisplayName": "Cura Setup",
                "CFBundleShortVersionString": VERSION,
                "CFBundleVersion": VERSION,
                "NSHighResolutionCapable": True,
                # Sequoia and later. Older systems are a separate build target
                # and an untested one -- do not imply support we have not run.
                "LSMinimumSystemVersion": "12.0",
                "LSApplicationCategoryType": "public.app-category.healthcare-fitness",
                "NSHumanReadableCopyright":
                    "Cura. Hippocratic License 3.0 with AI Welfare module.",
                # No microphone, camera or contacts usage strings: this app asks
                # questions and writes a file. If a future build touches any of
                # those, the matching NSxxxUsageDescription must be added here
                # or macOS kills the process with no message he can read.
            },
        )
