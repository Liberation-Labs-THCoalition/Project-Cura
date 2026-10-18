"""Does the health handler tell the companion app what Cura is NOT handling?

Phase 2 of rollout spec C3 (2026-10-16, Cura) adds a "gaps" field to the
status dict _handle_health returns. The gaps come from a new helper,
cura.readiness.gaps_for_health(config_path), which:

  * returns readiness_gaps(config_path) when a config path is given,
  * returns ["no elder config loaded"] when the path is empty,
  * returns a single line "the readiness check failed (...)" if anything
    raises, and never lets an exception escape.

The MCP package is not installed in the test environment, so cura_mcp_server
cannot be imported. We test the helper directly, and we test the server by
parsing its source with the ast module.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.test_production_seam import _wizard_config


# -- 1. No config path at all ---------------------------------------------

def test_health_gaps_with_no_config():
    """An empty config path means there is no elder to report gaps for."""
    from cura.readiness import gaps_for_health
    assert gaps_for_health("") == ["no elder config loaded"]


# -- 2. A real config: gaps match readiness_gaps --------------------------

def test_health_gaps_match_readiness(tmp_path):
    """For a config the wizard writes, gaps_for_health must return exactly
    what readiness_gaps returns, and that must include the line telling the
    caregiver there is no monitoring service or dispatch line on file."""
    from cura.readiness import gaps_for_health, readiness_gaps
    path = _wizard_config(tmp_path, dispatch=False)
    gaps = gaps_for_health(str(path))
    assert gaps == readiness_gaps(str(path))
    assert any(
        "no monitoring service or dispatch line on file" in line
        for line in gaps
    ), "the caregiver is never told what Cura is not handling"


# -- 3. The helper never raises ------------------------------------------

def test_health_gaps_never_raise(tmp_path, monkeypatch):
    """If readiness_gaps blows up, gaps_for_health must swallow it and return
    a single line saying the readiness check failed, not an exception."""
    import cura.readiness as readiness
    monkeypatch.setattr(
        readiness, "readiness_gaps",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    path = _wizard_config(tmp_path, dispatch=False)
    result = readiness.gaps_for_health(str(path))
    assert isinstance(result, list)
    assert len(result) == 1
    assert "readiness check failed" in result[0]


# -- 4. The health handler reports gaps (ast) ----------------------------

def test_the_health_handler_reports_gaps():
    """In cura_mcp_server.py, _handle_health (an AsyncFunctionDef nested
    inside create_server) must call gaps_for_health, and that helper must be
    imported inside a function, not at module level."""
    src = (Path(__file__).resolve().parent.parent / "cura_mcp_server.py").read_text()
    tree = ast.parse(src)

    # Find create_server, then the _handle_health nested inside it.
    create_server = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "create_server"
    )
    handle_health = next(
        n for n in ast.walk(create_server)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "_handle_health"
    )

    # _handle_health must contain a Call to gaps_for_health.
    calls = [
        c for c in ast.walk(handle_health)
        if isinstance(c, ast.Call)
        and getattr(c.func, "id", "") == "gaps_for_health"
    ]
    assert calls, "_handle_health never calls gaps_for_health"

    # gaps_for_health must be imported inside a function, not at module level.
    module_level_imports = [
        n for n in tree.body
        if isinstance(n, (ast.Import, ast.ImportFrom))
    ]
    for imp in module_level_imports:
        for alias in imp.names:
            assert alias.asname != "gaps_for_health" and alias.name != "gaps_for_health", (
                "gaps_for_health is imported at module level; it must be "
                "imported inside a function"
            )

    # And it must actually be imported somewhere inside a function.
    in_function_import = False
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for sub in ast.walk(node):
                if isinstance(sub, (ast.Import, ast.ImportFrom)):
                    for alias in sub.names:
                        if alias.name == "gaps_for_health" or alias.asname == "gaps_for_health":
                            in_function_import = True
    assert in_function_import, (
        "gaps_for_health is never imported inside a function"
    )
