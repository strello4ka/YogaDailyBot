"""Server notifications work without a Mini App or a Telegram initData session."""
from dataclasses import replace
from datetime import datetime
from io import BytesIO
import json
import unittest
from unittest.mock import Mock, MagicMock
from uuid import uuid4

import httpx

from app.payments.service import PaymentService, new_order
from app.payments.webhook import handle_notification
from app.miniapp.server import MiniApp
from app.miniapp.gateway import TestGateway
from app.subscription.tariff import MOSCOW
from data.subscription_repository import SubscriptionRepository

NOW = datetime(2026,10,20,18,tzinfo=MOSCOW)


class WebhookTest(unittest.TestCase):
    def setUp(self):
        self.order = replace(new_order(uuid4(),10,'month','u@example.org',NOW),
                             provider_payment_id=str(uuid4()))
        self.repo = Mock()
        self.repo.webhook_order.return_value = self.order
        self.repo.get_order.return_value = self.order
        self.repo.grant_order.return_value = True
        self.provider = Mock(expected_test=False)
        self.payment = dict(id=self.order.provider_payment_id,test=False,
            metadata={'order_id':self.order.order_id},status='succeeded',paid=True,
            amount={'value':'350.00','currency':'RUB'})
        self.provider.get_payment.return_value = self.payment
        self.service = PaymentService(self.repo,self.provider)
        self.event = dict(type='notification',event='payment.succeeded',object=dict(self.payment))

    def test_no_browser_required_and_provider_is_source_of_truth(self):
        self.event['object']['amount']={'value':'1.00','currency':'USD'}
        self.assertEqual(handle_notification(self.event,self.service,NOW),'succeeded')
        self.provider.get_payment.assert_called_once_with(self.order.provider_payment_id)
        self.repo.grant_order.assert_called_once_with(self.order,NOW)
        self.repo.signal_payment.assert_called_once_with(10)
        self.provider.create_payment.assert_not_called()

    def test_forged_success_does_not_grant_pending_payment(self):
        self.provider.get_payment.return_value=dict(self.payment,status='pending',paid=False)
        with self.assertRaises(RuntimeError):
            handle_notification(self.event,self.service,NOW)
        self.repo.grant_order.assert_not_called()
        self.repo.signal_payment.assert_not_called()

    def test_wrong_mode_amount_metadata_and_payment_id_fail_closed(self):
        for change in ({'test':True},{'id':str(uuid4())},{'metadata':{}},
                       {'amount':{'value':'1','currency':'RUB'}},{'paid':False}):
            self.provider.get_payment.return_value=dict(self.payment,**change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                handle_notification(self.event,self.service,NOW)
        self.repo.grant_order.assert_not_called()

    def test_duplicate_uses_existing_atomic_grant_and_wakes_delivery_again(self):
        self.repo.grant_order.side_effect=[True,False]
        for _ in range(2):
            self.assertEqual(handle_notification(self.event,self.service,NOW),'succeeded')
        self.assertEqual(self.repo.grant_order.call_count,2)
        self.assertEqual(self.repo.signal_payment.call_count,2)

    def test_cancellation_wakes_onboarding_without_access_grant(self):
        self.event['event']='payment.canceled'
        self.provider.get_payment.return_value=dict(self.payment,status='canceled',paid=False)
        self.assertEqual(handle_notification(self.event,self.service,NOW),'canceled')
        self.repo.cancel_order.assert_called_once()
        self.repo.grant_order.assert_not_called()
        self.repo.signal_payment.assert_called_once_with(10)

    def test_unknown_order_and_disallowed_user_are_ignored(self):
        self.assertEqual(handle_notification(self.event,self.service,NOW,{11}),'ignored')
        self.repo.webhook_order.return_value=None
        self.assertEqual(handle_notification(self.event,self.service,NOW),'ignored')
        self.provider.get_payment.assert_not_called()

    def test_race_before_payment_attachment_requests_retry_without_creating_payment(self):
        self.repo.webhook_order.return_value=replace(self.order,provider_payment_id=None)
        with self.assertRaises(RuntimeError):
            handle_notification(self.event,self.service,NOW)
        self.provider.create_payment.assert_not_called()
        self.provider.get_payment.assert_not_called()

    def test_reordered_event_uses_latest_status(self):
        self.event['event']='payment.canceled'
        self.assertEqual(handle_notification(self.event,self.service,NOW),'succeeded')
        self.repo.cancel_order.assert_not_called()

    def test_wakeup_failure_keeps_verified_durable_payment(self):
        self.repo.grant_order.return_value=False
        self.repo.signal_payment.side_effect=RuntimeError('offline')
        with self.assertLogs('app.payments.service',level='WARNING'):
            self.assertEqual(handle_notification(self.event,self.service,NOW),'succeeded')

    def request(self,app,data):
        body=json.dumps(data).encode()
        result=[]
        response=b''.join(app({'PATH_INFO':'/test-api/yookassa/webhook','REQUEST_METHOD':'POST',
            'CONTENT_TYPE':'application/json','CONTENT_LENGTH':str(len(body)),
            'wsgi.input':BytesIO(body)},lambda status,headers:result.append(status)))
        return result[0],response

    def gateway(self):
        backend=MiniApp(repository=self.repo,payments=self.service,allowed_users=None,clock=lambda:NOW)
        def transport(request):
            self.assertEqual(str(request.url),'https://backend.example/api/yookassa/webhook')
            response=[]
            body=b''.join(backend({'PATH_INFO':'/api/yookassa/webhook','REQUEST_METHOD':'POST',
                'CONTENT_TYPE':'application/json','CONTENT_LENGTH':str(len(request.content)),
                'wsgi.input':BytesIO(request.content)},lambda status,headers:response.append(status)))
            return httpx.Response(int(response[0].split()[0]),content=body)
        return TestGateway(MiniApp(preview=True),'https://backend.example',
                           transport=httpx.MockTransport(transport))

    def test_public_gateway_to_backend_without_telegram_auth(self):
        status,_=self.request(self.gateway(),self.event)
        self.assertEqual(status,'200 OK')
        self.repo.grant_order.assert_called_once()

    def test_transient_provider_error_is_503_for_retry(self):
        self.provider.get_payment.side_effect=httpx.ConnectError('offline')
        status,_=self.request(self.gateway(),self.event)
        self.assertEqual(status,'503 Service Unavailable')
        self.repo.grant_order.assert_not_called()

    def test_missing_tunnel_is_not_acknowledged(self):
        status,_=self.request(TestGateway(MiniApp(preview=True)),self.event)
        self.assertEqual(status,'503 Service Unavailable')

    def test_scope_is_bound_in_webhook_lookup(self):
        connection=MagicMock()
        cursor=connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value=None
        repo=SubscriptionRepository(Mock(return_value=connection),payment_scope='live:1495040')
        repo.webhook_order(self.order.provider_payment_id,self.order.order_id)
        sql,params=cursor.execute.call_args.args
        self.assertIn('payment_scope=%s',sql)
        self.assertEqual(params[-1],'live:1495040')
