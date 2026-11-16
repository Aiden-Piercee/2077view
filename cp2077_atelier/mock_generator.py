"""Mock Cyberpunk 2077 clothing mod generator for testing and demo mode."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import struct


MOCK_STORES = [
    {
        "pkg": "kwek_arasaka_cyberwear",
        "store": "Arasaka Black Ops Atelier",
        "prefix": "Arasaka",
        "color": "#ff2a6d",
        "accent": "#05d9e8",
        "tags": ["cyberwear", "corpo", "tactical"],
    },
    {
        "pkg": "neokitsch_edgerunner_fits",
        "store": "Kabuki Neon Threads",
        "prefix": "Kabuki",
        "color": "#fcee09",
        "accent": "#ff2a6d",
        "tags": ["streetwear", "neon", "edgerunner"],
    },
    {
        "pkg": "veegee_netrunner_vault",
        "store": "Netwatch Rogue Atelier",
        "prefix": "Netrunner",
        "color": "#05d9e8",
        "accent": "#7b2cbf",
        "tags": ["netrunner", "tech", "cyberwear"],
    },
    {
        "pkg": "nora_mox_boutique",
        "store": "Lizzie's Mox Boutique",
        "prefix": "Mox",
        "color": "#ff6ec7",
        "accent": "#fcee09",
        "tags": ["mox", "streetwear", "glam"],
    },
    {
        "pkg": "badlands_nomad_surplus",
        "store": "Aldecaldo Nomad Surplus",
        "prefix": "Nomad",
        "color": "#ff9f1c",
        "accent": "#2ec4b6",
        "tags": ["nomad", "tactical", "leather"],
    },
    {
        "pkg": "dogtown_barghest_gear",
        "store": "Dogtown Black Market",
        "prefix": "Barghest",
        "color": "#72efdd",
        "accent": "#ff2a6d",
        "tags": ["dogtown", "tactical", "military"],
    },
]

CATEGORIES = [
    ("Outer Torso", ["Jacket", "Trenchcoat", "Bolero", "Vest", "Harness"]),
    ("Inner Torso", ["Netrunner Suit", "Crop Top", "Turtleneck", "Bodysuit", "Shirt"]),
    ("Legs", ["Cargo Pants", "Synth-Leather Shorts", "Exo-Leggings", "Skirt", "Trousers"]),
    ("Feet", ["Exo-Boots", "Platform Sneakers", "Combat Boots", "Tech-Heels", "Kicks"]),
    ("Head", ["Visor Helmet", "Cyber-Beanie", "Tactical Hood", "Headset", "Beret"]),
    ("Face", ["BD Wreath", "Kiroshi Shades", "Respirator Mask", "Tech-Goggles", "Visor"]),
    ("Accessories", ["Cyber-Choker", "Holo-Belt", "Arm-Sleeves", "Data-Gloves", "Sash"]),
]

QUALITIES = ["Iconic", "Legendary", "Epic", "Rare", "Uncommon"]
BODY_TYPES = ["FemV", "MascV", "Unisex"]
VARIANTS = ["Obsidian", "Crimson", "Chrome", "Holo-Cyan", "Acid-Yellow"]


def _write_rdar_archive(path: Path, version: int = 12) -> None:
    """Write a minimal valid RED4 RDAR .archive header."""
    header = b"RDAR" + struct.pack("<I", version) + struct.pack("<Q", 64) + b"\x00" * 48
    path.write_bytes(header)


def _make_svg_preview(name: str, category: str, color: str, accent: str, quality: str) -> str:
    short_name = name[:26]
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="320" height="220" viewBox="0 0 320 220">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#0d0e15"/>
      <stop offset="100%" stop-color="#1a1c2c"/>
    </linearGradient>
  </defs>
  <rect width="320" height="220" fill="url(#bg)"/>
  <rect x="8" y="8" width="304" height="204" fill="none" stroke="{color}" stroke-width="2" stroke-opacity="0.7"/>
  <polygon points="160,36 218,74 202,162 118,162 102,74" fill="{color}" fill-opacity="0.16" stroke="{accent}" stroke-width="2"/>
  <circle cx="160" cy="96" r="26" fill="none" stroke="{color}" stroke-width="2" stroke-dasharray="5 3"/>
  <text x="160" y="102" fill="#f4f4f8" font-family="monospace" font-size="11" text-anchor="middle">{category.upper()}</text>
  <text x="18" y="192" fill="{accent}" font-family="monospace" font-size="12" font-weight="bold">{short_name}</text>
  <text x="302" y="28" fill="{color}" font-family="monospace" font-size="10" text-anchor="end">{quality.upper()}</text>
</svg>
"""


