"""Subscription persistence using an explicitly provided connection factory.

No import of data.db (which initializes the database on import), no automatic
migration, and no implicit enrollment of existing users.
"""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from app.subscription.access import Subscription
from app.subscription.access import AccessState
from app.subscription.demo import FAST_TRIAL_DURATION, Trial, start_trial
from app.subscription.old_users.prices import checkout_price as old_user_checkout_price
from app.subscription.old_users.repository import (CheckoutProfile, enroll as enroll_old_users,
                                                   offer_from_values)
from app.subscription.old_users.rules import GiftPeriod
from app.subscription.tariff import PaidPeriod, local_time, midnight


def _snapshot(row) -> Subscription:
    trial_start, trial_end, paid_start, paid_end, gift_start, gift_end = row
    return Subscription(
        Trial(trial_start, trial_end) if trial_start is not None else None,
        PaidPeriod(paid_start, paid_end) if paid_start is not None else None,
        GiftPeriod(gift_start, gift_end) if gift_start is not None else None,
    )


class SubscriptionRepository:
    def __init__(self, connection_factory: Callable, *, payment_scope=None):
        self.connection_factory = connection_factory
        self.payment_scope = payment_scope

    def _payment_scope_sql(self, alias=''):
        if self.payment_scope is None:
            return '', ()
        return ' AND {}payment_scope=%s '.format(alias), (self.payment_scope,)

    @contextmanager
    def _transaction(self):
        connection = self.connection_factory()
        try:
            with connection:
                with connection.cursor() as cursor:
                    yield cursor
        finally:
            connection.close()

    def get(self, user_id: int) -> Optional[Subscription]:
        """None means not enrolled, not a free user to restrict automatically."""
        with self._transaction() as cursor:
            cursor.execute(
                "SELECT trial_started_at,trial_ends_at,subscription_starts,subscription_ends,"
                "gift_starts,gift_ends "
                "FROM subscription_accounts WHERE user_id = %s", (user_id,),
            )
            row = cursor.fetchone()
        return _snapshot(row) if row is not None else None

    def enrolled_user_ids(self):
        """Only accounts that started the test flow need background jobs."""
        with self._transaction() as cursor:
            cursor.execute("SELECT user_id FROM subscription_accounts")
            return [row[0] for row in cursor.fetchall()]

    def verify_test_database(self, expected_name: str) -> None:
        with self._transaction() as cursor:
            cursor.execute("SELECT current_database(), to_regclass('subscription_accounts'), "
                           "to_regclass('subscription_daily_practices'), "
                           "to_regclass('subscription_orders'),to_regclass('subscription_notifications')")
            row = cursor.fetchone()
            if row[0] != expected_name or any(table is None for table in row[1:]):
                raise ValueError("Wrong test database or subscription migration has not been applied")
            cursor.execute("SELECT is_old_user,gift_starts,gift_ends,offer_ends,special_offer_used_at "
                           "FROM subscription_accounts LIMIT 0")
            cursor.execute("SELECT base_price,final_price,special_offer_applied,offer_ends_at_order "
                           "FROM subscription_orders LIMIT 0")
            cursor.execute("SELECT superseded_at FROM subscription_orders LIMIT 0")
            if self.payment_scope is not None:
                # Fail at startup, not after the buyer returns from checkout.
                cursor.execute('SELECT payment_scope FROM subscription_orders LIMIT 0')

    def save_order(self, order):
        """Persist before calling the provider; caller retains this ID on retries."""
        with self._transaction() as cursor:
            cursor.execute("SELECT user_id FROM subscription_accounts WHERE user_id=%s FOR UPDATE",
                           (order.user_id,))
            if cursor.fetchone() is None:
                raise ValueError('User is not enrolled in subscription testing')
            scope_column = ',payment_scope' if self.payment_scope is not None else ''
            scope_value = ',%s' if self.payment_scope is not None else ''
            cursor.execute("INSERT INTO subscription_orders "
                           "(order_id,user_id,tariff_code,duration_days,base_price,final_price,"
                           "special_offer_applied,offer_ends_at_order,email,created_at,updated_at"
                           + scope_column + ") VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s"
                           + scope_value + ")",
                           (order.order_id, order.user_id, order.tariff_code, order.duration_days,
                            order.base_price, order.final_price, order.special_offer_applied,
                            order.offer_ends_at_order,
                            order.email, order.created_at, order.created_at) +
                           ((self.payment_scope,) if self.payment_scope is not None else ()))

    @contextmanager
    def payment_creation_lock(self, user_id):
        # Covers provider timeouts/retries too; network calls have a bounded timeout.
        with self._transaction() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                           ('subscription_checkout:{}'.format(user_id),))
            yield

    def open_order_id(self, user_id):
        scope, params = self._payment_scope_sql()
        with self._transaction() as cursor:
            cursor.execute("SELECT order_id FROM subscription_orders WHERE user_id=%s "
                           "AND status IN ('created','pending') AND superseded_at IS NULL" + scope +
                           " ORDER BY created_at DESC LIMIT 1", (user_id,) + params)
            row = cursor.fetchone()
            return str(row[0]) if row else None

    def supersede_order(self, order_id, user_id, now):
        """Stop resuming an abandoned checkout without discarding its payment."""
        scope, params = self._payment_scope_sql()
        with self._transaction() as cursor:
            cursor.execute("UPDATE subscription_orders SET superseded_at=%s,updated_at=%s "
                           "WHERE order_id=%s AND user_id=%s AND status IN ('created','pending') "
                           "AND superseded_at IS NULL" + scope,
                           (now, now, order_id, user_id) + params)
            if cursor.rowcount != 1:
                raise ValueError('Open order changed before replacement')

    def checkout_profile(self, user_id):
        with self._transaction() as cursor:
            cursor.execute("SELECT email,trial_ends_at,subscription_ends,gift_starts,gift_ends,"
                           "offer_ends,special_offer_used_at FROM subscription_accounts "
                           "WHERE user_id=%s", (user_id,))
            row = cursor.fetchone()
            if not row:
                return None
            offer = offer_from_values(row[3], row[4], row[5], row[6])
            return CheckoutProfile(row[0], row[1], row[2], offer)

    def checkout_price(self, user_id, tariff_code, now):
        profile = self.checkout_profile(user_id)
        if profile is None:
            raise ValueError('Subscription account not found')
        price = old_user_checkout_price(tariff_code, profile.old_user_offer, now)
        offer_end = (profile.old_user_offer.offer_ends
                     if price.special_offer_applied else None)
        return price, offer_end

    def signal_payment(self, user_id):
        """Best-effort wakeup only; durable work remains in payment tables."""
        with self._transaction() as cursor:
            cursor.execute("SELECT pg_notify('subscription_payment_ready', %s)", (str(user_id),))

    def payment_work(self, user_id, limit=20):
        """Durable work survives a closed Mini App and bot restarts."""
        scope, params = self._payment_scope_sql()
        notice_scope, _ = self._payment_scope_sql('o.')
        with self._transaction() as cursor:
            cursor.execute("SELECT order_id FROM subscription_orders WHERE user_id=%s "
                           "AND status IN ('created','pending')" + scope +
                           " ORDER BY updated_at,created_at LIMIT %s",
                           (user_id,) + params + (limit,))
            pending = [str(row[0]) for row in cursor.fetchall()]
            cursor.execute("SELECT o.order_id FROM subscription_orders o WHERE o.user_id=%s "
                           "AND o.status='succeeded' AND o.granted_at IS NOT NULL AND NOT EXISTS "
                           "(SELECT 1 FROM subscription_notifications n WHERE n.user_id=o.user_id "
                           "AND n.event_key='payment_success:' || o.order_id::text) "
                           + notice_scope + " ORDER BY o.granted_at LIMIT %s",
                           (user_id,) + params + (limit,))
            return pending, [str(row[0]) for row in cursor.fetchall()]

    def payment_notice(self, order_id, user_id):
        with self._transaction() as cursor:
            cursor.execute("SELECT u.chat_id,COALESCE(u.user_name,''),a.subscription_ends "
                           "FROM subscription_orders o JOIN subscription_accounts a ON a.user_id=o.user_id "
                           "JOIN users u ON u.user_id=o.user_id WHERE o.order_id=%s AND o.user_id=%s "
                           "AND o.status='succeeded' AND o.granted_at IS NOT NULL", (order_id, user_id))
            return cursor.fetchone()

    def onboarding_payment_results(self, user_id, since):
        """Only terminal orders created during this subscription step."""
        scope, params = self._payment_scope_sql()
        with self._transaction() as cursor:
            cursor.execute("SELECT order_id,status FROM subscription_orders WHERE user_id=%s "
                           "AND created_at >= %s AND (status='canceled' OR "
                           "(status='succeeded' AND granted_at IS NOT NULL))" + scope +
                           " ORDER BY created_at", (user_id, since) + params)
            return [(str(row[0]), row[1]) for row in cursor.fetchall()]

    @contextmanager
    def notification_lock(self, user_id, event_key):
        """Non-blocking cross-process exclusion; release also on delivery failure."""
        with self._transaction() as cursor:
            cursor.execute("SELECT pg_try_advisory_xact_lock(hashtextextended(%s,0))",
                           ('subscription_notice:{}:{}'.format(user_id, event_key),))
            yield bool(cursor.fetchone()[0])

    def touch_order_check(self, order_id, user_id, now):
        with self._transaction() as cursor:
            cursor.execute("UPDATE subscription_orders SET updated_at=%s WHERE order_id=%s AND user_id=%s "
                           "AND status IN ('created','pending')", (now, order_id, user_id))

    def get_order(self, order_id, user_id):
        from app.payments.service import Order
        scope, params = self._payment_scope_sql()
        with self._transaction() as cursor:
            cursor.execute("SELECT order_id,user_id,tariff_code,duration_days,base_price,final_price,"
                           "special_offer_applied,offer_ends_at_order,email,created_at,provider_payment_id "
                           "FROM subscription_orders "
                           "WHERE order_id=%s AND user_id=%s" + scope,
                           (order_id, user_id) + params)
            row = cursor.fetchone()
            return Order(str(row[0]), *row[1:]) if row else None

    def webhook_order(self, payment_id, order_hint=None):
        """Untrusted IDs only select a scoped order; they never grant access."""
        from app.payments.service import Order
        scope, params = self._payment_scope_sql()
        with self._transaction() as cursor:
            cursor.execute("SELECT order_id,user_id,tariff_code,duration_days,base_price,final_price,"
                           "special_offer_applied,offer_ends_at_order,email,created_at,provider_payment_id "
                           "FROM subscription_orders "
                           "WHERE (provider_payment_id=%s OR "
                           "(order_id=%s AND provider_payment_id IS NULL))" + scope,
                           (payment_id, order_hint) + params)
            row = cursor.fetchone()
            return Order(str(row[0]), *row[1:]) if row else None

    def attach_payment(self, order, payment_id, now):
        with self._transaction() as cursor:
            cursor.execute("UPDATE subscription_orders SET provider_payment_id=%s, status='pending', "
                           "updated_at=%s WHERE order_id=%s AND user_id=%s AND status IN ('created','pending') "
                           "AND (provider_payment_id IS NULL OR provider_payment_id=%s)",
                           (payment_id, now, order.order_id, order.user_id, payment_id))
            if cursor.rowcount != 1:
                raise ValueError('Cannot attach payment to order')

    def grant_order(self, order, now):
        """Atomic and idempotent access grant after server-side verification."""
        with self._transaction() as cursor:
            # All grants for a user serialize before locking the individual order.
            cursor.execute("SELECT trial_started_at,trial_ends_at,subscription_starts,subscription_ends,"
                           "gift_starts,gift_ends,special_offer_used_at "
                           "FROM subscription_accounts WHERE user_id=%s FOR UPDATE", (order.user_id,))
            row = cursor.fetchone()
            if row is None:
                raise ValueError('Subscription account not found')
            snapshot = _snapshot(row[:6])
            cursor.execute("SELECT granted_at,status,duration_days,provider_payment_id,final_price,"
                           "special_offer_applied "
                           "FROM subscription_orders WHERE order_id=%s AND user_id=%s FOR UPDATE",
                           (order.order_id, order.user_id))
            saved = cursor.fetchone()
            if saved is None or saved[3] != order.provider_payment_id or saved[4] != order.final_price:
                raise ValueError('Order changed during payment verification')
            if saved[0] is not None:
                return False
            if saved[1] not in ('created', 'pending'):
                raise ValueError('Order is already terminal')
            start = max(local_time(value) for value in
                        (now, row[1], row[3], row[5]) if value is not None)
            end = midnight(start.date() + timedelta(days=saved[2]))
            # Renewals extend the existing contiguous period, not its start.
            account_start = row[2] if row[3] and local_time(row[3]) >= local_time(now) else start
            state = Subscription(snapshot.trial, PaidPeriod(account_start, end), snapshot.gift).state(now)
            cursor.execute("UPDATE subscription_accounts SET subscription_starts=%s,subscription_ends=%s,"
                           "email=%s,subscription_state=%s,updated_at=%s,"
                           "special_offer_used_at=CASE WHEN %s THEN COALESCE(special_offer_used_at,%s) "
                           "ELSE special_offer_used_at END,"
                           "schedule_restore_required=schedule_restore_required OR %s WHERE user_id=%s",
                           (account_start, end, order.email, state.value, now,
                            saved[5], now, snapshot.state(now) == AccessState.FREE, order.user_id))
            cursor.execute("UPDATE subscription_orders SET status='succeeded',granted_at=%s,"
                           "period_starts_at=%s,period_ends_at=%s,updated_at=%s WHERE order_id=%s",
                           (now, start, end, now, order.order_id))
            return True

    def cancel_order(self, order, now):
        with self._transaction() as cursor:
            cursor.execute("UPDATE subscription_orders SET status='canceled',updated_at=%s "
                           "WHERE order_id=%s AND user_id=%s AND provider_payment_id=%s "
                           "AND status IN ('created','pending') AND granted_at IS NULL",
                           (now, order.order_id, order.user_id, order.provider_payment_id))

    def synchronize_access(self, user_id, now):
        """Persist expiry and stop ordinary Daily delivery without losing settings."""
        with self._transaction() as cursor:
            cursor.execute("SELECT trial_started_at,trial_ends_at,subscription_starts,subscription_ends,"
                           "gift_starts,gift_ends "
                           "FROM subscription_accounts WHERE user_id = %s FOR UPDATE", (user_id,))
            row = cursor.fetchone()
            if row is None:
                return None
            snapshot = _snapshot(row)
            state = snapshot.state(now)
            cursor.execute("UPDATE subscription_accounts SET subscription_state=%s, updated_at=%s "
                           "WHERE user_id=%s AND subscription_state IS DISTINCT FROM %s",
                           (state.value, now, user_id, state.value))
            if state == AccessState.FREE:
                cursor.execute("UPDATE subscription_accounts SET schedule_restore_required=TRUE "
                               "WHERE user_id=%s", (user_id,))
                cursor.execute("UPDATE users SET daily_schedule_enabled=FALSE "
                               "WHERE user_id=%s AND bot_mode IS DISTINCT FROM 'challenge' "
                               "AND daily_schedule_enabled=TRUE", (user_id,))
            return snapshot

    def daily_practice(self, user_id, now, choose_practice, load_practice):
        """Serialize first choice across processes; preserve it on delivery failure.

        Callbacks perform catalog selection/loading only, no Telegram calls.
        Missing catalog entries return None rather than silently switching videos.
        """
        from app.subscription.tariff import local_time
        day = local_time(now).date()
        with self._transaction() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                           ("subscription_day:{}:{}".format(user_id, day.isoformat()),))
            cursor.execute("SELECT practice_id, practice_catalog FROM subscription_daily_practices "
                           "WHERE user_id = %s AND moscow_date = %s", (user_id, day))
            saved = cursor.fetchone()
            if saved is not None:
                return load_practice(saved[0], saved[1])
            selected = choose_practice()
            if selected is None:
                return None
            row, catalog = selected
            cursor.execute("INSERT INTO subscription_daily_practices "
                           "(user_id, moscow_date, practice_catalog, practice_id) VALUES (%s, %s, %s, %s)",
                           (user_id, day, catalog, row[0]))
            return row

    def begin_trial(self, user_id: int, now: datetime) -> Subscription:
        """Atomic first-start: concurrent/repeated requests retain original dates."""
        trial = start_trial(now)
        with self._transaction() as cursor:
            cursor.execute(
                "INSERT INTO subscription_accounts (user_id) VALUES (%s) "
                "ON CONFLICT (user_id) DO NOTHING", (user_id,),
            )
            cursor.execute(
                "SELECT trial_started_at,trial_ends_at,subscription_starts,subscription_ends,"
                "gift_starts,gift_ends "
                "FROM subscription_accounts WHERE user_id = %s FOR UPDATE", (user_id,),
            )
            state = _snapshot(cursor.fetchone())
            # A paid account must not get a trial through an old onboarding button.
            if state.trial is None and state.paid is None and state.gift is None:
                cursor.execute(
                    "UPDATE subscription_accounts SET trial_started_at = %s, trial_ends_at = %s, "
                    "updated_at = %s, subscription_state = 'trial' WHERE user_id = %s",
                    (trial.started_at, trial.ends_at, now, user_id),
                )
                state = Subscription(trial=trial, gift=state.gift)
        return state

    def begin_fast_trial(self, user_id: int, now: datetime, *, replay=False) -> Subscription:
        """Start an idempotent test trial; explicit replay is for the test command."""
        start = local_time(now)
        trial = Trial(start, start + FAST_TRIAL_DURATION)
        with self._transaction() as cursor:
            cursor.execute(
                "INSERT INTO subscription_accounts (user_id) VALUES (%s) "
                "ON CONFLICT (user_id) DO NOTHING", (user_id,),
            )
            cursor.execute(
                "SELECT trial_started_at,trial_ends_at,subscription_starts,subscription_ends,"
                "gift_starts,gift_ends "
                "FROM subscription_accounts WHERE user_id = %s FOR UPDATE", (user_id,),
            )
            current = _snapshot(cursor.fetchone())
            if not replay and (current.trial is not None or current.paid is not None):
                return current
            if current.paid is not None or current.gift is not None:
                raise ValueError("A paid test account cannot replay the trial")
            cursor.execute(
                "SELECT EXISTS(SELECT 1 FROM subscription_orders WHERE user_id=%s "
                "AND status IN ('created','pending','succeeded'))", (user_id,),
            )
            if cursor.fetchone()[0]:
                raise ValueError("A test account with payment orders cannot replay the trial")
            cursor.execute(
                "UPDATE subscription_accounts SET trial_started_at=%s, trial_ends_at=%s, "
                "subscription_state='trial', updated_at=%s WHERE user_id=%s",
                (trial.started_at, trial.ends_at, start, user_id),
            )
        return Subscription(trial=trial)

    def enroll_old_users(self, launch_at: datetime) -> int:
        """Explicit one-off activation; never called by application startup."""
        with self._transaction() as cursor:
            return enroll_old_users(cursor, launch_at)

    def notification_sent(self, user_id: int, event_key: str) -> bool:
        with self._transaction() as cursor:
            cursor.execute(
                "SELECT 1 FROM subscription_notifications WHERE user_id = %s AND event_key = %s",
                (user_id, event_key),
            )
            return cursor.fetchone() is not None

    def reminder_profile(self, user_id, trial=None):
        with self._transaction() as cursor:
            cursor.execute("SELECT chat_id,COALESCE(user_name,''),bot_mode FROM users WHERE user_id=%s", (user_id,))
            user = cursor.fetchone()
            if not user:
                return None
            result = dict(chat_id=user[0], name=user[1], challenge=user[2] == 'challenge',
                          completions=0, has_favorites=False, received_schedule=False, filter_keys=[])
            if trial is None:
                return result
            # Existing activity tables use naive UTC timestamps.
            start, end = [v.astimezone(timezone.utc).replace(tzinfo=None)
                          for v in (trial.started_at, trial.ends_at)]
            cursor.execute("SELECT COUNT(*) FROM practice_logs WHERE user_id=%s "
                           "AND completed_at >= %s AND completed_at < %s", (user_id, start, end))
            result['completions'] = cursor.fetchone()[0]
            cursor.execute("SELECT EXISTS(SELECT 1 FROM user_favorites WHERE user_id=%s "
                           "AND added_at >= %s AND added_at < %s)", (user_id, start, end))
            result['has_favorites'] = cursor.fetchone()[0]
            cursor.execute("SELECT EXISTS(SELECT 1 FROM practice_logs WHERE user_id=%s "
                           "AND day_number >= 1 AND sent_at >= %s AND sent_at < %s)", (user_id, start, end))
            result['received_schedule'] = cursor.fetchone()[0]
            cursor.execute("SELECT filter_key FROM quick_filter_events WHERE user_id=%s "
                           "AND clicked_at >= %s AND clicked_at < %s AND result_found IS TRUE "
                           "AND filter_key <> 'day' GROUP BY filter_key ORDER BY COUNT(*) DESC,filter_key LIMIT 2",
                           (user_id, start, end))
            result['filter_keys'] = [row[0] for row in cursor.fetchall()]
            return result

    def restore_offer(self, user_id, now):
        with self._transaction() as cursor:
            cursor.execute("SELECT u.chat_id,u.notify_time,a.subscription_starts FROM subscription_accounts a "
                           "JOIN users u ON u.user_id=a.user_id WHERE a.user_id=%s "
                           "AND a.schedule_restore_required=TRUE AND a.subscription_starts<=%s AND a.subscription_ends>%s "
                           "AND u.bot_mode IS DISTINCT FROM 'challenge' AND EXISTS "
                           "(SELECT 1 FROM subscription_orders o JOIN subscription_notifications n "
                           "ON n.user_id=o.user_id AND n.event_key='payment_success:' || o.order_id::text "
                           "WHERE o.user_id=a.user_id AND o.period_starts_at>=a.subscription_starts)",
                           (user_id, now, now))
            return cursor.fetchone()

    def dismiss_restore_offer(self, user_id):
        """The post-challenge flow owns the schedule choice for this user."""
        with self._transaction() as cursor:
            cursor.execute("UPDATE subscription_accounts SET schedule_restore_required=FALSE "
                           "WHERE user_id=%s", (user_id,))

    def resolve_restore(self, user_id, period_token, now, accept):
        """Consume consent once; an old button cannot affect a later subscription."""
        with self._transaction() as cursor:
            cursor.execute("SELECT subscription_starts,subscription_ends,schedule_restore_required "
                           "FROM subscription_accounts WHERE user_id=%s FOR UPDATE", (user_id,))
            row = cursor.fetchone()
            if (not row or not row[0] or not row[2] or str(int(row[0].timestamp())) != period_token
                    or not row[0] <= now < row[1]):
                return 'stale'
            cursor.execute("SELECT notify_time,bot_mode FROM users WHERE user_id=%s FOR UPDATE", (user_id,))
            user = cursor.fetchone()
            if not user or user[1] == 'challenge':
                return 'stale'
            if accept and user[0] not in (None, '', '00:00'):
                cursor.execute("UPDATE users SET daily_schedule_enabled=TRUE,is_paused=FALSE,paused_at=NULL,"
                               "first_daily_send_date=%s,bot_mode='daily' WHERE user_id=%s",
                               (local_time(now).date() + timedelta(days=1), user_id))
                result = 'restored'
            else:
                result = 'setup' if accept else 'declined'
            cursor.execute("UPDATE subscription_accounts SET schedule_restore_required=FALSE WHERE user_id=%s",
                           (user_id,))
            return result

    def mark_notification_sent(self, user_id: int, event_key: str, sent_at: datetime) -> None:
        """Delivery worker must serialize sends; this records completed deliveries."""
        with self._transaction() as cursor:
            cursor.execute(
                "INSERT INTO subscription_notifications (user_id, event_key, sent_at) "
                "VALUES (%s, %s, %s) ON CONFLICT (user_id, event_key) DO NOTHING",
                (user_id, event_key, sent_at),
            )
