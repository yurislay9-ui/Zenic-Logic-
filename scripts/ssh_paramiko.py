#!/usr/bin/env python3
"""
SSH wrapper using Paramiko for environments without openssh-client.

Usage: python3 ssh_paramiko.py [options] [user@]hostname command

Git calls this as: ssh -o StrictHostKeyChecking=no git@github.com git-receive-pack ...
"""
import sys
import os
import paramiko


def main():
    # Parse arguments - git passes: ssh [options] user@host command
    args = sys.argv[1:]

    # Extract host and command from args
    host = None
    command = None
    port = 22
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == '-p' and i + 1 < len(args):
            port = int(args[i + 1])
            i += 2
        elif arg in ('-o', '-oStrictHostKeyChecking=no'):
            # Skip -o and its value
            if '=' not in arg and i + 1 < len(args):
                i += 2
            else:
                i += 1
        elif '@' in arg and host is None:
            host = arg
            i += 1
        elif host is not None and command is None:
            # Everything from here is the command
            command = ' '.join(args[i:])
            break
        else:
            i += 1

    if not host or not command:
        print(f"Usage: {sys.argv[0]} [options] user@host command", file=sys.stderr)
        sys.exit(1)

    user, hostname = host.split('@', 1)

    # Load SSH key - prefer github-specific key
    key_path = os.path.expanduser('~/.ssh/id_ed25519_github')
    if not os.path.exists(key_path):
        key_path = os.path.expanduser('~/.ssh/id_ed25519')
    if not os.path.exists(key_path):
        key_path = os.path.expanduser('~/.ssh/id_rsa')

    # Connect and execute
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(
            hostname=hostname,
            port=port,
            username=user,
            key_filename=key_path,
            timeout=30,
            look_for_keys=False,
            allow_agent=False,
        )

        # Execute command with proper I/O forwarding for git
        transport = client.get_transport()
        channel = transport.open_session()
        channel.exec_command(command)

        # Forward data between stdin/stdout/stderr and the channel
        import select
        import socket

        channel.setblocking(0)

        while True:
            r, w, x = select.select([channel, sys.stdin], [], [], 1.0)

            if channel in r:
                try:
                    data = channel.recv(65536)
                    if data:
                        sys.stdout.buffer.write(data)
                        sys.stdout.buffer.flush()
                    else:
                        break
                except socket.timeout:
                    pass
                except EOFError:
                    break

            if sys.stdin in r:
                try:
                    data = sys.stdin.buffer.read1(65536) if hasattr(sys.stdin.buffer, 'read1') else sys.stdin.buffer.read(65536)
                    if data:
                        channel.sendall(data)
                    else:
                        channel.shutdown_write()
                except EOFError:
                    channel.shutdown_write()

        exit_status = channel.recv_exit_status()
        sys.exit(exit_status)

    except Exception as e:
        print(f"SSH Error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        client.close()


if __name__ == '__main__':
    main()
