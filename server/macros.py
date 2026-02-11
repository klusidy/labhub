"""Macro management module for LabHub.

This module provides functionality to:
- Watch a folder for Python macro files
- Parse macro files to extract function signatures
- Provide API for listing macros and retrieving file contents
"""

from __future__ import annotations
import ast
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger("labhub.macros")


@dataclass
class MacroFunction:
    """Represents a parsed macro function."""

    name: str
    args: List[Dict[str, Any]] = field(default_factory=list)
    doc: Optional[str] = None
    lineno: int = 0


@dataclass
class MacroFile:
    """Represents a macro file with its functions."""

    filename: str
    path: Path
    functions: List[MacroFunction] = field(default_factory=list)
    error: Optional[str] = None


class MacroManager:
    """Manages discovery and parsing of macro files."""

    def __init__(self, macros_path: Optional[Path] = None):
        """Initialize the macro manager.

        Args:
            macros_path: Path to the macros folder. If None, macros are disabled.
        """
        self.macros_path = macros_path
        self._files: Dict[str, MacroFile] = {}

        if self.macros_path:
            if not self.macros_path.exists():
                logger.warning(f"Macros folder does not exist: {self.macros_path}")
                self.macros_path = None
            elif not self.macros_path.is_dir():
                logger.error(f"Macros path is not a directory: {self.macros_path}")
                self.macros_path = None
            else:
                logger.info(f"Macros enabled from folder: {self.macros_path}")
                self.refresh()
        else:
            logger.info("Macros disabled (no path configured)")

    def refresh(self) -> None:
        """Scan the macros folder and parse all .py files."""
        if not self.macros_path:
            return

        self._files.clear()

        try:
            for py_file in self.macros_path.glob("*.py"):
                self._parse_file(py_file)
            logger.info(f"Loaded {len(self._files)} macro files")
        except Exception as e:
            logger.error(f"Error scanning macros folder: {e}", exc_info=True)

    def _parse_file(self, file_path: Path) -> None:
        """Parse a single Python file to extract functions.

        Args:
            file_path: Path to the Python file.
        """
        filename = file_path.name
        macro_file = MacroFile(filename=filename, path=file_path)

        try:
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=filename)

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    # Only process top-level functions
                    if not isinstance(node.parent, ast.Module):  # type: ignore
                        continue

                    # Skip private functions (starting with _)
                    if node.name.startswith("_"):
                        continue

                    func = self._parse_function(node)
                    macro_file.functions.append(func)

            self._files[filename] = macro_file
            logger.debug(
                f"Parsed {filename}: found {len(macro_file.functions)} functions"
            )

        except SyntaxError as e:
            macro_file.error = f"Syntax error: {e}"
            self._files[filename] = macro_file
            logger.warning(f"Failed to parse {filename}: {e}")
        except Exception as e:
            macro_file.error = f"Error: {e}"
            self._files[filename] = macro_file
            logger.error(f"Error parsing {filename}: {e}", exc_info=True)

    def _parse_function(self, node: ast.FunctionDef) -> MacroFunction:
        """Parse a function AST node to extract signature.

        Args:
            node: AST FunctionDef node.

        Returns:
            MacroFunction with name, args, and docstring.
        """
        func = MacroFunction(name=node.name, lineno=node.lineno)

        # Extract docstring
        docstring = ast.get_docstring(node)
        func.doc = docstring if docstring else None

        # Extract arguments
        for arg in node.args.args:
            arg_info: Dict[str, Any] = {"name": arg.arg}

            # Extract type annotation if present
            if arg.annotation:
                arg_info["type"] = ast.unparse(arg.annotation)
            else:
                arg_info["type"] = "Any"

            # Mark required/optional (simplified - actual default handling is complex)
            # We'll mark as required by default
            arg_info["required"] = True

            func.args.append(arg_info)

        # Handle default values
        defaults = node.args.defaults
        if defaults:
            # Defaults apply to the last N arguments
            num_defaults = len(defaults)
            for i, default in enumerate(defaults):
                arg_index = len(func.args) - num_defaults + i
                if arg_index >= 0:
                    func.args[arg_index]["required"] = False
                    try:
                        func.args[arg_index]["default"] = ast.unparse(default)
                    except Exception:
                        func.args[arg_index]["default"] = "..."

        return func

    def list_files(self) -> List[Dict[str, Any]]:
        """List all macro files with their functions.

        Returns:
            List of dicts with file info and function signatures.
        """
        if not self.macros_path:
            return []

        result = []
        for filename, macro_file in sorted(self._files.items()):
            file_info = {
                "filename": filename,
                "functions": [
                    {
                        "name": func.name,
                        "args": func.args,
                        "doc": func.doc,
                    }
                    for func in macro_file.functions
                ],
            }
            if macro_file.error:
                file_info["error"] = macro_file.error

            result.append(file_info)

        return result

    def get_file_content(self, filename: str) -> Optional[str]:
        """Get the source code of a macro file.

        Args:
            filename: Name of the macro file.

        Returns:
            Source code as string, or None if file not found.
        """
        if not self.macros_path:
            return None

        macro_file = self._files.get(filename)
        if not macro_file:
            return None

        try:
            return macro_file.path.read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"Error reading {filename}: {e}", exc_info=True)
            return None

    def _validate_filename(self, filename: str) -> bool:
        """Validate filename to prevent path traversal."""
        if ".." in filename or "/" in filename or "\\" in filename:
            logger.warning(f"Invalid filename (path traversal attempt): {filename}")
            return False
        if not filename.endswith(".py"):
            logger.warning(f"Invalid filename (must end with .py): {filename}")
            return False
        return True

    def create_file(self, filename: str) -> bool:
        """Create a new empty macro file.

        Args:
            filename: Name of the new file (must end with .py).

        Returns:
            True if successful, False otherwise.
        """
        if not self.macros_path:
            return False
        if not self._validate_filename(filename):
            return False

        file_path = self.macros_path / filename
        if file_path.exists():
            logger.warning(f"File already exists: {filename}")
            return False

        try:
            file_path.write_text("", encoding="utf-8")
            logger.info(f"Created macro file: {filename}")
            self._parse_file(file_path)
            return True
        except Exception as e:
            logger.error(f"Error creating {filename}: {e}", exc_info=True)
            return False

    def delete_file(self, filename: str) -> bool:
        """Delete a macro file.

        Args:
            filename: Name of the file to delete.

        Returns:
            True if successful, False otherwise.
        """
        if not self.macros_path:
            return False
        if not self._validate_filename(filename):
            return False

        file_path = self.macros_path / filename
        try:
            file_path.resolve().relative_to(self.macros_path.resolve())
        except ValueError:
            logger.warning(f"File path outside macros folder: {file_path}")
            return False

        if not file_path.exists():
            logger.warning(f"File not found: {filename}")
            return False

        try:
            file_path.unlink()
            self._files.pop(filename, None)
            logger.info(f"Deleted macro file: {filename}")
            return True
        except Exception as e:
            logger.error(f"Error deleting {filename}: {e}", exc_info=True)
            return False

    def rename_file(self, old_name: str, new_name: str) -> bool:
        """Rename a macro file.

        Args:
            old_name: Current filename.
            new_name: New filename (must end with .py).

        Returns:
            True if successful, False otherwise.
        """
        if not self.macros_path:
            return False
        if not self._validate_filename(old_name) or not self._validate_filename(new_name):
            return False

        old_path = self.macros_path / old_name
        new_path = self.macros_path / new_name

        if not old_path.exists():
            logger.warning(f"File not found: {old_name}")
            return False
        if new_path.exists():
            logger.warning(f"Target file already exists: {new_name}")
            return False

        try:
            old_path.rename(new_path)
            self._files.pop(old_name, None)
            self._parse_file(new_path)
            logger.info(f"Renamed macro file: {old_name} -> {new_name}")
            return True
        except Exception as e:
            logger.error(f"Error renaming {old_name} to {new_name}: {e}", exc_info=True)
            return False

    def save_file_content(self, filename: str, content: str) -> bool:
        """Save source code to a macro file.

        Args:
            filename: Name of the macro file.
            content: New source code.

        Returns:
            True if successful, False otherwise.
        """
        if not self.macros_path:
            return False

        # Security check: only allow saving to files in the macros folder
        # and prevent path traversal attacks
        if ".." in filename or "/" in filename or "\\" in filename:
            logger.warning(f"Invalid filename (path traversal attempt): {filename}")
            return False

        file_path = self.macros_path / filename

        # Check if file is within macros_path
        try:
            file_path.resolve().relative_to(self.macros_path.resolve())
        except ValueError:
            logger.warning(f"File path outside macros folder: {file_path}")
            return False

        try:
            file_path.write_text(content, encoding="utf-8")
            logger.info(f"Saved macro file: {filename}")

            # Re-parse the file
            self._parse_file(file_path)
            return True
        except Exception as e:
            logger.error(f"Error saving {filename}: {e}", exc_info=True)
            return False


