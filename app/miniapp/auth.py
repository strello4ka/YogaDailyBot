"""Validate Telegram Mini App initData on the server, not initDataUnsafe."""

import hashlib
import hmac
import json
from urllib.parse import parse_qsl


def authenticate(init_data, bot_token, now_timestamp, allowed_users, *, max_age=3600):
    if not isinstance(init_data, str) or len(init_data) > 16384:
        raise ValueError('Invalid Telegram session')
    try:
        pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
        fields = dict(pairs)
        if len(fields) != len(pairs):
            raise ValueError('Duplicate fields')
        supplied_hash = fields.pop('hash')
        check_string = '\n'.join('{}={}'.format(k, v) for k, v in sorted(fields.items()))
        secret = hmac.new(b'WebAppData', bot_token.encode(), hashlib.sha256).digest()
        expected = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, supplied_hash):
            raise ValueError('Invalid signature')
        age = now_timestamp - int(fields['auth_date'])
        if age < -30 or age > max_age:
            raise ValueError('Expired Telegram session')
        user = json.loads(fields['user'])
        user_id = user['id']
        if type(user_id) is not int or (allowed_users is not None and user_id not in allowed_users):
            raise ValueError('Not a subscription tester')
        return user_id
    except (KeyError, TypeError, UnicodeError, ValueError):
        raise ValueError('Открой страницу заново через кнопку в тестовом боте') from None
