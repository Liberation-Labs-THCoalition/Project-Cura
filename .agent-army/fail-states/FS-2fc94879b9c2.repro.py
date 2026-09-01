"""FS-2fc94879b9c2 — edits made in the reopened setup window never reach the config.

STATIC CASE. tkinter is not installed here and there is no display, so gui.run()
could not be driven and the behaviour itself was NOT observed; the record is
marked unverified for that reason. What is checked below is the shape that
causes it, read from the source: gui.py touches OUT_DIR -- the elder's config,
the file Cura dials from -- only inside finish(), which runs only from the last
question's "Finish" button. go_next() and on_close() persist to
~/.cura/setup-progress.json alone, and a completed setup reopens at question 1
as a review rather than at "Finish". So a caregiver who opens the window to
correct the phone number, types it, and closes the window sees the new number
stored and redisplayed on the next open, while Cura goes on dialling the old one
indefinitely with nothing to indicate the divergence.
"""
import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
GUI = ROOT / "cura" / "setup" / "gui.py"


def _innermost_functions_touching(tree, target="OUT_DIR"):
    """Nearest enclosing function name for every reference to `target`."""
    owners = set()

    def walk(node, enclosing):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                walk(child, child.name)
            else:
                if isinstance(child, ast.Name) and child.id == target and enclosing:
                    owners.add(enclosing)
                walk(child, enclosing)

    walk(tree, None)
    return owners


def test_answers_reach_the_config_without_reaching_the_last_screen():
    assert GUI.exists(), f"{GUI} is missing; the window wizard cannot be checked"
    owners = _innermost_functions_touching(ast.parse(GUI.read_text()))
    assert owners - {"finish"}, (
        "cura/setup/gui.py writes the elder's config only from finish(); an answer "
        "changed in a reopened window and then closed is saved to the progress file "
        f"but never to the config Cura dials from (config writers: {sorted(owners)})"
    )
