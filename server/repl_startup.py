"""
REPL Startup Script for LabHub

This script runs in each REPL session. It:
1. Sets up the Python environment
2. Imports necessary modules
3. Connects to the LabHub server
4. Imports all macro files
5. Runs an interactive REPL loop
"""

import sys
import os
from pathlib import Path
import traceback
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr
import code


def setup_environment():
    """Setup Python environment for REPL"""
    # Force UTF-8 encoding on Windows to avoid Unicode errors
    if sys.platform == "win32":
        import io

        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )
        sys.stderr = io.TextIOWrapper(
            sys.stderr.buffer, encoding="utf-8", errors="replace"
        )

    print("LabHub REPL Initializing...")
    print(f"Working directory: {Path.cwd()}")

    # Derive project root from this script's location: server/repl_startup.py -> ..
    project_root = Path(__file__).resolve().parent.parent
    # print(f"Project root: {project_root}")

    # Add project root to sys.path so "import client.python as labhub" works
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    # Add macros path if configured
    macros_path = os.environ.get("LABHUB_MACROS_PATH")
    if macros_path:
        macros_path = Path(macros_path)
        if macros_path.exists() and str(macros_path) not in sys.path:
            sys.path.insert(0, str(macros_path))
            print(f"Macros path: {macros_path}")

    return macros_path


def import_labhub_client(namespace):
    """Import and make the labhub client module available in the REPL namespace"""
    try:
        import client.python as labhub

        namespace["labhub"] = labhub

        # Auto-connect to running server
        try:
            labhub.connect()
            print("LabHub client connected")
        except Exception as conn_err:
            print(f"LabHub client imported but not connected: {conn_err}")
            print("  Use labhub.connect() to connect manually")
        return True
    except Exception as e:
        print(f"Warning: Could not import LabHub client: {e}")
        return False


def import_macro_files(macros_path, namespace):
    """Import all Python files from macros directory"""
    if not macros_path or not macros_path.exists():
        print("No macros directory configured")
        return

    print(f"\nImporting macro files from: {macros_path}")

    # Find all .py files
    py_files = list(macros_path.glob("*.py"))

    if not py_files:
        print("No Python files found in macros directory")
        return

    imported_count = 0
    for py_file in py_files:
        # Skip __init__.py and private files
        if py_file.name.startswith("_"):
            continue

        try:
            # Import the module
            code_obj = compile(py_file.read_text(), str(py_file), "exec")
            exec(code_obj, namespace)
            print(f"  [OK] Imported: {py_file.name}")
            imported_count += 1
        except Exception as e:
            print(f"  [ERROR] Failed to import {py_file.name}: {e}")

    print(f"\nImported {imported_count} macro file(s)")


class ReplConsole(code.InteractiveConsole):
    """Custom interactive console that captures output"""

    def __init__(self, locals=None):
        super().__init__(locals)
        self.output_buffer = []

    def write(self, data):
        """Capture console output"""
        if data:
            sys.stdout.write(data)
            sys.stdout.flush()


def run_repl_loop(namespace):
    """Run the main REPL loop"""
    print("\n" + "=" * 50)
    print("LabHub REPL Ready")
    print("=" * 50)
    print("READY")  # Signal to server that initialization is complete
    sys.stdout.flush()

    # Create interactive console
    console = ReplConsole(locals=namespace)

    # Main loop - read commands from stdin and execute
    while True:
        try:
            # Read command from stdin
            line = sys.stdin.readline()

            if not line:
                # EOF reached
                break

            # Strip the command
            command = line.rstrip("\n")

            # Skip empty lines
            if not command.strip():
                continue

            # Special commands
            if command.strip() == "exit()" or command.strip() == "quit()":
                print("Exiting REPL...")
                break

            # Execute the command and capture output
            stdout_capture = StringIO()
            stderr_capture = StringIO()

            try:
                with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                    # Try to eval first (for expressions)
                    try:
                        result = eval(command, namespace)
                        if result is not None:
                            print(repr(result))
                    except SyntaxError:
                        # Not an expression, try exec
                        exec(command, namespace)

            except Exception as e:
                # Print exception to stderr
                stderr_capture.write(traceback.format_exc())

            # Output captured stdout
            stdout_text = stdout_capture.getvalue()
            if stdout_text:
                sys.stdout.write(stdout_text)

            # Output captured stderr
            stderr_text = stderr_capture.getvalue()
            if stderr_text:
                sys.stderr.write(stderr_text)

            # Flush outputs
            sys.stdout.flush()
            sys.stderr.flush()

        except KeyboardInterrupt:
            print("\nKeyboardInterrupt")
            sys.stdout.flush()
        except EOFError:
            break
        except Exception as e:
            print(f"REPL Error: {e}", file=sys.stderr)
            traceback.print_exc()
            sys.stderr.flush()


def main():
    """Main entry point for REPL"""
    try:
        # Setup environment
        macros_path = setup_environment()

        # Create namespace for REPL
        namespace = {
            "__name__": "__main__",
            "__doc__": None,
        }

        # Import LabHub client
        import_labhub_client(namespace)

        # Import macro files (macros_path will be None if not configured)
        if macros_path is not None:
            import_macro_files(macros_path, namespace)

        # Run REPL loop
        run_repl_loop(namespace)

    except Exception as e:
        print(f"Fatal REPL error: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
