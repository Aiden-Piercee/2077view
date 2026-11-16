"""Cyberpunk 2077 save game metadata reader & CET command generator."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import json
from typing import Any


@dataclass
class CharacterProfile:
    save_name: str
    life_path: str
    body_gender: str  # FemV | MascV
    level: int
    street_cred: int
    play_time_hours: float
    difficulty: str
    timestamp: str
    save_path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _normalize_gender(raw: str | None) -> str:
    if not raw:
        return "FemV"
    lowered = raw.lower()
    if "female" in lowered or "fem" in lowered:
        return "FemV"
    if "male" in lowered or "masc" in lowered:
        return "MascV"
    return "FemV"


def parse_save_metadata(metadata_path: Path) -> CharacterProfile:
    """Parse a Cyberpunk 2077 metadata.9.json save file."""
    data = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
    meta = data.get("Data", {}).get("metadata", data)

    body_gender = _normalize_gender(
        meta.get("bodyGender") or meta.get("gender") or "Female"
    )
    play_seconds = float(meta.get("playTime", 0) or 0)
    return CharacterProfile(
        save_name=metadata_path.parent.name,
        life_path=str(meta.get("lifePath", "StreetKid")),
        body_gender=body_gender,
        level=int(float(meta.get("level", 1) or 1)),
        street_cred=int(float(meta.get("streetCred", 1) or 1)),
        play_time_hours=round(play_seconds / 3600.0, 1),
        difficulty=str(meta.get("difficulty", "Hard")),
        timestamp=str(meta.get("timestampString", "")),
        save_path=str(metadata_path.parent),
    )


def discover_saves(save_dir: Path) -> list[CharacterProfile]:
    """Scan a Cyberpunk 2077 save directory for metadata.9.json files."""
    save_dir = Path(save_dir)
    if not save_dir.exists():
        return []

    profiles: list[CharacterProfile] = []
    for meta_file in sorted(save_dir.rglob("metadata.9.json"), reverse=True):
        try:
            profiles.append(parse_save_metadata(meta_file))
        except (OSError, json.JSONDecodeError, ValueError):
            continue
    return profiles


def generate_cet_commands(tweak_ids: list[str], quantity: int = 1) -> str:
    """Generate Cyber Engine Tweaks (CET) console commands to add items to V's inventory."""
    lines = [f'Game.AddToInventory("{tid}", {quantity})' for tid in tweak_ids if tid]
    return "\n".join(lines)

