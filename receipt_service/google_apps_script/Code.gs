function doPost(e) {
  try {
    const data = JSON.parse(e.postData.contents);
    const secret = PropertiesService.getScriptProperties().getProperty('RECEIPT_RELAY_SECRET');
    if (!secret) throw new Error('Relay secret is not configured');

    const timestamp = String(data.timestamp || '');
    const kind = String(data.kind || 'receipt');
    const requestId = String(data.requestId || '').toLowerCase();
    const recipient = String(data.recipient || '').trim();
    const receiptUrl = String(data.receiptUrl || '').trim();
    const subject = String(data.subject || '').trim();
    const body = String(data.body || '');
    const signature = String(data.signature || '').toLowerCase();
    if (!/^\d{10}$/.test(timestamp) ||
        Math.abs(Date.now() / 1000 - Number(timestamp)) > 300) throw new Error('Expired request');
    if (!/^[a-f0-9]{64}$/.test(requestId)) throw new Error('Invalid request ID');
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(recipient)) throw new Error('Invalid recipient');
    if (kind === 'receipt') {
      if (!receiptUrl.startsWith('https://lknpd.nalog.ru/api/v1/receipt/')) {
        throw new Error('Invalid receipt URL');
      }
    } else if (kind === 'alert') {
      if (!subject || subject.length > 150 || !body || body.length > 5000) {
        throw new Error('Invalid alert');
      }
    } else {
      throw new Error('Invalid message kind');
    }

    const message = (kind === 'receipt'
      ? [timestamp, requestId, recipient, receiptUrl]
      : [timestamp, requestId, recipient, subject, body]).join('\n');
    const expected = toHex_(Utilities.computeHmacSha256Signature(
      message, secret, Utilities.Charset.UTF_8));
    if (!constantTimeEqual_(signature, expected)) throw new Error('Invalid signature');

    const lock = LockService.getScriptLock();
    lock.waitLock(30000);
    try {
      const properties = PropertiesService.getScriptProperties();
      cleanupSentProperties_(properties);
      const sentKey = 'SENT_' + requestId;
      if (properties.getProperty(sentKey)) return json_({ok: true, duplicate: true});
      if (MailApp.getRemainingDailyQuota() < 1) throw new Error('Daily email quota exhausted');
      if (kind === 'receipt') {
        MailApp.sendEmail(recipient, 'Чек об оплате YogaDailyBot',
          'Спасибо за оплату. Ваш чек: ' + receiptUrl + '\n');
      } else {
        MailApp.sendEmail(recipient, subject, body);
      }
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

function cleanupSentProperties_(properties) {
  const now = Date.now();
  const lastCleanup = Date.parse(properties.getProperty('LAST_SENT_CLEANUP_AT') || '');
  if (Number.isFinite(lastCleanup) && now - lastCleanup < 24 * 60 * 60 * 1000) return;

  const cutoff = now - 30 * 24 * 60 * 60 * 1000;
  const values = properties.getProperties();
  Object.keys(values).forEach(function(key) {
    if (key.startsWith('SENT_') && Date.parse(values[key]) < cutoff) {
      properties.deleteProperty(key);
    }
  });
  properties.setProperty('LAST_SENT_CLEANUP_AT', new Date(now).toISOString());
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
