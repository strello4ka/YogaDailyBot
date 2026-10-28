from email.message import EmailMessage
import smtplib


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
