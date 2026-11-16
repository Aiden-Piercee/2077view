"""Configuration management for 2077view."""

from dataclasses import dataclass, asdict
from pathlib import Path
import json
import os


def default_cp2077_save_dir() -> Path:
    """Return the default Windows Cyberpunk 2077 save directory."""
    user_profile = os.environ.get("USERPROFILE", str(Path.home()))
    return Path(user_profile) / "Saved Games" / "CD Projekt Red" / "Cyberpunk 2077"


def detect_cp2077_installations() -> list[dict[str, str]]:
    """Detect common Cyberpunk 2077 installation and mod directories on Windows."""
    import re
    import string

    candidates: list[Path] = [
        Path(r"C:\Program Files (x86)\Steam\steamapps\common\Cyberpunk 2077"),
        Path(r"C:\Program Files (x86)\GOG Galaxy\Games\Cyberpunk 2077"),
        Path(r"C:\Program Files\Epic Games\Cyberpunk 2077"),
    ]

    # Check all existing drive roots for common game/mod folders
    for letter in string.ascii_uppercase:
        drive = Path(f"{letter}:\\")
        if not drive.exists():
            continue
        for sub in ("Games", "SteamLibrary\\steamapps\\common", "GOG Games", "Vortex Mods"):
            parent = drive / sub
            if parent.exists():
                try:
                    for child in parent.iterdir():
                        if child.is_dir() and "cyberpunk" in child.name.lower():
                            candidates.append(child)
                except OSError:
                    pass

    # Parse Steam libraryfolders.vdf if available
    vdf = Path(r"C:\Program Files (x86)\Steam\steamapps\libraryfolders.vdf")
    if vdf.exists():
        try:
            text = vdf.read_text(encoding="utf-8", errors="ignore")
            for m in re.finditer(r'"path"\s+"([^"]+)"', text):
                lib = Path(m.group(1).replace("\\\\", "\\"))
                candidates.append(lib / "steamapps" / "common" / "Cyberpunk 2077")
        except OSError:
            pass

    found: list[dict[str, str]] = []
    seen: set[str] = set()
    for path in candidates:
        resolved = str(path.resolve()) if path.exists() else ""
        if resolved and resolved not in seen:
            seen.add(resolved)
            has_mods = (path / "archive" / "pc" / "mod").exists()
            found.append({
                "path": resolved,
                "label": f"{path.name} ({'archive/pc/mod found' if has_mods else 'game/mod folder'})",
                "mod_folder": str((path / "archive" / "pc" / "mod").resolve()) if has_mods else resolved,
            })
    return found


@dataclass
class AppConfig:
    mod_dir: Path
    quarantine_dir: Path
    state_file: Path
    save_dir: Path
    host: str = "127.0.0.1"
    port: int = 8077

    @classmethod
    def from_root(cls, root: Path, mod_dir: Path | None = None, quarantine_dir: Path | None = None,
                  save_dir: Path | None = None, port: int = 8077) -> "AppConfig":
        root = Path(root).resolve()
        resolved_mod = Path(mod_dir).resolve() if mod_dir else (root / "sample_mods")
        resolved_quarantine = Path(quarantine_dir).resolve() if quarantine_dir else (root / "_quarantine")
        resolved_state = root / ".2077view_state.json"
        resolved_save = Path(save_dir).resolve() if save_dir else default_cp2077_save_dir()
        return cls(
            mod_dir=resolved_mod,
            quarantine_dir=resolved_quarantine,
            state_file=resolved_state,
            save_dir=resolved_save,
            port=port,
        )

    def to_dict(self) -> dict:
        data = asdict(self)
        return {k: str(v) if isinstance(v, Path) else v for k, v in data.items()}

    def save_to_disk(self, config_path: Path) -> None:
        config_path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

