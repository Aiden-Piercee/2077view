"""Rejection & mod quarantine/removal management for 2077view."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
import json
import shutil
from typing import Any

from cp2077_atelier.scanner import ClothingItem


@dataclass
class QuarantineRecord:
    record_id: str
    item_ids: list[str]
    item_names: list[str]
    source_mod: str
    files: list[str]  # relative paths
    quarantined_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class QuarantineManager:
    """Manages rejected item flags, moving mod files to quarantine, restoring, and deleting."""

    def __init__(self, mod_dir: Path, quarantine_dir: Path, state_file: Path):
        self.mod_dir = Path(mod_dir)
        self.quarantine_dir = Path(quarantine_dir)
        self.state_file = Path(state_file)
        self._state = self._load_state()

    def _load_state(self) -> dict[str, Any]:
        if self.state_file.exists():
            try:
                data = json.loads(self.state_file.read_text(encoding="utf-8"))
                return {
                    "rejected_ids": list(dict.fromkeys(data.get("rejected_ids", []))),
                    "quarantined": list(data.get("quarantined", [])),
                }
            except (OSError, json.JSONDecodeError):
                pass
        return {"rejected_ids": [], "quarantined": []}

    def _save_state(self) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(self._state, indent=2), encoding="utf-8")

    @property
    def rejected_ids(self) -> set[str]:
        return set(self._state["rejected_ids"])

    def list_quarantined(self) -> list[dict[str, Any]]:
        return list(self._state["quarantined"])

    def reject_items(self, item_ids: list[str]) -> list[str]:
        current = set(self._state["rejected_ids"])
        current.update(item_ids)
        self._state["rejected_ids"] = sorted(current)
        self._save_state()
        return self._state["rejected_ids"]

    def unreject_items(self, item_ids: list[str]) -> list[str]:
        remove_set = set(item_ids)
        self._state["rejected_ids"] = [
            iid for iid in self._state["rejected_ids"] if iid not in remove_set
        ]
        self._save_state()
        return self._state["rejected_ids"]

    def _safe_rel_path(self, rel_path: str) -> Path:
        """Prevent path traversal outside mod_dir / quarantine_dir."""
        clean = Path(rel_path)
        if clean.is_absolute() or ".." in clean.parts:
            raise ValueError(f"Unsafe relative path: {rel_path}")
        return clean

    def execute_quarantine(
        self,
        items: list[ClothingItem],
        target_item_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Move files for rejected (or specified) items from mod_dir to quarantine_dir."""
        ids_to_quarantine = (
            set(target_item_ids) if target_item_ids is not None else self.rejected_ids
        )
        if not ids_to_quarantine:
            return {"moved_files": [], "records": [], "skipped": []}

        selected = [it for it in items if it.id in ids_to_quarantine]
        if not selected:
            return {"moved_files": [], "records": [], "skipped": []}

        self.quarantine_dir.mkdir(parents=True, exist_ok=True)
        moved_files: list[str] = []
        skipped: list[str] = []
        created_records: list[dict[str, Any]] = []

        # Group by source_mod so shared package files are tracked cleanly together
        by_mod: dict[str, list[ClothingItem]] = {}
        for it in selected:
            by_mod.setdefault(it.source_mod, []).append(it)

        now = datetime.now(timezone.utc).isoformat()
        for source_mod, mod_items in by_mod.items():
            unique_files: list[str] = []
            seen: set[str] = set()
            for it in mod_items:
                for rel in it.associated_files:
                    if rel not in seen:
                        seen.add(rel)
                        unique_files.append(rel)

            mod_moved: list[str] = []
            for rel in unique_files:
                safe_rel = self._safe_rel_path(rel)
                src = self.mod_dir / safe_rel
                dst = self.quarantine_dir / safe_rel
                if not src.exists():
                    skipped.append(rel)
                    continue
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
                moved_files.append(rel)
                mod_moved.append(rel)

                # Clean up empty parent directories inside mod_dir
                parent = src.parent
                while parent != self.mod_dir and parent.exists():
                    try:
                        parent.rmdir()
                    except OSError:
                        break
                    parent = parent.parent

            if mod_moved:
                rec = QuarantineRecord(
                    record_id=f"q_{int(datetime.now(timezone.utc).timestamp() * 1000)}_{len(self._state['quarantined'])}",
                    item_ids=[it.id for it in mod_items],
                    item_names=[it.name for it in mod_items],
                    source_mod=source_mod,
                    files=mod_moved,
                    quarantined_at=now,
                )
                rec_dict = rec.to_dict()
                self._state["quarantined"].append(rec_dict)
                created_records.append(rec_dict)

        # Remove quarantined item IDs from pending rejected_ids
        quarantined_item_ids = {it.id for it in selected}
        self._state["rejected_ids"] = [
            iid for iid in self._state["rejected_ids"] if iid not in quarantined_item_ids
        ]
        self._save_state()

        return {
            "moved_files": moved_files,
            "records": created_records,
            "skipped": skipped,
        }

    def restore_quarantined(self, record_id: str) -> dict[str, Any]:
        """Restore a quarantined mod record's files back into mod_dir."""
        target_idx = None
        for idx, rec in enumerate(self._state["quarantined"]):
            if rec.get("record_id") == record_id:
                target_idx = idx
                break

        if target_idx is None:
            raise KeyError(f"Quarantine record not found: {record_id}")

        rec = self._state["quarantined"][target_idx]
        restored_files: list[str] = []
        missing_files: list[str] = []

        for rel in rec.get("files", []):
            safe_rel = self._safe_rel_path(rel)
            src = self.quarantine_dir / safe_rel
            dst = self.mod_dir / safe_rel
            if not src.exists():
                missing_files.append(rel)
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            restored_files.append(rel)

            parent = src.parent
            while parent != self.quarantine_dir and parent.exists():
                try:
                    parent.rmdir()
                except OSError:
                    break
                parent = parent.parent

        self._state["quarantined"].pop(target_idx)
        self._save_state()
        return {
            "record_id": record_id,
            "restored_files": restored_files,
            "missing_files": missing_files,
        }

    def delete_quarantined(self, record_id: str, confirm: bool = False) -> dict[str, Any]:
        """Permanently delete a quarantined mod record's files (requires confirm=True)."""
        if not confirm:
            raise PermissionError("Permanent deletion requires confirm=True.")

        target_idx = None
        for idx, rec in enumerate(self._state["quarantined"]):
            if rec.get("record_id") == record_id:
                target_idx = idx
                break

        if target_idx is None:
            raise KeyError(f"Quarantine record not found: {record_id}")

        rec = self._state["quarantined"].pop(target_idx)
        deleted_files: list[str] = []
        for rel in rec.get("files", []):
            safe_rel = self._safe_rel_path(rel)
            target = self.quarantine_dir / safe_rel
            if target.exists():
                target.unlink()
                deleted_files.append(rel)
                parent = target.parent
                while parent != self.quarantine_dir and parent.exists():
                    try:
                        parent.rmdir()
                    except OSError:
                        break
                    parent = parent.parent

        self._save_state()
        return {"record_id": record_id, "deleted_files": deleted_files}

