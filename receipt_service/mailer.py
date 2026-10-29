from email.message import EmailMessage
import hashlib
import hmac
import smtplib
import time

import httpx


class ReceiptMailer:
    def __init__(self, host, port, user, password, sender):
        self.host, self.port = host, port
        self.user, self.password, self.sender = user, password, sender

    def send(self, recipient, receipt_url):
        message = EmailMessage()
        message['Subject'] = 'Чек об оплате YogaDailyBot'
        message['From'] = self.sender
        message['To'] = recipient
        message.set_content('Спасибо за оплату. Ваш чек: {}\n'.format(receipt_url))
        with smtplib.SMTP_SSL(self.host, self.port, timeout=30) as smtp:
            smtp.login(self.user, self.password)
            smtp.send_message(message)

    def send_alert(self, recipient, subject, body):
        message = EmailMessage()
        message['Subject'] = subject
        message['From'] = self.sender
        message['To'] = recipient
        message.set_content(body)
        with smtplib.SMTP_SSL(self.host, self.port, timeout=30) as smtp:
            smtp.login(self.user, self.password)
            smtp.send_message(message)


class AppsScriptMailer:
    def __init__(self, url, secret, transport=None):
        self.url, self.secret = url, secret
        self.client = httpx.Client(timeout=30, transport=transport, follow_redirects=True)

    def send(self, recipient, receipt_url):
        timestamp = str(int(time.time()))
        request_id = hashlib.sha256(f'{recipient}\n{receipt_url}'.encode()).hexdigest()
        signed = '\n'.join((timestamp, request_id, recipient, receipt_url))
        signature = hmac.new(self.secret.encode(), signed.encode(), hashlib.sha256).hexdigest()
        response = self.client.post(self.url, json={
            'timestamp': timestamp,
            'requestId': request_id,
            'recipient': recipient,
            'receiptUrl': receipt_url,
            'signature': signature,
        })
        response.raise_for_status()
        result = response.json()
        if result.get('ok') is not True:
            raise RuntimeError('Apps Script email relay rejected the request')

    def send_alert(self, recipient, subject, body):
        timestamp = str(int(time.time()))
        request_id = hashlib.sha256(f'{recipient}\n{subject}\n{body}'.encode()).hexdigest()
        signed = '\n'.join((timestamp, request_id, recipient, subject, body))
        signature = hmac.new(self.secret.encode(), signed.encode(), hashlib.sha256).hexdigest()
        response = self.client.post(self.url, json={
            'kind': 'alert',
            'timestamp': timestamp,
            'requestId': request_id,
            'recipient': recipient,
            'subject': subject,
            'body': body,
            'signature': signature,
        })
        response.raise_for_status()
        if response.json().get('ok') is not True:
            raise RuntimeError('Apps Script alert relay rejected the request')
