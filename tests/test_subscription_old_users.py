"""Temporary old-users transition rules, isolated from regular subscriptions."""

import unittest
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from app.subscription.access import AccessState, Subscription
from app.subscription.old_users.messages import (
    FEEDBACK_INPUT_PROMPT,
    feedback_keyboard,
    feedback_message,
    first_message,
    first_message_keyboard,
    gift_status,
    gift_expired,
    gift_expired_tariff_prompt,
    gift_last_day,
    gift_subscription_activated,
    special_prices_last_day,
    special_prices_seven_days,
    special_prices_three_days,
    gift_three_days,
    tariff_button_keyboard,
)
from app.subscription.old_users.handlers import (
    FEEDBACK_WAIT_SECONDS,
    WAITING_FOR_FEEDBACK,
    access_details_callback,
    cancel_feedback_wait,
    feedback_callback,
    handle_feedback_input,
)
from app.subscription.old_users.notifications import notification_schedule
from app.subscription.old_users.prices import SPECIAL_PRICES, checkout_price
from app.subscription.old_users.repository import enroll
from app.subscription.old_users.rules import launch_offer, registration_cutoff
from app.subscription.old_users.activation import preview
from app.subscription.tariff import MOSCOW


def at(day, hour=0):
    return datetime(2026, 10, day, hour, tzinfo=MOSCOW)


