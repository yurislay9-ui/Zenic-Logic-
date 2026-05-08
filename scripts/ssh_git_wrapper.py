#!/usr/bin/env python3
"""Git SSH wrapper using paramiko for environments without ssh binary."""
import paramiko
import sys
import os

def git_push_via_ssh(repo_path, remote="origin", branch="main"):
    key_path = os.path.expanduser("~/.ssh/id_ed25519")
    key = paramiko.Ed25519Key.from_private_key_file(key_path)
    
    # We need to use git's internal transport, not paramiko
    # So let's create a GIT_SSH_COMMAND wrapper script
    wrapper_script = os.path.expanduser("~/.ssh/git_ssh_wrapper.sh")
    with open(wrapper_script, 'w') as f:
        f.write(f"""#!/bin/bash
# Auto-generated SSH wrapper using python+paramiko
exec python3 -c "
import paramiko, sys, os
key = paramiko.Ed25519Key.from_private_key_file('{key_path}')
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(sys.argv[1], username='git', pkey=key)
transport = client.get_transport()
channel = transport.open_session()
cmd = ' '.join(sys.argv[2:])
channel.exec_command(cmd)
while True:
    if channel.recv_ready():
        sys.stdout.buffer.write(channel.recv(4096))
        sys.stdout.buffer.flush()
    if channel.recv_stderr_ready():
        sys.stderr.buffer.write(channel.recv_stderr(4096))
        sys.stderr.buffer.flush()
    if channel.exit_status_ready():
        break
sys.exit(channel.recv_exit_status())
" "$@"
""")
    os.chmod(wrapper_script, 0o755)
    return wrapper_script

if __name__ == "__main__":
    wrapper = git_push_via_ssh(".")
    print(f"Wrapper created: {wrapper}")
