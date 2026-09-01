"""FS-953f7ebba5ab — REJECTED. An interruption cannot tear the progress file.

Investigated because the wizard's whole promise is that an interruption loses
nothing. wizard.save() writes to a sibling .tmp and os.replace()s it, which is
atomic on the same filesystem, so a kill mid-write leaves the previous complete
file rather than a truncated one. load() also swallows a decode error and returns
{} rather than raising -- which is its own smaller problem (it silently restarts
the interview) but is not data loss of the config. Kept so the next audit does
not re-run it.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def test_progress_file_is_replaced_atomically(tmp_path, monkeypatch):
    from cura.setup import wizard
    state_path = tmp_path / ".cura" / "setup-progress.json"
    monkeypatch.setattr(wizard, "STATE", state_path)

    wizard.save({"name": "Margaret Chen"})
    first = state_path.read_text()

    wizard.save({"name": "Margaret Chen", "phone": "307-555-0101"})
    assert json.loads(state_path.read_text())["phone"] == "307-555-0101"
    assert first != state_path.read_text()
    assert not list(state_path.parent.glob("*.tmp")), "a temp file was left behind"
