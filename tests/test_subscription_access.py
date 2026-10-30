import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from app.subscription import messages
from app.subscription.access import Feature, Subscription, repository_for, runtime_has_access
from app.subscription.demo import Trial, start_trial
from app.subscription.old_users.rules import GiftPeriod
from app.subscription.free import locked_text, reply_keyboard, send_locked
from app.subscription.subscription_menu import (menu_text, send_menu, tariff_keyboard,
    test_settings, install_test_subscriptions, guard_update,
    subscription_test_command, subscription_test_start_callback)
from app.subscription.tariff import MOSCOW, purchased_period
from app.onboarding import messages as onboarding_messages
from app.onboarding.flow import _send_step, _subscription_variant, handle_reply


class ScheduleRestoreFlowTest(unittest.IsolatedAsyncioTestCase):
    async def test_setup_goes_directly_to_shared_time_screen(self):
        from app.subscription.subscription_menu import restore_schedule_callback
        from app.handlers.schedule import SCHEDULE_MENU_TIME_KEY
        repository = Mock()
        repository.resolve_restore.return_value = 'setup'
        query = SimpleNamespace(data='subscription_restore:yes:123', answer=AsyncMock(),
                                edit_message_reply_markup=AsyncMock())
        update = SimpleNamespace(effective_user=SimpleNamespace(id=1),
                                 effective_chat=SimpleNamespace(id=1), callback_query=query)
        context = SimpleNamespace(user_data={}, bot=SimpleNamespace(send_message=AsyncMock()),
            bot_data={'subscription_repository': repository, 'subscription_test_users': None})
        await restore_schedule_callback(update, context)
        context.bot.send_message.assert_awaited_once()
        self.assertEqual(context.bot.send_message.await_args.kwargs['text'], onboarding_messages.TIME_INPUT)
        self.assertTrue(context.user_data[SCHEDULE_MENU_TIME_KEY])
        query.answer.assert_awaited_once()


