"""
TITAN OMNISCALE X - Merkle Ledger v13 (Sandbox Isolated)

Ledger con arbol Merkle real para integridad criptografica.
Soporta snapshots, commits con verificacion, y rollbacks atomicos.

v13 - AISLAMIENTO:
- Los commits se escriben en el workspace AISLADO del sandbox
- NUNCA escribe directamente en el filesystem del proyecto real
- Los snapshots y rollbacks operan dentro del workspace aislado
- Las DBs del ledger son INDEPENDIENTES cuando opera en sandbox

Sin dependencias externas. Compatible con Android.
"""

import hashlib
import shutil
import sqlite3
import time
import logging
from pathlib import Path
from src.core.shared.contracts import MerkleNode
from src.core.shared.db_initializer import get_data_dir, get_connection

logger = logging.getLogger(__name__)


class MerkleLedger:
    """Ledger con arbol Merkle para integridad criptografica. Sandbox-isolated."""

    def __init__(self):
        self.bk_dir = get_data_dir() / "backups"
        self.bk_dir.mkdir(exist_ok=True)
        self._init_db()

    def _init_db(self):
        conn = get_connection("merkle_ledger.sqlite")
        conn.execute("""CREATE TABLE IF NOT EXISTS ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT NOT NULL,
            hash_sha256 TEXT NOT NULL,
            parent_hash TEXT NOT NULL,
            operation TEXT NOT NULL,
            timestamp REAL NOT NULL)""")
        conn.commit()

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

    def _get_last_hash(self, file_path, db_path=None):
        """Obtiene el ultimo hash para un archivo. Si db_path se proporciona, usa esa DB."""
        try:
            if db_path:
                conn = sqlite3.connect(db_path)
            else:
                conn = get_connection("merkle_ledger.sqlite")
            r = conn.execute(
                "SELECT hash_sha256 FROM ledger WHERE file_path=? ORDER BY id DESC LIMIT 1",
                (file_path,)).fetchone()
            if db_path:
                conn.close()
            return r[0] if r else "GENESIS"
        except Exception:
            return "GENESIS"

    def _record_operation(self, file_path, content_hash, parent_hash, operation, db_path=None):
        """Registra una operacion en el ledger. Si db_path se proporciona, usa esa DB."""
        if db_path:
            conn = sqlite3.connect(db_path)
        else:
            conn = get_connection("merkle_ledger.sqlite")
        conn.execute(
            "INSERT INTO ledger (file_path, hash_sha256, parent_hash, operation, timestamp) VALUES (?,?,?,?,?)",
            (file_path, content_hash, parent_hash, operation, time.time()))
        conn.commit()
        if db_path:
            conn.close()

    def snapshot(self, rel_path, project_dir, workspace=None):
        """
        Crea un snapshot (backup) de un archivo.

        Si se proporciona workspace, opera DENTRO del workspace aislado.
        Si no, opera en el directorio de proyectos del sistema (legacy).
        """
        if workspace is not None:
            # MODO AISLADO: operar dentro del workspace del sandbox
            content = workspace.read_project_file(rel_path)
            if content:
                workspace.snapshot_project_file(rel_path, content)
                content_hash = self._hash_content(content)
                parent_hash = self._get_last_hash(rel_path, workspace.get_db_path("merkle_ledger.sqlite"))
                # Inicializar DB del sandbox si no existe
                self._ensure_sandbox_db(workspace)
                self._record_operation(
                    rel_path, content_hash, parent_hash, "SNAPSHOT",
                    workspace.get_db_path("merkle_ledger.sqlite")
                )
                logger.debug("Snapshot (sandbox): %s in workspace %s", rel_path, workspace.sandbox_id)
        else:
            # MODO LEGACY: operar en el filesystem del sistema
            p = Path(project_dir) / rel_path
            if p.exists():
                content = p.read_text(encoding="utf-8")
                bk_path = self.bk_dir / rel_path.replace("/", "_")
                shutil.copy2(p, bk_path)
                content_hash = self._hash_content(content)
                parent_hash = self._get_last_hash(rel_path)
                self._record_operation(rel_path, content_hash, parent_hash, "SNAPSHOT")

    def commit(self, rel_path, content, project_dir, workspace=None):
        """
        Escribe contenido y registra el commit en el ledger.

        Si se proporciona workspace, escribe DENTRO del workspace aislado
        en vez del filesystem del proyecto real.

        Returns:
            MerkleNode con el hash del commit
        """
        if workspace is not None:
            # MODO AISLADO: escribir en el workspace del sandbox
            workspace.write_project_file(rel_path, content)
            content_hash = self._hash_content(content)
            self._ensure_sandbox_db(workspace)
            parent_hash = self._get_last_hash(rel_path, workspace.get_db_path("merkle_ledger.sqlite"))
            merkle_hash = self._merkle_root([content_hash, parent_hash])
            self._record_operation(
                rel_path, merkle_hash, parent_hash, "COMMIT",
                workspace.get_db_path("merkle_ledger.sqlite")
            )
            logger.info("Commit (sandbox): %s -> %s in workspace %s",
                        rel_path, merkle_hash[:12], workspace.sandbox_id)
        else:
            # MODO LEGADO: escribir en el filesystem del sistema
            p = Path(project_dir) / rel_path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            content_hash = self._hash_content(content)
            parent_hash = self._get_last_hash(rel_path)
            merkle_hash = self._merkle_root([content_hash, parent_hash])
            self._record_operation(rel_path, merkle_hash, parent_hash, "COMMIT")

        return MerkleNode(
            file_path=rel_path, hash_sha256=merkle_hash,
            parent_hash=parent_hash, timestamp=time.time(), operation="COMMIT"
        )

    def rollback(self, rel_path, project_dir, workspace=None):
        """
        Restaura un archivo desde el backup.

        Si se proporciona workspace, restaura DENTRO del workspace aislado.

        Returns:
            bool: True si el rollback fue exitoso
        """
        if workspace is not None:
            # MODO AISLADO: restaurar dentro del workspace
            success = workspace.rollback_project_file(rel_path)
            if success:
                content = workspace.read_project_file(rel_path)
                content_hash = self._hash_content(content)
                self._ensure_sandbox_db(workspace)
                parent_hash = self._get_last_hash(rel_path, workspace.get_db_path("merkle_ledger.sqlite"))
                self._record_operation(
                    rel_path, content_hash, parent_hash, "ROLLBACK",
                    workspace.get_db_path("merkle_ledger.sqlite")
                )
                logger.info("Rollback (sandbox): %s in workspace %s", rel_path, workspace.sandbox_id)
            else:
                logger.warning("Rollback (sandbox): no backup for %s in workspace %s",
                               rel_path, workspace.sandbox_id)
            return success
        else:
            # MODO LEGADO: restaurar en el filesystem
            bk = self.bk_dir / rel_path.replace("/", "_")
            p = Path(project_dir) / rel_path
            if bk.exists():
                shutil.copy2(bk, p)
                content = p.read_text(encoding="utf-8")
                content_hash = self._hash_content(content)
                parent_hash = self._get_last_hash(rel_path)
                self._record_operation(rel_path, content_hash, parent_hash, "ROLLBACK")
                logger.info("Rollback successful: %s", rel_path)
                return True
            elif p.exists():
                logger.warning("Rollback: no backup found for %s. Current file unchanged.", rel_path)
                return False
        return False

    def _ensure_sandbox_db(self, workspace):
        """Asegura que la DB del ledger existe en el workspace del sandbox."""
        db_path = workspace.get_db_path("merkle_ledger.sqlite")
        db_dir = Path(db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
        if not Path(db_path).exists():
            with sqlite3.connect(db_path) as conn:
                conn.execute("""CREATE TABLE IF NOT EXISTS ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT NOT NULL,
                    hash_sha256 TEXT NOT NULL,
                    parent_hash TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    timestamp REAL NOT NULL)""")
