import sys
import types
import unittest


fake_db = types.ModuleType("data.db")
fake_db.get_available_combined_difficulties = lambda *_args, **_kwargs: set()
fake_db.get_available_combined_tegs = lambda *_args, **_kwargs: set()
fake_db.pick_random_combined_mood_pool = lambda *_args, **_kwargs: None
fake_db.remove_extra_practices_inline_message = lambda *_args, **_kwargs: None
sys.modules["data.db"] = fake_db

fake_send_utils = types.ModuleType("app.by_mood.send_utils")
fake_send_utils.deliver_by_mood_practice = lambda *_args, **_kwargs: None
sys.modules["app.by_mood.send_utils"] = fake_send_utils

from app.by_mood import self_decide


def keyboard_labels(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


def keyboard_callbacks(markup) -> list[str]:
    return [button.callback_data for row in markup.inline_keyboard for button in row]


class SelfDecideTegTest(unittest.TestCase):
    def test_teg_keyboard_shows_only_available_tegs_and_any(self):
        markup = self_decide.teg_keyboard(
            "t15_20",
            {"Здоровая спина", "Зарядка", "Неизвестный тег"},
        )

        self.assertEqual(
            keyboard_labels(markup),
            ["Зарядка", "Здоровая спина", "любой"],
        )
        self.assertEqual(
            keyboard_callbacks(markup),
            [
                "self_teg:t15_20:charge",
                "self_teg:t15_20:back",
                "self_teg:t15_20:any",
            ],
        )

    def test_difficulty_keyboard_shows_available_levels_and_any(self):
        markup = self_decide.difficulty_keyboard(
            "t20_30",
            "core",
            {"низкий", "ВЫСОКАЯ", "сверх высокая"},
        )

        self.assertEqual(keyboard_labels(markup), ["низкая", "высокая", "любая"])
        self.assertEqual(
            keyboard_callbacks(markup),
            [
                "self_difficulty:t20_30:core:ilow",
                "self_difficulty:t20_30:core:ihigh",
                "self_difficulty:t20_30:core:iany",
            ],
        )

    def test_selected_teg_adds_parameterized_array_filter(self):
        where_sql, params = self_decide._sql_for_teg_choice("Кор и пресс")

        self.assertIn("%s = ANY", where_sql)
        self.assertIn("yp.teg", where_sql)
        self.assertEqual(params, ("Кор и пресс",))

    def test_any_teg_skips_teg_filter(self):
        self.assertEqual(
            self_decide._sql_for_teg_choice(self_decide.ANY_TEG_LABEL),
            ("", ()),
        )

    def test_callback_data_fits_telegram_limit(self):
        markup = self_decide.difficulty_keyboard(
            "t45_60p",
            "arm_balance",
            {"низкая", "средняя", "высокая"},
            callback_prefix="extra_self_difficulty",
        )

        self.assertTrue(all(len(value.encode("utf-8")) <= 64 for value in keyboard_callbacks(markup)))


if __name__ == "__main__":
    unittest.main()