# Fix AST walking to track parent nodes
def _patch_ast_tree(tree):
    """Add parent references to AST nodes."""
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            child.parent = parent  # type: ignore
    return tree


# Monkey-patch the _parse_file method to use patched tree
_original_parse_file = MacroManager._parse_file


def _patched_parse_file(self, file_path: Path) -> None:
    """Parse a single Python file to extract functions (with parent tracking)."""
    filename = file_path.name
    macro_file = MacroFile(filename=filename, path=file_path)

    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=filename)
        _patch_ast_tree(tree)

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Only process top-level functions
                parent = getattr(node, "parent", None)
                if not isinstance(parent, ast.Module):
                    continue

                # Skip private functions (starting with _)
                if node.name.startswith("_"):
                    continue

                func = self._parse_function(node)
                macro_file.functions.append(func)

        self._files[filename] = macro_file
        logger.debug(f"Parsed {filename}: found {len(macro_file.functions)} functions")

    except SyntaxError as e:
        macro_file.error = f"Syntax error: {e}"
        self._files[filename] = macro_file
        logger.warning(f"Failed to parse {filename}: {e}")
    except Exception as e:
        macro_file.error = f"Error: {e}"
        self._files[filename] = macro_file
        logger.error(f"Error parsing {filename}: {e}", exc_info=True)


MacroManager._parse_file = _patched_parse_file  # type: ignore
