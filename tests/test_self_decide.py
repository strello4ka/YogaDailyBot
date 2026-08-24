import sys
import types
import unittest


fake_db = types.ModuleType("data.db")
fake_db.get_available_combined_difficulties = lambda *_args, **_kwargs: set()
fake_db.get_available_combined_tegs = lambda *_args, **_kwargs: set()
fake_db.pick_random_combined_mood_pool = lambda *_args, **_kwargs: None
fake_db.remove_extra_practices_inline_message = lambda *_args, **_kwargs: None
fake_db.append_extra_practices_inline_message = lambda *_args, **_kwargs: None
fake_db.get_user_bot_mode = lambda *_args, **_kwargs: "by_mood"
fake_db.take_and_clear_extra_practices_inline_messages = lambda *_args, **_kwargs: []
fake_db.PRACTICE_CATALOG_YOGA = "yoga"
fake_db.PRACTICE_CATALOG_MOOD = "mood"
sys.modules["data.db"] = fake_db

fake_send_utils = types.ModuleType("app.by_mood.send_utils")
fake_send_utils.deliver_by_mood_practice = lambda *_args, **_kwargs: None
sys.modules["app.by_mood.send_utils"] = fake_send_utils

from app.by_mood import self_decide
from app.by_mood import quick_filters
from app.daily.extra_practices import get_extra_practices_inline_keyboard
from app.keyboards import get_by_mood_reply_keyboard


def keyboard_labels(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


def keyboard_callbacks(markup) -> list[str]:
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def keyboard_rows(markup) -> list[list[str]]:
    return [[button.text for button in row] for row in markup.inline_keyboard]


class SelfDecideTegTest(unittest.TestCase):
    def test_teg_keyboard_shows_only_available_tegs_and_any(self):
        markup = self_decide.teg_keyboard(
            "t15_20",
            {"Здоровая спина", "Зарядка", "Неизвестный тег"},
        )

        self.assertEqual(
            keyboard_labels(markup),
            ["Зарядка", "Здоровая спина", "назад", "любой"],
        )
        self.assertEqual(
            keyboard_callbacks(markup),
            [
                "self_teg:t15_20:charge",
                "self_teg:t15_20:back",
                "self_time:back",
                "self_teg:t15_20:any",
            ],
        )
        self.assertEqual(keyboard_rows(markup)[-1], ["назад", "любой"])

    def test_single_teg_hides_any_and_strong_legs_is_not_on_front(self):
        markup = self_decide.teg_keyboard(
            "t45_60p",
            {"ТБС и шпагаты", "Сильные ноги"},
        )

        self.assertEqual(keyboard_rows(markup), [["ТБС и шпагаты"], ["назад"]])
        self.assertNotIn("любой", keyboard_labels(markup))
        self.assertNotIn("Сильные ноги", keyboard_labels(markup))

    def test_difficulty_keyboard_shows_available_levels_and_any(self):
        markup = self_decide.difficulty_keyboard(
            "t20_30",
            "core",
            {"низкий", "ВЫСОКАЯ", "сверх высокая"},
        )

        self.assertEqual(
            keyboard_labels(markup),
            ["низкая", "высокая", "назад", "любая"],
        )
        self.assertEqual(
            keyboard_callbacks(markup),
            [
                "self_difficulty:t20_30:core:ilow",
                "self_difficulty:t20_30:core:ihigh",
                "self_time:t20_30",
                "self_difficulty:t20_30:core:iany",
            ],
        )
        self.assertEqual(keyboard_rows(markup)[-1], ["назад", "любая"])

    def test_single_difficulty_hides_any(self):
        markup = self_decide.difficulty_keyboard(
            "t10",
            "charge",
            {"средняя"},
            back_callback_prefix="extra_self_time",
        )

        self.assertEqual(keyboard_rows(markup), [["средняя"], ["назад"]])
        self.assertEqual(
            keyboard_callbacks(markup),
            [
                "self_difficulty:t10:charge:imed",
                "extra_self_time:t10",
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


class QuickFiltersTest(unittest.TestCase):
    def test_default_buttons_replace_hard_and_long(self):
        specs = quick_filters.get_active_quick_filters()
        labels = [spec.label for spec in specs]

        self.assertIn("Здоровая спина", labels)
        self.assertIn("Расслабление", labels)
        self.assertNotIn("Хард", labels)
        self.assertNotIn("Длинные", labels)

    def test_toggle_controls_order_and_ignores_duplicates(self):
        specs = quick_filters.get_active_quick_filters("hard,relax,hard,long")

        self.assertEqual(
            [spec.slug for spec in specs],
            ["hard", "relax", "long"],
        )

    def test_empty_or_invalid_toggle_keeps_self_decide(self):
        self.assertEqual(
            [spec.slug for spec in quick_filters.get_active_quick_filters("unknown")],
            ["self"],
        )

    def test_both_surfaces_use_same_default_buttons(self):
        reply_labels = [
            button.text
            for row in get_by_mood_reply_keyboard().keyboard
            for button in row
        ]
        inline_labels = keyboard_labels(get_extra_practices_inline_keyboard())

        self.assertEqual(reply_labels, inline_labels)

    def test_tag_quick_filters_use_parameterized_teg_search(self):
        healthy_back = quick_filters.get_quick_filter("healthy_back")
        relax = quick_filters.get_quick_filter("relax")

        self.assertIsNotNone(healthy_back)
        self.assertIsNotNone(relax)
        self.assertIn("%s = ANY", healthy_back.where_sql)
        self.assertEqual(healthy_back.params, ("Здоровая спина",))
        self.assertEqual(relax.params, ("Расслабление",))


if __name__ == "__main__":
    unittest.main()
