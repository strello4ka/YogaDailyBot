import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app import onboarding_messages as messages
from app.keyboards import (
    get_common_reply_keyboard,
    get_practice_completed_keyboard,
    onboarding_reply_keyboard,
)
from app.challenge.flow.start_flow import build_challenge_welcome_text, handle_challenge_time_input
from app.challenge.flow.exit_flow import build_challenge_finished_text
from app.handlers.progress import _progress_blocks
from app.handlers.help import _faq_blocks, _root_blocks, _suggest_blocks, _tips_blocks, help_section_callback
from app.challenge.flow.post_challenge import keyboard as post_challenge_keyboard, offer_text
from app.onboarding_flow import _finish, _send_step, agreement_callback, handle_reply
from app.handlers.reply_handlers import get_practice_command
from app.handlers.keyboard_refresh import refresh_old_user_keyboard
from app.onboarding_state import save_state as save_onboarding_state
from app.handlers.schedule import (
    FIRST_SETUP_TEXT,
    SCHEDULE_MENU_TIME_KEY,
    handle_schedule_menu_time_input,
    schedule_command,
    schedule_pick_time_callback,
)


class NewScenarioCopyTest(unittest.TestCase):
    @patch("app.onboarding_flow._send_step", new_callable=AsyncMock)
    @patch("app.onboarding_flow.save_state")
    def test_final_onboarding_messages_are_five_seconds_apart(self, _save, _send):
        job_queue = SimpleNamespace(run_once=unittest.mock.Mock())
        context = SimpleNamespace(job_queue=job_queue)
        state = {"user_id": 1}

        __import__("asyncio").run(_finish(context, state))

        delay = job_queue.run_once.call_args.args[1]
        self.assertEqual(delay.total_seconds(), 5)

    def test_onboarding_time_note_follows_example_without_blank_line(self):
        self.assertIn("(например, 9.30)\nPS. Время учитывается по МСК", messages.TIME_INPUT)
        self.assertNotIn("(например, 9.30)\n\nPS. Время учитывается по МСК", messages.TIME_INPUT)

    @patch("data.db.mark_reply_keyboard_version")
    @patch("app.challenge.flow.start_flow._should_send_challenge_practice_immediately", return_value=False)
    @patch("app.challenge.flow.start_flow.complete_user_challenge_setup", return_value=True)
    @patch("app.onboarding.cancel_reminders", new_callable=AsyncMock)
    def test_challenge_time_input_sends_confirmation(
        self, _cancel, _complete, _send_now, _mark_keyboard
    ):
        message = SimpleNamespace(text="7.00", reply_text=AsyncMock())
        update = SimpleNamespace(
            message=message,
            effective_user=SimpleNamespace(id=1, first_name="Катя", username="katya"),
            effective_chat=SimpleNamespace(id=10),
        )
        context = SimpleNamespace(
            user_data={
                "waiting_for_time": True,
                "waiting_for_challenge_time": True,
                "pending_challenge_practice_id": 7,
            }
        )

        __import__("asyncio").run(handle_challenge_time_input(update, context))

        message.reply_text.assert_awaited_once()
        confirmation = message.reply_text.await_args.args[0]
        self.assertIn("Готово ✅", confirmation)
        self.assertIn("07:00", confirmation)
        self.assertIn("<blockquote>", confirmation)
        self.assertNotIn("waiting_for_time", context.user_data)

    @patch("app.onboarding_state.get_connection")
    def test_onboarding_completion_without_schedule_clears_stale_time(self, get_connection):
        from unittest.mock import MagicMock

        cursor = MagicMock()
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor
        get_connection.return_value = connection

        save_onboarding_state({"user_id": 1, "step": "complete"}, complete=True)

        completion_sql = cursor.execute.call_args_list[0].args[0]
        self.assertIn("notify_time=CASE WHEN bot_mode='pending' THEN '00:00'", completion_sql)
        self.assertIn("daily_schedule_enabled=CASE WHEN bot_mode='pending' THEN FALSE", completion_sql)

    @patch("app.handlers.keyboard_refresh.mark_reply_keyboard_version")
    @patch("app.handlers.keyboard_refresh.needs_reply_keyboard_refresh", return_value=True)
    def test_old_user_gets_current_keyboard_once_on_activity(self, _needs, mark):
        bot = SimpleNamespace(send_message=AsyncMock())
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=1),
            effective_chat=SimpleNamespace(id=10),
            effective_message=None,
            callback_query=None,
        )

        __import__("asyncio").run(refresh_old_user_keyboard(update, SimpleNamespace(bot=bot)))

        bot.send_message.assert_awaited_once()
        self.assertEqual(
            bot.send_message.await_args.kwargs["reply_markup"].keyboard[-1][0].text,
            "расписание",
        )
        mark.assert_called_once()

    @patch("app.handlers.keyboard_refresh.needs_reply_keyboard_refresh")
    def test_start_does_not_send_keyboard_refresh(self, needs_refresh):
        bot = SimpleNamespace(send_message=AsyncMock())
        message = SimpleNamespace(text="/start")
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=1),
            effective_chat=SimpleNamespace(id=10),
            effective_message=message,
            callback_query=None,
        )

        __import__("asyncio").run(refresh_old_user_keyboard(update, SimpleNamespace(bot=bot)))

        needs_refresh.assert_not_called()
        bot.send_message.assert_not_awaited()

    @patch("app.handlers.keyboard_refresh.needs_reply_keyboard_refresh")
    def test_restart_confirmation_does_not_send_keyboard_refresh(self, needs_refresh):
        bot = SimpleNamespace(send_message=AsyncMock())
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=1),
            effective_chat=SimpleNamespace(id=10),
            effective_message=SimpleNamespace(text=None),
            callback_query=SimpleNamespace(data="start_restart_no"),
        )

        __import__("asyncio").run(refresh_old_user_keyboard(update, SimpleNamespace(bot=bot)))

        needs_refresh.assert_not_called()
        bot.send_message.assert_not_awaited()

    @patch("app.onboarding_flow.SUBSCRIPTION_ONBOARDING_ENABLED", False)
    @patch("app.onboarding_flow._transition", new_callable=AsyncMock)
    @patch("app.onboarding_flow.edit_rich_message", new_callable=AsyncMock)
    @patch("app.onboarding_flow.save_state")
    @patch(
        "app.onboarding_flow.load_state",
        return_value={"user_id": 1, "chat_id": 10, "step": "agreement", "screen_id": 20},
    )
    def test_accepted_agreement_skips_hidden_subscription(
        self, _load, _save, _edit, transition
    ):
        query = SimpleNamespace(
            data=f"ob3:accept:{messages.AGREEMENT_VERSION}",
            answer=AsyncMock(),
            message=SimpleNamespace(message_id=20),
        )
        update = SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=1))
        context = SimpleNamespace(bot=object())

        __import__("asyncio").run(agreement_callback(update, context))

        self.assertEqual(transition.await_args.args[2], "schedule_offer")

    @patch("app.onboarding_flow.time.time", return_value=1000)
    @patch("app.onboarding_flow._send_step", new_callable=AsyncMock)
    @patch("app.onboarding_flow.save_state")
    def test_skipping_subscription_keeps_three_day_deadline(self, _save, _send, _time):
        from app.onboarding_flow import _transition

        state = {"step": "agreement"}
        __import__("asyncio").run(_transition(SimpleNamespace(), state, "schedule_offer"))

        self.assertEqual(state["deadline_at"], 1000 + 72 * 3600)

    @patch("app.handlers.schedule.get_user_schedule_settings", return_value={"notify_time": "00:00", "enabled": False})
    def test_schedule_without_saved_time_shows_first_setup(self, _settings):
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=1),
            effective_message=message,
        )
        context = SimpleNamespace(user_data={})

        __import__("asyncio").run(schedule_command(update, context))

        kwargs = message.reply_text.await_args.kwargs
        self.assertEqual(message.reply_text.await_args.args[0], FIRST_SETUP_TEXT)
        self.assertIn("<blockquote expandable>", FIRST_SETUP_TEXT)
        self.assertEqual(kwargs["reply_markup"].inline_keyboard[0][0].text, "Выбрать время")

    @patch(
        "app.handlers.schedule.get_user_schedule_settings",
        return_value={
            "notify_time": "07:00", "enabled": True, "paused": False,
            "bot_mode": "daily", "challenge_start_id": None, "challenge_day": 0,
        },
    )
    def test_configured_schedule_shows_management_actions(self, _settings):
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(effective_user=SimpleNamespace(id=1), effective_message=message)

        __import__("asyncio").run(schedule_command(update, SimpleNamespace(user_data={})))

        self.assertIn("Рассылка активна", message.reply_text.await_args.args[0])
        rows = message.reply_text.await_args.kwargs["reply_markup"].inline_keyboard
        self.assertEqual([row[0].text for row in rows], [
            "Остановить рассылку", "Изменить время",
        ])

    @patch(
        "app.handlers.schedule.get_user_schedule_settings",
        return_value={
            "notify_time": "07:00", "enabled": True, "paused": False,
            "bot_mode": "challenge", "challenge_start_id": 7, "challenge_day": 3,
        },
    )
    def test_challenge_schedule_adds_week_action_and_exit_hint(self, _settings):
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(effective_user=SimpleNamespace(id=1), effective_message=message)

        __import__("asyncio").run(schedule_command(update, SimpleNamespace(user_data={})))

        text = message.reply_text.await_args.args[0]
        self.assertIn("Сейчас ты в челлендже", text)
        self.assertIn("Твоё время — 07:00", text)
        self.assertNotIn("/challenge_off", text)
        rows = message.reply_text.await_args.kwargs["reply_markup"].inline_keyboard
        self.assertEqual(rows[0][0].text, "Остановить рассылку")
        self.assertEqual(rows[2][0].text, "Расписание челленджа")

    @patch(
        "app.handlers.schedule.get_user_schedule_settings",
        return_value={
            "notify_time": "07:00", "paused": False, "bot_mode": "challenge",
            "challenge_start_id": 7, "challenge_day": 3,
        },
    )
    @patch("app.handlers.schedule.toggle_user_pause")
    def test_challenge_stop_button_explains_exit_without_stopping(self, toggle, _settings):
        query = SimpleNamespace(answer=AsyncMock(), message=SimpleNamespace(reply_text=AsyncMock()))
        update = SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=1))

        from app.handlers.schedule import schedule_toggle_callback
        __import__("asyncio").run(schedule_toggle_callback(update, SimpleNamespace()))

        toggle.assert_not_called()
        explanation = query.message.reply_text.await_args.args[0]
        self.assertIn("Когда челлендж закончится", explanation)
        self.assertIn("/challenge_off", explanation)

    @patch(
        "app.handlers.schedule.get_user_schedule_settings",
        side_effect=[
            {"notify_time": "07:00", "paused": False, "bot_mode": "daily", "challenge_start_id": None},
            {"notify_time": "07:00", "paused": True, "bot_mode": "daily", "challenge_start_id": None},
        ],
    )
    @patch("app.handlers.schedule.toggle_user_pause", return_value=(True, True, False))
    def test_pausing_keeps_management_buttons_and_offers_resume(self, _toggle, _settings):
        query = SimpleNamespace(
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        update = SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=1))

        from app.handlers.schedule import schedule_toggle_callback
        __import__("asyncio").run(schedule_toggle_callback(update, SimpleNamespace()))

        markup = query.edit_message_text.await_args.kwargs["reply_markup"]
        self.assertEqual(markup.inline_keyboard[0][0].text, "Возобновить рассылку")
        confirmation = query.message.reply_text.await_args.args[0]
        self.assertIn("Возобновить рассылку", confirmation)

    @patch(
        "app.handlers.schedule.get_user_schedule_settings",
        side_effect=[
            {"notify_time": "07:00", "paused": True, "bot_mode": "daily", "challenge_start_id": None},
            {"notify_time": "07:00", "paused": False, "bot_mode": "daily", "challenge_start_id": None},
        ],
    )
    @patch("app.handlers.schedule.toggle_user_pause", return_value=(True, False, False))
    def test_resume_confirmation_has_no_redundant_menu_paragraph(self, _toggle, _settings):
        query = SimpleNamespace(
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        update = SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=1))

        from app.handlers.schedule import schedule_toggle_callback
        __import__("asyncio").run(schedule_toggle_callback(update, SimpleNamespace()))

        confirmation = query.message.reply_text.await_args.args[0]
        self.assertIn("Следующая практика придет", confirmation)
        self.assertNotIn("Изменить время и сбросить прогресс", confirmation)

    def test_schedule_pick_time_removes_button_and_starts_waiting(self):
        query = SimpleNamespace(answer=AsyncMock(), edit_message_reply_markup=AsyncMock())
        bot = SimpleNamespace(send_message=AsyncMock())
        context = SimpleNamespace(user_data={}, bot=bot)
        update = SimpleNamespace(callback_query=query, effective_chat=SimpleNamespace(id=10))

        __import__("asyncio").run(schedule_pick_time_callback(update, context))

        query.edit_message_reply_markup.assert_awaited_once_with(reply_markup=None)
        self.assertTrue(context.user_data[SCHEDULE_MENU_TIME_KEY])
        self.assertTrue(context.user_data["waiting_for_time"])
        self.assertIn("Введи время", bot.send_message.await_args.kwargs["text"])

    @patch("app.handlers.schedule.save_user_time", return_value=True)
    def test_schedule_time_is_normalized_saved_without_progress_reset(self, save_time):
        message = SimpleNamespace(text="7.00", reply_text=AsyncMock())
        update = SimpleNamespace(
            effective_message=message,
            effective_user=SimpleNamespace(id=1, first_name="Катя", username="katya"),
            effective_chat=SimpleNamespace(id=10),
        )
        context = SimpleNamespace(user_data={SCHEDULE_MENU_TIME_KEY: True, "waiting_for_time": True})

        handled = __import__("asyncio").run(handle_schedule_menu_time_input(update, context))

        self.assertTrue(handled)
        self.assertNotIn(SCHEDULE_MENU_TIME_KEY, context.user_data)
        self.assertEqual(save_time.call_args.args[2], "07:00")
        self.assertFalse(save_time.call_args.kwargs["reset_days"])
        self.assertIn("07:00", message.reply_text.await_args.args[0])

    @patch("app.handlers.schedule.save_user_time")
    def test_invalid_schedule_time_keeps_waiting(self, save_time):
        message = SimpleNamespace(text="25:00", reply_text=AsyncMock())
        update = SimpleNamespace(effective_message=message)
        context = SimpleNamespace(user_data={SCHEDULE_MENU_TIME_KEY: True, "waiting_for_time": True})

        handled = __import__("asyncio").run(handle_schedule_menu_time_input(update, context))

        self.assertTrue(handled)
        self.assertTrue(context.user_data[SCHEDULE_MENU_TIME_KEY])
        save_time.assert_not_called()

    def test_practice_menu_sends_tutorial_video_and_caches_file_id(self):
        sent = SimpleNamespace(video=SimpleNamespace(file_id="telegram-video-id"))
        effective_message = SimpleNamespace(reply_video=AsyncMock(return_value=sent))
        context = SimpleNamespace(bot_data={"practice_keyboard_tutorial_video": "source-video"})
        update = SimpleNamespace(effective_message=effective_message)

        __import__("asyncio").run(get_practice_command(update, context))

        effective_message.reply_video.assert_awaited_once()
        self.assertTrue(effective_message.reply_video.await_args.kwargs["supports_streaming"])
        self.assertEqual(context.bot_data["practice_keyboard_tutorial_file_id"], "telegram-video-id")

    def test_permanent_keyboard_has_final_layout_and_labels(self):
        keyboard = get_common_reply_keyboard()
        rows = [[button.text for button in row] for row in keyboard.keyboard]
        self.assertEqual(rows, [
            ["ленивые дни", "без коврика"],
            ["здоровая спина", "расслабление"],
            ["мини", "strello4ka"],
            ["хард", "практика дня"],
            ["САМ решу"],
            ["расписание"],
        ])
        self.assertFalse(keyboard.is_persistent)

    def test_onboarding_keyboard_is_persistent_only_during_onboarding(self):
        self.assertTrue(onboarding_reply_keyboard([["Дальше"]]).is_persistent)

    def test_completed_practice_keeps_visible_noop_button(self):
        keyboard = get_practice_completed_keyboard(7, False)
        self.assertEqual(keyboard.inline_keyboard[0][1].text, "✅ Я сделал!")
        self.assertEqual(keyboard.inline_keyboard[0][1].api_kwargs, {"disabled": {}})

    def test_only_long_reference_copy_is_expandable(self):
        self.assertIn("<blockquote>", messages.welcome("Катя"))
        self.assertNotIn("<blockquote expandable>", messages.welcome("Катя"))
        self.assertIn("<blockquote>", messages.SCHEDULE_OFFER)
        self.assertNotIn("<blockquote expandable>", messages.SCHEDULE_OFFER)
        self.assertIn("<blockquote expandable>", messages.TIME_INPUT)
        self.assertIn("В какое время хочешь получать", messages.TIME_INPUT)
        self.assertIn("Введи время в формате", messages.TIME_INPUT)
        self.assertIn("<blockquote expandable>", messages.COMPLETE)

    @patch("app.challenge.flow.start_flow.get_challenge_start_date")
    def test_challenge_welcome_contains_date_range_and_week_quote(self, get_start):
        from datetime import date
        get_start.return_value = date(2026, 9, 14)
        text = build_challenge_welcome_text()
        self.assertIn("14.09", text)
        self.assertIn("11.10", text)
        self.assertIn("<blockquote expandable>", text)

    @patch("app.handlers.progress.get_user_bot_mode", return_value="by_mood")
    def test_progress_stats_are_paragraphs_not_disabled_buttons(self, _mode):
        blocks = _progress_blocks(1, 4, 1, "")
        self.assertTrue(all(block.get("type") != "buttons" for block in blocks[:-1]))
        self.assertFalse(any("disabled" in str(block) for block in blocks))

    def test_post_challenge_actions_keep_expected_layout(self):
        rows = [[button.text for button in row] for row in post_challenge_keyboard("07:00").inline_keyboard]
        self.assertEqual(rows, [["Не хочу", "Изменить время"], ["Продолжить в 07:00"]])
        self.assertTrue(offer_text("07:00").startswith("🕐"))
        finished = build_challenge_finished_text(12)
        self.assertIn("*12/28*", finished)
        self.assertNotIn("Продолжай пользоваться", finished)

    @patch("app.onboarding_flow.load_state", return_value={"step": "declined"})
    def test_declined_user_cannot_bypass_agreement_with_text(self, _state):
        message = SimpleNamespace(text="09.30", reply_text=AsyncMock())
        update = SimpleNamespace(effective_user=SimpleNamespace(id=1), effective_message=message)
        handled = __import__("asyncio").run(handle_reply(update, SimpleNamespace()))
        self.assertTrue(handled)
        message.reply_text.assert_awaited_once()

    def test_help_uses_bold_paragraph_instead_of_heading(self):
        blocks = _root_blocks()
        self.assertEqual(blocks[0]["type"], "paragraph")
        self.assertEqual(blocks[0]["text"]["type"], "bold")
        self.assertTrue(blocks[1]["text"].startswith("\n"))
        self.assertFalse(blocks[1]["text"].startswith("\n\n"))

        tips = _tips_blocks()
        self.assertTrue(tips[1]["text"].startswith("\n"))
        self.assertFalse(tips[1]["text"].startswith("\n\n"))

    def test_practice_suggestion_starts_with_question_and_uses_static_quote(self):
        blocks = _suggest_blocks()
        self.assertEqual(blocks[0]["type"], "paragraph")
        self.assertEqual(
            blocks[0]["text"][0]["text"],
            "Хочешь, чтобы твоя любимая практика появилась в YogaDailyBot?",
        )
        self.assertTrue(blocks[1]["text"][0].startswith("\n"))
        self.assertEqual(blocks[2]["type"], "blockquote")

    def test_faq_reuses_onboarding_filter_and_week_copy(self):
        blocks = _faq_blocks()
        self.assertIn("Что означают кнопки-фильтры?", str(blocks))
        self.assertIn("Как составляется неделя?", str(blocks))
        self.assertIn("ленивые дни", str(blocks))
        week = next(block for block in blocks if block.get("summary") == "Как составляется неделя?")
        week_text = "".join(week["blocks"][0]["text"])
        self.assertIn("🌀 2–3 бодрые, 5–15 минут\n", week_text)

        sleep_tip = next(
            block for block in _tips_blocks()
            if block.get("summary") == "Почему плохо выполнять активные практики перед сном?"
        )
        sleep_tip_text = "".join(
            part if isinstance(part, str) else part["text"]
            for part in sleep_tip["blocks"][0]["text"]
        )
        self.assertIn("активируется симпатическая нервная система", sleep_tip_text)
        self.assertNotIn("Как строится неделя", str(_tips_blocks()))

    @patch("app.handlers.help.edit_rich_message", new_callable=AsyncMock)
    def test_help_section_edits_same_message_and_has_back_button(self, edit):
        query = SimpleNamespace(
            data="help_faq",
            answer=AsyncMock(),
            message=SimpleNamespace(chat_id=10, message_id=20),
        )
        context = SimpleNamespace(bot=object(), user_data={})
        update = SimpleNamespace(callback_query=query)

        __import__("asyncio").run(help_section_callback(update, context))

        blocks = edit.await_args.args[3]
        self.assertIn("help_back", str(blocks))
        self.assertEqual(edit.await_args.args[1:3], (10, 20))

    @patch("app.onboarding_flow.save_state")
    def test_welcome_screen_does_not_require_time(self, save_state):
        bot = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=42)))
        state = {"step": "welcome", "chat_id": 10, "name": "Катя"}

        __import__("asyncio").run(_send_step(SimpleNamespace(bot=bot), state))

        bot.send_message.assert_awaited_once()
        self.assertEqual(state["screen_id"], 42)
        save_state.assert_called_once_with(state)


if __name__ == "__main__":
    unittest.main()
