import hashlib
import hmac
import json
from unittest.mock import patch
import unittest

import httpx

from receipt_service.mailer import AppsScriptMailer


class AppsScriptMailerTest(unittest.TestCase):
    def test_sends_signed_https_request(self):
        captured = {}

        def handler(request):
            captured.update(json.loads(request.content))
            return httpx.Response(200, json={'ok': True})

        mailer = AppsScriptMailer(
            'https://script.google.com/macros/s/example/exec', 'relay-secret',
            transport=httpx.MockTransport(handler))
        with patch('receipt_service.mailer.time.time', return_value=1234567890):
            mailer.send('buyer@example.com', 'https://lknpd.nalog.ru/api/v1/receipt/1/2/print')

        request_id = hashlib.sha256(
            b'buyer@example.com\nhttps://lknpd.nalog.ru/api/v1/receipt/1/2/print').hexdigest()
        signed = ('1234567890\n' + request_id
                  + '\nbuyer@example.com\nhttps://lknpd.nalog.ru/api/v1/receipt/1/2/print')
        expected = hmac.new(b'relay-secret', signed.encode(), hashlib.sha256).hexdigest()
        self.assertEqual(captured['signature'], expected)
        self.assertEqual(captured['timestamp'], '1234567890')
        self.assertEqual(captured['requestId'], request_id)

    def test_rejects_negative_relay_response(self):
        transport = httpx.MockTransport(lambda request: httpx.Response(200, json={'ok': False}))
        mailer = AppsScriptMailer('https://script.google.com/example', 'secret', transport=transport)
        with self.assertRaises(RuntimeError):
            mailer.send('buyer@example.com', 'https://example.com/receipt')

    def test_sends_signed_alert(self):
        captured = {}
        transport = httpx.MockTransport(lambda request: (
            captured.update(json.loads(request.content)) or httpx.Response(200, json={'ok': True})))
        mailer = AppsScriptMailer('https://script.google.com/example', 'secret', transport=transport)
        with patch('receipt_service.mailer.time.time', return_value=1234567890):
            mailer.send_alert('owner@example.com', 'Проверка', 'Нужна ручная проверка')

        signed = ('1234567890\n' + captured['requestId']
                  + '\nowner@example.com\nПроверка\nНужна ручная проверка')
        self.assertEqual(captured['kind'], 'alert')
        self.assertEqual(captured['signature'],
                         hmac.new(b'secret', signed.encode(), hashlib.sha256).hexdigest())


if __name__ == '__main__':
    unittest.main()
