#!/usr/bin/env python3
"""
Git SSH wrapper using paramiko.
Usage: Set GIT_SSH_COMMAND="python3 git_push.py" and then git push.
"""

import sys
import os
import paramiko

def main():
    # Args: git_push.py <host> <git-upload-pack/receive-pack 'repo'>
    if len(sys.argv) < 3:
        print("Usage: git_push.py <host> <command>", file=sys.stderr)
        sys.exit(1)

    host = sys.argv[1]
    git_command = sys.argv[2]

    # Parse repo path from command like: git-receive-pack 'yurislay9-ui/Zenic-Logic-.git'
    parts = git_command.split("'", 1)
    if len(parts) >= 2:
        repo_path = parts[1].rstrip("'")
    else:
        repo_path = git_command

    # Load SSH key
    key_path = os.path.expanduser("~/.ssh/id_rsa_github")
    # Fallback to default RSA key if GitHub-specific key not found
    if not os.path.exists(key_path):
        key_path = os.path.expanduser("~/.ssh/id_rsa")
    try:
        pkey = paramiko.RSAKey.from_private_key_file(key_path)
    except FileNotFoundError:
        print(f"Error: SSH key not found at {key_path}", file=sys.stderr)
        print("Generate one with: ssh-keygen -t rsa -f ~/.ssh/id_rsa", file=sys.stderr)
        sys.exit(1)
    except paramiko.PasswordRequiredException:
        print(f"Error: SSH key at {key_path} requires a passphrase", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: Could not load SSH key at {key_path}: {e}", file=sys.stderr)
        sys.exit(1)

    # Connect
    client = paramiko.SSHClient()
    # SECURITY: Use RejectPolicy instead of AutoAddPolicy to prevent MITM attacks
    # Load known_hosts file if available; otherwise reject unknown hosts
    known_hosts = os.path.expanduser("~/.ssh/known_hosts")
    if os.path.exists(known_hosts):
        client.load_host_keys(known_hosts)
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    try:
        client.connect(host, username="git", pkey=pkey)
    except paramiko.SSHException as e:
        print(f"SSH host key verification failed: {e}", file=sys.stderr)
        print(f"Add the host key to ~/.ssh/known_hosts first: ssh-keyscan {host} >> ~/.ssh/known_hosts", file=sys.stderr)
        sys.exit(1)

    # Execute git command via SSH channel
    chan = client.get_transport().open_session()
    chan.exec_command(git_command)

    # Proxy data between git and SSH
    import select
    import socket

    # Simple proxy loop
    import fcntl
    try:
        # Set stdin to non-blocking
        fd = sys.stdin.fileno()
        fl = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)
    except (OSError, IOError):
        pass

    while not chan.exit_status_ready():
        # Read from channel -> stdout
        if chan.recv_ready():
            data = chan.recv(4096)
            sys.stdout.buffer.write(data)
            sys.stdout.buffer.flush()
        if chan.recv_stderr_ready():
            data = chan.recv_stderr(4096)
            sys.stderr.buffer.write(data)
            sys.stderr.buffer.flush()
        # Read from stdin -> channel
        try:
            data = sys.stdin.buffer.read(4096)
            if data:
                chan.send(data)
        except (OSError, IOError):
            pass

    # Flush remaining
    while chan.recv_ready():
        sys.stdout.buffer.write(chan.recv(4096))
    while chan.recv_stderr_ready():
        sys.stderr.buffer.write(chan.recv_stderr(4096))
    sys.stdout.buffer.flush()
    sys.stderr.buffer.flush()

    client.close()
    sys.exit(chan.recv_exit_status())

if __name__ == "__main__":
    main()
