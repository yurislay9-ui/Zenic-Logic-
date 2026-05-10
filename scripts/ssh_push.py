#!/usr/bin/env python3
"""
Git push via dulwich + paramiko — robust approach.

Uses dulwich (pure Python git) with paramiko SSH transport
to push local commits to GitHub without requiring openssh-client.
"""

import io
import os
import select
import sys
import logging
import subprocess

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Try Ed25519 first (modern), then RSA (legacy), accept override via env
_ssh_key_env = os.environ.get("SSH_KEY_PATH", "")
if _ssh_key_env and os.path.exists(_ssh_key_env):
    SSH_KEY_PATH = _ssh_key_env
elif os.path.exists(os.path.expanduser("~/.ssh/id_ed25519_github")):
    SSH_KEY_PATH = os.path.expanduser("~/.ssh/id_ed25519_github")
else:
    SSH_KEY_PATH = os.path.expanduser("~/.ssh/id_rsa_github")

REPO_URL = "git@github.com:yurislay9-ui/Zenic-Logic-.git"
BRANCH = "main"


class ParamikoSSHVendor:
    """Custom SSH vendor using paramiko instead of subprocess ssh."""

    def __init__(self, pkey):
        self._pkey = pkey

    def run_command(self, host, command, username=None, port=None,
                    password=None, key_filename=None, ssh_command=None,
                    protocol_version=None):
        import paramiko

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        conn_user = username or "git"
        conn_port = port or 22

        logger.info(f"SSH connecting to {conn_user}@{host}:{conn_port}...")
        client.connect(host, port=conn_port, username=conn_user,
                       pkey=self._pkey, timeout=30,
                       look_for_keys=False, allow_agent=False)

        transport = client.get_transport()
        channel = transport.open_session()

        cmd_str = command.decode() if isinstance(command, bytes) else command
        logger.info(f"Executing: {cmd_str[:80]}...")
        channel.exec_command(cmd_str)

        return _ParamikoChannel(channel, client)


class _ParamikoChannel:
    """Wrapper that makes a paramiko Channel look like dulwich's SubprocessWrapper.

    Dulwich expects these attributes/methods:
      - read(size) -> bytes
      - write(data)
      - close()
      - can_read() -> bool
      - stderr (file-like, can be None)
    """

    def __init__(self, channel, client):
        self._channel = channel
        self._client = client
        self._stdout_file = channel.makefile('rb')
        self._stdin_file = channel.makefile('wb')
        self._stderr_file = channel.makefile_stderr('rb')

    def read(self, size=-1):
        """Read from stdout — used by dulwich Protocol."""
        return self._stdout_file.read(size)

    def write(self, data):
        """Write to stdin — used by dulwich Protocol."""
        return self._stdin_file.write(data)

    def can_read(self):
        """Check if data is available to read."""
        if self._channel.recv_ready():
            return True
        return False

    @property
    def stderr(self):
        """Return stderr stream."""
        return self._stderr_file

    def close(self, timeout=60):
        """Close the channel and SSH client."""
        try:
            self._stdin_file.close()
        except Exception:
            pass
        try:
            self._stdout_file.close()
        except Exception:
            pass
        try:
            self._stderr_file.close()
        except Exception:
            pass
        try:
            self._channel.close()
        except Exception:
            pass
        try:
            self._client.close()
        except Exception:
            pass


def push():
    import paramiko
    from dulwich import porcelain
    from dulwich.repo import Repo
    import dulwich.client

    logger.info(f"Repository: {REPO_DIR}")
    logger.info(f"SSH key: {SSH_KEY_PATH}")

    # Load SSH key with paramiko
    logger.info("Loading SSH key...")
    pkey = None
    for key_class, key_name in [
        (paramiko.Ed25519Key, "Ed25519"),
        (paramiko.RSAKey, "RSA"),
        (paramiko.ECDSAKey, "ECDSA"),
    ]:
        try:
            pkey = key_class.from_private_key_file(SSH_KEY_PATH)
            logger.info(f"Loaded {key_name} key from {SSH_KEY_PATH}")
            break
        except (paramiko.SSHException, ValueError, Exception):
            continue

    if pkey is None:
        logger.error("Cannot load any SSH key!")
        sys.exit(1)

    # Open the repository
    repo = Repo(REPO_DIR)

    # Check local vs remote
    local_head = repo.refs[b"refs/heads/" + BRANCH.encode()]
    remote_key = b"refs/remotes/origin/" + BRANCH.encode()
    remote_head = repo.refs[remote_key] if remote_key in repo.refs else None

    logger.info(f"Local HEAD:  {local_head.decode()}")
    logger.info(f"Remote HEAD: {remote_head.decode() if remote_head else 'unknown'}")

    # Count commits to push
    if remote_head and local_head == remote_head:
        logger.info("Already up to date — nothing to push!")
        return

    # Count commits ahead
    result = subprocess.run(
        ["git", "rev-list", "--count", f"{remote_head.decode() if remote_head else 'origin/main'}..HEAD"],
        cwd=REPO_DIR, capture_output=True, text=True
    )
    num_commits = result.stdout.strip() if result.returncode == 0 else "?"
    logger.info(f"Commits to push: {num_commits}")

    # Install our custom SSH vendor
    custom_vendor = ParamikoSSHVendor(pkey)
    original_get_vendor = dulwich.client.get_ssh_vendor
    dulwich.client.get_ssh_vendor = lambda: custom_vendor

    try:
        logger.info("Pushing to GitHub via dulwich+paramiko...")
        result = porcelain.push(
            repo,
            remote_location=REPO_URL,
            refspecs=BRANCH.encode(),
        )
        logger.info("Push completed successfully!")
        if result:
            for ref, status in result.items():
                logger.info(f"  {ref}: {status}")
    except Exception as e:
        err_msg = str(e)
        if "DivergedBranches" in type(e).__name__ or "diverged" in err_msg.lower():
            logger.warning("Branches diverged — forcing push (our local is authoritative)...")
            try:
                result = porcelain.push(
                    repo,
                    remote_location=REPO_URL,
                    refspecs=BRANCH.encode(),
                    force=True,
                )
                logger.info("Force push completed successfully!")
            except Exception as e2:
                logger.error(f"Force push also failed: {e2}")
                import traceback
                traceback.print_exc()
                sys.exit(1)
        else:
            logger.error(f"Push failed: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    finally:
        dulwich.client.get_ssh_vendor = original_get_vendor

    # Update remote ref locally
    repo.refs[b"refs/remotes/origin/" + BRANCH.encode()] = local_head
    logger.info("Local remote-tracking refs updated")


if __name__ == "__main__":
    push()
