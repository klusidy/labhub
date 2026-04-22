"""
REPL Session Management for LabHub

Manages Python REPL sessions with WebSocket communication.
Each client gets a persistent session that survives reconnections.
"""

from dataclasses import dataclass, field
from datetime import datetime
import asyncio
import os
from pathlib import Path
from typing import Dict, Optional, List
import uuid
import logging
import tempfile
import shutil

logger = logging.getLogger(__name__)


@dataclass
class SessionInfo:
    """Information about a REPL session"""
    session_id: str
    client_id: str
    process: asyncio.subprocess.Process
    created_at: datetime
    work_dir: Path  # Working directory for this session
    is_temp_dir: bool = True  # Whether work_dir is a temp dir (should be cleaned up)
    output_buffer: List[Dict[str, str]] = field(default_factory=list)
    max_buffer_size: int = 1000
    # Per-websocket subscriber queues (populated by background reader tasks)
    _subscriber_queues: List[asyncio.Queue] = field(default_factory=list, init=False)
    # Background reader tasks (one for stdout, one for stderr)
    _reader_tasks: List["asyncio.Task[None]"] = field(default_factory=list, init=False)

    def add_output(self, stream: str, data: str):
        """Add output to ring buffer and fan out to all WebSocket subscribers."""
        self.output_buffer.append({"stream": stream, "data": data})
        if len(self.output_buffer) > self.max_buffer_size:
            self.output_buffer.pop(0)
        for q in list(self._subscriber_queues):
            try:
                q.put_nowait({"stream": stream, "data": data})
            except asyncio.QueueFull:
                pass  # slow subscriber — drop rather than block

    def subscribe(self, maxsize: int = 200) -> asyncio.Queue:
        """Return a new queue that will receive all future output items."""
        q: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._subscriber_queues.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        """Remove a subscriber queue."""
        try:
            self._subscriber_queues.remove(q)
        except ValueError:
            pass

    async def _read_stream_loop(self, stream, stream_name: str) -> None:
        """Background task: read process stdout/stderr and fan out to subscribers."""
        try:
            while True:
                line = await stream.readline()
                if not line:
                    break
                self.add_output(stream_name, line.decode("utf-8", errors="replace"))
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Error reading {stream_name} for session {self.session_id}: {e}")


