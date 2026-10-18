"""The call path must never reach cura.readiness or kintsugi.

These are static (ast) checks: they read the source as text and walk the parse
tree. They import nothing from the modules under test, so they cannot be fooled
by an import that only happens at runtime.

The rule: the production call path (comms, pulse, memory, privacy, setup,
sensors, integrations, household, console) must not import cura.readiness or
kintsugi. Only `_preview` in cura/__main__.py may import cura.readiness, and
only inside that function. The MCP server must not import cura.readiness at
module level.
"""
from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Directories whose .py files form the production call path.
CALL_PATH_DIRS = [
    "cura/comms",
    "cura/pulse",
    "cura/memory",
    "cura/privacy",
    "cura/setup",
    "cura/sensors",
    "cura/integrations",
]
# Plus these specific files.
CALL_PATH_FILES = [
    "cura/household/__init__.py",
    "cura/console.py",
]

FORBIDDEN = ("cura.readiness", "kintsugi")


def _is_forbidden(name: str) -> bool:
    """True if a module name is, or is a submodule of, a forbidden module."""
    for prefix in FORBIDDEN:
        if name == prefix or name.startswith(prefix + "."):
            return True
    return False


def _import_module_names(node: ast.AST, path: Path | None = None) -> list[str]:
    """The module names named by a single Import/ImportFrom node. For `from X import y` that is X and X.y, so
    `from cura import readiness` names cura.readiness; a relative import is resolved against the file's package."""
    names: list[str] = []
    if isinstance(node, ast.Import):
        for alias in node.names:
            names.append(alias.name)
    elif isinstance(node, ast.ImportFrom):
        base = node.module or ""
        if node.level and path is not None:
            pkg = list(path.relative_to(REPO_ROOT).with_suffix("").parts[:-1])
            pkg = pkg[:len(pkg) - (node.level - 1)]
            base = ".".join(pkg + ([node.module] if node.module else []))
        if base:
            names.append(base)
        names.extend(f"{base}.{alias.name}" if base else alias.name for alias in node.names)
    return names


def _file_has_forbidden_import(path: Path) -> list[str]:
    """All forbidden module names named anywhere in a file's parse tree."""
    tree = ast.parse(path.read_text(), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for name in _import_module_names(node, path):
                if _is_forbidden(name):
                    found.append(name)
    return found


def test_the_call_path_never_imports_readiness_or_kintsugi():
    """No file in the production call path may import cura.readiness or
    kintsugi, anywhere in its parse tree."""
    paths: list[Path] = []
    for d in CALL_PATH_DIRS:
        paths.extend((REPO_ROOT / d).rglob("*.py"))
    for f in CALL_PATH_FILES:
        paths.append(REPO_ROOT / f)

    violations: list[str] = []
    for path in paths:
        for name in _file_has_forbidden_import(path):
            violations.append(f"{path.relative_to(REPO_ROOT)}: {name}")
    assert not violations, (
        "the call path must not import cura.readiness or kintsugi:\n"
        + "\n".join(violations))


def test_only_preview_imports_readiness_in_main():
    """In cura/__main__.py, the only function that imports cura.readiness is
    `_preview`, and there is no module-level import of it."""
    path = REPO_ROOT / "cura/__main__.py"
    tree = ast.parse(path.read_text(), filename=str(path))

    # No module-level (top-level) import of cura.readiness.
    module_level = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for name in _import_module_names(node, path):
                if name == "cura.readiness" or name.startswith("cura.readiness."):
                    module_level.append(name)
    assert not module_level, (
        "cura/__main__.py must not import cura.readiness at module level: "
        + ", ".join(module_level))

    # The only FunctionDef whose body (walked) imports cura.readiness is _preview.
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for sub in ast.walk(node):
                if isinstance(sub, (ast.Import, ast.ImportFrom)):
                    for name in _import_module_names(sub, path):
                        if (name == "cura.readiness"
                                or name.startswith("cura.readiness.")):
                            offenders.append(node.name)
                            break
    assert offenders == ["_preview"], (
        f"only _preview may import cura.readiness; found: {offenders}")


def test_the_mcp_server_has_no_module_level_readiness_import():
    """cura_mcp_server.py must not import cura.readiness at module level."""
    path = REPO_ROOT / "cura_mcp_server.py"
    tree = ast.parse(path.read_text(), filename=str(path))

    module_level = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for name in _import_module_names(node, path):
                if name == "cura.readiness" or name.startswith("cura.readiness."):
                    module_level.append(name)
    assert not module_level, (
        "cura_mcp_server.py must not import cura.readiness at module level: "
        + ", ".join(module_level))