class SubscriptionScreensTest(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 13, 12, tzinfo=MOSCOW)
        self.trial = start_trial(self.now)

    def test_four_menu_states(self):
        paid = purchased_period("month", self.now, trial_ends_at=self.trial.ends_at)
        states = [
            (Subscription(), self.now, "нет активных подписок"),
            (Subscription(self.trial), self.now, "Ты можешь оформить"),
            (Subscription(self.trial, paid), self.now, "Ты уже оформил"),
            (Subscription(self.trial, paid), paid.starts_at, "Подписка активна"),
        ]
        for snapshot, now, expected in states:
            with self.subTest(expected=expected):
                text = menu_text(snapshot, now)
                self.assertIn(expected, text)
                self.assertNotIn("оферта", text)

    def test_unpaid_trial_status_describes_full_access(self):
        text = messages.trial_status(9, self.trial.ends_at)
        self.assertIn('Полный доступ ко всем возможностям YogaDailyBot', text)
        self.assertIn('<b>9 дней</b>', text)
        self.assertIn('<b>1 день</b>', messages.trial_status(1, self.trial.ends_at))
        self.assertIn('<b>2 дня</b>', messages.trial_status(2, self.trial.ends_at))

    def test_paid_trial_status_shows_future_subscription_dates(self):
        paid = purchased_period('month', self.now, trial_ends_at=self.trial.ends_at)
        text = menu_text(Subscription(self.trial, paid), self.now)
        self.assertIn('после окончания пробного периода', text)
        self.assertIn(f'<b>{paid.starts_at:%d.%m.%Y}</b> по', text)
        self.assertIn(f'<b>{messages.last_access_date(paid.ends_at):%d.%m.%Y}</b>', text)

    def test_gift_status_matches_trial_status_for_unpaid_and_paid_users(self):
        gift = GiftPeriod(self.now, self.now + timedelta(days=30))
        unpaid = menu_text(Subscription(gift=gift), self.now)
        self.assertIn('🎁 У тебя сейчас подарочный период', unpaid)
        self.assertIn('Полный доступ ко всем возможностям YogaDailyBot', unpaid)
        self.assertIn('<b>30 дней</b>', unpaid)
        self.assertIn('Ты можешь оформить подписку', unpaid)

        paid = purchased_period('month', self.now, trial_ends_at=gift.ends_at)
        purchased = menu_text(Subscription(paid=paid, gift=gift), self.now)
        self.assertIn('🎁 У тебя сейчас подарочный период', purchased)
        self.assertIn('Осталось дней 30', purchased)
        self.assertIn('Ты уже оформил подписку', purchased)
        self.assertIn('после окончания подарочного периода', purchased)
        self.assertIn('<b>12.11.2026</b>', purchased)
        self.assertIn('<b>11.12.2026</b>', purchased)
        self.assertNotIn('нет активных подписок', purchased)

    def test_fast_trial_status_uses_minutes_without_changing_normal_status(self):
        fast = Trial(self.now, self.now + timedelta(minutes=15))
        text = menu_text(Subscription(fast), self.now + timedelta(minutes=10))
        self.assertIn('5 мин', text)
        self.assertIn('тестового бота', text)
        self.assertIn('Полный доступ ко всем возможностям',
                      menu_text(Subscription(self.trial), self.now))

    def test_html_from_user_data_is_escaped(self):
        text = messages.payment_accepted('<b>A&B</b>', self.trial.ends_at)
        self.assertIn('&lt;b&gt;A&amp;B&lt;/b&gt;', text)
        text = messages.trial_subscription_activated('<b>A&B</b>', self.trial.ends_at)
        self.assertIn('&lt;b&gt;A&amp;B&lt;/b&gt;', text)
        text = messages.trial_last_day(completions=4, categories=['<a>'])
        self.assertIn('«&lt;a&gt;»', text)

    def test_personalization_threshold_and_absent_categories(self):
        self.assertNotIn('blockquote', messages.trial_last_day(completions=3))
        text = messages.trial_last_day(completions=4)
        self.assertIn('<blockquote>', text)
        self.assertNotIn('Чаще всего', text)
        self.assertNotIn('blockquote', messages.paid_last_day())

    def test_challenge_subscription_expiry_keeps_challenge_schedule(self):
        last_day = messages.challenge_access_last_day()
        self.assertIn('направления', last_day)
        self.assertNotIn('рассылка по расписанию', last_day)
        expired = messages.challenge_access_expired()
        self.assertIn('Программа челленджа', expired)
        self.assertNotIn('Рассылка по расписанию остановлена', expired)

    def test_finished_challenge_without_subscription_offers_subscription(self):
        text = messages.challenge_finished_without_subscription()
        self.assertIn('как во время челленджа', text)
        self.assertIn('доступна только по подписке', text)

    def test_free_keyboard_and_expanding_selection_quote(self):
        self.assertEqual([[b.text for b in row] for row in reply_keyboard().keyboard],
                         [["Практика дня"], ["🔒 Подобрать практику"]])
        self.assertIn('<blockquote expandable>', locked_text(Feature.SELECTION))
        with self.assertRaises(KeyError):
            locked_text(Feature.PROGRESS)

    def test_tariff_button_opens_web_app_and_not_payment(self):
        button = tariff_keyboard('https://example.org/subscription').inline_keyboard[0][0]
        self.assertEqual(button.text, 'Посмотреть тарифы')
        self.assertEqual(button.web_app.url, 'https://example.org/subscription')
        self.assertEqual(button.api_kwargs, {'style': 'primary'})
        self.assertEqual(button.to_dict()['style'], 'primary')
        self.assertFalse(button.pay)
        with self.assertRaises(ValueError):
            tariff_keyboard('http://example.org')

    def test_followup_priority(self):
        text = messages.trial_followup(has_favorites=True, received_schedule=True, used_filters=True)
        self.assertIn('избранные', text)
        text = messages.trial_followup(has_favorites=False, received_schedule=True, used_filters=True)
        self.assertIn('расписанию', text)
        text = messages.trial_followup(has_favorites=False, received_schedule=False, used_filters=True)
        self.assertNotIn('Мини', text)
        text = messages.trial_followup(has_favorites=False, received_schedule=False, used_filters=False)
        self.assertIn('Какую практику хочется', text)


