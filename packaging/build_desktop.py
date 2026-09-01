#!/usr/bin/env python3
"""Build the double-clickable Cura Setup app for whichever OS this is.

    python packaging/build_desktop.py

Runs the same way on a laptop and in CI, because a build you can only reproduce
in CI is a build nobody can debug. It refuses to produce a broken artifact: a
setup app that opens no window is worse than no download at all, so the tkinter
check below is a hard failure, not a warning.

PyInstaller cannot cross-compile, so this builds for the machine it runs on.
Mac artifacts come from a Mac runner, Windows artifacts from a Windows runner.

Environment variables (all optional):
    CURA_VERSION            version string        (default 0.1.0)
    CURA_TARGET_ARCH        macOS: universal2 | arm64 | x86_64
    CURA_CODESIGN_IDENTITY  macOS: "Developer ID Application: NAME (TEAMID)"
"""
from __future__ import annotations

import hashlib
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "packaging" / "cura.spec"
DIST = ROOT / "dist"
BUILD = ROOT / "build"
VERSION = os.environ.get("CURA_VERSION", "0.1.0")

IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"


def say(msg: str = "") -> None:
    print(msg, flush=True)


def die(problem: str, next_step: str) -> None:
    say("")
    say("  BUILD STOPPED")
    say("")
    for line in problem.splitlines():
        say("  " + line)
    say("")
    say("  Do this next:")
    for line in next_step.splitlines():
        say("      " + line)
    say("")
    sys.exit(1)


def preflight() -> None:
    say(f"  Building Cura Setup {VERSION} on {platform.system()} "
        f"{platform.machine()}, Python {platform.python_version()}")

    if sys.version_info < (3, 10):
        die(f"This Python is {platform.python_version()}. Cura needs 3.10 or newer.",
            "Build with a newer Python.")

    # The whole point of this artifact is that it opens a window. If Tcl/Tk is
    # missing from the build Python, PyInstaller cheerfully produces an app that
    # starts and immediately dies on his machine. Fail here instead.
    try:
        import tkinter
        say(f"  Tcl/Tk present: {tkinter.TkVersion}")
    except Exception as exc:
        die(
            "This Python cannot import tkinter, so the app it builds would have\n"
            f"no window to open. ({exc.__class__.__name__}: {exc})",
            "macOS:   install Python from python.org -- those installers ship\n"
            "         their own Tcl/Tk 8.6. Homebrew python needs python-tk.\n"
            "Windows: re-run the python.org installer and tick 'tcl/tk and IDLE'.\n"
            "Linux:   sudo apt install python3-tk",
        )

    try:
        import PyInstaller
        say(f"  PyInstaller {PyInstaller.__version__}")
    except ImportError:
        die("PyInstaller is not installed in this Python.",
            f"{sys.executable} -m pip install pyinstaller")

    if IS_MAC:
        want = os.environ.get("CURA_TARGET_ARCH")
        if want == "universal2":
            # A single-arch Python cannot produce a universal2 binary; asking it
            # to produces a confusing failure deep inside PyInstaller.
            out = subprocess.run(["file", "-b", sys.executable],
                                 capture_output=True, text=True).stdout
            if "universal" not in out.lower():
                die("CURA_TARGET_ARCH=universal2 but this Python is not a "
                    f"universal2 build.\n  file says: {out.strip()}",
                    "Install the macOS 'universal2' installer from python.org,\n"
                    "or unset CURA_TARGET_ARCH to build for this machine only.")
        if not os.environ.get("CURA_CODESIGN_IDENTITY"):
            say("  No CURA_CODESIGN_IDENTITY: PyInstaller will ad-hoc sign.")
            say("  Ad-hoc signed apps RUN on Apple Silicon but are still")
            say("  blocked by Gatekeeper when downloaded. See packaging/README.md.")


def clean() -> None:
    for d in (BUILD, DIST):
        if d.exists():
            shutil.rmtree(d)
    say("  Cleaned build/ and dist/")


def run_pyinstaller() -> None:
    cmd = [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm",
           "--distpath", str(DIST), "--workpath", str(BUILD),
           str(SPEC)]
    say(f"  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        die(f"PyInstaller exited {result.returncode}.",
            "Read the output above. The warning file under build/ lists every\n"
            "module PyInstaller could not find.")


def built_binary() -> Path:
    """The executable to run for the selftest."""
    if IS_MAC:
        return DIST / "Cura Setup.app" / "Contents" / "MacOS" / "Cura Setup"
    if IS_WIN:
        return DIST / "Cura-Setup.exe"
    return DIST / "cura-setup" / "cura-setup"


def selftest() -> None:
    """Run the artifact itself. A build that has never been executed is a guess."""
    exe = built_binary()
    if not exe.exists():
        die(f"PyInstaller reported success but {exe} does not exist.",
            "Check the dist/ directory and the spec's output names.")
    say(f"  Running selftest: {exe}")
    result = subprocess.run([str(exe), "--selftest"],
                            capture_output=True, text=True, timeout=180)
    say("  " + "\n  ".join((result.stdout or "").strip().splitlines()))
    if result.returncode != 0 or "SELFTEST OK" not in (result.stdout or ""):
        say("  " + "\n  ".join((result.stderr or "").strip().splitlines()))
        die(f"The built app failed its own selftest (exit {result.returncode}).",
            "Something is missing from the bundle. The selftest output above\n"
            "names the import that failed; add it to hiddenimports in cura.spec.")
    say("  Selftest passed.")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def package() -> Path:
    """Produce the one file he downloads."""
    if IS_MAC:
        app = DIST / "Cura Setup.app"
        out = DIST / f"Cura-Setup-macOS-{VERSION}.zip"
        # ditto, not zip: it preserves symlinks, resource forks and extended
        # attributes inside the bundle. A bundle zipped with plain `zip` can
        # arrive with a broken signature and macOS then calls it "damaged".
        subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent",
                        str(app), str(out)], check=True)
        return out
    if IS_WIN:
        exe = DIST / "Cura-Setup.exe"
        out = DIST / f"Cura-Setup-Windows-{VERSION}.exe"
        shutil.move(str(exe), str(out))
        return out
    folder = DIST / "cura-setup"
    out = DIST / f"cura-setup-linux-{VERSION}.tar.gz"
    subprocess.run(["tar", "-czf", str(out), "-C", str(DIST), folder.name],
                   check=True)
    return out


def main() -> int:
    say("")
    preflight()
    clean()
    run_pyinstaller()
    selftest()
    artifact = package()
    size_mb = artifact.stat().st_size / (1024 * 1024)
    say("")
    say("  BUILD OK")
    say(f"  {artifact}")
    say(f"  {size_mb:.1f} MB")
    say(f"  sha256 {sha256(artifact)}")
    say("")
    if IS_MAC and not os.environ.get("CURA_CODESIGN_IDENTITY"):
        say("  NOT SIGNED. If this is downloaded from a browser, macOS will")
        say("  refuse it with 'Apple could not verify ... is free of malware'")
        say("  and offer only 'Move to Trash' and 'Done'. Do not ship this to")
        say("  an end user. See packaging/README.md.")
        say("")
    if IS_WIN:
        say("  NOT SIGNED. SmartScreen will show 'Windows protected your PC'")
        say("  on a downloaded copy. See packaging/README.md.")
        say("")
    return 0


if __name__ == "__main__":
    sys.exit(main())