class ReplSessionManager:
    """Manages all REPL sessions"""

    def __init__(
        self,
        python_path: Optional[Path],
        project_root: Path,
        macros_path: Optional[Path],
        startup_folder: Optional[Path] = None,
    ):
        self.sessions: Dict[str, SessionInfo] = {}
        self.python_path = python_path
        self.project_root = project_root
        self.macros_path = macros_path
        self.startup_folder = startup_folder
        self.client_sessions: Dict[str, str] = {}  # client_id -> session_id
        logger.info(
            f"REPL Session Manager initialized. Python: {python_path or 'default .venv'}, "
            f"Startup folder: {startup_folder or 'temp dir'}"
        )

    async def get_or_create_session(self, client_id: str) -> SessionInfo:
        """Get existing session for client or create new one"""
        # Check if client already has a session
        if client_id in self.client_sessions:
            session_id = self.client_sessions[client_id]
            if session_id in self.sessions:
                session = self.sessions[session_id]
                # Check if process is still alive
                if session.process.returncode is None:
                    logger.info(f"Reusing session {session_id} for client {client_id}")
                    return session
                else:
                    # Process died, cleanup and create new
                    logger.warning(
                        f"Session {session_id} process died, creating new session"
                    )
                    await self._cleanup_session(session_id)

        # Create new session
        return await self._create_new_session(client_id)

    async def _create_new_session(self, client_id: str) -> SessionInfo:
        """Create a new REPL session"""
        session_id = str(uuid.uuid4())
        logger.info(f"Creating new REPL session {session_id} for client {client_id}")

        # Determine Python executable
        if self.python_path:
            python_exe = self.python_path
        else:
            # Use server's .venv
            if os.name == 'nt':
                python_exe = Path(".venv") / "Scripts" / "python.exe"
            else:
                python_exe = Path(".venv") / "bin" / "python"

        if not python_exe.exists():
            raise FileNotFoundError(f"Python executable not found: {python_exe}")

        logger.info(f"Using Python executable: {python_exe}")

        # Prepare startup script path
        startup_script = Path(__file__).parent / "repl_startup.py"
        if not startup_script.exists():
            raise FileNotFoundError(f"Startup script not found: {startup_script}")

        logger.info(f"Starting REPL with script: {startup_script}")

        # Determine working directory for this session
        if self.startup_folder and self.startup_folder.exists():
            work_dir = self.startup_folder
            is_temp_dir = False
            logger.info(f"Using startup folder as working directory: {work_dir}")
        else:
            work_dir = Path(tempfile.mkdtemp(prefix=f"labhub_repl_{session_id[:8]}_"))
            is_temp_dir = True
            logger.info(f"Created temp directory: {work_dir}")

        # Build environment
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        if self.macros_path:
            env["LABHUB_MACROS_PATH"] = str(self.macros_path)

        # Start subprocess with working directory
        process = await asyncio.create_subprocess_exec(
            str(python_exe),
            "-u",  # Unbuffered output
            str(startup_script),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(work_dir),
            env=env,
        )

        session = SessionInfo(
            session_id=session_id,
            client_id=client_id,
            process=process,
            created_at=datetime.now(),
            work_dir=work_dir,
            is_temp_dir=is_temp_dir,
        )

        self.sessions[session_id] = session
        self.client_sessions[client_id] = session_id

        # Start persistent background readers — these outlive individual WS connections
        session._reader_tasks = [
            asyncio.create_task(session._read_stream_loop(process.stdout, "stdout")),
            asyncio.create_task(session._read_stream_loop(process.stderr, "stderr")),
        ]

        logger.info(f"Session {session_id} created successfully")
        return session

    async def close_session(self, session_id: str):
        """Close a specific session"""
        if session_id in self.sessions:
            logger.info(f"Closing session {session_id}")
            await self._cleanup_session(session_id)

    async def _cleanup_session(self, session_id: str):
        """Internal cleanup of session"""
        session = self.sessions.get(session_id)
        if not session:
            return

        # Cancel background reader tasks
        for task in session._reader_tasks:
            task.cancel()
        if session._reader_tasks:
            await asyncio.gather(*session._reader_tasks, return_exceptions=True)

        # Terminate process if still running
        if session.process.returncode is None:
            try:
                session.process.terminate()
                await asyncio.wait_for(session.process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning(f"Session {session_id} did not terminate, killing")
                session.process.kill()
                await session.process.wait()

        # Clean up temporary directory (only if we created it)
        if session.is_temp_dir:
            try:
                if session.work_dir.exists():
                    shutil.rmtree(session.work_dir)
                    logger.info(f"Removed temp directory: {session.work_dir}")
            except Exception as e:
                logger.warning(f"Failed to remove temp directory {session.work_dir}: {e}")

        # Remove from mappings
        del self.sessions[session_id]
        for cid, sid in list(self.client_sessions.items()):
            if sid == session_id:
                del self.client_sessions[cid]

    async def close_all_sessions(self):
        """Close all sessions (called on server shutdown)"""
        logger.info(f"Closing all {len(self.sessions)} REPL sessions")
        for session_id in list(self.sessions.keys()):
            await self._cleanup_session(session_id)

    def get_session(self, session_id: str) -> Optional[SessionInfo]:
        """Get session by ID"""
        return self.sessions.get(session_id)

    async def execute_code(self, session_id: str, code: str):
        """Send code to session for execution"""
        session = self.sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        if session.process.returncode is not None:
            raise RuntimeError(f"Session {session_id} process has terminated")

        # Send code followed by newline
        session.process.stdin.write((code + "\n").encode("utf-8"))
        await session.process.stdin.drain()

    async def send_interrupt(self, session_id: str):
        """Send interrupt signal to session (Ctrl+C)"""
        session = self.sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        # Send Ctrl+C on Windows
        if os.name == "nt":
            import ctypes

            # Send CTRL_BREAK_EVENT on Windows
            kernel32 = ctypes.windll.kernel32
            kernel32.GenerateConsoleCtrlEvent(1, session.process.pid)
        else:
            # Unix: send SIGINT
            import signal
            session.process.send_signal(signal.SIGINT)

    def get_session_count(self) -> int:
        """Get number of active sessions"""
        return len(self.sessions)
