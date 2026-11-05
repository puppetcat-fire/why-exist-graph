"""证据校验：产物 hash 与同代 evidence 的采信条件。"""

from __future__ import annotations

import hashlib
from pathlib import Path

__all__ = ["evidence_qualifies", "sha256_file"]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def evidence_qualifies(conn, feature_id: str, generation: int) -> bool:
    """BehaviorPassed 采信的 evidence：同代、exit_code=0，且产物仍存在 / hash 未变。"""
    rows = conn.execute(
        "SELECT artifact_path, artifact_sha256 FROM evidence "
        "WHERE feature_id=? AND generation=? AND exit_code=0",
        (feature_id, generation),
    ).fetchall()
    for row in rows:
        path = row["artifact_path"]
        if path:
            artifact = Path(path)
            if not artifact.is_file():
                continue
            if row["artifact_sha256"] and sha256_file(artifact) != row["artifact_sha256"]:
                continue
        return True
    return False