class TestRolloutSafetyTest(unittest.TestCase):
    def settings(self):
        return dict(SUBSCRIPTION_TEST_ENABLED="true", ENV_FILE="test/.env.test",
                    BOT_TOKEN="123:dummy", SUBSCRIPTION_TEST_USERS="1,2",
                    SUBSCRIPTION_MINIAPP_URL="https://example.org",
                    SUBSCRIPTION_TEST_DATABASE="yogadaily_test")

    def test_disabled_does_not_require_configuration(self):
        self.assertIsNone(test_settings({}))

    def test_test_environment_and_database_must_be_explicit(self):
        env = self.settings()
        self.assertEqual(test_settings(env)[0], frozenset((1, 2)))
        self.assertIsNone(test_settings(dict(env, SUBSCRIPTION_TEST_USERS=""))[0])
        for key, value in [("ENV_FILE", ".env"), ("BOT_TOKEN", "bad-token"),
                           ("SUBSCRIPTION_TEST_DATABASE", ""),
                           ("SUBSCRIPTION_TEST_DATABASE", "production")]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                test_settings(dict(env, **{key: value}))

    def test_test_mode_without_checkout_url(self):
        env = dict(self.settings(), SUBSCRIPTION_MINIAPP_URL="")
        self.assertEqual(test_settings(env)[1], "")
        with self.assertRaises(ValueError):
            test_settings(dict(env, SUBSCRIPTION_MINIAPP_URL="http://localhost:8765"))

    def test_test_bot_uses_tariff_preview_without_checkout_url(self):
        from app.handlers.donations import MINIAPP_PREVIEW_URL
        env = dict(self.settings(), SUBSCRIPTION_MINIAPP_URL="",
                   SUBSCRIPTION_YOOKASSA_TEST_SHOP_ID="test-shop",
                   SUBSCRIPTION_YOOKASSA_TEST_SECRET_KEY="test-secret")
        application = Mock(bot_data={}, job_queue=Mock())
        with patch('data.subscription_repository.SubscriptionRepository'):
            install_test_subscriptions(application, env, Mock())
        self.assertEqual(application.bot_data['subscription_miniapp_url'], MINIAPP_PREVIEW_URL)
        self.assertEqual(tariff_keyboard(application.bot_data['subscription_miniapp_url'])
                         .inline_keyboard[0][0].text, 'Посмотреть тарифы')
        self.assertNotIn('subscription_payment_service', application.bot_data)

    def test_unlisted_users_do_not_touch_subscription_storage(self):
        repository = Mock()
        context = SimpleNamespace(bot_data=dict(subscription_repository=repository, subscription_test_users={1}))
        self.assertIsNone(repository_for(context, 2))
        self.assertTrue(runtime_has_access(context, 2, Feature.FAVORITES))
        repository.get.assert_not_called()

    def test_missing_enrollment_does_not_restrict_old_users(self):
        repository = Mock()
        repository.get.return_value = None
        context = SimpleNamespace(bot_data=dict(subscription_repository=repository, subscription_test_users={1}))
        self.assertTrue(runtime_has_access(context, 1, Feature.SELECTION))

    def test_isolated_test_bot_can_include_all_its_users(self):
        repository = Mock()
        context = SimpleNamespace(bot_data=dict(subscription_repository=repository,
                                                subscription_test_users=None))
        self.assertIs(repository_for(context, 946774551), repository)


class TestGuardTest(unittest.IsolatedAsyncioTestCase):
    async def test_start_and_restart_callbacks_reach_existing_handlers(self):
        repository = Mock()
        repository.synchronize_access.return_value = Subscription()
        bot = SimpleNamespace(send_message=AsyncMock())
        context = SimpleNamespace(bot=bot, user_data={}, bot_data=dict(
            subscription_test_users={1}, subscription_repository=repository,
            subscription_miniapp_url="https://example.org"))
        for text, callback in (("/start", None), (None, "start_restart_yes")):
            with self.subTest(text=text, callback=callback):
                update = SimpleNamespace(
                    effective_user=SimpleNamespace(id=1),
                    effective_chat=SimpleNamespace(id=1, type="private"),
                    effective_message=SimpleNamespace(text=text),
                    callback_query=(SimpleNamespace(data=callback, answer=AsyncMock())
                                    if callback else None))
                await guard_update(update, context)
                bot.send_message.assert_not_called()
                if update.callback_query:
                    update.callback_query.answer.assert_not_called()

    async def test_existing_test_user_can_start_trial_without_onboarding_reset(self):
        repository = Mock()
        repository.get.return_value = None
        now = datetime(2026, 10, 13, 12, tzinfo=MOSCOW)
        repository.begin_fast_trial.return_value = Subscription(
            Trial(now, now + timedelta(minutes=15)))
        bot = SimpleNamespace(send_message=AsyncMock())
        context = SimpleNamespace(bot=bot, bot_data=dict(
            subscription_repository=repository, subscription_test_users=None,
            subscription_miniapp_url=''))
        query = SimpleNamespace(answer=AsyncMock(), edit_message_reply_markup=AsyncMock())
        update = SimpleNamespace(effective_user=SimpleNamespace(id=1),
            effective_chat=SimpleNamespace(id=1),
            effective_message=SimpleNamespace(reply_text=AsyncMock()), callback_query=query)
        await subscription_test_command(update, context)
        repository.begin_fast_trial.assert_not_called()
        self.assertEqual(update.effective_message.reply_text.call_args.kwargs[
            'reply_markup'].inline_keyboard[0][0].text, 'Запустить тест')
        await subscription_test_start_callback(update, context)
        repository.begin_fast_trial.assert_called_once()
        self.assertEqual(bot.send_message.await_count, 2)
        self.assertIn('15 минут', bot.send_message.await_args_list[0].args[1])
        self.assertEqual(bot.send_message.await_args_list[0].kwargs['reply_markup']
                         .keyboard[-1][0].text, 'расписание')

    async def test_status_and_locked_screen_without_checkout(self):
        bot = SimpleNamespace(send_message=AsyncMock())
        await send_menu(bot, 1, Subscription(), datetime(2026, 10, 13, tzinfo=MOSCOW), "")
        status = bot.send_message.call_args.kwargs
        self.assertIsNone(status['reply_markup'])
        self.assertNotIn('Смотри тарифы ниже', status['text'])
        await send_locked(bot, 1, Feature.FAVORITES, "")
        self.assertIsNone(bot.send_message.call_args.kwargs['reply_markup'])

    async def test_old_favorite_button_is_blocked_before_legacy_handler(self):
        import sys
        from unittest.mock import patch
        from telegram.ext import ApplicationHandlerStop
        repository = Mock()
        repository.get.return_value = Subscription()
        repository.synchronize_access.return_value = Subscription()
        context = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()), user_data={},
            bot_data=dict(subscription_test_users={1}, subscription_repository=repository,
                          subscription_miniapp_url="https://example.org"))
        update = SimpleNamespace(effective_user=SimpleNamespace(id=1),
            effective_chat=SimpleNamespace(id=1, type="private"),
            effective_message=SimpleNamespace(text=None),
            callback_query=SimpleNamespace(data="fav_toggle:yoga:10", answer=AsyncMock()))
        fake_db = SimpleNamespace(get_user_schedule_settings=lambda _: {})
        with patch.dict(sys.modules, {"data.db": fake_db}):
            with self.assertRaises(ApplicationHandlerStop):
                await guard_update(update, context)
        self.assertIn("Избранное доступно по подписке", context.bot.send_message.await_args.kwargs["text"])


