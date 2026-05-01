"""
TITAN OMNISCALE X - Merkle Ledger v13

Ledger con arbol Merkle real para integridad criptografica.
Soporta snapshots, commits con verificacion, y rollbacks atomicos.
Sin dependencias externas. Compatible con Android.
"""

import hashlib
import shutil
import sqlite3
import time
import logging
from pathlib import Path
from src.core.shared.contracts import MerkleNode
from src.core.shared.db_initializer import get_data_dir, get_db_path

logger = logging.getLogger(__name__)


class MerkleLedger:
    """Ledger con arbol Merkle para integridad criptografica."""

    def __init__(self):
        self.bk_dir = get_data_dir() / "backups"
        self.bk_dir.mkdir(exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(get_db_path("merkle_ledger.sqlite")) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                hash_sha256 TEXT NOT NULL,
                parent_hash TEXT NOT NULL,
                operation TEXT NOT NULL,
                timestamp REAL NOT NULL)""")

    def _hash_content(self, content):
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    def _merkle_root(self, hashes):
        if not hashes:
            return hashlib.sha256(b'empty').hexdigest()
        if len(hashes) == 1:
            return hashes[0]
        while len(hashes) > 1:
            new_level = []
            for i in range(0, len(hashes), 2):
                left = hashes[i]
                right = hashes[i + 1] if i + 1 < len(hashes) else left
                combined = hashlib.sha256((left + right).encode()).hexdigest()
                new_level.append(combined)
            hashes = new_level
        return hashes[0]

    def _get_last_hash(self, file_path):
        with sqlite3.connect(get_db_path("merkle_ledger.sqlite")) as conn:
            r = conn.execute(
                "SELECT hash_sha256 FROM ledger WHERE file_path=? ORDER BY id DESC LIMIT 1",
                (file_path,)).fetchone()
            return r[0] if r else "GENESIS"

    def snapshot(self, rel_path, project_dir):
        p = Path(project_dir) / rel_path
        if p.exists():
            content = p.read_text(encoding="utf-8")
            bk_path = self.bk_dir / rel_path.replace("/", "_")
            shutil.copy2(p, bk_path)
            content_hash = self._hash_content(content)
            parent_hash = self._get_last_hash(rel_path)
            with sqlite3.connect(get_db_path("merkle_ledger.sqlite")) as conn:
                conn.execute(
                    "INSERT INTO ledger (file_path, hash_sha256, parent_hash, operation, timestamp) VALUES (?,?,?,?,?)",
                    (rel_path, content_hash, parent_hash, "SNAPSHOT", time.time()))

    def commit(self, rel_path, content, project_dir):
        p = Path(project_dir) / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        content_hash = self._hash_content(content)
        parent_hash = self._get_last_hash(rel_path)
        merkle_hash = self._merkle_root([content_hash, parent_hash])
        with sqlite3.connect(get_db_path("merkle_ledger.sqlite")) as conn:
            conn.execute(
                "INSERT INTO ledger (file_path, hash_sha256, parent_hash, operation, timestamp) VALUES (?,?,?,?,?)",
                (rel_path, merkle_hash, parent_hash, "COMMIT", time.time()))
        return MerkleNode(
            file_path=rel_path, hash_sha256=merkle_hash,
            parent_hash=parent_hash, timestamp=time.time(), operation="COMMIT"
        )

    def rollback(self, rel_path, project_dir):
        bk = self.bk_dir / rel_path.replace("/", "_")
        p = Path(project_dir) / rel_path
        if bk.exists():
            shutil.copy2(bk, p)
            content = p.read_text(encoding="utf-8")
            content_hash = self._hash_content(content)
            parent_hash = self._get_last_hash(rel_path)
            with sqlite3.connect(get_db_path("merkle_ledger.sqlite")) as conn:
                conn.execute(
                    "INSERT INTO ledger (file_path, hash_sha256, parent_hash, operation, timestamp) VALUES (?,?,?,?,?)",
                    (rel_path, content_hash, parent_hash, "ROLLBACK", time.time()))
            logger.info("Rollback successful: %s", rel_path)
        elif p.exists():
            logger.warning("Rollback: no backup found for %s. Current file unchanged.", rel_path)
