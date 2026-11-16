"""Cyberpunk 2077 mod directory scanner & metadata extractor.

Supports:
- RED4 .archive binary header inspection (RDAR magic, version, size)
- Virtual Atelier .reds store scripts
- ArchiveXL / TweakXL .yaml / .yml / .tweak item definitions
- Sidecar preview images (.png, .jpg, .jpeg, .webp, .svg) and 3D meshes (.obj, .glb, .gltf)
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
import json
import re
import struct
from typing import Any


RDAR_MAGIC = b"RDAR"

SLOT_ALIASES = {
    "head": "Head",
    "hat": "Head",
    "helmet": "Head",
    "face": "Face",
    "glasses": "Face",
    "mask": "Face",
    "outertorso": "Outer Torso",
    "outer_torso": "Outer Torso",
    "torsoouter": "Outer Torso",
    "jacket": "Outer Torso",
    "coat": "Outer Torso",
    "innertorso": "Inner Torso",
    "inner_torso": "Inner Torso",
    "torsoinner": "Inner Torso",
    "shirt": "Inner Torso",
    "top": "Inner Torso",
    "legs": "Legs",
    "pants": "Legs",
    "skirt": "Legs",
    "feet": "Feet",
    "shoes": "Feet",
    "boots": "Feet",
    "outfit": "Outfit",
    "fullbody": "Outfit",
    "accessories": "Accessories",
    "accessory": "Accessories",
    "jewelry": "Accessories",
}

QUALITY_ORDER = {
    "Iconic": 5,
    "Legendary": 4,
    "Epic": 3,
    "Rare": 2,
    "Uncommon": 1,
    "Common": 0,
}

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".svg"}
MESH_EXTS = {".obj", ".glb", ".gltf"}


@dataclass
class ArchiveHeaderInfo:
    path: str
    valid_rdar: bool
    version: int | None
    file_size: int
    index_offset: int | None


@dataclass
class ClothingItem:
    id: str
    name: str
    tweak_id: str
    category: str
    source_mod: str
    atelier_store: str
    body_type: str
    quality: str
    price: int
    tags: list[str] = field(default_factory=list)
    description: str = ""
    appearance_name: str = ""
    preview_image: str | None = None
    icon_image: str | None = None
    mesh_file: str | None = None
    atlas_path: str | None = None
    atlas_part: str | None = None
    entity_name: str | None = None
    associated_files: list[str] = field(default_factory=list)
    file_size: int = 0
    date_added: str = ""
    status: str = "active"  # active | rejected | quarantined
    archive_info: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _match_clothing_category(raw: str | None) -> str | None:
    if not raw:
        return None
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "", raw.split(".")[-1]).lower()
    for key, val in SLOT_ALIASES.items():
        if key in cleaned:
            return val
    if any(k in cleaned for k in ("chest", "torso")):
        return "Outer Torso"
    if any(k in cleaned for k in ("hand", "wrist", "finger", "neck", "ear", "ankle", "back", "waist", "prop")):
        return "Accessories"
    return None


def normalize_category(raw: str | None) -> str:
    return _match_clothing_category(raw) or "Accessories"


def inspect_archive_header(archive_path: Path) -> ArchiveHeaderInfo:
    """Read RED4 .archive header (RDAR magic, version, index offset)."""
    size = archive_path.stat().st_size if archive_path.exists() else 0
    try:
        with archive_path.open("rb") as fh:
            header = fh.read(24)
        if len(header) >= 16 and header[:4] == RDAR_MAGIC:
            version = struct.unpack("<I", header[4:8])[0]
            index_offset = struct.unpack("<Q", header[8:16])[0]
            return ArchiveHeaderInfo(
                path=str(archive_path),
                valid_rdar=True,
                version=version,
                file_size=size,
                index_offset=index_offset,
            )
    except OSError:
        pass
    return ArchiveHeaderInfo(
        path=str(archive_path),
        valid_rdar=False,
        version=None,
        file_size=size,
        index_offset=None,
    )


def parse_reds_atelier(reds_path: Path) -> dict[str, Any]:
    """Extract Virtual Atelier store name and item mappings from a .reds file."""
    try:
        text = reds_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return {}

    store_name = None
    m_store = re.search(
        r'(?:AddStore|RegisterStore)\s*\([^,]+,\s*"([^"]+)"', text
    )
    if m_store:
        store_name = m_store.group(1)
    else:
        m_title = re.search(r'storeName\s*=\s*"([^"]+)"', text)
        if m_title:
            store_name = m_title.group(1)

    items: dict[str, dict[str, Any]] = {}
    # Match patterns like AddStoreItem("Items.MyJacket", 2500, "Legendary", ...)
    for m in re.finditer(
        r'"(Items\.[A-Za-z0-9_.\-]+)"\s*(?:,\s*(\d+))?(?:\s*,\s*"([^"]+)")?',
        text,
    ):
        tweak_id = m.group(1)
        price = int(m.group(2)) if m.group(2) else 1200
        quality = m.group(3) if m.group(3) else ""
        items[tweak_id] = {"price": price, "quality": quality}

    return {"store_name": store_name, "items": items}


def _is_clothing_record(rec: dict[str, Any], reds_by_tweak: dict[str, Any]) -> bool:
    """Filter out non-clothing TweakXL records (cyberware, weapons, UI, stat shards)."""
    tid = rec.get("tweak_id", "")
    if not tid.startswith("Items."):
        return False
    tid_l = tid.lower()
    excluded = (
        "_ui", "statshard", "cyberware", "weapon", "vehicle", "recipe", "quickhack",
        "sandevistan", "berserk", "deck", "preset_", "grenade", "consumable", "ammo",
        "booster", "scope", "muzzle", "magazine", "program", "skillbook", "perk",
    )
    if any(tok in tid_l for tok in excluded):
        return False
    if tid in reds_by_tweak:
        return True
    if rec.get("atlas_path"):
        return True
    base = str(rec.get("base_type", "")).lower()
    if any(k in base for k in ("clothing", "outfit", "jacket", "shirt", "pants", "shoes", "boots", "hat", "glasses", "mask", "vest", "coat", "garment")):
        return True
    if rec.get("has_clothing_slot"):
        return True
    return bool(rec.get("appearance_name") and rec.get("entity_name"))


NON_CLOTHING_ARCHIVE_KEYWORDS = (
    "tattoo", "_vtk", "femuv", "mascuv", "maleuv", "tattoouv", "buttons_replacer", "buttons replacer",
    "removeunderwear", "facialcustomization", "charactercreator", "population", "novacity",
    "weather", "lut_", "_lut", "lighting", "photomode", "pose", "anim", "animation",
    "cyberware", "statshard", "weapon", "vehicle", "radio", "sound", "audio", "voice",
    "core_dependency", "material_override", "hair", "eyebrow", "eyelash", "eyeshadow",
    "lipstick", "makeup", "nails", "spawn0_body", "rig_", "skeleton", "microblend",
    "garment_support", "_addon", "armset",
)


def _is_non_clothing_archive(stem: str) -> bool:
    s = stem.lower()
    return any(kw in s for kw in NON_CLOTHING_ARCHIVE_KEYWORDS)


def _clean_display_name(raw_name: str, tweak_id: str, inst: dict[str, str] | None = None) -> str:
    name = raw_name.replace("LocKey#", "").strip()
    if name.isdigit():
        name = ""
    name = re.sub(r"^\d+[_\-\s]+", "", name)
    name = re.sub(r"[_\-\s]*name$", "", name, flags=re.IGNORECASE)
    if not name or re.search(r"[\$\{\}]", name) or "_" in name:
        base = name if (name and not re.search(r"[\$\{\}]", name)) else tweak_id.split(".")[-1]
        base = re.sub(r"[\$\{\}\(\)]+", "", base)
        base = re.sub(r"^[!#_\-\s\d]+", "", base)
        base = re.sub(r"[_\-\s]*name$", "", base, flags=re.IGNORECASE)
        name = base.replace("_", " ").replace("-", " ").strip().title()
    name = re.sub(r"^[!#_\-\s]+", "", name).strip()
    if inst:
        variant_parts = [v for k, v in inst.items() if k.lower() in ("color", "colour", "variant", "style", "tone", "metal") and v]
        if variant_parts:
            v_str = ", ".join(v.replace("_", " ").title() for v in variant_parts)
            if v_str.lower() not in name.lower():
                name = f"{name} ({v_str})"
    return name or tweak_id.split(".")[-1]


def _format_fallback_name(tweak_id: str) -> str:
    return _clean_display_name("", tweak_id)


def _expand_template(text: str, inst: dict[str, str]) -> str:
    result = text
    for k, v in inst.items():
        result = result.replace(f"$({k})", v).replace(f"${{{k}}}", v)
    return result


def parse_yaml_tweaks(yaml_path: Path) -> list[dict[str, Any]]:
    """Lightweight parser for ArchiveXL / TweakXL .yaml / .yml / .tweak files (with $instances)."""
    try:
        lines = yaml_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return []

    raw_records: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    active_list_key: str | None = None
    active_anchor: str | None = None
    anchors: dict[str, list[dict[str, str]]] = {}

    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(raw_line) - len(raw_line.lstrip(" "))
        # Top-level item key, e.g. Items.cyber_jacket_$(color):
        if indent == 0 and stripped.endswith(":"):
            if current:
                raw_records.append(current)
            tweak_id = stripped[:-1].strip().strip('"').strip("'")
            current = {"tweak_id": tweak_id, "_instances": []}
            active_list_key = None
            active_anchor = None
            continue

        if current is None:
            continue

        # Handle list items under $instances or placementSlots
        if stripped.startswith("- ") and active_list_key:
            item_val = stripped[2:].strip()
            if active_list_key == "$instances" and item_val.startswith("{") and item_val.endswith("}"):
                inst: dict[str, str] = {}
                for pair in item_val[1:-1].split(","):
                    if ":" in pair:
                        ik, iv = pair.split(":", 1)
                        inst[ik.strip()] = iv.strip().strip('"').strip("'")
                if inst:
                    current["_instances"].append(inst)
                    if active_anchor:
                        anchors.setdefault(active_anchor, []).append(inst)
            elif active_list_key in ("slot", "placementSlots", "equipArea"):
                slot_tok = item_val.replace("!append", "").strip()
                matched_cat = _match_clothing_category(slot_tok)
                if matched_cat:
                    current["category"] = matched_cat
                    current["has_clothing_slot"] = True
            continue

        active_list_key = None
        active_anchor = None
        if ":" in stripped:
            key, val = stripped.split(":", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key == "$instances":
                if val.startswith("*") and val[1:] in anchors:
                    current["_instances"].extend(anchors[val[1:]])
                else:
                    active_list_key = "$instances"
                    if val.startswith("&"):
                        active_anchor = val[1:].strip()
                continue
            if val == "" and key in ("placementSlots", "slot", "equipArea"):
                active_list_key = key
                continue
            if key in ("displayName", "name", "localizedName"):
                cleaned_name = val.replace("LocKey#", "").strip()
                if cleaned_name and not cleaned_name.isdigit() and not cleaned_name.startswith("$( "):
                    current["name"] = cleaned_name
            elif key in ("localizedDescription", "description"):
                current["description"] = val.replace("LocKey#", "").strip()
            elif key in ("appearanceName", "appearance"):
                current["appearance_name"] = val
            elif key == "entityName":
                current["entity_name"] = val
            elif key == "$base":
                current["base_type"] = val
                matched_base = _match_clothing_category(val)
                if matched_base and "category" not in current:
                    current["category"] = matched_base
            elif key == "atlasResourcePath":
                current["atlas_path"] = val.replace("\\", "/")
            elif key == "atlasPartName":
                current["atlas_part"] = val
            elif key in ("quality", "rarity"):
                current["quality"] = val.split(".")[-1]
            elif key in ("slot", "placementSlots", "equipArea"):
                matched_cat = _match_clothing_category(val.replace("!append", "").strip())
                if matched_cat:
                    current["category"] = matched_cat
                    current["has_clothing_slot"] = True
            elif key in ("bodyType", "gender"):
                current["body_type"] = val
            elif key == "price" and val.isdigit():
                current["price"] = int(val)
            elif key == "tags":
                if val.startswith("[") and val.endswith("]"):
                    tags = [
                        t.strip().strip('"').strip("'")
                        for t in val[1:-1].split(",")
                        if t.strip()
                    ]
                    current["tags"] = tags
            elif key == "atelierStore":
                current["atelier_store"] = val
            elif key == "previewImage":
                current["preview_image"] = val
            elif key == "meshFile":
                current["mesh_file"] = val

    if current:
        raw_records.append(current)

    expanded: list[dict[str, Any]] = []
    for rec in raw_records:
        if not rec.get("tweak_id"):
            continue
        instances = rec.pop("_instances", [])
        if not instances:
            expanded.append(rec)
        elif len(instances) <= 2 and not rec.get("atlas_path") and not rec.get("entity_name"):
            for inst in instances:
                clone = dict(rec)
                for field_name in ("tweak_id", "name", "description", "appearance_name", "entity_name", "atlas_path", "atlas_part"):
                    if field_name in clone and isinstance(clone[field_name], str):
                        clone[field_name] = _expand_template(clone[field_name], inst)
                if "name" not in clone or "_" in clone["name"] or "$" in clone["name"]:
                    clone["name"] = _clean_display_name(clone.get("name", ""), clone["tweak_id"], inst)
                inst_tags = list(clone.get("tags", []))
                for v in inst.values():
                    if v and v not in inst_tags:
                        inst_tags.append(v)
                clone["tags"] = inst_tags
                expanded.append(clone)
        else:
            # Collapse color/style $instances into a single item card with variant count
            first_inst = instances[0]
            primary = dict(rec)
            base_name = _clean_display_name(rec.get("name", ""), rec["tweak_id"], None)
            for field_name in ("tweak_id", "description", "appearance_name", "entity_name", "atlas_path", "atlas_part"):
                if field_name in primary and isinstance(primary[field_name], str):
                    primary[field_name] = _expand_template(primary[field_name], first_inst)
            primary["name"] = f"{base_name} ({len(instances)} variants)" if len(instances) > 1 else base_name
            inst_tags = list(primary.get("tags", []))
            if len(instances) > 1:
                inst_tags.append(f"{len(instances)}-colors")
            primary["tags"] = inst_tags
            expanded.append(primary)

    # Also collapse multiple top-level YAML blocks in the same file that share the same (entity_name, category)
    deduped: list[dict[str, Any]] = []
    by_entity: dict[tuple[str, str], dict[str, Any]] = {}
    entity_counts: dict[tuple[str, str], int] = {}
    for rec in expanded:
        ent = rec.get("entity_name", "")
        cat = rec.get("category", "")
        if ent and ent not in ("default", "clothing_item"):
            key = (ent.lower(), cat.lower())
            entity_counts[key] = entity_counts.get(key, 0) + 1
            if key not in by_entity:
                by_entity[key] = rec
                deduped.append(rec)
        else:
            deduped.append(rec)

    for key, count in entity_counts.items():
        if count > 1:
            rep = by_entity[key]
            base_n = re.sub(r"\s*\(\d+\s*variants\)$", "", rep.get("name", ""))
            # Strip trailing color words like Og, Pink, Black, White, Red
            base_n = re.sub(r"\s+(Og|Pink|Black|White|Red|Blue|Green|Yellow|Purple|Gold|Silver)$", "", base_n, flags=re.IGNORECASE)
            rep["name"] = f"{base_n} ({count} variants)"

    return deduped


def _find_best_asset(base_dir: Path, stem_hints: list[str], exts: set[str], mod_root: Path) -> str | None:
    """Locate a matching preview image or 3D mesh relative to mod_root."""
    if not base_dir.exists():
        return None
    candidates = [
        p for p in base_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in exts
    ]
    if not candidates:
        return None

    lowered_hints = [h.lower() for h in stem_hints if h]
    for hint in lowered_hints:
        for cand in candidates:
            if hint in cand.stem.lower():
                return cand.relative_to(mod_root).as_posix()

    return candidates[0].relative_to(mod_root).as_posix()


def _not_quarantine(p: Path) -> bool:
    return "_quarantine" not in p.parts


def is_game_root(mod_dir: Path) -> bool:
    """Return True if mod_dir is a Cyberpunk 2077 game root folder."""
    return (mod_dir / "archive" / "pc" / "mod").exists() or (mod_dir / "r6").exists()


def collect_mod_files(mod_dir: Path) -> dict[str, list[Path]]:
    """Collect .archive, .yaml/.yml/.tweak, .reds, and mod_manifest.json files quickly.

    When mod_dir is a Cyberpunk 2077 game root, only mod subdirectories
    (archive/pc/mod, r6/tweaks, r6/scripts, mods) are scanned so basegame
    content archives (archive/pc/content, archive/pc/ep1) are never touched.
    """
    mod_dir = Path(mod_dir)
    archives: list[Path] = []
    yamls: list[Path] = []
    reds: list[Path] = []
    manifests: list[Path] = []

    if is_game_root(mod_dir):
        arch_mod = mod_dir / "archive" / "pc" / "mod"
        if arch_mod.exists():
            archives.extend(sorted(p for p in arch_mod.rglob("*.archive") if _not_quarantine(p)))
        redmod_dir = mod_dir / "mods"
        if redmod_dir.exists():
            archives.extend(sorted(p for p in redmod_dir.rglob("*.archive") if _not_quarantine(p)))
            manifests.extend(sorted(p for p in redmod_dir.rglob("mod_manifest.json") if _not_quarantine(p)))
        tweaks_dir = mod_dir / "r6" / "tweaks"
        if tweaks_dir.exists():
            yamls.extend(sorted(
                p for ext in ("*.yaml", "*.yml", "*.tweak")
                for p in tweaks_dir.rglob(ext) if _not_quarantine(p)
            ))
        scripts_dir = mod_dir / "r6" / "scripts"
        if scripts_dir.exists():
            reds.extend(sorted(p for p in scripts_dir.rglob("*.reds") if _not_quarantine(p)))
    else:
        archives = sorted(p for p in mod_dir.rglob("*.archive") if _not_quarantine(p))
        yamls = sorted(
            p for ext in ("*.yaml", "*.yml", "*.tweak")
            for p in mod_dir.rglob(ext) if _not_quarantine(p)
        )
        reds = sorted(p for p in mod_dir.rglob("*.reds") if _not_quarantine(p))
        manifests = sorted(p for p in mod_dir.rglob("mod_manifest.json") if _not_quarantine(p))

    return {
        "archives": archives,
        "yamls": yamls,
        "reds": reds,
        "manifests": manifests,
    }


def scan_mod_directory(mod_dir: Path, rejected_ids: set[str] | None = None) -> list[ClothingItem]:
    """Scan a Cyberpunk 2077 mod directory (or game root) and return ClothingItem objects."""
    mod_dir = Path(mod_dir)
    if not mod_dir.exists():
        return []

    rejected_ids = rejected_ids or set()
    items: list[ClothingItem] = []

    collected = collect_mod_files(mod_dir)
    all_archives = collected["archives"]
    all_yamls = collected["yamls"]
    all_reds = collected["reds"]
    all_manifests = collected["manifests"]

    # Pre-index archives by stem, normalized stem, and parent directory for O(1) matching
    def _norm_stem(s: str) -> str:
        return re.sub(r"[^a-z0-9]", "", s.lower())

    archives_by_stem: dict[str, list[Path]] = {}
    archives_by_norm: dict[str, list[Path]] = {}
    archives_by_parent: dict[Path, list[Path]] = {}
    for arch in all_archives:
        archives_by_stem.setdefault(arch.stem.lower(), []).append(arch)
        ns = _norm_stem(arch.stem)
        if ns:
            archives_by_norm.setdefault(ns, []).append(arch)
        archives_by_parent.setdefault(arch.parent, []).append(arch)

    # Parse Virtual Atelier .reds stores & build O(1) lookup by tweak_id
    reds_by_tweak: dict[str, dict[str, Any]] = {}
    for reds_file in all_reds:
        info = parse_reds_atelier(reds_file)
        if info:
            s_name = info.get("store_name")
            for tid, tmeta in info.get("items", {}).items():
                reds_by_tweak[tid] = {
                    "store_name": s_name,
                    "price": tmeta.get("price", 1400),
                    "quality": tmeta.get("quality", ""),
                }

    # 1) Load explicit mod_manifest.json files if present (rich mock or curated mod packs)
    covered_dirs: set[Path] = set()
    for manifest_path in all_manifests:
        pkg_dir = manifest_path.parent
        covered_dirs.add(pkg_dir)
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        pkg_name = data.get("source_mod", pkg_dir.name)
        store_name = data.get("atelier_store", f"{pkg_name} Atelier")
        pkg_archives = [p for p in pkg_dir.rglob("*.archive")]
        archive_meta = (
            asdict(inspect_archive_header(pkg_archives[0]))
            if pkg_archives else None
        )
        pkg_files = [
            p.relative_to(mod_dir).as_posix()
            for p in pkg_dir.rglob("*")
            if p.is_file()
        ]
        pkg_size = sum(p.stat().st_size for p in pkg_dir.rglob("*") if p.is_file())
        mtime = datetime.fromtimestamp(
            manifest_path.stat().st_mtime, tz=timezone.utc
        ).isoformat()

        for entry in data.get("items", []):
            item_id = entry.get("id") or entry.get("tweak_id") or f"{pkg_name}_{len(items)}"
            preview_rel = entry.get("preview_image")
            if preview_rel and not (mod_dir / preview_rel).exists():
                candidate = pkg_dir / preview_rel
                if candidate.exists():
                    preview_rel = candidate.relative_to(mod_dir).as_posix()

            mesh_rel = entry.get("mesh_file")
            if mesh_rel and not (mod_dir / mesh_rel).exists():
                candidate = pkg_dir / mesh_rel
                if candidate.exists():
                    mesh_rel = candidate.relative_to(mod_dir).as_posix()

            associated = entry.get("associated_files") or pkg_files
            items.append(
                ClothingItem(
                    id=item_id,
                    name=entry.get("name", item_id),
                    tweak_id=entry.get("tweak_id", f"Items.{item_id}"),
                    category=normalize_category(entry.get("category")),
                    source_mod=pkg_name,
                    atelier_store=entry.get("atelier_store", store_name),
                    body_type=entry.get("body_type", "Unisex"),
                    quality=entry.get("quality", "Legendary"),
                    price=int(entry.get("price", 1500)),
                    tags=list(entry.get("tags", [])),
                    description=entry.get("description", ""),
                    appearance_name=entry.get("appearance_name", "default"),
                    preview_image=preview_rel,
                    icon_image=entry.get("icon_image") or preview_rel,
                    mesh_file=mesh_rel,
                    associated_files=list(associated),
                    file_size=int(entry.get("file_size", pkg_size)),
                    date_added=entry.get("date_added", mtime),
                    status="rejected" if item_id in rejected_ids else "active",
                    archive_info=archive_meta,
                )
            )

    # 2) Parse standalone .yaml / .yml / .tweak files not already covered by a manifest
    seen_tweak_ids = {item.tweak_id for item in items}
    tweaks_root = (mod_dir / "r6" / "tweaks").resolve()
    for yaml_path in all_yamls:
        if any(parent in covered_dirs for parent in yaml_path.parents):
            continue
        pkg_dir = yaml_path.parent
        records = parse_yaml_tweaks(yaml_path)
        if not records:
            continue

        stem_l = yaml_path.stem.lower()
        pkg_archives = list(archives_by_stem.get(stem_l, []))
        if not pkg_archives:
            norm_s = _norm_stem(yaml_path.stem)
            pkg_archives = list(archives_by_norm.get(norm_s, []))
            if not pkg_archives and pkg_dir.resolve() != tweaks_root:
                norm_parent = _norm_stem(pkg_dir.name)
                pkg_archives = list(archives_by_norm.get(norm_parent, []))
            if not pkg_archives and len(norm_s) >= 5:
                for k_norm, arch_list in archives_by_norm.items():
                    if norm_s in k_norm or (len(k_norm) >= 5 and k_norm in norm_s):
                        pkg_archives = list(arch_list)
                        break
        if not pkg_archives and pkg_dir in archives_by_parent:
            pkg_archives = list(archives_by_parent[pkg_dir])
        archive_meta = (
            asdict(inspect_archive_header(pkg_archives[0]))
            if pkg_archives else None
        )
        assoc_files = [yaml_path.relative_to(mod_dir).as_posix()] + [
            a.relative_to(mod_dir).as_posix() for a in pkg_archives
        ]
        mtime = datetime.fromtimestamp(
            yaml_path.stat().st_mtime, tz=timezone.utc
        ).isoformat()
        total_size = sum((mod_dir / f).stat().st_size for f in assoc_files if (mod_dir / f).exists())

        # Avoid scanning r6/tweaks folders for images/meshes when inside a game root
        asset_search_dir = None if is_game_root(mod_dir) else (pkg_dir if pkg_dir.resolve() != tweaks_root else None)

        for rec in records:
            tweak_id = rec["tweak_id"]
            if tweak_id in seen_tweak_ids:
                continue
            if not _is_clothing_record(rec, reds_by_tweak):
                continue
            seen_tweak_ids.add(tweak_id)
            item_id = re.sub(r"[^A-Za-z0-9_\-]", "_", tweak_id)
            raw_n = rec.get("name", "")
            if not raw_n or "_" in raw_n or "$" in raw_n:
                display_name = _clean_display_name(raw_n, tweak_id)
            else:
                display_name = raw_n

            # Cross-reference .reds atelier stores in O(1)
            store_name = rec.get("atelier_store", f"{yaml_path.stem} Atelier")
            price = rec.get("price", 1400)
            quality = rec.get("quality", "Epic")
            r_meta = reds_by_tweak.get(tweak_id)
            if r_meta:
                store_name = r_meta.get("store_name") or store_name
                price = r_meta.get("price", price)
                if r_meta.get("quality"):
                    quality = r_meta["quality"]

            preview = rec.get("preview_image") or (
                _find_best_asset(
                    asset_search_dir, [item_id, tweak_id.split(".")[-1], yaml_path.stem], IMAGE_EXTS, mod_dir
                )
                if asset_search_dir else None
            )
            mesh = rec.get("mesh_file") or (
                _find_best_asset(
                    asset_search_dir, [item_id, tweak_id.split(".")[-1], yaml_path.stem], MESH_EXTS, mod_dir
                )
                if asset_search_dir else None
            )

            items.append(
                ClothingItem(
                    id=item_id,
                    name=display_name,
                    tweak_id=tweak_id,
                    category=rec.get("category", "Outer Torso"),
                    source_mod=yaml_path.stem,
                    atelier_store=store_name,
                    body_type=rec.get("body_type", "Unisex"),
                    quality=quality,
                    price=price,
                    tags=rec.get("tags", ["tweakxl", "custom"]),
                    description=rec.get("description", ""),
                    appearance_name=rec.get("appearance_name", "default"),
                    preview_image=preview,
                    icon_image=preview,
                    mesh_file=mesh,
                    atlas_path=rec.get("atlas_path"),
                    atlas_part=rec.get("atlas_part"),
                    entity_name=rec.get("entity_name"),
                    associated_files=assoc_files,
                    file_size=total_size,
                    date_added=mtime,
                    status="rejected" if item_id in rejected_ids else "active",
                    archive_info=archive_meta,
                )
            )

    # 3) Fallback for bare .archive files with no manifest or yaml
    covered_archives = {
        f for item in items for f in item.associated_files if f.endswith(".archive")
    }
    archive_mod_root = (mod_dir / "archive" / "pc" / "mod").resolve()
    inspect_headers = len(all_archives) <= 300
    for arch in all_archives:
        rel = arch.relative_to(mod_dir).as_posix()
        if rel in covered_archives:
            continue
        if _is_non_clothing_archive(arch.stem):
            continue
        if inspect_headers:
            header_info = inspect_archive_header(arch)
            file_size = header_info.file_size
            arch_dict = asdict(header_info)
            arch_tag = "rdar" if header_info.valid_rdar else "raw"
        else:
            st = arch.stat()
            file_size = st.st_size
            arch_dict = {"path": str(arch), "valid_rdar": True, "version": None, "file_size": file_size, "index_offset": None}
            arch_tag = "archive"
        item_id = f"archive_{arch.stem}"
        mtime = datetime.fromtimestamp(arch.stat().st_mtime, tz=timezone.utc).isoformat()
        if arch.parent.resolve() != archive_mod_root:
            preview = _find_best_asset(arch.parent, [arch.stem], IMAGE_EXTS, mod_dir)
            mesh = _find_best_asset(arch.parent, [arch.stem], MESH_EXTS, mod_dir)
        else:
            preview = None
            mesh = None
        clean_arch_name = re.sub(r"^(?:[!#_\-\s]+|0+[_\-\s]+)+", "", arch.stem).replace("_", " ").replace("-", " ").strip().title() or arch.stem
        items.append(
            ClothingItem(
                id=item_id,
                name=clean_arch_name,
                tweak_id=f"Items.{arch.stem}",
                category=normalize_category(arch.stem),
                source_mod=arch.stem,
                atelier_store="Standalone Archives",
                body_type="Unisex",
                quality="Rare",
                price=1000,
                tags=["archive", arch_tag],
                description=f"RED4 Archive ({file_size} bytes)",
                appearance_name="default",
                preview_image=preview,
                icon_image=preview,
                mesh_file=mesh,
                associated_files=[rel],
                file_size=file_size,
                date_added=mtime,
                status="rejected" if item_id in rejected_ids else "active",
                archive_info=arch_dict,
            )
        )

    return items


def filter_and_sort_items(
    items: list[ClothingItem],
    query: str = "",
    category: str = "",
    source_mod: str = "",
    atelier_store: str = "",
    body_type: str = "",
    quality: str = "",
    tag: str = "",
    status: str = "active",
    sort_by: str = "name",
    sort_dir: str = "asc",
) -> list[ClothingItem]:
    """Filter and sort clothing items across hundreds of entries."""
    q = query.strip().lower()
    cat_l = category.strip().lower()
    mod_l = source_mod.strip().lower()
    store_l = atelier_store.strip().lower()
    body_l = body_type.strip().lower()
    qual_l = quality.strip().lower()
    tag_l = tag.strip().lower()
    status_l = status.strip().lower()

    filtered: list[ClothingItem] = []
    for item in items:
        if status_l and status_l != "all" and item.status.lower() != status_l:
            continue
        if cat_l and item.category.lower() != cat_l:
            continue
        if mod_l and item.source_mod.lower() != mod_l:
            continue
        if store_l and item.atelier_store.lower() != store_l:
            continue
        if body_l and item.body_type.lower() != body_l:
            continue
        if qual_l and item.quality.lower() != qual_l:
            continue
        if tag_l and not any(tag_l == t.lower() for t in item.tags):
            continue
        if q:
            haystack = " ".join([
                item.name,
                item.tweak_id,
                item.source_mod,
                item.atelier_store,
                item.category,
                item.description,
                " ".join(item.tags),
            ]).lower()
            if q not in haystack:
                continue
        filtered.append(item)

    reverse = sort_dir.lower() == "desc"

    def sort_key(item: ClothingItem) -> Any:
        if sort_by == "date_added":
            return item.date_added or ""
        if sort_by == "category":
            return (item.category.lower(), item.name.lower())
        if sort_by == "source_mod":
            return (item.source_mod.lower(), item.name.lower())
        if sort_by == "quality":
            return (QUALITY_ORDER.get(item.quality, 0), item.name.lower())
        if sort_by == "file_size":
            return item.file_size
        if sort_by == "price":
            return item.price
        return item.name.lower()

    filtered.sort(key=sort_key, reverse=reverse)
    return filtered

