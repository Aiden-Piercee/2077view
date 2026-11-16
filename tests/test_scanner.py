"""Tests for mod directory scanning, metadata extraction, filtering, and sorting."""

from pathlib import Path
import struct
import tempfile
import unittest

from cp2077_atelier.mock_generator import generate_mock_mods
from cp2077_atelier.scanner import (
    filter_and_sort_items,
    inspect_archive_header,
    parse_reds_atelier,
    parse_yaml_tweaks,
    scan_mod_directory,
)


class TestScanner(unittest.TestCase):
    def test_inspect_rdar_archive_header(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            arch = Path(tmp) / "test_jacket.archive"
            arch.write_bytes(b"RDAR" + struct.pack("<I", 12) + struct.pack("<Q", 128) + b"\x00" * 32)
            info = inspect_archive_header(arch)
            self.assertTrue(info.valid_rdar)
            self.assertEqual(info.version, 12)
            self.assertEqual(info.index_offset, 128)
            self.assertEqual(info.file_size, 48)

    def test_parse_yaml_and_reds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            yaml_file = root / "cyber_coat.yaml"
            yaml_file.write_text(
                "Items.cyber_coat_01:\n"
                "  displayName: Neon Trenchcoat\n"
                "  slot: EquipmentAreas.OuterTorso\n"
                "  quality: Quality.Legendary\n"
                "  bodyType: FemV\n"
                "  tags: [neon, streetwear]\n",
                encoding="utf-8",
            )
            reds_file = root / "neon_atelier.reds"
            reds_file.write_text(
                'RegisterStore(this, "Kabuki Neon Store");\n'
                'AddStoreItem("Items.cyber_coat_01", 4200, "Iconic");\n',
                encoding="utf-8",
            )
            (root / "cyber_coat.archive").write_bytes(b"RDAR" + b"\x00" * 20)

            tweaks = parse_yaml_tweaks(yaml_file)
            self.assertEqual(len(tweaks), 1)
            self.assertEqual(tweaks[0]["name"], "Neon Trenchcoat")

            reds = parse_reds_atelier(reds_file)
            self.assertEqual(reds["store_name"], "Kabuki Neon Store")
            self.assertIn("Items.cyber_coat_01", reds["items"])

            items = scan_mod_directory(root)
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].atelier_store, "Kabuki Neon Store")
            self.assertEqual(items[0].price, 4200)
            self.assertEqual(items[0].quality, "Iconic")
            self.assertEqual(items[0].category, "Outer Torso")

    def test_mock_120_items_filter_and_sort(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mod_dir = Path(tmp) / "mods"
            generate_mock_mods(mod_dir, count=120)
            items = scan_mod_directory(mod_dir)
            self.assertEqual(len(items), 120)

            # Filter by category
            outer = filter_and_sort_items(items, category="Outer Torso")
            self.assertTrue(len(outer) > 0)
            self.assertTrue(all(i.category == "Outer Torso" for i in outer))

            # Search query
            arasaka = filter_and_sort_items(items, query="Arasaka")
            self.assertEqual(len(arasaka), 20)

            # Sort by name desc
            sorted_desc = filter_and_sort_items(items, sort_by="name", sort_dir="desc")
            names = [i.name.lower() for i in sorted_desc]
            self.assertEqual(names, sorted(names, reverse=True))

            # Sort by date_added desc
            sorted_date = filter_and_sort_items(items, sort_by="date_added", sort_dir="desc")
            dates = [i.date_added for i in sorted_date]
            self.assertEqual(dates, sorted(dates, reverse=True))

    def test_archivexl_instances_and_game_root_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            game_root = Path(tmp) / "Cyberpunk 2077"
            (game_root / "archive" / "pc" / "mod").mkdir(parents=True)
            (game_root / "r6" / "tweaks" / "my_mod").mkdir(parents=True)
            (game_root / "r6" / "scripts" / "my_mod").mkdir(parents=True)

            (game_root / "archive" / "pc" / "mod" / "my_jacket.archive").write_bytes(
                b"RDAR" + struct.pack("<I", 12) + struct.pack("<Q", 64) + b"\x00" * 16
            )
            (game_root / "r6" / "tweaks" / "my_mod" / "my_jacket.yaml").write_text(
                "Items.my_jacket_$(color):\n"
                "  $instances:\n"
                "    - { color: black }\n"
                "    - { color: red }\n"
                "  displayName: Cyber Jacket $(color)\n"
                "  quality: Quality.Legendary\n"
                "  placementSlots:\n"
                "    - !append OutfitSlots.TorsoOuter\n",
                encoding="utf-8",
            )
            (game_root / "r6" / "scripts" / "my_mod" / "atelier.reds").write_text(
                'RegisterStore(this, "Night City Armory");\n'
                'AddStoreItem("Items.my_jacket_black", 3000, "Iconic");\n',
                encoding="utf-8",
            )

            items = scan_mod_directory(game_root)
            self.assertEqual(len(items), 2)
            names = sorted(i.name for i in items)
            self.assertEqual(names, ["Cyber Jacket black", "Cyber Jacket red"])
            self.assertTrue(all(i.category == "Outer Torso" for i in items))
            black = [i for i in items if i.tweak_id == "Items.my_jacket_black"][0]
            self.assertEqual(black.atelier_store, "Night City Armory")
            self.assertEqual(black.price, 3000)


if __name__ == "__main__":
    unittest.main()

