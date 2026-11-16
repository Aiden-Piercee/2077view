"""Persistent in-memory WolvenKitDaemon bridge for sub-second .png preview & .glb 3D mesh extraction."""

from __future__ import annotations

from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
from typing import Any


_DAEMON_LOCK = threading.Lock()
_DAEMON_PROC: subprocess.Popen[str] | None = None
_DAEMON_DIR: Path | None = None
_PRIORITY_WAITING = 0
_BATCH_EXTRACTED_ARCHIVES: set[str] = set()
_SHARED_PNG_INDEX: list[str] = []

CACHE_MARKER_VERSION = "v3"

# Uncook base .mesh files and diffuse/color .xbm textures (skipping duplicate body refits and normal/roughness/mask maps)
FAST_UNCOOK_REGEX = (
    r"^(?!.*(_ebb|_rb|_angel|_lush|_solo|_gymfiend|_adonis|_vtk|original\d|_lod|_shadow|lining|normal|roughness|metallic|_n0|_rm0|\.mlmask))"
    r".*(\.mesh|\.xbm|\.bin)$"
)

ICON_ONLY_REGEX = r".*((icon|preview|atlas|ui|thumb|store).*\.xbm|\.bin)$"


def find_wolvenkit_cli(project_root: Path | None = None) -> Path | None:
    """Locate WolvenKitDaemon.exe or WolvenKit.CLI.exe in tools/wolvenkit."""
    if project_root:
        daemon = Path(project_root) / "tools" / "wolvenkit" / "WolvenKitDaemon.exe"
        if daemon.exists():
            return daemon
        local = Path(project_root) / "tools" / "wolvenkit" / "WolvenKit.CLI.exe"
        if local.exists():
            return local
    which = shutil.which("WolvenKit.CLI") or shutil.which("WolvenKit.CLI.exe")
    return Path(which) if which else None


