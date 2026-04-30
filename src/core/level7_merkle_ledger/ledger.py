import hashlib, shutil, logging
from pathlib import Path
from src.core.shared.contracts import MerkleNode
from src.core.shared.db_initializer import get_data_dir

logger = logging.getLogger(__name__)


class MerkleLedger:
    def __init__(self):
        self.bk_dir = get_data_dir().parent / "backups"
        self.bk_dir.mkdir(exist_ok=True)

    def _hash(self, path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""

    def snapshot(self, rel_path: str, project_dir: str):
        p = Path(project_dir) / rel_path
        if p.exists():
            bk_path = self.bk_dir / rel_path.replace("/", "_")
            shutil.copy2(p, bk_path)

    def commit(self, rel_path: str, content: str, project_dir: str) -> MerkleNode:
        p = Path(project_dir) / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return MerkleNode(file_path=rel_path, hash_sha256=self._hash(p))

    def rollback(self, rel_path: str, project_dir: str):
        bk = self.bk_dir / rel_path.replace("/", "_")
        p = Path(project_dir) / rel_path
        if bk.exists():
            shutil.copy2(bk, p)
            logger.info("Rollback exitoso: restaurado desde backup %s", bk)
        elif p.exists():
            # Si no hay backup pero el archivo existe, NO lo eliminamos
            # para evitar pérdida de datos. Solo registramos la advertencia.
            logger.warning(
                "Rollback: no se encontró backup para %s. El archivo actual se mantiene sin cambios.", rel_path
            )
