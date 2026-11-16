# 2077view — External Cyberpunk 2077 Virtual Atelier & Clothing Mod Batch Viewer

A lightweight, zero-dependency local web application for browsing, filtering, inspecting (2D + 3D), and managing Cyberpunk 2077 clothing mods **outside of the game**.

## Features

- **External Batch Viewer**: Scans your Cyberpunk 2077 mod folder (`.archive` RDAR headers, `.yaml`/`.yml`/`.tweak` ArchiveXL/TweakXL configs, `.reds` Virtual Atelier scripts, preview images, and `.obj` meshes) or loads 120 realistic mock clothing mods for testing.
- **Comprehensive Filtering & Sorting**: Real-time text search, multi-attribute filters (Status, Category/Slot, Atelier Store, Source Mod, Body Type, Quality, Tags), and sorting (Name, Date Added, Category, Source Mod, Quality, File Size, Price).
- **2D & Interactive 3D Preview**: Displays atelier icons/preview images alongside an interactive zero-dependency 3D `.obj` & procedural garment mesh viewer (orbit, zoom, wireframe toggle).
- **Rejection & Quarantine System**: Mark single or batch items as rejected, safely move their mod files into a configurable `_quarantine` backup folder, restore quarantined mods back to the game directory, or permanently delete them with confirmation.
- **V Save Profile & CET Integration**: Reads Cyberpunk 2077 `metadata.9.json` save files to load V's body type (`FemV` / `MascV`), LifePath, and Level, and generates ready-to-copy Cyber Engine Tweaks (`Game.AddToInventory(...)`) commands.

## Quick Start

Requires Python 3.11+ (no external packages needed).

```bash
# Start with built-in 120 mock clothing mods (auto-opens browser)
python run_viewer.py

# Or point directly to your Cyberpunk 2077 game/mod folder
python run_viewer.py --mod-dir "C:\Program Files (x86)\Steam\steamapps\common\Cyberpunk 2077"
```

Then open `http://127.0.0.1:8077/` in your browser (if it doesn't open automatically).

## Running Automated Tests

```bash
python -m unittest discover -s tests -v
```
