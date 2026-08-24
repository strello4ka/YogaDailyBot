import importlib.util
import sys
import unittest
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = PROJECT_ROOT / "tools" / "migrate_practice_teg.py"
SPEC = importlib.util.spec_from_file_location("migrate_practice_teg", MODULE_PATH)
assert SPEC and SPEC.loader
migration = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = migration
SPEC.loader.exec_module(migration)


class PracticeTegPayloadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = migration.load_payload(migration.DEFAULT_PAYLOAD_PATH)

    def test_expected_catalog_counts(self):
        counts = Counter(item.catalog for item in self.payload.practices)
        self.assertEqual(len(self.payload.practices), 99)
        self.assertEqual(counts, Counter({"yoga": 68, "mood": 31}))

    def test_keys_and_tegs_are_unique(self):
        keys = [
            (item.catalog, item.practice_id)
            for item in self.payload.practices
        ]
        self.assertEqual(len(keys), len(set(keys)))
        for item in self.payload.practices:
            self.assertTrue(item.teg)
            self.assertEqual(len(item.teg), len(set(item.teg)))
            self.assertTrue(set(item.teg) <= self.payload.allowed_teg)

    def test_expected_teg_distribution(self):
        counts = Counter(
            tag
            for item in self.payload.practices
            for tag in item.teg
        )
        self.assertEqual(
            counts,
            Counter(
                {
                    "Всё тело": 48,
                    "Зарядка": 44,
                    "Расслабление": 28,
                    "Сильное тело": 22,
                    "Здоровая спина": 18,
                    "Кор и пресс": 15,
                    "ТБС и шпагаты": 11,
                    "Балансы на руках": 8,
                    "Сильные ноги": 1,
                }
            ),
        )

    def test_replaced_duplicate_practices_are_excluded(self):
        keys = {
            (item.catalog, item.practice_id)
            for item in self.payload.practices
        }
        self.assertNotIn(("yoga", 13), keys)
        self.assertNotIn(("yoga", 78), keys)

    def test_apply_requires_exact_confirmation(self):
        migration.validate_apply_confirmation(False, None)
        migration.validate_apply_confirmation(True, migration.CONFIRMATION)
        with self.assertRaises(ValueError):
            migration.validate_apply_confirmation(True, None)
        with self.assertRaises(ValueError):
            migration.validate_apply_confirmation(True, "YES")

    def test_title_comparison_ignores_outer_spaces_only(self):
        self.assertEqual(
            migration.normalize_title("Йога-зарядка "),
            migration.normalize_title("Йога-зарядка"),
        )
        self.assertNotEqual(
            migration.normalize_title("Йога для рук"),
            migration.normalize_title("Йога для спины"),
        )


if __name__ == "__main__":
    unittest.main()