class OldUsersRulesTest(unittest.TestCase):
    def test_exact_launch_cutoff_includes_same_day_starts_before_launch(self):
        launch = at(1, 15)
        cutoff = registration_cutoff(launch)
        self.assertEqual(cutoff, datetime(2026, 10, 1, 12))
        before = launch - timedelta(microseconds=1)
        for first_start, expected in ((before, True), (launch, False),
                                      (launch + timedelta(seconds=1), False)):
            utc_timestamp = first_start.astimezone(timezone.utc).replace(tzinfo=None)
            self.assertEqual(utc_timestamp < cutoff, expected)
        self.assertEqual(registration_cutoff(launch.astimezone(timezone.utc)), cutoff)

    def test_preview_and_activation_use_the_same_timestamp_without_onboarding_filter(self):
        launch = at(1, 15)
        cursor = Mock()
        cursor.fetchone.return_value = (4,)
        count, offer = preview(cursor, launch)
        self.assertEqual(count, 4)
        preview_sql, preview_params = cursor.execute.call_args.args
        self.assertIn('created_at < %s', preview_sql)
        self.assertNotIn('onboarding', preview_sql)
        self.assertEqual(preview_params, (datetime(2026, 10, 1, 12),))
        cursor.fetchone.return_value = None
        enroll(cursor, launch)
        sql, params = cursor.execute.call_args.args
        self.assertIn('WHERE created_at < %s', sql)
        self.assertNotIn('created_at::date', sql)
        self.assertNotIn('onboarding', sql)
        self.assertEqual(params[4], preview_params[0])
        self.assertEqual(offer.gift.starts_at, launch)

    def test_launch_cli_accepts_exact_instant_with_required_timezone(self):
        from tools.activate_old_users import parse_launch_at
        self.assertEqual(parse_launch_at('2026-10-01T15:00:00+03:00'), at(1, 15))
        self.assertEqual(parse_launch_at('2026-10-01T12:00:00Z'), at(1, 15))
        for invalid in ('2026-10-01', '2026-10-01T15:00:00', 'not-a-date'):
            with self.assertRaises(ValueError):
                parse_launch_at(invalid)

    def test_launch_builds_thirty_day_gift_and_fourteen_extra_offer_days(self):
        offer = launch_offer(at(1, 18))
        self.assertEqual(offer.gift.starts_at, at(1, 18))
        self.assertEqual(offer.gift.ends_at, at(31))
        self.assertEqual(offer.offer_ends, datetime(2026, 11, 14, tzinfo=MOSCOW))

    def test_gift_is_full_access_and_marks_future_purchase(self):
        offer = launch_offer(at(1))
        self.assertEqual(Subscription(gift=offer.gift).state(at(30)), AccessState.GIFT)
        self.assertEqual(Subscription(gift=offer.gift).state(at(31)), AccessState.FREE)

    def test_special_prices_are_fixed_and_one_time(self):
        offer = launch_offer(at(1))
        self.assertEqual(list(SPECIAL_PRICES.values()), [25000, 60000, 100000, 180000])
        price = checkout_price('year', offer, at(20))
        self.assertEqual((price.base_price, price.final_price, price.special_offer_applied),
                         (250000, 180000, True))
        used = type(offer)(offer.gift, offer.offer_ends, at(10))
        self.assertFalse(checkout_price('year', used, at(20)).special_offer_applied)

    def test_special_prices_do_not_start_before_launch(self):
        offer = launch_offer(at(2))
        self.assertFalse(offer.special_price_active(at(1)))
        self.assertTrue(offer.special_price_active(at(2)))

    def test_existing_cohort_cannot_be_expanded_with_another_launch_date(self):
        frozen = launch_offer(at(1))
        cursor = Mock()
        cursor.fetchone.return_value = (
            frozen.gift.starts_at, frozen.gift.ends_at, frozen.offer_ends)
        self.assertEqual(enroll(cursor, at(1)), 0)
        with self.assertRaisesRegex(ValueError, 'already frozen'):
            enroll(cursor, at(2))
        self.assertEqual(cursor.execute.call_count, 2)

    def test_enrollment_marks_a_future_purchase_as_gift_paid(self):
        cursor = Mock()
        cursor.fetchone.return_value = None
        cursor.rowcount = 4
        self.assertEqual(enroll(cursor, at(1)), 4)
        statement, params = cursor.execute.call_args.args
        self.assertIn("THEN 'paid'", statement)
        self.assertIn("THEN 'gift_paid'", statement)
        self.assertEqual(params[-4:], (at(1), at(1), at(1), at(1)))

    def test_notifications_have_separate_schedule(self):
        offer = launch_offer(at(1))
        schedule = notification_schedule(offer)
        self.assertEqual([item.kind for item in schedule], [
            'launch', 'launch_feedback',
            'gift_three_days', 'gift_last_day', 'gift_expired',
            'special_prices_seven_days', 'special_prices_three_days',
            'special_prices_last_day'])
        self.assertEqual(schedule[0].scheduled_at, offer.gift.starts_at)
        self.assertEqual(schedule[1].scheduled_at,
                         offer.gift.starts_at + timedelta(hours=2))
        self.assertEqual(schedule[2].scheduled_at,
                         offer.gift.ends_at - timedelta(days=3) + timedelta(hours=13))
        self.assertEqual(schedule[3].scheduled_at,
                         offer.gift.ends_at - timedelta(days=1) + timedelta(hours=19))
        self.assertEqual(schedule[4].scheduled_at,
                         offer.gift.ends_at + timedelta(hours=8))
        self.assertEqual(schedule[5].scheduled_at,
                         offer.offer_ends - timedelta(days=7) + timedelta(hours=19))
        self.assertEqual(schedule[6].scheduled_at,
                         offer.offer_ends - timedelta(days=3) + timedelta(hours=19))
        self.assertEqual(schedule[7].scheduled_at,
                         offer.offer_ends - timedelta(days=1) + timedelta(hours=19))

    def test_first_message_uses_regular_quote_and_approved_buttons(self):
        text = first_message(at(31))
        self.assertIn("ты — легенда", text)
        self.assertIn("До <b>30.10.2026</b>", text)
        self.assertIn("<blockquote>", text)
        self.assertNotIn("<blockquote expandable>", text)
        self.assertIn(
            "Конечно, я подготовил <b>подарки для своих:</b>\n<blockquote>• До",
            text,
        )

        keyboard = first_message_keyboard("https://example.org/subscription")
        rows = keyboard.inline_keyboard
        self.assertEqual([row[0].text for row in rows], [
            "Посмотреть тарифы",
            "Что останется бесплатным?",
            "Что входит в подписку?",
        ])
        self.assertEqual(rows[0][0].api_kwargs, {"style": "primary"})
        self.assertEqual(rows[1][0].api_kwargs, {})
        self.assertEqual(rows[2][0].api_kwargs, {})
        self.assertEqual(rows[0][0].web_app.url, "https://example.org/subscription")

        self.assertIn("особенно важно узнать твоё мнение", feedback_message())
        feedback_button = feedback_keyboard().inline_keyboard[0][0]
        self.assertEqual(feedback_button.text, "Поделиться мнением")
        self.assertEqual(feedback_button.callback_data, "old_users:feedback")
        self.assertEqual(feedback_button.api_kwargs, {"style": "primary"})

    def test_feedback_button_collects_one_text_message_in_the_bot(self):
        message = SimpleNamespace(reply_text=AsyncMock())
        query = SimpleNamespace(message=message, answer=AsyncMock())
        context = SimpleNamespace(user_data={"waiting_for_time": True})
        callback_update = SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=42),
        )
        with patch("app.subscription.old_users.handlers._begin_feedback_wait") as begin:
            asyncio.run(feedback_callback(callback_update, context))
        begin.assert_called_once_with(42)
        self.assertTrue(context.user_data[WAITING_FOR_FEEDBACK])
        self.assertNotIn("waiting_for_time", context.user_data)
        message.reply_text.assert_awaited_once_with(FEEDBACK_INPUT_PROMPT)

        reply = SimpleNamespace(text="Мне всё нравится, но не хватает поиска.",
                                reply_text=AsyncMock())
        update = SimpleNamespace(
            effective_chat=SimpleNamespace(type="private"),
            effective_message=reply,
            effective_user=SimpleNamespace(id=42, username="katya"),
        )
        with (patch("app.subscription.old_users.handlers._load_feedback_wait",
                    return_value={"entered_at": 1_000}),
              patch("app.subscription.old_users.handlers._clear_feedback_wait") as clear,
              patch("app.subscription.old_users.handlers.time.time", return_value=1_001),
              patch("app.subscription.old_users.handlers._save_feedback") as save):
            asyncio.run(handle_feedback_input(update, context))
        save.assert_called_once_with(42, "katya", "Мне всё нравится, но не хватает поиска.")
        clear.assert_called_once_with(42)
        self.assertNotIn(WAITING_FOR_FEEDBACK, context.user_data)
        self.assertIn("Спасибо за твою обратную связь", reply.reply_text.call_args.args[0])

    def test_feedback_wait_expires_after_24_hours_and_can_be_canceled(self):
        context = SimpleNamespace(user_data={WAITING_FOR_FEEDBACK: True})
        update = SimpleNamespace(
            effective_chat=SimpleNamespace(type="private"),
            effective_message=SimpleNamespace(text="Обычное сообщение", reply_text=AsyncMock()),
            effective_user=SimpleNamespace(id=42, username="katya"),
        )
        with (patch("app.subscription.old_users.handlers._load_feedback_wait",
                    return_value={"entered_at": 1_000}),
              patch("app.subscription.old_users.handlers._clear_feedback_wait") as clear,
              patch("app.subscription.old_users.handlers.time.time",
                    return_value=1_000 + FEEDBACK_WAIT_SECONDS)):
            handled = asyncio.run(handle_feedback_input(update, context))
        self.assertFalse(handled)
        clear.assert_called_once_with(42)
        self.assertNotIn(WAITING_FOR_FEEDBACK, context.user_data)

        callback = SimpleNamespace(data="help_faq")
        cancel_update = SimpleNamespace(
            effective_user=SimpleNamespace(id=42), callback_query=callback)
        context.user_data[WAITING_FOR_FEEDBACK] = True
        with patch("app.subscription.old_users.handlers._clear_feedback_wait") as clear:
            asyncio.run(cancel_feedback_wait(cancel_update, context))
        clear.assert_called_once_with(42)
        self.assertNotIn(WAITING_FOR_FEEDBACK, context.user_data)

    def test_first_message_detail_button_reuses_faq_copy(self):
        from app.handlers.help import SUBSCRIPTION_FAQ_TEXT

        message = SimpleNamespace(reply_text=AsyncMock())
        query = SimpleNamespace(
            data="old_users:subscription_details",
            message=message,
            answer=AsyncMock(),
        )
        asyncio.run(access_details_callback(
            SimpleNamespace(callback_query=query),
            SimpleNamespace(),
        ))

        query.answer.assert_awaited_once()
        message.reply_text.assert_awaited_once_with(SUBSCRIPTION_FAQ_TEXT)

    def test_gift_status_copy_is_isolated_with_old_user_messages(self):
        paid = gift_status(30, at(31), purchased=True,
                           ends_at=datetime(2026, 11, 30, tzinfo=MOSCOW))
        self.assertIn("Осталось <b>30</b> дней", paid)
        self.assertIn("после окончания подарочного периода", paid)
        self.assertIn("<b>31.10.2026</b> по <b>29.11.2026</b>", paid)

    def test_gift_three_days_uses_access_and_offer_last_days(self):
        text = gift_three_days(
            "<Катя>",
            at(31),
            datetime(2026, 11, 14, tzinfo=MOSCOW),
        )
        self.assertIn("&lt;Катя&gt;", text)
        self.assertIn("до <b>30.10.2026</b>", text)
        self.assertIn("до 13.11.2026", text)
        self.assertIn("начнётся она через 3 дня", text)

        keyboard = tariff_button_keyboard("https://example.org/subscription")
        button = keyboard.inline_keyboard[0][0]
        self.assertEqual(button.text, "Посмотреть тарифы")
        self.assertEqual(button.web_app.url, "https://example.org/subscription")

    def test_gift_last_day_lists_lost_and_free_features(self):
        text = gift_last_day()
        self.assertIn("Сегодня последний день подарочного периода", text)
        self.assertIn("автоматическая рассылка по расписанию", text)
        self.assertIn("Бесплатно останутся: «Практика дня» и твой прогресс.", text)

    def test_gift_expired_switches_copy_to_free_mode_and_keeps_offer(self):
        offer_end = datetime(2026, 11, 14, tzinfo=MOSCOW)
        text = gift_expired(offer_end)
        self.assertIn("Подарочный месяц завершился", text)
        self.assertIn("Теперь ты в бесплатной версии YogaDailyBot", text)
        self.assertNotIn("Только для своих", text)
        prompt = gift_expired_tariff_prompt(offer_end)
        self.assertIn("<b>Только для своих</b>", prompt)
        self.assertIn("до <b>13.11.2026</b>", prompt)

        offer = launch_offer(at(1))
        self.assertEqual(Subscription(gift=offer.gift).state(offer.gift.ends_at),
                         AccessState.FREE)

    def test_gift_subscription_activation_copy(self):
        text = gift_subscription_activated('<Катя>', at(31))
        self.assertIn('Подарочный месяц завершился', text)
        self.assertIn('до <b>30.10.2026</b>', text)
        self.assertNotIn('&lt;Катя&gt;', text)

    def test_special_prices_seven_day_copy_uses_last_offer_day(self):
        text = special_prices_seven_days(datetime(2026, 11, 14, tzinfo=MOSCOW))
        self.assertIn('специальные цены', text)
        self.assertIn('до <b>13.11.2026</b>', text)

    def test_special_prices_three_day_copy_shows_all_price_differences(self):
        text = special_prices_three_days()
        self.assertIn('Специальные цены исчезнут через 3 дня', text)
        self.assertIn('Только для олдов:', text)
        self.assertIn('1 месяц: 350 ₽ → 250 ₽', text)
        self.assertIn('1 год: 2 500 ₽ → 1 800 ₽', text)
        self.assertIn('Выбирай любой тариф 👇', text)

    def test_special_prices_last_day_copy_is_short_and_friendly(self):
        text = special_prices_last_day()
        self.assertIn('Сегодня последний день специальных цен', text)
        self.assertIn('такие же цены, как для всех', text)
        self.assertIn('запрыгивать в последний вагон', text)
        self.assertIn('то момент настал!', text)


