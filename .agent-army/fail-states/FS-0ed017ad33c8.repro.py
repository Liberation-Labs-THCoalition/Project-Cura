"""FS-0ed017ad33c8 — the companion memory file is written world-readable.

MemoryStore.save() is a bare path.write_text(): no chmod on the file, no chmod
on ~/.cura/memory. Both take the process umask, so 0644 / 0755 on a normal
desktop.

What is in that file (cura/memory/companion_memory.py dataclasses): mood_history,
observations tagged "health", the names and relationships of everyone she talks
about, upcoming events. For this household that is a running record of a dementia
decline -- the pantry, the confusion, the bad nights -- sitting in the home
directory at 0644.

CLAUDE.md for this project commits to "HIPAA-grade privacy", "No cloud, no
database, no third-party storage", and "Health data never shared with insurance
companies". The file's own docstring says "Belongs to the family." A world-readable
file in a directory that every backup tool sweeps does not belong to the family.

RED = a saved memory file is readable by group or other.
"""
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from cura.memory.companion_memory import CompanionMemory, MemoryStore


def test_saved_memory_is_not_readable_by_other_accounts():
    with tempfile.TemporaryDirectory() as td:
        data_dir = pathlib.Path(td) / "memory"
        memory = CompanionMemory(elder_name="Margaret Chen")
        path = MemoryStore(data_dir=str(data_dir)).save(memory)

        mode = path.stat().st_mode & 0o777
        assert not (mode & 0o077), (
            f"{path.name} is {oct(mode)}. It holds mood history and health "
            "observations for a person with late-stage dementia, and any other "
            "account on the machine can read it."
        )


def test_memory_directory_is_not_world_traversable():
    with tempfile.TemporaryDirectory() as td:
        data_dir = pathlib.Path(td) / "memory"
        MemoryStore(data_dir=str(data_dir)).save(
            CompanionMemory(elder_name="Margaret Chen"))
        mode = data_dir.stat().st_mode & 0o777
        assert not (mode & 0o077), (
            f"the memory directory is {oct(mode)}; it should be 0700."
        )
