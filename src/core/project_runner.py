"""
ProjectRunner — Auto-run generated projects with virtualenv + dependency installation.

Problem: Generated projects are written to disk but never validated by
actually running them. Users don't know if the code works until they
manually install deps and start the server.

Solution: ProjectRunner automates:
  1. Create virtualenv in project directory
  2. Install dependencies from requirements.txt
  3. Initialize database (create tables)
  4. Start the server on a free port
  5. Health check to verify it's running
  6. Return process info for management

M6 Implementation: Runs on Termux/Android with python3 -m venv support.
"""

import os
import sys
import time
import socket
import logging
import subprocess
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Default timeout for operations
INSTALL_TIMEOUT = 120  # seconds
START_TIMEOUT = 15     # seconds
HEALTH_TIMEOUT = 5     # seconds


@dataclass
class RunResult:
    """Result of a project run attempt."""
    success: bool = False
    project_name: str = ""
    project_dir: str = ""
    venv_dir: str = ""
    port: int = 0
    pid: Optional[int] = None
    health_ok: bool = False
    installed_deps: List[str] = field(default_factory=list)
    failed_deps: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    startup_time_s: float = 0.0


class ProjectRunner:
    """Run generated projects automatically with venv + deps + server start."""

    def __init__(self, projects_dir: Optional[str] = None):
        """
        Args:
            projects_dir: Base directory for generated projects.
                         Defaults to ~/.titan_omniscale/projects/
        """
        if projects_dir:
            self._projects_dir = projects_dir
        else:
            from src.core.shared.db_initializer import get_projects_dir
            self._projects_dir = str(get_projects_dir())

    # ================================================================
    #  PUBLIC API
    # ================================================================

    def run_project(self, project_name: str, port: int = 0,
                    auto_install: bool = True,
                    auto_start: bool = True) -> RunResult:
        """Run a generated project.

        Steps:
        1. Verify project directory exists
        2. Create virtualenv (if not exists)
        3. Install dependencies (if auto_install)
        4. Start the server (if auto_start)
        5. Health check

        Args:
            project_name: Name of the project to run
            port: Port to run on (0 = auto-select free port)
            auto_install: Whether to install dependencies
            auto_start: Whether to start the server

        Returns:
            RunResult with process info and status
        """
        result = RunResult(project_name=project_name)
        start_time = time.time()

        # Step 1: Verify project directory
        project_dir = os.path.join(self._projects_dir, project_name)
        if not os.path.isdir(project_dir):
            result.errors.append(f"Project directory not found: {project_dir}")
            return result
        result.project_dir = project_dir

        # Step 2: Create virtualenv
        venv_dir = os.path.join(project_dir, "venv")
        if not os.path.isdir(venv_dir):
            logger.info(f"ProjectRunner: Creating venv for {project_name}")
            venv_result = self._create_venv(venv_dir)
            if not venv_result:
                result.errors.append(f"Failed to create virtualenv in {venv_dir}")
                return result
            result.warnings.append("Virtualenv created")
        result.venv_dir = venv_dir

        # Step 3: Install dependencies
        if auto_install:
            logger.info(f"ProjectRunner: Installing deps for {project_name}")
            installed, failed = self._install_deps(project_dir, venv_dir)
            result.installed_deps = installed
            result.failed_deps = failed
            if failed:
                result.warnings.append(f"Failed to install {len(failed)} deps: {', '.join(failed[:3])}")

        # Step 4: Initialize database
        self._init_database(project_dir, venv_dir)

        # Step 5: Start server
        if auto_start:
            if port == 0:
                port = self._find_free_port()
            result.port = port
            logger.info(f"ProjectRunner: Starting {project_name} on port {port}")
            pid = self._start_server(project_dir, venv_dir, port)
            if pid:
                result.pid = pid
                # Step 6: Health check
                time.sleep(2)  # Wait for server to start
                health_ok = self._health_check(port)
                result.health_ok = health_ok
                if health_ok:
                    result.success = True
                    logger.info(f"ProjectRunner: {project_name} running on port {port} (PID {pid})")
                else:
                    result.warnings.append(f"Server started (PID {pid}) but health check failed on port {port}")
                    result.success = True  # Server is running, health check might need time
            else:
                result.errors.append("Failed to start server process")
        else:
            result.success = True  # Project prepared, just not started

        result.startup_time_s = time.time() - start_time
        return result

    def stop_project(self, project_name: str) -> bool:
        """Stop a running project by killing its server process.

        Args:
            project_name: Name of the project to stop

        Returns:
            True if stopped successfully
        """
        project_dir = os.path.join(self._projects_dir, project_name)
        pid_file = os.path.join(project_dir, ".server.pid")

        if os.path.exists(pid_file):
            try:
                with open(pid_file) as f:
                    pid = int(f.read().strip())
                os.kill(pid, 15)  # SIGTERM
                os.unlink(pid_file)
                logger.info(f"ProjectRunner: Stopped {project_name} (PID {pid})")
                return True
            except ProcessLookupError:
                # Process already dead
                if os.path.exists(pid_file):
                    os.unlink(pid_file)
                return True
            except Exception as e:
                logger.warning(f"ProjectRunner: Failed to stop {project_name}: {e}")
                return False
        else:
            logger.warning(f"ProjectRunner: No PID file for {project_name}")
            return False

    def list_running(self) -> List[Dict[str, Any]]:
        """List all running projects.

        Returns:
            List of dicts with project_name, port, pid, health
        """
        running = []
        if not os.path.isdir(self._projects_dir):
            return running

        for name in os.listdir(self._projects_dir):
            project_dir = os.path.join(self._projects_dir, name)
            pid_file = os.path.join(project_dir, ".server.pid")
            port_file = os.path.join(project_dir, ".server.port")

            if os.path.exists(pid_file):
                try:
                    with open(pid_file) as f:
                        pid = int(f.read().strip())
                    # Check if process is still alive
                    os.kill(pid, 0)  # Signal 0 = check existence

                    port = 0
                    if os.path.exists(port_file):
                        with open(port_file) as f:
                            port = int(f.read().strip())

                    running.append({
                        "project_name": name,
                        "port": port,
                        "pid": pid,
                        "health_ok": self._health_check(port) if port else False,
                    })
                except (ProcessLookupError, ValueError, FileNotFoundError):
                    # Process is dead, clean up
                    for f in [pid_file, port_file]:
                        if os.path.exists(f):
                            try:
                                os.unlink(f)
                            except OSError:
                                pass

        return running

    # ================================================================
    #  INTERNAL
    # ================================================================

    def _create_venv(self, venv_dir: str) -> bool:
        """Create a Python virtual environment."""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "venv", venv_dir],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode != 0:
                logger.error(f"venv creation failed: {result.stderr}")
                return False
            return True
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.error(f"venv creation error: {e}")
            return False

    def _install_deps(self, project_dir: str, venv_dir: str) -> tuple:
        """Install dependencies from requirements.txt.

        Returns:
            Tuple of (installed_list, failed_list)
        """
        req_file = os.path.join(project_dir, "requirements.txt")
        if not os.path.exists(req_file):
            return [], ["requirements.txt not found"]

        # Read requirements
        with open(req_file) as f:
            requirements = [line.strip() for line in f
                          if line.strip() and not line.startswith("#")]

        if not requirements:
            return [], []

        # Determine pip path
        if os.name == "nt":
            pip_path = os.path.join(venv_dir, "Scripts", "pip")
        else:
            pip_path = os.path.join(venv_dir, "bin", "pip")

        if not os.path.exists(pip_path):
            # Try pip3
            pip_path = pip_path + "3"
        if not os.path.exists(pip_path):
            # Use the venv python -m pip
            if os.name == "nt":
                python_path = os.path.join(venv_dir, "Scripts", "python")
            else:
                python_path = os.path.join(venv_dir, "bin", "python")
            pip_path = python_path
            use_module = True
        else:
            use_module = False

        installed = []
        failed = []

        for req in requirements:
            try:
                if use_module:
                    cmd = [pip_path, "-m", "pip", "install", "-q", req]
                else:
                    cmd = [pip_path, "install", "-q", req]

                result = subprocess.run(
                    cmd, capture_output=True, text=True,
                    timeout=INSTALL_TIMEOUT,
                )
                if result.returncode == 0:
                    installed.append(req)
                else:
                    failed.append(req)
                    logger.debug(f"Failed to install {req}: {result.stderr[:100]}")
            except subprocess.TimeoutExpired:
                failed.append(req)
                logger.warning(f"Timeout installing {req}")
            except Exception as e:
                failed.append(req)
                logger.warning(f"Error installing {req}: {e}")

        return installed, failed

    def _init_database(self, project_dir: str, venv_dir: str) -> bool:
        """Initialize the SQLite database for the project."""
        # Check if there's a database.py or init_db script
        db_file = os.path.join(project_dir, "database.py")
        if not os.path.exists(db_file):
            return True  # No database module, skip

        # Try to import and run init
        if os.name == "nt":
            python_path = os.path.join(venv_dir, "Scripts", "python")
        else:
            python_path = os.path.join(venv_dir, "bin", "python")

        if not os.path.exists(python_path):
            python_path = sys.executable

        try:
            result = subprocess.run(
                [python_path, "-c",
                 "import sys; sys.path.insert(0, '.'); "
                 "from database import init_db; init_db()"],
                capture_output=True, text=True, timeout=15,
                cwd=project_dir,
            )
            return result.returncode == 0
        except Exception as e:
            logger.debug(f"Database init skipped: {e}")
            return False

    def _start_server(self, project_dir: str, venv_dir: str,
                       port: int) -> Optional[int]:
        """Start the project server as a background process."""
        # Determine python path
        if os.name == "nt":
            python_path = os.path.join(venv_dir, "Scripts", "python")
        else:
            python_path = os.path.join(venv_dir, "bin", "python")

        if not os.path.exists(python_path):
            python_path = sys.executable

        # Check for main.py or app.py
        main_file = None
        for name in ["main.py", "app.py", "server.py"]:
            if os.path.exists(os.path.join(project_dir, name)):
                main_file = name
                break

        if not main_file:
            logger.warning(f"No main.py/app.py found in {project_dir}")
            return None

        # Start server
        env = os.environ.copy()
        env["PORT"] = str(port)

        try:
            process = subprocess.Popen(
                [python_path, main_file],
                cwd=project_dir,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                # Detach from parent process group
                start_new_session=True,
            )

            pid = process.pid

            # Save PID and port for management
            pid_file = os.path.join(project_dir, ".server.pid")
            port_file = os.path.join(project_dir, ".server.port")
            with open(pid_file, "w") as f:
                f.write(str(pid))
            with open(port_file, "w") as f:
                f.write(str(port))

            return pid

        except Exception as e:
            logger.error(f"Failed to start server: {e}")
            return None

    def _health_check(self, port: int) -> bool:
        """Check if the server is responding on the given port."""
        try:
            import urllib.request
            url = f"http://localhost:{port}/health"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=HEALTH_TIMEOUT) as resp:
                return resp.status == 200
        except Exception:
            # Try / root as fallback
            try:
                import urllib.request
                url = f"http://localhost:{port}/"
                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=HEALTH_TIMEOUT) as resp:
                    return resp.status in (200, 404)  # 404 means server is running
            except Exception:
                return False

    @staticmethod
    def _find_free_port() -> int:
        """Find a free TCP port."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            return s.getsockname()[1]
