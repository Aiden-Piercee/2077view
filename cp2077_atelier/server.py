"""Local HTTP server & REST API for 2077view."""

from __future__ import annotations

from collections import Counter
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import mimetypes
import threading
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse

from cp2077_atelier.config import AppConfig, default_cp2077_save_dir, detect_cp2077_installations
from cp2077_atelier.mock_generator import generate_mock_mods
from cp2077_atelier.quarantine import QuarantineManager
from cp2077_atelier.save_reader import discover_saves, generate_cet_commands
from cp2077_atelier.scanner import ClothingItem, collect_mod_files, filter_and_sort_items, scan_mod_directory
from cp2077_atelier.wolvenkit_bridge import (
    extract_page_icons_batch,
    extract_preview_only,
    find_wolvenkit_cli,
    match_shared_icon,
    safe_archive_key,
    uncook_archive,
    warm_up_daemon_async,
)


STATIC_DIR = Path(__file__).parent / "static"


class AtelierAppState:
    """Shared thread-safe application state."""

    def __init__(self, config: AppConfig, async_scan: bool = False):
        self.lock = threading.RLock()
        self.config = config
        self.quarantine = QuarantineManager(
            config.mod_dir, config.quarantine_dir, config.state_file
        )
        self.items: list[ClothingItem] = []
        self.scanning = False
        self.cache_dir = config.state_file.parent / ".2077view_cache"
        self.wolvenkit_cli = find_wolvenkit_cli(config.state_file.parent)
        if async_scan:
            warm_up_daemon_async(self.wolvenkit_cli, None, self.cache_dir)
            self.rescan_async()
        else:
            self.rescan()

    def rescan(self) -> list[ClothingItem]:
        with self.lock:
            self.scanning = True
        try:
            scanned = scan_mod_directory(
                self.config.mod_dir, rejected_ids=self.quarantine.rejected_ids
            )
            with self.lock:
                self.items = scanned
                for it in scanned:
                    for rel in it.associated_files:
                        if rel.endswith(".archive"):
                            warm_up_daemon_async(self.wolvenkit_cli, self.config.mod_dir / rel, self.cache_dir)
                            return self.items
                return self.items
        finally:
            with self.lock:
                self.scanning = False

    def rescan_async(self) -> None:
        threading.Thread(target=self.rescan, daemon=True).start()

    def update_paths(
        self,
        mod_dir: str | None = None,
        quarantine_dir: str | None = None,
        save_dir: str | None = None,
    ) -> dict[str, Any]:
        with self.lock:
            if mod_dir:
                self.config.mod_dir = Path(mod_dir).resolve()
            if quarantine_dir:
                self.config.quarantine_dir = Path(quarantine_dir).resolve()
            if save_dir:
                self.config.save_dir = Path(save_dir).resolve()
            self.quarantine = QuarantineManager(
                self.config.mod_dir, self.config.quarantine_dir, self.config.state_file
            )
            self.rescan()
            return self.config.to_dict()


