"""FS-377864fb7cfe — the memory filename is the elder's name, unsanitised.

    safe_name = memory.elder_name.lower().replace(" ", "_")
    path = self._dir / f"{safe_name}.json"

`safe_name` is not safe. It strips nothing but spaces, so a separator or a "not"
component in the name walks straight out of the memory directory. Observed:
elder_name "../ESCAPED" wrote to <dir>/../escaped.json, one level above the
store's own directory.

The wizard's config filename does this correctly two files away --

    safe = re.sub(r"[^a-z0-9]+", "-", state["preferred_name"].lower()).strip("-")

-- and a previous audit checked that one and cleared it (FS-1e8f7a8ce112). The
memory store never got the same treatment.

Reachability: elder_name comes from the config the wizard writes and from
`--elder-name` on cura_mcp_server.py and `cura webhook`, so today it is
caregiver-typed rather than attacker-supplied, which is why this is not rated
higher. What it costs the household is still real: a name typed with a slash --
"Margaret Chen / Mom", the kind of label a caregiver actually types -- silently
splits the memory into a path that load() will not find again. Cura then has no
history for her, greets her like a stranger every morning, and nothing reports
that anything was lost.

RED = a name containing a separator writes outside the memory directory.
"""
import pathlib
import sys
import tempfile

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from cura.memory.companion_memory import CompanionMemory, MemoryStore

NAMES = ["../ESCAPED", "../../ESCAPED", "Margaret Chen/Mom"]


@pytest.mark.parametrize("elder_name", NAMES)
def test_memory_file_stays_inside_the_memory_directory(elder_name):
    with tempfile.TemporaryDirectory() as td:
        data_dir = (pathlib.Path(td) / "memory").resolve()
        store = MemoryStore(data_dir=str(data_dir))
        try:
            path = store.save(CompanionMemory(elder_name=elder_name)).resolve()
        except OSError:
            return                      # refused outright: acceptable
        assert str(path).startswith(str(data_dir) + "/"), (
            f"elder_name {elder_name!r} wrote to {path}, outside {data_dir}. "
            "MemoryStore.save() sanitises spaces and nothing else."
        )


@pytest.mark.parametrize("elder_name", NAMES)
def test_what_was_saved_can_be_loaded_back(elder_name):
    with tempfile.TemporaryDirectory() as td:
        data_dir = (pathlib.Path(td) / "memory").resolve()
        store = MemoryStore(data_dir=str(data_dir))
        memory = CompanionMemory(elder_name=elder_name)
        memory.conversation_count = 47
        try:
            store.save(memory)
        except OSError:
            return
        assert store.load(elder_name).conversation_count == 47, (
            f"memory saved for {elder_name!r} does not come back on load; "
            "every morning Cura meets her as a stranger and nothing says so."
        )
