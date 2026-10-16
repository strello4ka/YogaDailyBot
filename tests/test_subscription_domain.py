"""Local subscription rules; no network, Telegram calls or database imports."""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.subscription.access import AccessState, Feature, Subscription, has_access
from app.subscription.demo import start_trial
from app.subscription.tariff import MOSCOW, TARIFFS, last_access_date, purchased_period
from data.subscription_repository import SubscriptionRepository


def at(day, hour=0):
    return datetime(2026, 10, day, hour, tzinfo=MOSCOW)


class SubscriptionDomainTest(unittest.TestCase):
    def test_tariffs_are_fixed_days_and_integer_money(self):
        self.assertEqual([(t.days, t.amount) for t in TARIFFS.values()],
                         [(30, "350.00"), (90, "800.00"), (180, "1400.00"), (365, "2500.00")])

    def test_trial_late_start_counts_first_calendar_day(self):
        trial = start_trial(at(1, 23))
        self.assertEqual(trial.ends_at, at(15))
        self.assertEqual(trial.days_left(at(1, 23)), 14)
        self.assertEqual(trial.days_left(at(14, 23)), 1)
        self.assertFalse(trial.is_active(at(15)))
        self.assertEqual(trial.days_left(at(15)), 0)
        self.assertEqual(start_trial(at(1)).ends_at, trial.ends_at)

    def test_repeat_start_keeps_even_expired_trial(self):
        trial = start_trial(at(1))
        self.assertIs(start_trial(at(2), trial), trial)
        self.assertIs(start_trial(at(30), trial), trial)

    def test_utc_start_uses_moscow_date(self):
        trial = start_trial(datetime(2026, 9, 30, 22, tzinfo=timezone.utc))
        self.assertEqual(trial.ends_at, at(15))

    def test_naive_time_is_rejected(self):
        with self.assertRaises(ValueError):
            start_trial(datetime(2026, 10, 1))

    def test_late_purchase_counts_purchase_date_as_first_paid_day(self):
        for hour in (0, 12, 23):
            with self.subTest(hour=hour):
                bought_at = at(13, hour)
                paid = purchased_period("month", bought_at)
                self.assertEqual(paid.starts_at, bought_at)
                self.assertEqual(paid.ends_at, datetime(2026, 11, 12, tzinfo=MOSCOW))
                self.assertEqual(last_access_date(paid.ends_at).isoformat(), "2026-11-11")
                state = Subscription(paid=paid)
                self.assertEqual(state.state(bought_at - timedelta(microseconds=1)), AccessState.FREE)
                self.assertEqual(state.state(bought_at), AccessState.PAID)
                self.assertEqual(state.state(paid.ends_at), AccessState.FREE)

    def test_purchase_after_expired_periods_starts_immediately(self):
        now = at(20, 23)
        paid = purchased_period("month", now, trial_ends_at=at(15), paid_ends_at=at(19))
        self.assertEqual(paid.starts_at, now)
        self.assertEqual(paid.ends_at, datetime(2026, 11, 19, tzinfo=MOSCOW))

    def test_purchase_near_midnight_uses_moscow_date(self):
        now = datetime(2026, 10, 13, 22, tzinfo=timezone.utc)
        paid = purchased_period("month", now)
        self.assertEqual(paid.starts_at, at(14, 1))
        self.assertEqual(paid.ends_at, datetime(2026, 11, 13, tzinfo=MOSCOW))

    def test_late_purchase_during_trial_keeps_full_paid_days(self):
        trial = start_trial(at(1))
        paid = purchased_period("month", at(14, 23), trial_ends_at=trial.ends_at)
        self.assertEqual(paid.starts_at, at(15))
        self.assertEqual(paid.ends_at - paid.starts_at, timedelta(days=30))

    def test_trial_purchase_has_no_access_gap(self):
        trial = start_trial(at(1))
        paid = purchased_period("month", at(4), trial_ends_at=trial.ends_at)
        state = Subscription(trial, paid)
        self.assertEqual(paid.starts_at, at(15))
        self.assertEqual(state.state(at(14, 23)), AccessState.TRIAL_PAID)
        self.assertEqual(state.state(at(15)), AccessState.PAID)
        self.assertEqual(state.state(paid.ends_at), AccessState.FREE)
        self.assertEqual(last_access_date(paid.ends_at).isoformat(), "2026-11-13")

    def test_renewal_preserves_paid_and_trial_days(self):
        trial = start_trial(at(1))
        first = purchased_period("month", at(4), trial_ends_at=trial.ends_at)
        second = purchased_period("quarter", at(5), trial_ends_at=trial.ends_at,
                                  paid_ends_at=first.ends_at)
        self.assertEqual(second.starts_at, first.ends_at)
        self.assertEqual(second.ends_at - first.ends_at, timedelta(days=90))

    def test_year_is_365_days_over_leap_boundary(self):
        paid = purchased_period("year", datetime(2027, 3, 1, tzinfo=MOSCOW))
        self.assertEqual(paid.ends_at, datetime(2028, 2, 29, tzinfo=MOSCOW))

    def test_access_expires_without_waiting_for_a_job(self):
        trial = start_trial(at(1))
        subscription = Subscription(trial)
        for feature in (Feature.FAVORITES, Feature.SELECTION, Feature.SCHEDULE):
            self.assertTrue(has_access(subscription, feature, at(14, 23)))
            self.assertFalse(has_access(subscription, feature, at(15)))
        for feature in (Feature.PROGRESS, Feature.PRACTICE_OF_DAY, Feature.HELP,
                        Feature.COMPLETION_REMINDER):
            self.assertTrue(has_access(subscription, feature, at(15)))

    def test_unknown_feature_is_not_granted(self):
        with self.assertRaises(ValueError):
            has_access(Subscription(start_trial(at(1))), "typo", at(2))


class SubscriptionStorageBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.factory = MagicMock()
        self.connection = self.factory.return_value
        self.cursor = self.connection.cursor.return_value.__enter__.return_value
        self.repository = SubscriptionRepository(self.factory)

    def test_constructing_repository_does_not_open_a_connection(self):
        self.factory.assert_not_called()

    def test_missing_user_is_not_implicitly_free_or_enrolled(self):
        self.cursor.fetchone.return_value = None
        self.assertIsNone(self.repository.get(10))
        statements = [c.args[0] for c in self.cursor.execute.call_args_list]
        self.assertTrue(all(statement.startswith('SELECT') for statement in statements))
        self.connection.close.assert_called_once()

    def test_existing_expired_trial_is_not_replaced(self):
        trial = start_trial(at(1))
        self.cursor.fetchone.return_value = (trial.started_at, trial.ends_at, None, None)
        result = self.repository.begin_trial(10, at(30))
        self.assertEqual(result.trial, trial)
        self.assertFalse(any(c.args[0].startswith('UPDATE') for c in self.cursor.execute.call_args_list))

    def test_test_onboarding_keeps_existing_trial_but_explicit_replay_restarts_it(self):
        original = start_trial(at(1))
        row = (original.started_at, original.ends_at, None, None)
        self.cursor.fetchone.return_value = row
        unchanged = self.repository.begin_fast_trial(10, at(2))
        self.assertEqual(unchanged.trial, original)
        self.assertFalse(any(c.args[0].startswith('UPDATE') for c in self.cursor.execute.call_args_list))

        self.cursor.reset_mock()
        self.cursor.fetchone.side_effect = [row, (False,)]
        replayed = self.repository.begin_fast_trial(10, at(2), replay=True)
        self.assertEqual(replayed.trial.ends_at - replayed.trial.started_at,
                         timedelta(minutes=15))
        self.assertTrue(any(c.args[0].startswith('UPDATE') for c in self.cursor.execute.call_args_list))

    def test_database_error_closes_connection_and_propagates(self):
        self.cursor.execute.side_effect = RuntimeError('database unavailable')
        with self.assertRaisesRegex(RuntimeError, 'database unavailable'):
            self.repository.get(10)
        self.connection.close.assert_called_once()

    def test_daily_practice_uses_saved_choice_without_randomizing(self):
        from unittest.mock import Mock
        self.cursor.fetchone.return_value = (12, 'yoga')
        choose, load = Mock(), Mock(return_value=(12, 'video'))
        result = self.repository.daily_practice(10, at(13, 23), choose, load)
        self.assertEqual(result, (12, 'video'))
        choose.assert_not_called()
        load.assert_called_once_with(12, 'yoga')

    def test_daily_practice_records_first_choice_under_database_lock(self):
        from unittest.mock import Mock
        self.cursor.fetchone.return_value = None
        choose, load = Mock(return_value=((12, 'video'), 'yoga')), Mock()
        self.assertEqual(self.repository.daily_practice(10, at(13), choose, load), (12, 'video'))
        statements = [c.args[0] for c in self.cursor.execute.call_args_list]
        self.assertIn('pg_advisory_xact_lock', statements[0])
        self.assertTrue(statements[-1].startswith('INSERT'))
        load.assert_not_called()

    def test_old_restore_button_cannot_change_schedule(self):
        from datetime import timedelta
        start = at(20)
        self.cursor.fetchone.return_value = (start, start + timedelta(days=30), True)
        self.assertEqual(self.repository.resolve_restore(10, str(int(at(19).timestamp())),
                                                         at(21), True), 'stale')
        self.assertFalse(any(c.args[0].startswith('UPDATE') for c in self.cursor.execute.call_args_list))

    def test_restore_consent_enables_saved_time_from_next_day(self):
        start = at(20)
        self.cursor.fetchone.side_effect = [(start, at(30), True), ('09:30', 'daily')]
        self.assertEqual(self.repository.resolve_restore(10, str(int(start.timestamp())),
                                                         at(21), True), 'restored')
        updates = [c.args for c in self.cursor.execute.call_args_list if c.args[0].startswith('UPDATE')]
        self.assertEqual(updates[0][1][0], at(22).date())
        self.assertIn('schedule_restore_required=FALSE', updates[-1][0])

    def test_no_saved_time_routes_to_setup_without_enabling_delivery(self):
        start = at(20)
        self.cursor.fetchone.side_effect = [(start, at(30), True), ('00:00', 'daily')]
        self.assertEqual(self.repository.resolve_restore(10, str(int(start.timestamp())),
                                                         at(21), True), 'setup')
        self.assertFalse(any('daily_schedule_enabled=TRUE' in c.args[0]
                             for c in self.cursor.execute.call_args_list))


if __name__ == "__main__":
    unittest.main()