class ReturningOnboardingSubscriptionTest(unittest.IsolatedAsyncioTestCase):
    async def test_used_trial_shows_tariffs_and_free_continue_without_new_trial(self):
        old_trial = start_trial(datetime(2025, 1, 1, tzinfo=MOSCOW))
        repository = Mock()
        repository.get.return_value = Subscription(old_trial)
        bot = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=9)))
        context = SimpleNamespace(bot=bot, bot_data={"subscription_miniapp_url":
                                  "https://example.org", "subscription_test_users": None,
                                  "subscription_repository": repository})
        state = {"user_id": 1, "chat_id": 1, "step": "subscription"}
        with patch("app.onboarding.flow.save_state"), patch(
                "app.subscription.access.repository_for", return_value=repository):
            self.assertEqual(await _subscription_variant(context, 1), "used")
            await _send_step(context, state)
        sent, tariffs = bot.send_message.await_args_list
        self.assertEqual(sent.args[1], onboarding_messages.SUBSCRIPTION_USED)
        buttons = sent.kwargs["reply_markup"].keyboard
        self.assertEqual(buttons[0][0].text, "Продолжить бесплатно")
        self.assertIsNone(buttons[0][0].web_app)
        button = tariffs.kwargs['reply_markup'].inline_keyboard[0][0]
        self.assertEqual(button.web_app.url, "https://example.org")
        self.assertEqual(button.to_dict()["style"], "primary")
        repository.begin_fast_trial.assert_not_called()

    async def test_free_continue_skips_paid_schedule_offer(self):
        repository = Mock()
        repository.get.return_value = Subscription(
            start_trial(datetime(2025, 1, 1, tzinfo=MOSCOW)))
        context = SimpleNamespace(bot_data={"subscription_test_users": None,
                                  "subscription_repository": repository})
        state = {"user_id": 1, "chat_id": 1, "step": "subscription"}
        update = SimpleNamespace(effective_user=SimpleNamespace(id=1),
                                 effective_message=SimpleNamespace(text="Продолжить бесплатно"))
        with patch("app.onboarding.flow.load_state", return_value=state), patch(
                "app.subscription.access.repository_for", return_value=repository), patch(
                "app.onboarding.flow._finish", new_callable=AsyncMock) as finish:
            self.assertTrue(await handle_reply(update, context))
        finish.assert_awaited_once_with(context, state)

    async def test_active_subscription_skips_sales_screen(self):
        now = datetime.now(MOSCOW)
        repository = Mock()
        repository.get.return_value = Subscription(paid=purchased_period("month", now))
        context = SimpleNamespace(bot_data={"subscription_test_users": None,
                                  "subscription_repository": repository})
        with patch("app.subscription.access.repository_for", return_value=repository):
            self.assertEqual(await _subscription_variant(context, 1), "active")

    async def test_disabled_guard_does_not_interfere(self):
        update = SimpleNamespace(effective_user=SimpleNamespace(id=1),
                                 effective_chat=SimpleNamespace(id=1, type="private"))
        context = SimpleNamespace(bot_data={})
        await guard_update(update, context)
