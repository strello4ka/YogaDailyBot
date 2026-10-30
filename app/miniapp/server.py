"""Dependency-injected WSGI app; no database, bot or listener on import.

The preview CLI is static-only. Payment routes require an explicitly configured
test repository/provider supplied by the caller and signed Telegram initData.
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit
from uuid import UUID

import httpx

from app.payments.service import PriceChanged
from app.subscription.old_users.prices import checkout_price
from app.subscription.tariff import MOSCOW, TARIFFS, last_access_date
from .auth import authenticate

logger = logging.getLogger(__name__)
STATIC = Path(__file__).with_name('static')
OFFER_URL = 'https://seatbackandrelax.tilda.ws/yogadailybot-offer'


def tariffs(offer=None, now=None):
    result = []
    for tariff in TARIFFS.values():
        price = checkout_price(tariff.code, offer, now) if now is not None else None
        result.append(dict(code=tariff.code, title=tariff.title, days=tariff.days,
                           base_price=price.base_price if price else tariff.base_price,
                           final_price=price.final_price if price else tariff.base_price))
    return result


class MiniApp:
    def __init__(self, *, repository=None, payments=None, bot_token='', allowed_users=(),
                 return_url='', preview=False, preview_offer=None, clock=None):
        self.repository, self.payments = repository, payments
        self.bot_token = bot_token
        self.allowed_users = frozenset(allowed_users) if allowed_users is not None else None
        self.return_url, self.preview, self.preview_offer = return_url, preview, preview_offer
        self.clock = clock or (lambda: datetime.now(MOSCOW))

    def __call__(self, environ, start_response):
        path, method = environ.get('PATH_INFO', '/'), environ.get('REQUEST_METHOD', 'GET')
        headers = [('Cache-Control', 'no-store'), ('X-Content-Type-Options', 'nosniff'),
                   ('Referrer-Policy', 'no-referrer')]

        def respond(status, data, content_type='application/json; charset=utf-8'):
            body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode()
            start_response(status, headers + [('Content-Type', content_type), ('Content-Length', str(len(body)))])
            return [body]

        assets = {'/': ('index.html', 'text/html'), '/styles.css': ('styles.css', 'text/css'),
                  '/app.js': ('app.js', 'application/javascript')}
        if method == 'GET' and path in assets:
            filename, content_type = assets[path]
            return respond('200 OK', (STATIC / filename).read_bytes(), content_type + '; charset=utf-8')
        if method != 'POST' or not path.startswith('/api/'):
            return respond('404 Not Found', {'error': 'Страница не найдена'})
        try:
            if not environ.get('CONTENT_TYPE', '').startswith('application/json'):
                return respond('415 Unsupported Media Type', {'error': 'Ожидается JSON'})
            size = int(environ.get('CONTENT_LENGTH') or '0')
            if not 0 < size <= 20000:
                return respond('413 Payload Too Large', {'error': 'Некорректный запрос'})
            data = json.loads(environ['wsgi.input'].read(size))
            if not isinstance(data, dict):
                raise ValueError('Invalid body')
            now = self.clock()
            if self.preview:
                if path == '/api/session':
                    offer = self.preview_offer
                    offer_ends_on = (last_access_date(offer.offer_ends).isoformat()
                                     if offer and offer.special_price_active(now) else None)
                    return respond('200 OK', {'tariffs': tariffs(offer, now), 'email': '', 'note': '',
                                             'offer_ends_on': offer_ends_on, 'offer_url': OFFER_URL,
                                             'preview': True, 'order_id': None})
                return respond('403 Forbidden', {'error': 'В предпросмотре оплата отключена'})
            if self.repository is None or self.payments is None:
                return respond('503 Service Unavailable', {'error': 'Тестовая оплата ещё не подключена'})
            if path == '/api/yookassa/webhook':
                from app.payments.webhook import handle_notification
                handle_notification(data, self.payments, now, self.allowed_users)
                # Acknowledge only after verified durable state is committed.
                return respond('200 OK', {'received': True})
            try:
                user_id = authenticate(data.get('init_data'), self.bot_token, now.timestamp(), self.allowed_users)
            except ValueError:
                return respond('401 Unauthorized', {'error': 'Открой страницу заново через кнопку в тестовом боте'})
            profile = self.repository.checkout_profile(user_id)
            if profile is None:
                return respond('403 Forbidden', {'error': 'Сначала пройди онбординг в тестовом боте'})
            if path == '/api/session':
                email, trial_end, paid_end = profile.email, profile.trial_ends, profile.subscription_ends
                note = ''
                if paid_end and paid_end > now:
                    note = 'Новый период добавится к текущей подписке. Оставшиеся дни сохранятся.'
                elif trial_end and trial_end > now:
                    note = 'Подписка начнёт действовать с {} — после пробного периода.'.format(
                        trial_end.astimezone(MOSCOW).strftime('%d.%m.%Y'))
                allowed = getattr(self.payments, 'allowed_tariffs', None)
                catalog = tariffs(profile.old_user_offer, now)
                if allowed is not None:
                    catalog = [t for t in catalog if t['code'] in allowed]
                if allowed is not None:
                    note = 'Настоящее списание 350 ₽. Проверка реального магазина. ' + note
                offer_ends_on = (last_access_date(profile.old_user_offer.offer_ends).isoformat()
                                 if profile.old_user_offer and
                                 profile.old_user_offer.special_price_active(now) else None)
                return respond('200 OK', {'tariffs': catalog, 'email': email or '', 'note': note,
                                         'offer_ends_on': offer_ends_on,
                                         'offer_url': OFFER_URL, 'preview': False,
                                         'order_id': self.repository.open_order_id(user_id)})
            if path == '/api/payments':
                order_id = str(UUID(data['order_id']))
                code = data['tariff_code']
                if code not in TARIFFS:
                    raise ValueError('Unknown tariff')
                replace_open_order = data.get('replace_open_order', False)
                if not isinstance(replace_open_order, bool):
                    raise ValueError('Invalid replacement flag')
                order_id, payment = self.payments.checkout(
                    order_id, user_id, code, data['email'], self.return_url, now,
                    expected_final_price=data.get('final_price'),
                    replace_open_order=replace_open_order)
                confirmation = (payment or {}).get('confirmation') or {}
                return respond('200 OK', {'order_id': order_id,
                                         'confirmation_url': confirmation.get('confirmation_url')})
            if path.startswith('/api/payments/'):
                order_id = str(UUID(path.removeprefix('/api/payments/')))
                details = self.payments.refresh_details(order_id, user_id, now, self.return_url)
                status = details['status']
                # Refresh returns succeeded only after the grant transaction commits.
                end = (self.repository.checkout_profile(user_id).subscription_ends
                       if status == 'succeeded' else None)
                return respond('200 OK', {'status': status, 'confirmation_url': details.get('confirmation_url'),
                                         'ends_on': last_access_date(end).isoformat() if end else None})
            return respond('404 Not Found', {'error': 'Страница не найдена'})
        except LookupError:
            return respond('404 Not Found', {'error': 'Заказ не найден'})
        except PriceChanged as error:
            return respond('409 Conflict', {'error': str(error), 'reload': True})
        except (ValueError, TypeError):
            return respond('400 Bad Request', {'error': 'Проверь выбранный тариф и адрес e-mail'})
        except httpx.HTTPError:
            return respond('503 Service Unavailable', {'error': 'Не удалось проверить оплату. Попробуй ещё раз.'})
        except Exception:
            # Do not expose provider responses, auth headers or email in error output.
            logger.error('Mini App request failed path=%s', path.split('/')[1:3])
            return respond('503 Service Unavailable', {'error': 'Не удалось завершить запрос. Повтори проверку позже.'})


def create_preview_app():
    """Public preview: tariff UI only, with all payment routes disabled."""
    import os
    from .gateway import TestGateway
    return TestGateway(MiniApp(preview=True), os.environ.get('MINIAPP_TEST_BACKEND_URL', ''))


def create_test_app(environment, connection_factory, *, provider=None):
    """Fail closed before accepting requests from an HTTPS reverse proxy."""
    from app.subscription.subscription_menu import test_settings
    from data.subscription_repository import SubscriptionRepository
    from app.payments.service import PaymentService
    from app.payments.config import payment_settings

    settings = test_settings(environment)
    if settings is None:
        raise ValueError('Test subscription mode is disabled')
    users, url, database_name = settings
    config = payment_settings(environment)
    if not config.shop_id or not config.secret or not url:
        raise ValueError('YooKassa credentials and Mini App URL are required for checkout')
    return_url = environment.get('SUBSCRIPTION_PAYMENT_RETURN_URL', '').strip() or url
    parsed_return = urlsplit(return_url)
    query = dict(parse_qsl(parsed_return.query, keep_blank_values=True))
    same_host = parsed_return.hostname == urlsplit(url).hostname
    telegram_main_app = (parsed_return.hostname == 't.me' and parsed_return.path.strip('/')
                         and 'startapp' in query)
    if (parsed_return.scheme != 'https' or parsed_return.username or parsed_return.password
            or not (same_host or telegram_main_app)):
        raise ValueError('Payment return URL must open this Mini App or its Telegram Main Mini App')
    repository = SubscriptionRepository(connection_factory, payment_scope=config.scope)
    repository.verify_test_database(database_name)
    owns_provider = provider is None
    if owns_provider:
        provider = config.client()
    try:
        if provider.expected_test is not (not config.live):
            raise ValueError('Provider does not match configured payment mode')
        if config.live:
            provider.verify_store()
        else:
            provider.verify_test_store()
    except Exception:
        if owns_provider:
            provider.close()
        raise
    return MiniApp(repository=repository, payments=PaymentService(
                       repository, provider, allowed_tariffs=('month',) if config.live else None),
                   bot_token=environment['BOT_TOKEN'], allowed_users=users, return_url=return_url)


def create_hosted_test_app():
    """Run the same isolated test checkout on persistent Railway infrastructure."""
    import os
    if os.environ.get('SUBSCRIPTION_HOSTED_TEST_ENABLED', '').lower() != 'true':
        raise ValueError('Hosted test Mini App is disabled')
    from data.postgres_db import get_connection
    return create_test_app(os.environ, get_connection)


if __name__ == '__main__':
    import argparse
    import os
    from wsgiref.simple_server import make_server
    parser = argparse.ArgumentParser(description='Local Mini App preview or explicit test checkout')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--test', action='store_true', help='Require .env.test, allowlist and test YooKassa')
    parser.add_argument('--old-user-preview', action='store_true',
                        help='Preview the agreed old-user special-price screen')
    args = parser.parse_args()
    if args.test:
        from pathlib import Path
        env_file = os.environ.get('ENV_FILE', '')
        if Path(env_file).name != '.env.test':
            parser.error('--test requires ENV_FILE=test/.env.test')
        from dotenv import load_dotenv
        load_dotenv(env_file)
        from data.postgres_db import get_connection
        app = create_test_app(os.environ, get_connection)
    else:
        if args.old_user_preview:
            from app.subscription.old_users.rules import launch_offer
            app = MiniApp(preview=True, preview_offer=launch_offer(datetime.now(MOSCOW)))
        else:
            app = MiniApp(preview=True)
    try:
        with make_server('127.0.0.1', args.port, app) as server:
            mode = 'test checkout' if args.test else 'preview, payments disabled'
            print('Local Mini App: http://127.0.0.1:{}/ ({})'.format(args.port, mode), flush=True)
            server.serve_forever()
    finally:
        if args.test:
            app.payments.provider.close()
