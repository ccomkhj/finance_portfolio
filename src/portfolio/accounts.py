from __future__ import annotations

import json
from pathlib import Path

from portfolio.snapshot import Snapshot, snapshot_from_dict, snapshot_to_dict


def save_snapshot(accounts_dir: Path, snap: Snapshot) -> Path:
    accounts_dir.mkdir(parents=True, exist_ok=True)
    path = accounts_dir / f"{snap.source}.json"
    path.write_text(json.dumps(snapshot_to_dict(snap), indent=2, ensure_ascii=False))
    return path


def load_snapshot(accounts_dir: Path, source: str) -> Snapshot:
    path = accounts_dir / f"{source}.json"
    return snapshot_from_dict(json.loads(path.read_text()))


def load_all(accounts_dir: Path) -> list[Snapshot]:
    if not accounts_dir.exists():
        return []
    return [
        snapshot_from_dict(json.loads(p.read_text()))
        for p in sorted(accounts_dir.glob("*.json"))
    ]


def list_sources(accounts_dir: Path) -> list[str]:
    if not accounts_dir.exists():
        return []
    return sorted(p.stem for p in accounts_dir.glob("*.json"))
