"""Tests for rejection marking, quarantine file moves, restore, and permanent delete."""

from pathlib import Path
import tempfile
import unittest

from cp2077_atelier.mock_generator import generate_mock_mods
from cp2077_atelier.quarantine import QuarantineManager
from cp2077_atelier.scanner import scan_mod_directory


class TestQuarantine(unittest.TestCase):
    def test_reject_quarantine_restore_and_delete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mod_dir = root / "mods"
            quarantine_dir = root / "_quarantine"
            state_file = root / ".state.json"

            generate_mock_mods(mod_dir, count=12)  # 2 items per 6 stores
            qm = QuarantineManager(mod_dir, quarantine_dir, state_file)
            items = scan_mod_directory(mod_dir)
            self.assertEqual(len(items), 12)

            # Reject items belonging to first mod package
            target_mod = items[0].source_mod
            target_ids = [i.id for i in items if i.source_mod == target_mod]
            qm.reject_items(target_ids)
            self.assertEqual(qm.rejected_ids, set(target_ids))

            # Execute quarantine
            res = qm.execute_quarantine(items)
            self.assertTrue(len(res["moved_files"]) > 0)
            self.assertEqual(len(res["records"]), 1)
            rec_id = res["records"][0]["record_id"]

            # Files should no longer exist in mod_dir, and should exist in quarantine_dir
            for rel in res["moved_files"]:
                self.assertFalse((mod_dir / rel).exists())
                self.assertTrue((quarantine_dir / rel).exists())

            # Rescanning mod_dir should now only show the remaining 10 items
            remaining = scan_mod_directory(mod_dir, rejected_ids=qm.rejected_ids)
            self.assertEqual(len(remaining), 10)

            # Restore from quarantine
            restored = qm.restore_quarantined(rec_id)
            self.assertEqual(set(restored["restored_files"]), set(res["moved_files"]))
            for rel in res["moved_files"]:
                self.assertTrue((mod_dir / rel).exists())
                self.assertFalse((quarantine_dir / rel).exists())

            # Re-quarantine and test permanent delete requires confirm=True
            qm.reject_items(target_ids)
            res2 = qm.execute_quarantine(scan_mod_directory(mod_dir))
            rec_id2 = res2["records"][0]["record_id"]

            with self.assertRaises(PermissionError):
                qm.delete_quarantined(rec_id2, confirm=False)

            del_res = qm.delete_quarantined(rec_id2, confirm=True)
            self.assertEqual(set(del_res["deleted_files"]), set(res2["moved_files"]))
            for rel in del_res["deleted_files"]:
                self.assertFalse((quarantine_dir / rel).exists())


if __name__ == "__main__":
    unittest.main()

