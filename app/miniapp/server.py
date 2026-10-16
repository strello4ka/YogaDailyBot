"""Dependency-injected WSGI app; no database, bot or listener on import.

The preview CLI is static-only. Payment routes require an explicitly configured
test repository/provider supplied by the caller and signed Telegram initData.
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from uuid import UUID

import httpx

from app.subscription.tariff import MOSCOW, TARIFFS, last_access_date
from .auth import authenticate

logger = logging.getLogger(__name__)
STATIC = Path(__file__).with_name('static')
OFFER_URL = 'https://seatbackandrelax.tilda.ws/yogadailybot-offer'


def tariffs():
    return [dict(code=t.code, title=t.title, days=t.days, amount=t.amount_kopecks)
            for t in TARIFFS.values()]


class MiniApp:
    def __init__(self, *, repository=None, payments=None, bot_token='', allowed_users=(),
                 return_url='', preview=False, clock=None):
        self.repository, self.payments = repository, payments
        self.bot_token = bot_token
        self.allowed_users = frozenset(allowed_users) if allowed_users is not None else None
        self.return_url, self.preview = return_url, preview
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
                    return respond('200 OK', {'tariffs': tariffs(), 'email': '', 'note': '',
                                             'offer_url': OFFER_URL, 'preview': True, 'order_id': None})
                return respond('403 Forbidden', {'error': 'В предпросмотре оплата отключена'})
            if self.repository is None or self.payments is None:
                return respond('503 Service Unavailable', {'error': 'Тестовая оплата ещё не подключена'})
            try:
                user_id = authenticate(data.get('init_data'), self.bot_token, now.timestamp(), self.allowed_users)
            except ValueError:
                return respond('401 Unauthorized', {'error': 'Открой страницу заново через кнопку в тестовом боте'})
            profile = self.repository.checkout_profile(user_id)
            if profile is None:
                return respond('403 Forbidden', {'error': 'Сначала пройди онбординг в тестовом боте'})
            if path == '/api/session':
                email, trial_end, paid_end = profile
                note = ''
                if paid_end and paid_end > now:
                    note = 'Новый период добавится к текущей подписке. Оставшиеся дни сохранятся.'
                elif trial_end and trial_end > now:
                    note = 'Подписка начнёт действовать с {} — после пробного периода.'.format(
                        trial_end.astimezone(MOSCOW).strftime('%d.%m.%Y'))
                return respond('200 OK', {'tariffs': tariffs(), 'email': email or '', 'note': note,
                                         'offer_url': OFFER_URL, 'preview': False,
                                         'order_id': self.repository.open_order_id(user_id)})
            if path == '/api/payments':
                order_id = str(UUID(data['order_id']))
                code = data['tariff_code']
                if code not in TARIFFS:
                    raise ValueError('Unknown tariff')
                order_id, payment = self.payments.checkout(order_id, user_id, code, data['email'],
                                                          self.return_url, now)
                confirmation = (payment or {}).get('confirmation') or {}
                return respond('200 OK', {'order_id': order_id,
                                         'confirmation_url': confirmation.get('confirmation_url')})
            if path.startswith('/api/payments/'):
                order_id = str(UUID(path.removeprefix('/api/payments/')))
                details = self.payments.refresh_details(order_id, user_id, now, self.return_url)
                status = details['status']
                # Refresh returns succeeded only after the grant transaction commits.
                end = self.repository.checkout_profile(user_id)[2] if status == 'succeeded' else None
                return respond('200 OK', {'status': status, 'confirmation_url': details.get('confirmation_url'),
                                         'ends_on': last_access_date(end).isoformat() if end else None})
            return respond('404 Not Found', {'error': 'Страница не найдена'})
        except LookupError:
            return respond('404 Not Found', {'error': 'Заказ не найден'})
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
    from app.payments.yookassa import YooKassaTestClient

    settings = test_settings(environment)
    if settings is None:
        raise ValueError('Test subscription mode is disabled')
    users, url, database_name = settings
    shop_id = environment.get('SUBSCRIPTION_YOOKASSA_TEST_SHOP_ID', '')
    secret = environment.get('SUBSCRIPTION_YOOKASSA_TEST_SECRET_KEY', '')
    if not shop_id or not secret:
        raise ValueError('Test YooKassa credentials are required for checkout')
    repository = SubscriptionRepository(connection_factory)
    repository.verify_test_database(database_name)
    owns_provider = provider is None
    if owns_provider:
        provider = YooKassaTestClient(shop_id, secret)
    try:
        provider.verify_test_store()
    except Exception:
        if owns_provider:
            provider.close()
        raise
    return MiniApp(repository=repository, payments=PaymentService(repository, provider),
                   bot_token=environment['BOT_TOKEN'], allowed_users=users, return_url=url)


if __name__ == '__main__':
    import argparse
    import os
    from wsgiref.simple_server import make_server
    parser = argparse.ArgumentParser(description='Local Mini App preview or explicit test checkout')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--test', action='store_true', help='Require .env.test, allowlist and test YooKassa')
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
        app = MiniApp(preview=True)
    try:
        with make_server('127.0.0.1', args.port, app) as server:
            mode = 'test checkout' if args.test else 'preview, payments disabled'
            print('Local Mini App: http://127.0.0.1:{}/ ({})'.format(args.port, mode), flush=True)
            server.serve_forever()
    finally:
        if args.test:
            app.payments.provider.close()