def make_handler(app_state: AtelierAppState) -> type[BaseHTTPRequestHandler]:
    class AtelierRequestHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            # Suppress noisy default stderr logging during tests unless debugging
            pass

        def _send_json(self, payload: Any, status: int = HTTPStatus.OK) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _send_file(self, file_path: Path) -> None:
            if not file_path.exists() or not file_path.is_file():
                self.send_error(HTTPStatus.NOT_FOUND, "File not found")
                return
            mime, _ = mimetypes.guess_type(str(file_path))
            if file_path.suffix.lower() == ".svg":
                mime = "image/svg+xml"
            elif file_path.suffix.lower() == ".obj":
                mime = "text/plain; charset=utf-8"
            data = file_path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", mime or "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _read_json_body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length <= 0:
                return {}
            raw = self.rfile.read(length)
            return json.loads(raw.decode("utf-8"))

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path

            if path == "/" or path == "/index.html":
                return self._send_file(STATIC_DIR / "index.html")

            if path.startswith("/static/"):
                rel = unquote(path[len("/static/"):])
                target = (STATIC_DIR / rel).resolve()
                if STATIC_DIR.resolve() not in target.parents and target != STATIC_DIR.resolve():
                    return self.send_error(HTTPStatus.FORBIDDEN)
                return self._send_file(target)

            if path.startswith("/mod-assets/"):
                rel = unquote(path[len("/mod-assets/"):])
                mod_root = app_state.config.mod_dir.resolve()
                target = (mod_root / rel).resolve()
                if mod_root not in target.parents:
                    return self.send_error(HTTPStatus.FORBIDDEN)
                return self._send_file(target)

            if path.startswith("/cache-assets/"):
                rel = unquote(path[len("/cache-assets/"):])
                cache_root = app_state.cache_dir.resolve()
                target = (cache_root / rel).resolve()
                if cache_root not in target.parents:
                    return self.send_error(HTTPStatus.FORBIDDEN)
                return self._send_file(target)

            if path == "/api/config":
                with app_state.lock:
                    return self._send_json(app_state.config.to_dict())

            if path == "/api/detect-installs":
                with app_state.lock:
                    mod_dir = app_state.config.mod_dir
                    if mod_dir.exists():
                        collected = collect_mod_files(mod_dir)
                        diag = {
                            "archive_count": len(collected["archives"]),
                            "tweak_count": len(collected["yamls"]),
                            "reds_count": len(collected["reds"]),
                        }
                    else:
                        diag = {"archive_count": 0, "tweak_count": 0, "reds_count": 0}
                    return self._send_json({
                        "installations": detect_cp2077_installations(),
                        "default_save_dir": str(default_cp2077_save_dir()),
                        "diagnostics": diag,
                    })

            if path == "/api/browse":
                qs = parse_qs(parsed.query)
                raw_path = qs.get("path", [""])[0].strip()
                if not raw_path:
                    import string
                    drives = [f"{d}:\\" for d in string.ascii_uppercase if Path(f"{d}:\\").exists()]
                    return self._send_json({"current": "", "parent": "", "dirs": [{"name": d, "path": d} for d in drives]})
                target_dir = Path(raw_path)
                if not target_dir.exists() or not target_dir.is_dir():
                    return self._send_json({"error": "Directory not found"}, HTTPStatus.NOT_FOUND)
                dirs = []
                try:
                    for child in sorted(target_dir.iterdir(), key=lambda p: p.name.lower()):
                        if child.is_dir() and not child.name.startswith("."):
                            dirs.append({"name": child.name, "path": str(child)})
                except OSError:
                    pass
                parent = str(target_dir.parent) if target_dir.parent != target_dir else ""
                return self._send_json({"current": str(target_dir), "parent": parent, "dirs": dirs[:200]})

            if path == "/api/items":
                qs = parse_qs(parsed.query)
                def qget(k: str, default: str = "") -> str:
                    return qs.get(k, [default])[0]

                with app_state.lock:
                    all_items = list(app_state.items)
                    filtered = filter_and_sort_items(
                        all_items,
                        query=qget("q"),
                        category=qget("category"),
                        source_mod=qget("source_mod"),
                        atelier_store=qget("atelier_store"),
                        body_type=qget("body_type"),
                        quality=qget("quality"),
                        tag=qget("tag"),
                        status=qget("status", "active"),
                        sort_by=qget("sort_by", "name"),
                        sort_dir=qget("sort_dir", "asc"),
                    )

                    page = max(1, int(qget("page", "1") or "1"))
                    page_size = max(1, min(500, int(qget("page_size", "60") or "60")))
                    start = (page - 1) * page_size
                    paged = filtered[start : start + page_size]

                    facets = {
                        "categories": dict(Counter(i.category for i in all_items)),
                        "source_mods": dict(Counter(i.source_mod for i in all_items)),
                        "atelier_stores": dict(Counter(i.atelier_store for i in all_items)),
                        "body_types": dict(Counter(i.body_type for i in all_items)),
                        "qualities": dict(Counter(i.quality for i in all_items)),
                        "tags": dict(Counter(t for i in all_items for t in i.tags).most_common(30)),
                    }

                    summary = {
                        "total_scanned": len(all_items),
                        "total_active": sum(1 for i in all_items if i.status == "active"),
                        "total_rejected": sum(1 for i in all_items if i.status == "rejected"),
                        "total_quarantined": len(app_state.quarantine.list_quarantined()),
                    }

                    return self._send_json({
                        "items": [i.to_dict() for i in paged],
                        "total_filtered": len(filtered),
                        "page": page,
                        "page_size": page_size,
                        "facets": facets,
                        "summary": summary,
                        "scanning": app_state.scanning,
                    })

            if path == "/api/quarantine":
                with app_state.lock:
                    return self._send_json({
                        "records": app_state.quarantine.list_quarantined(),
                        "rejected_ids": sorted(app_state.quarantine.rejected_ids),
                    })

            if path == "/api/saves":
                with app_state.lock:
                    saves = discover_saves(app_state.config.save_dir)
                    return self._send_json({
                        "save_dir": str(app_state.config.save_dir),
                        "saves": [s.to_dict() for s in saves],
                    })

            return self.send_error(HTTPStatus.NOT_FOUND, "Unknown endpoint")

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path

            try:
                body = self._read_json_body()
            except json.JSONDecodeError:
                return self._send_json({"error": "Invalid JSON body"}, HTTPStatus.BAD_REQUEST)

            if path == "/api/config":
                cfg = app_state.update_paths(
                    mod_dir=body.get("mod_dir"),
                    quarantine_dir=body.get("quarantine_dir"),
                    save_dir=body.get("save_dir"),
                )
                return self._send_json({"config": cfg, "total_items": len(app_state.items)})

            if path == "/api/rescan":
                items = app_state.rescan()
                return self._send_json({"total_items": len(items)})

            if path == "/api/generate-mock":
                count = int(body.get("count", 120))
                with app_state.lock:
                    generate_mock_mods(app_state.config.mod_dir, count=count)
                    items = app_state.rescan()
                return self._send_json({"generated": count, "total_items": len(items)})

            if path == "/api/reject":
                item_ids = list(body.get("item_ids", []))
                with app_state.lock:
                    rejected = app_state.quarantine.reject_items(item_ids)
                    app_state.rescan()
                return self._send_json({"rejected_ids": rejected})

            if path == "/api/unreject":
                item_ids = list(body.get("item_ids", []))
                with app_state.lock:
                    rejected = app_state.quarantine.unreject_items(item_ids)
                    app_state.rescan()
                return self._send_json({"rejected_ids": rejected})

            if path == "/api/quarantine/execute":
                target_ids = body.get("item_ids")
                with app_state.lock:
                    result = app_state.quarantine.execute_quarantine(
                        app_state.items, target_item_ids=target_ids
                    )
                    app_state.rescan()
                return self._send_json(result)

            if path == "/api/quarantine/restore":
                record_id = body.get("record_id", "")
                with app_state.lock:
                    try:
                        result = app_state.quarantine.restore_quarantined(record_id)
                    except KeyError as exc:
                        return self._send_json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
                    app_state.rescan()
                return self._send_json(result)

            if path == "/api/quarantine/delete":
                record_id = body.get("record_id", "")
                confirm = bool(body.get("confirm", False))
                with app_state.lock:
                    try:
                        result = app_state.quarantine.delete_quarantined(
                            record_id, confirm=confirm
                        )
                    except PermissionError as exc:
                        return self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                    except KeyError as exc:
                        return self._send_json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
                return self._send_json(result)

            if path == "/api/cet-commands":
                tweak_ids = list(body.get("tweak_ids", []))
                cmd = generate_cet_commands(tweak_ids)
                return self._send_json({"commands": cmd})

            if path == "/api/extract-page-batch":
                if not app_state.wolvenkit_cli:
                    return self._send_json({"results": {}})
                item_ids = list(body.get("item_ids", []))
                with app_state.lock:
                    id_map = {i.id: i for i in app_state.items}
                    mod_dir = app_state.config.mod_dir
                target_items = [id_map[iid] for iid in item_ids if iid in id_map]

                arch_paths: list[Path] = []
                seen_arch: set[str] = set()
                for it in target_items:
                    for rel in it.associated_files:
                        if rel.endswith(".archive"):
                            ap = mod_dir / rel
                            if str(ap) not in seen_arch and ap.exists():
                                seen_arch.add(str(ap))
                                arch_paths.append(ap)
                            break

                extract_page_icons_batch(arch_paths, app_state.cache_dir, app_state.wolvenkit_cli)

                results: dict[str, dict[str, str | None]] = {}
                for it in target_items:
                    img_rel = match_shared_icon(
                        app_state.cache_dir, it.atlas_path, it.source_mod, it.tweak_id
                    )
                    img_url = f"/cache-assets/{quote(img_rel, safe='/')}" if img_rel else None
                    results[it.id] = {"image": img_url}
                return self._send_json({"results": results})

            if path in ("/api/extract-item", "/api/extract-preview"):
                if not app_state.wolvenkit_cli:
                    return self._send_json({"error": "WolvenKit.CLI.exe not found"}, HTTPStatus.NOT_FOUND)
                item_id = body.get("item_id", "")
                with app_state.lock:
                    match = next((i for i in app_state.items if i.id == item_id), None)
                    mod_dir = app_state.config.mod_dir
                if not match:
                    return self._send_json({"error": "Item not found"}, HTTPStatus.NOT_FOUND)

                arch_path: Path | None = None
                for rel in match.associated_files:
                    if rel.endswith(".archive") and (mod_dir / rel).exists():
                        arch_path = mod_dir / rel
                        break
                if arch_path is None:
                    arch_mod = mod_dir / "archive" / "pc" / "mod"
                    if arch_mod.exists():
                        stem_hint = match.source_mod.lower().replace("_", "").replace("-", "")
                        for cand in arch_mod.glob("*.archive"):
                            cand_norm = cand.stem.lower().replace("_", "").replace("-", "")
                            if stem_hint in cand_norm or cand_norm in stem_hint:
                                arch_path = cand
                                break
                if arch_path is None:
                    return self._send_json({"image": None, "mesh": None, "images": [], "meshes": [], "message": "No matching .archive found for item"})

                item_hint = f"{match.entity_name or ''} {match.appearance_name or ''} {match.tweak_id}"

                if path == "/api/extract-preview":
                    shared_rel = match_shared_icon(
                        app_state.cache_dir, match.atlas_path, match.source_mod, match.tweak_id
                    )
                    if shared_rel:
                        return self._send_json({
                            "image": f"/cache-assets/{quote(shared_rel, safe='/')}",
                            "mesh": None,
                            "cached": True,
                        })
                    res = extract_preview_only(
                        arch_path,
                        app_state.cache_dir,
                        app_state.wolvenkit_cli,
                        item_hint=item_hint,
                    )
                    img_rel = res.get("image")
                    mesh_rel = res.get("mesh")
                    return self._send_json({
                        "image": f"/cache-assets/{quote(img_rel, safe='/')}" if img_rel else None,
                        "mesh": f"/cache-assets/{quote(mesh_rel, safe='/')}" if mesh_rel else None,
                        "cached": res.get("cached", False),
                    })

                res = uncook_archive(
                    arch_path,
                    mod_dir,
                    app_state.cache_dir,
                    app_state.wolvenkit_cli,
                    item_hint=item_hint,
                )
                imgs = [f"/cache-assets/{quote(rel, safe='/')}" for rel in res.get("images", [])]
                if not imgs:
                    shared_rel = match_shared_icon(
                        app_state.cache_dir, match.atlas_path, match.source_mod, match.tweak_id
                    )
                    if shared_rel:
                        imgs = [f"/cache-assets/{quote(shared_rel, safe='/')}"]
                meshes = [f"/cache-assets/{quote(rel, safe='/')}" for rel in res.get("meshes", [])]
                return self._send_json({
                    "archive": arch_path.name,
                    "images": imgs,
                    "meshes": meshes,
                    "cached": res.get("cached", False),
                })

            return self.send_error(HTTPStatus.NOT_FOUND, "Unknown endpoint")

    return AtelierRequestHandler


def create_server(config: AppConfig, async_scan: bool = False) -> tuple[ThreadingHTTPServer, AtelierAppState]:
    state = AtelierAppState(config, async_scan=async_scan)
    handler = make_handler(state)
    httpd = ThreadingHTTPServer((config.host, config.port), handler)
    return httpd, state

