"""Public static preview with a bounded proxy to an isolated local test backend."""
import json
from urllib.parse import urlsplit
from uuid import UUID

import httpx


class TestGateway:
    def __init__(self, preview, backend_url='', *, transport=None):
        self.preview = preview
        self.backend_url = backend_url.rstrip('/')
        self.transport = transport
        if backend_url:
            url = urlsplit(backend_url)
            if (url.scheme != 'https' or not url.hostname or url.username or url.password
                    or url.path not in ('', '/') or url.query or url.fragment):
                raise ValueError('Test backend must be an HTTPS origin')

    def __call__(self, environ, start_response):
        path = environ.get('PATH_INFO', '')
        if not path.startswith('/test-api/'):
            return self.preview(environ, start_response)

        def respond(status, payload):
            body = json.dumps(payload, ensure_ascii=False).encode()
            start_response(status, [('Content-Type', 'application/json; charset=utf-8'),
                                    ('Cache-Control', 'no-store'),
                                    ('X-Content-Type-Options', 'nosniff'),
                                    ('Content-Length', str(len(body)))])
            return [body]

        target = path.removeprefix('/test-api/')
        valid = target in ('session', 'payments')
        if target.startswith('payments/'):
            try:
                valid = target == 'payments/' + str(UUID(target[len('payments/'):]))
            except ValueError:
                valid = False
        if not valid or environ.get('REQUEST_METHOD') != 'POST':
            return respond('404 Not Found', {'error': 'Страница не найдена'})
        try:
            size = int(environ.get('CONTENT_LENGTH') or '0')
        except ValueError:
            size = 0
        if not 0 < size <= 20000:
            return respond('413 Payload Too Large', {'error': 'Некорректный запрос'})
        if not environ.get('CONTENT_TYPE', '').startswith('application/json'):
            return respond('415 Unsupported Media Type', {'error': 'Ожидается JSON'})
        if not self.backend_url:
            return respond('503 Service Unavailable', {'error': 'Тестовая оплата временно недоступна'})
        try:
            # Never forward cookies, authorization, query strings or caller-controlled hosts.
            with httpx.Client(timeout=15, follow_redirects=False, transport=self.transport) as client:
                with client.stream('POST', self.backend_url + '/api/' + target,
                                   content=environ['wsgi.input'].read(size),
                                   headers={'Content-Type': 'application/json'}) as response:
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > 100000:
                            raise ValueError('Oversized backend response')
                    payload = json.loads(body)
                    if not isinstance(payload, dict) or response.status_code not in (200, 400, 401, 403, 404, 413, 415, 503):
                        raise ValueError('Invalid backend response')
                    status = '{} {}'.format(response.status_code, response.reason_phrase)
            return respond(status, payload)
        except (httpx.HTTPError, ValueError):
            return respond('503 Service Unavailable', {'error': 'Тестовая оплата временно недоступна. Попробуй позже.'})
