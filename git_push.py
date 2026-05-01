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
    key_path = os.path.expanduser("~/.ssh/id_rsa")
    pkey = paramiko.RSAKey.from_private_key_file(key_path)

    # Connect
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, username="git", pkey=pkey)

    # Execute git command
    stdin, stdout, stderr = client.get_transport().open_session().exec_command(git_command)

    # Proxy data between git and SSH
    import select
    import socket

    # Use exec_command with proper channel
    chan = client.get_transport().open_session()
    chan.exec_command(git_command)

    # Simple proxy loop
    import fcntl
    try:
        # Set stdin to non-blocking
        fd = sys.stdin.fileno()
        fl = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)
    except:
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
        except:
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
