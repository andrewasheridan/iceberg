"""AST-based walker for extracting public API surface from Python modules."""

import ast
import contextlib
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "ModuleInfo",
    "load_modules",
    "walk_module",
    "walk_path",
]


@dataclass
class ModuleInfo:
    """Information extracted from a single Python module.

    Attributes:
        path: Absolute path to the module file.
        declared_all: The list declared in __all__, or None if absent.
        inferred_all: Names inferred from top-level non-underscore definitions.
    """

    path: Path
    declared_all: list[str] | None
    inferred_all: list[str] = field(default_factory=list)

    @property
    def effective_all(self) -> list[str]:
        """Return the authoritative public API surface.

        Returns:
            ``declared_all`` when present, otherwise ``inferred_all``.
        """
        if self.declared_all is not None:
            return self.declared_all
        return self.inferred_all


def _extract_declared_all(tree: ast.Module) -> list[str] | None:
    """Extract the value of ``__all__`` from a parsed AST, if present.

    Only handles the common pattern ``__all__ = [...]`` or ``__all__ = (...)``.
    More exotic assignments (augmented, annotated, etc.) are ignored and treated
    as absent.

    Args:
        tree: Parsed AST of a module.

    Returns:
        A list of names, or ``None`` if ``__all__`` is not found or unparseable.
    """
    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not (isinstance(target, ast.Name) and target.id == "__all__"):
                continue
            value = node.value
            if isinstance(value, (ast.List, ast.Tuple)):
                names: list[str] = []
                for elt in value.elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        names.append(elt.value)
                    else:
                        # Non-string element — treat as unparseable
                        return None
                return names
    return None


def _infer_public_names(tree: ast.Module) -> list[str]:
    """Infer public names from top-level definitions.

    Collects names of top-level functions, classes, and simple variable
    assignments that do not start with an underscore.

    Args:
        tree: Parsed AST of a module.

    Returns:
        Sorted list of inferred public names.
    """
    names: list[str] = []
    for node in ast.iter_child_nodes(tree):
        match node:
            case ast.FunctionDef(name=name) | ast.AsyncFunctionDef(name=name):
                if not name.startswith("_"):
                    names.append(name)
            case ast.ClassDef(name=name):
                if not name.startswith("_"):
                    names.append(name)
            case ast.Assign(targets=targets):
                for target in targets:
                    if isinstance(target, ast.Name) and not target.id.startswith("_") and target.id != "__all__":
                        names.append(target.id)
    return sorted(names)


def load_modules(path: Path) -> list[ModuleInfo]:
    """Load module info from a file or directory.

    Convenience wrapper: if ``path`` is a file, returns a single-element list;
    if it is a directory, delegates to :func:`walk_path`.

    Args:
        path: A ``.py`` file or a directory to walk recursively.

    Returns:
        List of parsed :class:`ModuleInfo`.

    Raises:
        SyntaxError: If a single file cannot be parsed.
        OSError: If a single file cannot be read.
    """
    if path.is_dir():
        return walk_path(path)
    return [walk_module(path)]


def walk_module(path: Path) -> ModuleInfo:
    """Parse a single Python file and extract its public API surface.

    Args:
        path: Path to a ``.py`` file.

    Returns:
        A :class:`ModuleInfo` describing the module's public surface.

    Raises:
        SyntaxError: If the file cannot be parsed as valid Python.
        OSError: If the file cannot be read.
    """
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    declared = _extract_declared_all(tree)
    inferred = _infer_public_names(tree)
    return ModuleInfo(path=path, declared_all=declared, inferred_all=inferred)


def walk_path(root: Path) -> list[ModuleInfo]:
    """Recursively walk a directory and parse all Python modules.

    Skips files that cannot be parsed (logs a warning but continues).

    Args:
        root: Root directory to walk.

    Returns:
        List of :class:`ModuleInfo` for each parseable ``.py`` file found.
    """
    results: list[ModuleInfo] = []
    for py_file in sorted(root.rglob("*.py")):
        with contextlib.suppress(SyntaxError, OSError):
            results.append(walk_module(py_file))
    return results
