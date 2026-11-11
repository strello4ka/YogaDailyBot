"""Pure notification eligibility rules; no scheduler or database on import.

The eventual worker must reload access immediately before delivery and persist
the returned key, so retries and restarts do not intentionally resend an event.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import List, Optional
import logging
import asyncio
from contextlib import asynccontextmanager

from .access import AccessState, Subscription
from .tariff import MOSCOW, local_time

logger = logging.getLogger(__name__)


async def _user_reminders(context, user_id, subscription, now):
    offer, pending = None, False
    launch_sent_at = None
    if subscription.gift is not None:
        repository = context.bot_data['subscription_repository']
        offer, pending = await asyncio.to_thread(repository.old_user_reminder_context, user_id)
        if offer is not None:
            launch_key = 'launch:' + local_time(offer.gift.ends_at).isoformat()
            launch_sent_at = await asyncio.to_thread(repository.notification_sent_at,
                                                     user_id, launch_key)
    return due_reminders(subscription, now, old_user_offer=offer,
                         payment_pending=pending, launch_sent_at=launch_sent_at)


async def _subscription_user_ids(context, repository):
    configured = context.bot_data.get('subscription_allowed_users')
    if configured is not None:
        return configured
    return await asyncio.to_thread(repository.enrolled_user_ids)


@asynccontextmanager
async def _notice_lock(repository, user_id, event_key):
    manager = repository.notification_lock(user_id, event_key)
    # Database I/O must not block Telegram's event loop.
    acquired = await asyncio.to_thread(manager.__enter__)
    try:
        yield acquired
    finally:
        await asyncio.to_thread(manager.__exit__, None, None, None)


async def deliver_payment_notice(context, user_id, order_id, now):
    from .messages import payment_accepted
    from app.keyboards import get_common_reply_keyboard
    repository = context.bot_data['subscription_repository']
    event_key = 'payment_success:' + order_id
    async with _notice_lock(repository, user_id, event_key) as acquired:
        if not acquired or await asyncio.to_thread(repository.notification_sent, user_id, event_key):
            return
        notice = await asyncio.to_thread(repository.payment_notice, order_id, user_id)
        if notice is None:
            return
        chat_id, name, end = notice
        # Refresh Telegram's reply keyboard along with the durable confirmation.
        await context.bot.send_message(chat_id=chat_id, text=payment_accepted(name, end),
                                       parse_mode='HTML', reply_markup=get_common_reply_keyboard())
        # Record only after Telegram acknowledges the send. Access was committed
        # earlier and is never rolled back by a notification failure.
        await asyncio.to_thread(repository.mark_notification_sent, user_id, event_key, now)


async def deliver_canceled_payment_notice(context, user_id, order_id, now):
    from .messages import PAYMENT_FAILED
    from .subscription_menu import optional_tariff_keyboard
    repository = context.bot_data['subscription_repository']
    event_key = 'payment_canceled:' + order_id
    async with _notice_lock(repository, user_id, event_key) as acquired:
        if not acquired or await asyncio.to_thread(repository.notification_sent, user_id, event_key):
            return
        chat_id = await asyncio.to_thread(repository.canceled_payment_notice, order_id, user_id)
        if chat_id is None:
            return
        keyboard = optional_tariff_keyboard(context.bot_data.get('subscription_miniapp_url', ''))
        await context.bot.send_message(chat_id=chat_id, text=PAYMENT_FAILED,
                                       parse_mode='HTML', reply_markup=keyboard)
        await asyncio.to_thread(repository.mark_notification_sent, user_id, event_key, now)


async def _deliver_ready_payments(context, user_id):
    """Deliver durable results without making any provider requests."""
    repository = context.bot_data['subscription_repository']
    _, notices = await asyncio.to_thread(repository.payment_work, user_id)
    for order_id in notices:
        try:
            await deliver_payment_notice(context, user_id, order_id, datetime.now(MOSCOW))
        except Exception:
            logger.warning('Payment notification failed order=%s', order_id)
    canceled = await asyncio.to_thread(repository.canceled_payment_work, user_id)
    for order_id in canceled:
        try:
            await deliver_canceled_payment_notice(context, user_id, order_id,
                                                  datetime.now(MOSCOW))
        except Exception:
            logger.warning('Canceled payment notification failed order=%s', order_id)
    from app.onboarding.flow import continue_after_subscription_payment
    await continue_after_subscription_payment(context, user_id)


async def reconcile_payments(context, *, user_ids=None, check_pending=True):
    """Deliver ready results first; only periodic reconciliation polls YooKassa."""
    repository = context.bot_data.get('subscription_repository')
    service = context.bot_data.get('subscription_payment_service')
    if repository is None:
        return
    allowed = await _subscription_user_ids(context, repository)
    selected = allowed if user_ids is None else set(user_ids).intersection(allowed)
    for user_id in selected:
        try:
            await _deliver_ready_payments(context, user_id)
            if not check_pending:
                continue
            pending, _ = await asyncio.to_thread(repository.payment_work, user_id)
            if service is not None:
                for order_id in pending:
                    try:
                        await asyncio.to_thread(service.refresh_details, order_id, user_id,
                                                datetime.now(MOSCOW),
                                                context.bot_data['subscription_miniapp_url'])
                    except Exception:
                        # No provider body, personal data or credentials in logs.
                        logger.warning('Payment reconciliation failed order=%s', order_id)
                    finally:
                        await asyncio.to_thread(repository.touch_order_check, order_id, user_id,
                                                datetime.now(MOSCOW))
            # Also deliver grants discovered by this periodic reconciliation.
            if service is not None and pending:
                await _deliver_ready_payments(context, user_id)
        except Exception:
            logger.warning('Payment worker failed user=%s', user_id)


_FILTER_LABELS = {
    'five': 'Мини', 'relax': 'Расслабление', 'lazy': 'Ленивые дни',
    'healthy_back': 'Здоровая спина', 'no_mat': 'Без коврика',
    'hard': 'Хард', 'strello4ka': 'strello4ka',
}


def reminder_text(event, profile):
    from . import messages
    from .old_users.notifications import NOTIFICATION_KINDS
    kind = event.kind
    if kind in NOTIFICATION_KINDS:
        from .old_users.messages import reminder_text as old_user_reminder_text
        return old_user_reminder_text(kind, profile['name'], event.period_ends_at,
                                      event.offer_ends_at)
    if kind == 'trial_three_days':
        renderer = (messages.challenge_access_three_days if profile['challenge']
                    else messages.trial_three_days)
        return renderer(profile['name'], event.period_ends_at)
    if kind == 'paid_three_days':
        renderer = (messages.challenge_access_three_days if profile['challenge']
                    else messages.paid_three_days)
        return renderer(profile['name'], event.period_ends_at)
    if kind == 'trial_last_day':
        if profile['challenge']:
            return messages.challenge_access_last_day()
        categories = [_FILTER_LABELS.get(key, key) for key in profile['filter_keys']]
        return messages.trial_last_day(completions=profile['completions'], categories=categories)
    if kind == 'paid_last_day':
        return (messages.challenge_access_last_day() if profile['challenge']
                else messages.paid_last_day())
    if kind == 'trial_expired':
        return (messages.challenge_access_expired() if profile['challenge']
                else messages.trial_expired())
    if kind == 'paid_expired':
        return (messages.challenge_access_expired() if profile['challenge']
                else messages.paid_expired())
    if kind == 'trial_subscription_activated':
        return messages.trial_subscription_activated(
            profile['name'], event.period_ends_at)
    if kind == 'gift_subscription_activated':
        from .old_users.messages import gift_subscription_activated
        return gift_subscription_activated(profile['name'], event.period_ends_at)
    if kind == 'trial_followup':
        return messages.trial_followup(has_favorites=profile['has_favorites'])
    raise ValueError('Unknown reminder')


async def _send_reminder(context, user_id, event, profile, now):
    from .messages import TARIFF_PROMPT
    from .access import AccessState
    from .free import reply_keyboard
    from .subscription_menu import optional_tariff_keyboard
    repository = context.bot_data['subscription_repository']
    async with _notice_lock(repository, user_id, event.key) as acquired:
        if not acquired:
            return
        already_sent = await asyncio.to_thread(repository.notification_sent, user_id, event.key)
        # Recheck dates and purchase state immediately before sending: renewal
        # invalidates the old end and therefore the old reminder key.
        current = await asyncio.to_thread(repository.get, user_id)
        moment = datetime.now(MOSCOW)
        eligible = (await _user_reminders(context, user_id, current, moment)
                    if current is not None else [])
        if event.key not in {item.key for item in eligible}:
            return
        if event.kind.endswith('expired'):
            keyboard = reply_keyboard()
        elif event.kind.endswith('subscription_activated'):
            keyboard = None
        else:
            from .old_users.notifications import NOTIFICATION_KINDS
            from .old_users.messages import (feedback_keyboard, first_message_keyboard,
                                             tariff_button_keyboard)
            url = context.bot_data['subscription_miniapp_url']
            if event.kind == 'launch':
                keyboard = first_message_keyboard(url) if url else None
            elif event.kind == 'launch_feedback':
                keyboard = feedback_keyboard()
            else:
                keyboard = (tariff_button_keyboard(url)
                            if url and event.kind in NOTIFICATION_KINDS
                            else optional_tariff_keyboard(url))
        if event.kind.endswith('expired') and current.state(moment) != AccessState.FREE:
            return
        if not already_sent:
            await context.bot.send_message(chat_id=profile['chat_id'],
                                           text=reminder_text(event, profile),
                                           parse_mode='HTML', reply_markup=keyboard)
            await asyncio.to_thread(repository.mark_notification_sent, user_id, event.key,
                                    datetime.now(MOSCOW))
    # Telegram messages can have one keyboard type. Change the reply keyboard
    # on the expiry message; offer tariff navigation in a separate short message.
    if event.kind.endswith('expired') and context.bot_data['subscription_miniapp_url']:
        tariff_prompt = TARIFF_PROMPT
        if event.kind == 'gift_expired':
            from .old_users.messages import gift_expired_tariff_prompt
            tariff_prompt = gift_expired_tariff_prompt(event.offer_ends_at)
        tariff_key = event.key + ':tariffs'
        async with _notice_lock(repository, user_id, tariff_key) as acquired:
            if acquired and not await asyncio.to_thread(repository.notification_sent, user_id, tariff_key):
                current = await asyncio.to_thread(repository.get, user_id)
                eligible = (await _user_reminders(context, user_id, current, datetime.now(MOSCOW))
                            if current is not None else [])
                if event.key not in {item.key for item in eligible}:
                    return
                await context.bot.send_message(chat_id=profile['chat_id'],
                                               text=tariff_prompt,
                                               parse_mode='HTML',
                                               reply_markup=optional_tariff_keyboard(
                                                   context.bot_data['subscription_miniapp_url']))
                await asyncio.to_thread(repository.mark_notification_sent, user_id, tariff_key,
                                        datetime.now(MOSCOW))

async def deliver_reminders(context):
    repository = context.bot_data.get('subscription_repository')
    if repository is None:
        return
    for user_id in await _subscription_user_ids(context, repository):
        try:
            now = datetime.now(MOSCOW)
            subscription = await asyncio.to_thread(repository.synchronize_access, user_id, now)
            if subscription is None:
                continue
            events = await _user_reminders(context, user_id, subscription, now)
            profile = await asyncio.to_thread(repository.reminder_profile, user_id,
                                               subscription.trial if any(
                                                   e.kind in ('trial_last_day', 'trial_followup') for e in events)
                                               else None)
            if profile is None:
                continue
            # The generic follow-up can claim that schedule delivery stopped,
            # while the challenge schedule remains active.
            if profile['challenge']:
                events = [event for event in events if event.kind != 'trial_followup']
            for event in events:
                try:
                    await _send_reminder(context, user_id, event, profile, now)
                except Exception as error:
                    # A blocked recipient must leave the reminder queue. Other
                    # failures remain unacknowledged and are retried later.
                    from app.block import mark_blocked_if_forbidden
                    blocked = await asyncio.to_thread(
                        mark_blocked_if_forbidden, user_id, error)
                    if not blocked:
                        logger.warning(
                            'Subscription reminder failed user=%s kind=%s',
                            user_id, event.kind, exc_info=True)
        except Exception:
            logger.warning('Subscription reminder worker failed user=%s', user_id)


@dataclass(frozen=True)
class Reminder:
    kind: str
    period_ends_at: datetime
    scheduled_at: datetime
    offer_ends_at: Optional[datetime] = None

    @property
    def key(self) -> str:
        return "{}:{}".format(self.kind, local_time(self.period_ends_at).isoformat())


def _at(day: date, hour: int) -> datetime:
    return datetime.combine(day, time(hour), tzinfo=MOSCOW)


def due_reminders(subscription: Subscription, now: datetime, *, old_user_offer=None,
                  payment_pending=False, launch_sent_at=None) -> List[Reminder]:
    """Return today's eligible events, not a backlog of obsolete sales messages.

    The three-day event uses the exclusive expiry date minus three days:
    three accessible calendar dates remain, including the notification date.
    """
    now = local_time(now)
    result = []

    def add(kind, end, day, hour):
        scheduled = _at(day, hour)
        if scheduled.date() == now.date() and scheduled <= now:
            result.append(Reminder(kind, end, scheduled))

    state = subscription.state(now)
    if old_user_offer is not None:
        from .old_users.notifications import due_notifications
        for event in due_notifications(old_user_offer, now,
                gift_active=state == AccessState.GIFT, free=state == AccessState.FREE,
                has_paid=subscription.paid is not None, payment_pending=payment_pending,
                launch_sent_at=launch_sent_at):
            end = (old_user_offer.gift.ends_at
                   if event.kind.startswith('gift_') or event.kind.startswith('launch')
                   else old_user_offer.offer_ends)
            result.append(Reminder(event.kind, end, event.scheduled_at,
                                   old_user_offer.offer_ends))
        # The old-user transition replaces expired-trial marketing, not paid
        # subscription reminders or the activation of a prepaid gift period.
        if subscription.paid is None:
            return result
    if state == AccessState.TRIAL:
        end = local_time(subscription.trial.ends_at)
        add("trial_three_days", end, end.date() - timedelta(days=3), 13)
        add("trial_last_day", end, end.date() - timedelta(days=1), 19)
    elif state == AccessState.PAID:
        paid_start = local_time(subscription.paid.starts_at)
        activation_kind = None
        activation_time = _at(paid_start.date(), 8)
        if (subscription.gift
                and local_time(subscription.gift.ends_at) == paid_start):
            activation_kind = "gift_subscription_activated"
        elif (subscription.trial
              and local_time(subscription.trial.ends_at) == paid_start):
            activation_kind = "trial_subscription_activated"
        if (activation_kind and activation_time.date() == now.date()
                and activation_time <= now):
            result.append(Reminder(activation_kind, subscription.paid.ends_at,
                                   activation_time))
        end = local_time(subscription.paid.ends_at)
        add("paid_three_days", end, end.date() - timedelta(days=3), 13)
        add("paid_last_day", end, end.date() - timedelta(days=1), 19)
    elif state == AccessState.FREE:
        # A future paid period also suppresses offers to buy again.
        if subscription.paid and local_time(subscription.paid.ends_at) > now:
            return result
        if subscription.paid:
            end = local_time(subscription.paid.ends_at)
            add("paid_expired", end, end.date(), 8)
        elif subscription.trial:
            end = local_time(subscription.trial.ends_at)
            if end <= now:
                add("trial_expired", end, end.date(), 8)
                add("trial_followup", end, end.date() + timedelta(days=7), 10)
    return result


async def synchronize_access(context):
    """Synchronize enrolled users, optionally limited by a test allowlist."""
    repository = context.bot_data.get("subscription_repository")
    if repository is None:
        return
    now = datetime.now(MOSCOW)
    for user_id in await _subscription_user_ids(context, repository):
        try:
            await asyncio.to_thread(repository.synchronize_access, user_id, now)
        except Exception:
            logger.exception("Subscription state synchronization failed user=%s", user_id)
