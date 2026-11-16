"""CLI entry point for 2077view External Virtual Atelier."""

from __future__ import annotations

import argparse
from pathlib import Path
import threading
import webbrowser

from cp2077_atelier.config import AppConfig, detect_cp2077_installations
from cp2077_atelier.mock_generator import generate_mock_mods
from cp2077_atelier.server import create_server


def main() -> None:
    parser = argparse.ArgumentParser(
        description="2077view — Cyberpunk 2077 External Virtual Atelier & Clothing Mod Batch Viewer"
    )
    parser.add_argument("--mod-dir", type=Path, default=None, help="Path to Cyberpunk 2077 mods or game directory")
    parser.add_argument("--quarantine-dir", type=Path, default=None, help="Path to quarantine/backup directory")
    parser.add_argument("--save-dir", type=Path, default=None, help="Path to Cyberpunk 2077 saves directory")
    parser.add_argument("--port", type=int, default=8077, help="Local server port (default: 8077)")
    parser.add_argument("--generate-mock", type=int, default=0, help="Generate N mock clothing items on startup")
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically open the browser")
    args = parser.parse_args()

    root = Path(__file__).parent.resolve()
    chosen_mod_dir = args.mod_dir
    if chosen_mod_dir is None and args.generate_mock == 0:
        detected = detect_cp2077_installations()
        for inst in detected:
            p = Path(inst["path"])
            if (p / "archive" / "pc" / "mod").exists():
                chosen_mod_dir = p
                break

    config = AppConfig.from_root(
        root=root,
        mod_dir=chosen_mod_dir,
        quarantine_dir=args.quarantine_dir,
        save_dir=args.save_dir,
        port=args.port,
    )

    if args.generate_mock > 0:
        generate_mock_mods(config.mod_dir, count=args.generate_mock)
    elif chosen_mod_dir is None and not config.mod_dir.exists():
        generate_mock_mods(config.mod_dir, count=120)

    httpd, state = create_server(config, async_scan=True)
    url = f"http://{config.host}:{config.port}/"
    print(f"2077view running at {url}")
    print(f"  Mod dir:        {config.mod_dir} ({len(state.items)} items loaded)")
    print(f"  Quarantine dir: {config.quarantine_dir}")
    print(f"  Save dir:       {config.save_dir}")
    print("Press Ctrl+C to stop.")

    if not args.no_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down 2077view...")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()

