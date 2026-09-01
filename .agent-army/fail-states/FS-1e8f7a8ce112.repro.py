"""FS-1e8f7a8ce112 — REJECTED. The config filename cannot escape ~/.cura.

Investigated because the preferred name is interpolated straight into a filename.
It is sanitised: re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "person",
which flattens dots and slashes, so "../../../etc/passwd" lands at
~/.cura/etc-passwd.json. Kept so the next audit does not re-run it.
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

HOSTILE = ["../../../etc/passwd", "..", "/", "~/.ssh/authorized_keys", "😀 Peggy", "O'Brien"]


def _safe(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "person"


def test_config_filename_stays_inside_the_cura_directory():
    base = pathlib.Path("/home/nobody/.cura").resolve()
    for name in HOSTILE:
        out = (base / f"{_safe(name)}.json").resolve()
        assert out.parent == base, f"{name!r} escaped to {out}"
        assert out.name.endswith(".json")
