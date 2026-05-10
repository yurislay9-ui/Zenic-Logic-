#!/usr/bin/env python3
"""Git push via paramiko - direct approach."""

import paramiko
import os
import sys

SSH_KEY_PATH = os.path.expanduser("~/.ssh/id_rsa_github")
REPO_DIR = os.path.dirname(os.path.abspath(__file__))


def push():
    print("Loading SSH key...")
    key = paramiko.RSAKey.from_private_key_file(SSH_KEY_PATH)

    print("Connecting to GitHub...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect("github.com", username="git", pkey=key, timeout=30)

    print("Running git push via SSH...")
    # Use git-receive-pack protocol
    # Actually, let's try exec_command with git push
    # Git push is a local operation, we need to use the git protocol over SSH
    
    # Instead, let's use a different approach: run git-receive-pack manually
    # This is the proper way to push over SSH without a local git SSH client
    
    # Step 1: Get local refs
    import subprocess
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_DIR, capture_output=True, text=True
    )
    local_head = result.stdout.strip()
    print(f"Local HEAD: {local_head}")

    # Step 2: Get the objects we need to push
    result = subprocess.run(
        ["git", "rev-list", "--objects", "origin/main..HEAD"],
        cwd=REPO_DIR, capture_output=True, text=True
    )
    objects = result.stdout.strip()
    print(f"Objects to push: {len(objects.splitlines())} items")

    if not objects:
        print("Nothing to push!")
        client.close()
        return

    # Step 3: Create a pack file
    result = subprocess.run(
        ["git", "rev-parse", "origin/main"],
        cwd=REPO_DIR, capture_output=True, text=True
    )
    remote_head = result.stdout.strip() if result.returncode == 0 else "0000000000000000000000000000000000000000"
    print(f"Remote HEAD: {remote_head}")

    # Step 4: Use git send-pack (if available) or manually implement the protocol
    # Let's try git push with the SSH transport via paramiko channel
    
    # Open a transport channel for git-receive-pack
    transport = client.get_transport()
    channel = transport.open_session()
    channel.exec_command("git-receive-pack '/yurislay9-ui/Zenic-Logic-.git'")

    # Read the reference advertisement
    import time
    time.sleep(2)  # Wait for data
    
    ref_data = b""
    while channel.recv_ready():
        ref_data += channel.recv(65536)
    
    print(f"Received ref data: {len(ref_data)} bytes")
    
    # Parse refs to find remote HEAD
    remote_refs = {}
    if ref_data:
        # Skip first line (service announcement) 
        lines = ref_data.split(b"\n")
        for line in lines:
            if b" " in line and b"\x00" not in line:
                parts = line.strip().split(b" ", 1)
                if len(parts) == 2:
                    sha = parts[0].decode()
                    ref = parts[1].decode()
                    remote_refs[ref] = sha
    
    print(f"Remote refs: {list(remote_refs.keys())[:5]}...")

    # Build the update command
    # Format: <old-sha> <new-sha> <ref-name>\n
    # Then a pack file
    old_sha = remote_refs.get("refs/heads/main", "0" * 40)
    update_cmd = f"{old_sha} {local_head} refs/heads/main\n".encode()
    
    # Add flush packet
    update_cmd += b"0000"
    
    # Create pack data
    result = subprocess.run(
        ["git", "pack-objects", "--stdout", "--thin"],
        cwd=REPO_DIR,
        input=subprocess.run(
            ["git", "rev-list", "--objects", f"{old_sha}..{local_head}"],
            cwd=REPO_DIR, capture_output=True, text=True
        ).stdout.encode(),
        capture_output=True,
    )
    pack_data = result.stdout
    print(f"Pack data: {len(pack_data)} bytes")

    # Send everything
    channel.sendall(update_cmd + pack_data)
    channel.shutdown_write()

    # Read response
    time.sleep(3)
    response = b""
    while channel.recv_ready():
        response += channel.recv(65536)
    
    print(f"Response: {response.decode(errors='replace')}")
    
    channel.close()
    client.close()
    print("Done!")


if __name__ == "__main__":
    push()