class OldUserOnboardingGuardTest(unittest.IsolatedAsyncioTestCase):
    async def test_announcement_buttons_work_during_old_user_onboarding(self):
        from app.onboarding.flow import guard_callback
        old = Subscription(gift=launch_offer(at(1)).gift)
        for step in ('welcome', 'agreement', 'subscription', 'time_input'):
            for data in ('old_users:subscription_details', 'old_users:free_details',
                         'old_users:feedback'):
                with self.subTest(step=step, data=data):
                    state = dict(user_id=42, step=step)
                    query = SimpleNamespace(data=data, answer=AsyncMock())
                    update = SimpleNamespace(effective_user=SimpleNamespace(id=42), callback_query=query)
                    with patch('app.onboarding.flow.load_state', return_value=state), patch(
                            'app.subscription.access.current_subscription', return_value=old), patch(
                            'app.onboarding.flow.save_state') as save:
                        await guard_callback(update, SimpleNamespace())
                    query.answer.assert_not_awaited()
                    save.assert_not_called()
                    self.assertEqual(state['step'], step)

    async def test_unrelated_callbacks_and_non_old_users_remain_guarded(self):
        from app.onboarding.flow import guard_callback
        from telegram.ext import ApplicationHandlerStop
        for subscription, data in ((Subscription(), 'old_users:feedback'),
                                   (None, 'old_users:subscription_details'),
                                   (Subscription(gift=launch_offer(at(1)).gift), 'schedule_pick_time')):
            with self.subTest(subscription=subscription, data=data):
                query = SimpleNamespace(data=data, answer=AsyncMock())
                update = SimpleNamespace(effective_user=SimpleNamespace(id=42), callback_query=query)
                with patch('app.onboarding.flow.load_state', return_value={'step': 'welcome'}), patch(
                        'app.subscription.access.current_subscription', return_value=subscription):
                    with self.assertRaises(ApplicationHandlerStop):
                        await guard_callback(update, SimpleNamespace())
                query.answer.assert_awaited_once()


if __name__ == '__main__':
    unittest.main()
