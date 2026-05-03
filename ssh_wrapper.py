#!/usr/bin/env python3
"""
Paramiko-based SSH wrapper for git push.

Acts as a drop-in replacement for the 'ssh' command when used as
GIT_SSH_COMMAND. Handles the git-receive-pack protocol over SSH
using paramiko.
"""

import sys
import os
import threading
import paramiko


def main():
    # GIT_SSH_COMMAND receives: <wrapper> <user@host> <git-command>
    # We need to split user@host into username and hostname
    if len(sys.argv) < 3:
        print("Usage: ssh_wrapper.py <user@host> <command>", file=sys.stderr)
        sys.exit(1)

    user_host = sys.argv[1]
    git_command = " ".join(sys.argv[2:])

    # Parse user@host
    if '@' in user_host:
        username, hostname = user_host.split('@', 1)
    else:
        username = 'git'
        hostname = user_host

    # Load SSH key (try Ed25519 first, then RSA)
    pkey = None
    for key_path_str, loader in [
        ("~/.ssh/id_ed25519", paramiko.Ed25519Key.from_private_key_file),
        ("~/.ssh/id_rsa", paramiko.RSAKey.from_private_key_file),
    ]:
        key_path = os.path.expanduser(key_path_str)
        if os.path.exists(key_path):
            try:
                pkey = loader(key_path)
                break
            except Exception as e:
                print(f"Warning: Could not load {key_path}: {e}", file=sys.stderr)

    if pkey is None:
        print("Error: No SSH key found (~/.ssh/id_ed25519 or ~/.ssh/id_rsa)", file=sys.stderr)
        sys.exit(1)

    # Connect
    client = paramiko.SSHClient()
    # SECURITY: Use RejectPolicy instead of AutoAddPolicy to prevent MITM attacks
    known_hosts = os.path.expanduser("~/.ssh/known_hosts")
    if os.path.exists(known_hosts):
        client.load_host_keys(known_hosts)
    client.set_missing_host_key_policy(paramiko.RejectPolicy())

    try:
        client.connect(hostname, username=username, pkey=pkey, timeout=30)
    except paramiko.SSHException as e:
        print(f"SSH host key verification failed: {e}", file=sys.stderr)
        print(f"Add the host key first: ssh-keyscan {hostname} >> ~/.ssh/known_hosts", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"SSH connection error: {e}", file=sys.stderr)
        sys.exit(1)

    # Execute git command via SSH
    transport = client.get_transport()
    chan = transport.open_session()
    chan.exec_command(git_command)

    # Bidirectional proxy between local git and remote SSH channel
    def pipe_to_channel(ch, out):
        """Read from stdin, write to channel."""
        try:
            while True:
                data = os.read(0, 4096)
                if not data:
                    break
                ch.sendall(data)
        except (OSError, IOError):
            pass
        finally:
            try:
                ch.shutdown_write()
            except (OSError, IOError):
                pass

    def pipe_from_channel(ch, out):
        """Read from channel, write to stdout."""
        try:
            while True:
                data = ch.recv(4096)
                if not data:
                    break
                os.write(out, data)
        except (OSError, IOError):
            pass

    # Start threads for piping
    t_in = threading.Thread(target=pipe_to_channel, args=(chan, 1), daemon=True)
    t_out = threading.Thread(target=pipe_from_channel, args=(chan, 1), daemon=True)
    t_err = threading.Thread(
        target=pipe_from_channel,
        args=(chan, 2), daemon=True
    )

    t_in.start()
    t_out.start()
    t_err.start()

    # Wait for channel to close
    chan.status_event.wait()
    exit_code = chan.recv_exit_status()

    # Wait for threads to finish
    t_in.join(timeout=5)
    t_out.join(timeout=5)
    t_err.join(timeout=5)

    client.close()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
