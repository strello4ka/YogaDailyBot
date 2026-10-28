"""Temporary old-users transition rules, isolated from regular subscriptions."""

import unittest
import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from app.subscription.access import AccessState, Subscription
from app.subscription.old_users.messages import (
    first_message,
    first_message_keyboard,
    gift_expired,
    gift_last_day,
    gift_subscription_activated,
    special_prices_last_day,
    special_prices_seven_days,
    special_prices_three_days,
    gift_three_days,
    tariff_button_keyboard,
)
from app.subscription.old_users.handlers import access_details_callback
from app.subscription.old_users.notifications import notification_schedule
from app.subscription.old_users.prices import SPECIAL_PRICES, checkout_price
from app.subscription.old_users.repository import enroll
from app.subscription.old_users.rules import launch_offer
from app.subscription.tariff import MOSCOW


def at(day, hour=0):
    return datetime(2026, 10, day, hour, tzinfo=MOSCOW)


class OldUsersRulesTest(unittest.TestCase):
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
            'gift_three_days', 'gift_last_day', 'gift_expired',
            'special_prices_seven_days', 'special_prices_three_days',
            'special_prices_last_day'])
        self.assertEqual(schedule[0].scheduled_at,
                         offer.gift.ends_at - timedelta(days=3) + timedelta(hours=13))
        self.assertEqual(schedule[1].scheduled_at,
                         offer.gift.ends_at - timedelta(days=1) + timedelta(hours=19))
        self.assertEqual(schedule[2].scheduled_at,
                         offer.gift.ends_at + timedelta(hours=8))
        self.assertEqual(schedule[3].scheduled_at,
                         offer.offer_ends - timedelta(days=7) + timedelta(hours=19))
        self.assertEqual(schedule[4].scheduled_at,
                         offer.offer_ends - timedelta(days=3) + timedelta(hours=19))
        self.assertEqual(schedule[5].scheduled_at,
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
            "Что входит в подписку?",
            "Что останется бесплатным?",
        ])
        self.assertEqual(rows[0][0].api_kwargs, {"style": "primary"})
        self.assertEqual(rows[1][0].api_kwargs, {})
        self.assertEqual(rows[2][0].api_kwargs, {})
        self.assertEqual(rows[0][0].web_app.url, "https://example.org/subscription")

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
        self.assertEqual(button.text, "⭐ Посмотреть тарифы")
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
        self.assertIn("🌀 Практика дня\n🌀 Прогресс", text)
        self.assertIn("до <b>13.11.2026</b>", text)

        offer = launch_offer(at(1))
        self.assertEqual(Subscription(gift=offer.gift).state(offer.gift.ends_at),
                         AccessState.FREE)

    def test_gift_subscription_activation_copy(self):
        text = gift_subscription_activated('<Катя>', at(31))
        self.assertIn('Подарочный месяц завершился', text)
        self.assertIn('до <b>30.10.2026</b>', text)
        self.assertIn('&lt;Катя&gt;, рад', text)

    def test_special_prices_seven_day_copy_uses_last_offer_day(self):
        text = special_prices_seven_days(datetime(2026, 11, 14, tzinfo=MOSCOW))
        self.assertIn('специальные цены', text)
        self.assertIn('до <b>13.11.2026</b>', text)

    def test_special_prices_three_day_copy_shows_all_price_differences(self):
        text = special_prices_three_days()
        self.assertIn('Специальные цены исчезнут через 3 дня', text)
        self.assertIn('Только для олдов:', text)
        self.assertIn('<b>1 месяц:</b> 350 ₽ → <b>250 ₽</b>', text)
        self.assertIn('<b>1 год:</b> 2 500 ₽ → <b>1 800 ₽</b>', text)
        self.assertIn('Выбирай любой тариф 👇', text)

    def test_special_prices_last_day_copy_is_short_and_friendly(self):
        text = special_prices_last_day()
        self.assertIn('Сегодня последний день специальных цен', text)
        self.assertIn('такие же цены, как для всех', text)
        self.assertIn('запрыгивать в последний вагон', text)
        self.assertIn('до конца сегодняшнего дня 👇', text)


if __name__ == '__main__':
    unittest.main()
