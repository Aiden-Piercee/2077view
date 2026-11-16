"""Tests for Cyberpunk 2077 save metadata parsing and CET command generation."""

from pathlib import Path
import json
import tempfile
import unittest

from cp2077_atelier.save_reader import discover_saves, generate_cet_commands, parse_save_metadata


class TestSaveReader(unittest.TestCase):
    def test_parse_and_discover_saves(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            save_folder = Path(tmp) / "ManualSave-0"
            save_folder.mkdir(parents=True)
            meta_file = save_folder / "metadata.9.json"
            meta_file.write_text(
                json.dumps({
                    "Data": {
                        "metadata": {
                            "lifePath": "Corpo",
                            "bodyGender": "Female",
                            "level": 50,
                            "streetCred": 50,
                            "playTime": 18000,
                            "difficulty": "VeryHard",
                            "timestampString": "2026-11-16 18:00:00",
                        }
                    }
                }),
                encoding="utf-8",
            )

            profile = parse_save_metadata(meta_file)
            self.assertEqual(profile.life_path, "Corpo")
            self.assertEqual(profile.body_gender, "FemV")
            self.assertEqual(profile.level, 50)
            self.assertEqual(profile.play_time_hours, 5.0)

            discovered = discover_saves(Path(tmp))
            self.assertEqual(len(discovered), 1)
            self.assertEqual(discovered[0].save_name, "ManualSave-0")

    def test_generate_cet_commands(self) -> None:
        cmds = generate_cet_commands(["Items.jacket_01", "Items.boots_02"])
        self.assertEqual(
            cmds,
            'Game.AddToInventory("Items.jacket_01", 1)\nGame.AddToInventory("Items.boots_02", 1)',
        )


if __name__ == "__main__":
    unittest.main()