def _ensure_daemon(cli_path: Path) -> subprocess.Popen[str] | None:
    """Start or return the persistent WolvenKitDaemon.exe process (keeps IHost & hashes warm in RAM)."""
    global _DAEMON_PROC, _DAEMON_DIR
    daemon_exe = cli_path.parent / "WolvenKitDaemon.exe"
    if not daemon_exe.exists():
        return None
    if _DAEMON_PROC is not None and _DAEMON_PROC.poll() is None:
        return _DAEMON_PROC

    _DAEMON_DIR = daemon_exe.parent
    proc = subprocess.Popen(
        [str(daemon_exe)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        cwd=str(_DAEMON_DIR),
        bufsize=1,
    )
    ready_line = proc.stdout.readline().strip() if proc.stdout else ""
    if ready_line != "READY":
        try:
            proc.kill()
        except OSError:
            pass
        return None
    _DAEMON_PROC = proc
    return _DAEMON_PROC


def _run_uncook(
    cli_path: Path,
    out_dir: Path,
    regex: str,
    archive_paths: list[Path],
    timeout_sec: int = 30,
) -> bool:
    """Run uncook via the warm in-memory WolvenKitDaemon (~100-800ms) or fallback to CLI."""
    if not archive_paths:
        return True
    out_dir.mkdir(parents=True, exist_ok=True)
    with _DAEMON_LOCK:
        proc = _ensure_daemon(cli_path)
        if proc and proc.stdin and proc.stdout:
            try:
                arch_joined = "|".join(str(p.resolve()) for p in archive_paths)
                cmd_line = f"{out_dir.resolve()}\t{regex}\t{arch_joined}\n"
                proc.stdin.write(cmd_line)
                proc.stdin.flush()
                resp = proc.stdout.readline().strip()
                if resp.startswith("OK"):
                    return True
            except OSError:
                global _DAEMON_PROC
                _DAEMON_PROC = None

    cmd = [
        str(cli_path.parent / "WolvenKit.CLI.exe" if cli_path.name == "WolvenKitDaemon.exe" else cli_path),
        "uncook",
        *[str(p) for p in archive_paths],
        "-o",
        str(out_dir),
        "--uext",
        "png",
        "-r",
        regex,
        "-v",
        "Quiet",
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec, check=False)
        return True
    except subprocess.TimeoutExpired:
        return False


def warm_up_daemon_async(cli_path: Path | None, sample_archive: Path | None = None, cache_root: Path | None = None) -> None:
    """Pre-warm the persistent WolvenKitDaemon and its hash table in a background thread."""
    if not cli_path:
        return

    def _warm() -> None:
        with _DAEMON_LOCK:
            proc = _ensure_daemon(cli_path)
            if proc and sample_archive and sample_archive.exists() and cache_root and proc.stdin and proc.stdout:
                warm_dir = Path(cache_root) / "_warmup"
                warm_dir.mkdir(parents=True, exist_ok=True)
                try:
                    proc.stdin.write(f"{warm_dir.resolve()}\t{ICON_ONLY_REGEX}\t{sample_archive.resolve()}\n")
                    proc.stdin.flush()
                    proc.stdout.readline()
                except OSError:
                    pass

    threading.Thread(target=_warm, daemon=True).start()


def safe_archive_key(archive_path: Path) -> str:
    """Return a URL-safe cache folder name without '#', '?', or spaces."""
    cleaned = re.sub(r"[^A-Za-z0-9_\-]", "_", archive_path.stem).strip("_")
    return cleaned or "archive"


def _collect_extracted(
    out_dir: Path,
    cache_root: Path,
    item_hint: str = "",
) -> dict[str, list[str]]:
    """Collect and rank extracted .glb 3D meshes, 3D diffuse textures (.png), and 2D icons (.png)."""
    if not out_dir.exists():
        return {"images": [], "meshes": [], "textures": []}

    hint_tokens = [
        t for t in re.split(r"[^a-z0-9]+", item_hint.lower())
        if len(t) >= 3 and t not in ("items", "default", "base", "body", "name", "archive")
    ]

    img_candidates: list[tuple[int, str]] = []
    tex_candidates: list[tuple[int, int, str]] = []
    mesh_candidates: list[tuple[int, int, str]] = []

    for p in out_dir.rglob("*"):
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        rel = p.relative_to(cache_root).as_posix()
        rel_l = rel.lower()
        stem_l = p.stem.lower()
        size = p.stat().st_size

        if ext in (".png", ".jpg", ".jpeg", ".webp"):
            if size < 3000:
                continue
            is_pbr_map = any(k in stem_l for k in ("_mask", "masksset", "_n0", "_rm0", "normal", "roughness", "metallic", "opacity"))
            is_icon_sheet = any(k in rel_l for k in ("icon", "preview", "atlas", "thumb", "store", "inkatlas"))
            hint_match = sum(1 for tok in hint_tokens if tok in rel_l)

            # Candidate for 3D surface texture (prefer diffuse / base color / albedo / non-icon textures)
            if not is_pbr_map and not is_icon_sheet:
                is_diffuse = any(k in stem_l for k in ("base_color", "base color", "albedo", "diffuse", "_d0", "color", "tex", "cloth", "leather", "fabric"))
                tex_score = (40 if is_diffuse else 10) + hint_match * 25
                tex_candidates.append((-tex_score, -size, rel))
            elif not is_pbr_map and is_icon_sheet:
                # Fallback texture if no dedicated diffuse texture exists
                tex_candidates.append((10 - hint_match * 10, -size, rel))

            # Candidate for 2D icon
            is_icon_sized = 4000 <= size <= 950_000
            score = (50 if not is_pbr_map else 0) + (35 if is_icon_sheet else 0) + (25 if is_icon_sized else 0) + hint_match * 20
            img_candidates.append((-score, rel))

        elif ext in (".glb", ".gltf", ".obj"):
            if size < 500:
                continue
            hint_match = sum(1 for tok in hint_tokens if tok in stem_l)
            mesh_candidates.append((-hint_match, -size, rel))

    img_candidates.sort()
    tex_candidates.sort()
    mesh_candidates.sort()

    return {
        "images": [rel for _, rel in img_candidates],
        "textures": [rel for _, _, rel in tex_candidates],
        "meshes": [rel for _, _, rel in mesh_candidates],
    }


def _is_marker_valid(marker: Path) -> bool:
    if not marker.exists():
        return False
    try:
        return marker.read_text(encoding="utf-8").strip() == CACHE_MARKER_VERSION
    except OSError:
        return False


def uncook_archive(
    archive_path: Path,
    game_dir: Path,
    cache_root: Path,
    cli_path: Path,
    item_hint: str = "",
    timeout_sec: int = 30,
    priority: bool = True,
) -> dict[str, Any]:
    """Fast in-memory uncook of base .mesh -> .glb and icon .xbm -> .png (~100-800ms via WolvenKitDaemon)."""
    global _PRIORITY_WAITING
    archive_path = Path(archive_path)
    safe_key = safe_archive_key(archive_path)
    out_dir = Path(cache_root) / safe_key
    marker = out_dir / ".done"

    if _is_marker_valid(marker):
        assets = _collect_extracted(out_dir, cache_root, item_hint=item_hint)
        return {"cached": True, "out_dir": str(out_dir), **assets}

    if priority:
        _PRIORITY_WAITING += 1
    try:
        if _is_marker_valid(marker):
            assets = _collect_extracted(out_dir, cache_root, item_hint=item_hint)
            return {"cached": True, "out_dir": str(out_dir), **assets}

        _run_uncook(cli_path, out_dir, FAST_UNCOOK_REGEX, [archive_path], timeout_sec=timeout_sec)
        assets = _collect_extracted(out_dir, cache_root, item_hint=item_hint)
        marker.write_text(CACHE_MARKER_VERSION, encoding="utf-8")
        return {
            "cached": False,
            "out_dir": str(out_dir),
            **assets,
        }
    finally:
        if priority:
            _PRIORITY_WAITING = max(0, _PRIORITY_WAITING - 1)


def extract_preview_only(
    archive_path: Path,
    cache_root: Path,
    cli_path: Path,
    item_hint: str = "",
    timeout_sec: int = 25,
) -> dict[str, Any]:
    """Background preview + mesh extractor (yields to priority 3D inspector requests)."""
    while _PRIORITY_WAITING > 0:
        time.sleep(0.05)
    res = uncook_archive(
        archive_path=archive_path,
        game_dir=archive_path.parent,
        cache_root=cache_root,
        cli_path=cli_path,
        item_hint=item_hint,
        timeout_sec=timeout_sec,
        priority=False,
    )
    return {
        "cached": res.get("cached", False),
        "image": res["images"][0] if res.get("images") else None,
        "texture": res["textures"][0] if res.get("textures") else None,
        "mesh": res["meshes"][0] if res.get("meshes") else None,
        "images": res.get("images", []),
        "textures": res.get("textures", []),
        "meshes": res.get("meshes", []),
    }


def _refresh_shared_png_index(cache_root: Path) -> list[str]:
    global _SHARED_PNG_INDEX
    shared_dir = Path(cache_root) / "_shared_icons"
    if not shared_dir.exists():
        _SHARED_PNG_INDEX = []
        return _SHARED_PNG_INDEX
    _SHARED_PNG_INDEX = [
        p.relative_to(cache_root).as_posix()
        for p in sorted(shared_dir.rglob("*.png"))
        if p.is_file() and p.stat().st_size >= 3000
    ]
    return _SHARED_PNG_INDEX


def match_shared_icon(
    cache_root: Path,
    atlas_path: str | None,
    source_mod: str,
    tweak_id: str,
) -> str | None:
    """Match an item to an extracted .png in _shared_icons using atlas_path or mod/item tokens."""
    shared_dir = Path(cache_root) / "_shared_icons"
    if not shared_dir.exists():
        return None

    if atlas_path:
        clean_atlas = atlas_path.replace("\\", "/").lstrip("/")
        png_cand = shared_dir / Path(clean_atlas).with_suffix(".png")
        if png_cand.exists() and png_cand.stat().st_size >= 3000:
            return png_cand.relative_to(cache_root).as_posix()
        parent_dir = (shared_dir / Path(clean_atlas).parent)
        if parent_dir.exists():
            siblings = [p for p in sorted(parent_dir.glob("*.png")) if p.stat().st_size >= 3000]
            if siblings:
                return siblings[0].relative_to(cache_root).as_posix()

    return None


def extract_page_icons_batch(
    archive_paths: list[Path],
    cache_root: Path,
    cli_path: Path,
    timeout_sec: int = 25,
) -> int:
    return 0
