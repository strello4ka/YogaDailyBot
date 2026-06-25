"""Unit-тесты утренней сводки челленджа."""

import unittest

from app.challenge.messages import (
    CHALLENGE_DURATION,
    ChallengeParticipant,
    ProgressRow,
    build_final_rows,
    build_progress_rows,
    build_summary_message,
    detect_summary_kind,
    display_name,
    rank_final_results,
)


def _participant(user_id: int, nickname=None, name=None, day=7):
    return ChallengeParticipant(
        user_id=user_id,
        user_name=name,
        user_nickname=nickname,
        challenge_day=day,
    )


class DisplayNameTests(unittest.TestCase):
    def test_nickname_with_at(self):
        self.assertEqual(display_name("@anna", "Anna"), "@anna")

    def test_nickname_without_at(self):
        self.assertEqual(display_name("petr", "Petr"), "@petr")

    def test_fallback_to_name(self):
        self.assertEqual(display_name(None, "Екатерина"), "Екатерина")

    def test_fallback_participant(self):
        self.assertEqual(display_name(None, None), "Участник")


class DetectSummaryKindTests(unittest.TestCase):
    def test_daily(self):
        self.assertEqual(detect_summary_kind(3, False), "daily")

    def test_intermediate_days(self):
        for day in (7, 14, 21):
            self.assertEqual(detect_summary_kind(day, False), "intermediate")

    def test_final(self):
        self.assertEqual(detect_summary_kind(28, False), "final")

    def test_stopped(self):
        self.assertIsNone(detect_summary_kind(5, True))

    def test_after_final_day(self):
        self.assertIsNone(detect_summary_kind(29, False))


class RankFinalResultsTests(unittest.TestCase):
    def test_competition_ranking_with_tie(self):
        rows = [
            ProgressRow(_participant(1, "a", day=28), completed=28, total=28),
            ProgressRow(_participant(2, "b", day=28), completed=28, total=28),
            ProgressRow(_participant(3, "c", day=28), completed=20, total=28),
        ]
        ranked = rank_final_results(rows)
        self.assertEqual([r.rank for r in ranked], [1, 1, 3])
        self.assertEqual(ranked[0].label, "1 место")
        self.assertEqual(ranked[2].label, "молодец")

    def test_top_two_places_only(self):
        rows = [
            ProgressRow(_participant(1, "a", day=28), completed=25, total=28),
            ProgressRow(_participant(2, "b", day=28), completed=20, total=28),
            ProgressRow(_participant(3, "c", day=28), completed=18, total=28),
        ]
        ranked = rank_final_results(rows)
        self.assertEqual(ranked[0].label, "1 место")
        self.assertEqual(ranked[1].label, "2 место")
        self.assertEqual(ranked[2].label, "молодец")


class BuildSummaryMessageTests(unittest.TestCase):
    def test_daily_message(self):
        participants = [
            _participant(1, "anna"),
            _participant(2, nickname=None, name="Екатерина"),
        ]
        text = build_summary_message("daily", participants, {1})
        self.assertIn("🌅 Доброе утро, йоги!", text)
        self.assertIn("1 из 2 участников", text)
        self.assertIn("@anna", text)
        self.assertNotIn("Промежуточные", text)

    def test_intermediate_message(self):
        participants = [_participant(1, "anna", day=7), _participant(2, "petr", day=7)]
        progress = build_progress_rows(participants, {1: 7, 2: 6})
        text = build_summary_message("intermediate", participants, {1, 2}, progress_rows=progress)
        self.assertIn("Промежуточные итоги челленджа:", text)
        self.assertIn("@anna — 7/7 дней", text)
        self.assertIn("@petr — 6/7 дней", text)

    def test_final_message(self):
        participants = [
            _participant(1, "anna", day=28),
            _participant(2, "petr", day=28),
            _participant(3, nickname=None, name="Екатерина", day=28),
        ]
        completed = {1: 28, 2: 20, 3: 18}
        final_rows = build_final_rows(participants, completed)
        text = build_summary_message("final", participants, set(), final_rows=final_rows)
        self.assertIn("Поздравляю с окончанием челленджа!", text)
        self.assertIn("@anna — 28/28 дней — 1 место", text)
        self.assertIn("@petr — 20/28 дней — 2 место", text)
        self.assertIn("Екатерина — 18/28 дней — молодец", text)
        self.assertNotIn("Итоги за вчера", text)


if __name__ == "__main__":
    unittest.main()