def _make_obj_garment(category: str) -> str:
    """Return a clean low-poly 3D .obj mesh tailored to the garment category."""
    if category in ("Head", "Face"):
        return (
            "# Cyberpunk Head/Visor Mesh\n"
            "v -0.45 0.50 0.45\nv 0.45 0.50 0.45\nv 0.45 1.15 0.45\nv -0.45 1.15 0.45\n"
            "v -0.45 0.50 -0.45\nv 0.45 0.50 -0.45\nv 0.45 1.15 -0.45\nv -0.45 1.15 -0.45\n"
            "f 1 2 3 4\nf 5 6 7 8\nf 1 2 6 5\nf 2 3 7 6\nf 3 4 8 7\nf 4 1 5 8\n"
        )
    if category in ("Legs", "Feet"):
        return (
            "# Cyberpunk Legs/Boots Mesh\n"
            "v -0.55 -1.10 0.30\nv -0.10 -1.10 0.30\nv -0.15 0.10 0.35\nv -0.50 0.10 0.35\n"
            "v 0.10 -1.10 0.30\nv 0.55 -1.10 0.30\nv 0.50 0.10 0.35\nv 0.15 0.10 0.35\n"
            "v -0.55 -1.10 -0.30\nv -0.10 -1.10 -0.30\nv -0.15 0.10 -0.35\nv -0.50 0.10 -0.35\n"
            "v 0.10 -1.10 -0.30\nv 0.55 -1.10 -0.30\nv 0.50 0.10 -0.35\nv 0.15 0.10 -0.35\n"
            "f 1 2 3 4\nf 5 6 7 8\nf 9 10 11 12\nf 13 14 15 16\n"
            "f 1 4 12 9\nf 2 3 11 10\nf 5 8 16 13\nf 6 7 15 14\n"
        )
    # Torso / Jacket / Outfit silhouette
    return (
        "# Cyberpunk Torso Garment Mesh\n"
        "v -0.70 0.85 0.35\nv 0.70 0.85 0.35\nv 0.52 -0.35 0.32\nv -0.52 -0.35 0.32\n"
        "v -0.70 0.85 -0.35\nv 0.70 0.85 -0.35\nv 0.52 -0.35 -0.32\nv -0.52 -0.35 -0.32\n"
        "v -0.95 0.30 0.20\nv 0.95 0.30 0.20\nv -0.95 0.30 -0.20\nv 0.95 0.30 -0.20\n"
        "f 1 2 3 4\nf 5 6 7 8\nf 1 4 8 5\nf 2 3 7 6\nf 1 2 6 5\nf 4 3 7 8\n"
        "f 1 9 11 5\nf 2 10 12 6\n"
    )


def generate_mock_mods(target_dir: Path, count: int = 120) -> list[Path]:
    """Generate `count` realistic Cyberpunk 2077 clothing mod items across 6 mod packages."""
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    base_time = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
    per_store: dict[int, list[dict]] = {i: [] for i in range(len(MOCK_STORES))}

    for idx in range(count):
        store_idx = idx % len(MOCK_STORES)
        store = MOCK_STORES[store_idx]
        cat_name, nouns = CATEGORIES[(idx // len(MOCK_STORES)) % len(CATEGORIES)]
        noun = nouns[(idx // (len(MOCK_STORES) * len(CATEGORIES))) % len(nouns)]
        variant = VARIANTS[idx % len(VARIANTS)]
        quality = QUALITIES[idx % len(QUALITIES)]
        body_type = BODY_TYPES[idx % len(BODY_TYPES)]

        item_name = f"{store['prefix']} {variant} {noun}"
        item_slug = f"{store['prefix'].lower()}_{variant.lower().replace('-', '_')}_{noun.lower().replace(' ', '_')}_{idx:03d}"
        tweak_id = f"Items.{item_slug}"

        pkg_dir = target_dir / store["pkg"]
        preview_rel = f"previews/{item_slug}.svg"
        mesh_rel = f"meshes/{cat_name.lower().replace(' ', '_')}.obj"

        per_store[store_idx].append({
            "id": item_slug,
            "name": item_name,
            "tweak_id": tweak_id,
            "category": cat_name,
            "source_mod": store["pkg"],
            "atelier_store": store["store"],
            "body_type": body_type,
            "quality": quality,
            "price": 800 + (idx % 12) * 350,
            "tags": list(store["tags"]) + [variant.lower()],
            "description": f"{quality} {cat_name.lower()} piece from {store['store']} ({body_type}).",
            "appearance_name": f"{variant.lower()}_default",
            "preview_image": preview_rel,
            "mesh_file": mesh_rel,
            "date_added": (base_time + timedelta(hours=idx * 3)).isoformat(),
            "color": store["color"],
            "accent": store["accent"],
        })

    created_manifests: list[Path] = []
    for store_idx, store in enumerate(MOCK_STORES):
        pkg_dir = target_dir / store["pkg"]
        (pkg_dir / "previews").mkdir(parents=True, exist_ok=True)
        (pkg_dir / "meshes").mkdir(parents=True, exist_ok=True)

        _write_rdar_archive(pkg_dir / f"{store['pkg']}.archive")

        # Write shared category .obj meshes
        for cat_name, _ in CATEGORIES:
            mesh_path = pkg_dir / "meshes" / f"{cat_name.lower().replace(' ', '_')}.obj"
            if not mesh_path.exists():
                mesh_path.write_text(_make_obj_garment(cat_name), encoding="utf-8")

        # Write preview SVGs and strip helper color keys before saving manifest
        manifest_items = []
        for entry in per_store[store_idx]:
            svg_path = pkg_dir / entry["preview_image"]
            svg_path.write_text(
                _make_svg_preview(
                    entry["name"],
                    entry["category"],
                    entry["color"],
                    entry["accent"],
                    entry["quality"],
                ),
                encoding="utf-8",
            )
            cleaned = {k: v for k, v in entry.items() if k not in ("color", "accent")}
            manifest_items.append(cleaned)

        manifest_path = pkg_dir / "mod_manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "source_mod": store["pkg"],
                    "atelier_store": store["store"],
                    "items": manifest_items,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        created_manifests.append(manifest_path)

    return created_manifests

