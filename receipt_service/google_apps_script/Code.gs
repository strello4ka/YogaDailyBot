function doPost(e) {
  try {
    const data = JSON.parse(e.postData.contents);
    const secret = PropertiesService.getScriptProperties().getProperty('RECEIPT_RELAY_SECRET');
    if (!secret) throw new Error('Relay secret is not configured');

    const timestamp = String(data.timestamp || '');
    const requestId = String(data.requestId || '').toLowerCase();
    const recipient = String(data.recipient || '').trim();
    const receiptUrl = String(data.receiptUrl || '').trim();
    const signature = String(data.signature || '').toLowerCase();
    if (Math.abs(Date.now() / 1000 - Number(timestamp)) > 300) throw new Error('Expired request');
    if (!/^[a-f0-9]{64}$/.test(requestId)) throw new Error('Invalid request ID');
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(recipient)) throw new Error('Invalid recipient');
    if (!receiptUrl.startsWith('https://lknpd.nalog.ru/api/v1/receipt/')) {
      throw new Error('Invalid receipt URL');
    }

    const message = [timestamp, requestId, recipient, receiptUrl].join('\n');
    const expected = toHex_(Utilities.computeHmacSha256Signature(
      message, secret, Utilities.Charset.UTF_8));
    if (!constantTimeEqual_(signature, expected)) throw new Error('Invalid signature');

    const lock = LockService.getScriptLock();
    lock.waitLock(30000);
    try {
      const properties = PropertiesService.getScriptProperties();
      const sentKey = 'SENT_' + requestId;
      if (properties.getProperty(sentKey)) return json_({ok: true, duplicate: true});
      MailApp.sendEmail(recipient, 'Чек об оплате YogaDailyBot',
        'Спасибо за оплату. Ваш чек: ' + receiptUrl + '\n');
      properties.setProperty(sentKey, new Date().toISOString());
      return json_({ok: true});
    } finally {
      lock.releaseLock();
    }
  } catch (error) {
    console.error(error);
    return json_({ok: false});
  }
}

function toHex_(bytes) {
  return bytes.map(function(value) {
    const byte = value < 0 ? value + 256 : value;
    return ('0' + byte.toString(16)).slice(-2);
  }).join('');
}

function constantTimeEqual_(left, right) {
  if (left.length !== right.length) return false;
  let result = 0;
  for (let index = 0; index < left.length; index++) {
    result |= left.charCodeAt(index) ^ right.charCodeAt(index);
  }
  return result === 0;
}

function json_(value) {
  return ContentService.createTextOutput(JSON.stringify(value))
    .setMimeType(ContentService.MimeType.JSON);
}
