import json, tempfile, unittest
from pathlib import Path
from blockreel import parts
from blockreel.avatar import load_avatar


class Parts(unittest.TestCase):
    def test_every_shipped_part_validates(self):
        for folder in parts.FOLDERS:
            for pid in parts.all_part_ids(folder):
                parts.load_part(folder, pid)          # raises on a bad part

    def test_main_is_minifig_and_locked(self):
        a = load_avatar("main", None, None)
        self.assertEqual(a.rig.data.get("kind"), "minifig")
        self.assertTrue(a.locked)

    def test_bad_part_gives_clear_error(self):
        with self.assertRaises(Exception):
            parts.validate_part("hair", "x", {"pieces": [{"shape": "banana"}]}, Path("."))

    def test_fingerprint_changes_with_variant(self):
        self.assertNotEqual(load_avatar("main", None, None).fingerprint,
                            load_avatar("main", "jacket", None).fingerprint)


if __name__ == "__main__":
    unittest.main()
