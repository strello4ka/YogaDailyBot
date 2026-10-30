"use strict";
const $ = id => document.getElementById(id);
const tg = window.Telegram?.WebApp;
// This switch selects a route only; the local server authenticates every request.
const testCheckout = new URLSearchParams(window.location.search).get('test') === '1';
const returnedOrder = new URLSearchParams(window.location.search).get('checkout_order');
function clearSavedOrder() {
  sessionStorage.removeItem('yoga-order');
  const url = new URL(window.location.href);
  url.searchParams.delete('checkout_order');
  window.history.replaceState(null, '', url.href);
}
const money = value => new Intl.NumberFormat('ru-RU', {maximumFractionDigits: 0}).format(value / 100) + ' ₽';
const tariffMonths = {month: 1, quarter: 3, half_year: 6, year: 12};
function monthlyPrice(tariff) {
  const months = tariffMonths[tariff.code];
  if (months === 1) return '';
  return `${money(tariff.final_price / months)} в месяц`;
}
let catalog = [], preview = false, orderId = null, poll = null, checking = false;
let confirmationUrl = '', replaceOpenOrder = false;
let checkEpoch = 0;
let initData = tg?.initData || sessionStorage.getItem('yoga-init-data') || '';
if (tg?.initData) sessionStorage.setItem('yoga-init-data', tg.initData);
tg?.ready();
tg?.expand();

async function api(path, body = {}) {
  const endpoint = testCheckout ? path.replace(/^\/api\//, '/test-api/') : path;
  const response = await fetch(endpoint, {method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({...body, init_data:initData}), signal:AbortSignal.timeout(12000)});
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(data.error || 'Не удалось выполнить запрос. Попробуй ещё раз.');
    error.status = response.status; throw error;
  }
  return data;
}
function error(message) { $('error').textContent = message; $('error').hidden = !message; }
const emailInput = $('email');
const emailField = $('email-field');
const emailError = $('email-error');
const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/u;
let emailTouched = false;
function validateEmail(showError = false) {
  const value = emailInput.value.trim();
  const valid = emailInput.checkValidity() && emailPattern.test(value);
  const invalid = showError && !valid;
  emailField.classList.toggle('invalid', invalid);
  emailInput.setAttribute('aria-invalid', String(invalid));
  emailError.textContent = invalid
    ? (value ? 'Проверь адрес e-mail, например name@example.com' : 'Укажи e-mail для чека') : '';
  emailError.hidden = !invalid;
  return valid;
}
emailInput.addEventListener('focus', () => {
  document.body.classList.add('editing-email');
  $('email-done').hidden = false;
});
emailInput.addEventListener('blur', () => {
  emailInput.value = emailInput.value.trim();
  document.body.classList.remove('editing-email');
  $('email-done').hidden = true;
  emailTouched = true;
  validateEmail(true);
});
emailInput.addEventListener('input', () => { if (emailTouched) validateEmail(true); });
emailInput.addEventListener('keydown', event => {
  if (event.key === 'Enter') { event.preventDefault(); emailInput.blur(); }
});
$('email-done').addEventListener('pointerdown', event => {
  event.preventDefault();
  emailInput.blur();
});
$('email-done').addEventListener('click', () => emailInput.blur());
document.addEventListener('pointerdown', event => {
  if (document.activeElement === emailInput && !emailField.contains(event.target)) emailInput.blur();
});
function selected() { return document.querySelector('input[name="tariff"]:checked')?.value; }
function updatePrice() {
  const tariff = catalog.find(t => t.code === selected());
  const pay = $('pay');
  pay.replaceChildren();
  if (!tariff) {
    pay.textContent = 'Выбери период';
  } else {
    pay.append(document.createTextNode(`Оплатить · ${money(tariff.final_price)}`));
    if (tariff.final_price < tariff.base_price) {
      const basePrice = document.createElement('span');
      basePrice.className = 'pay-base-price';
      basePrice.textContent = money(tariff.base_price);
      pay.append(basePrice);
    }
  }
  $('pay').disabled = preview || !tariff;
}
function status(title, text) {
  $('loading').hidden = true;
  $('checkout').hidden = true; $('payment-status').hidden = false;
  $('status-title').textContent = title; $('status-text').textContent = text;
}
function rememberConfirmation(value) {
  confirmationUrl = '';
  $('resume').hidden = true;
  $('resume').removeAttribute('href');
  if (!value) return false;
  try {
    const url = new URL(value);
    if (url.protocol !== 'https:') return false;
    confirmationUrl = url.href;
    $('resume').href = confirmationUrl;
    $('resume').hidden = false;
    return true;
  } catch (_) { return false; }
}
function openConfirmation(value) {
  if (!rememberConfirmation(value)) throw new Error('invalid-payment-url');
  window.location.assign(confirmationUrl);
}
function paymentErrorText(errorObject) {
  if (errorObject?.status && errorObject.message) return errorObject.message;
  return 'Не удалось связаться с сервером. Проверь интернет и попробуй ещё раз.';
}
async function checkPayment() {
  if (checking || !orderId) return;
  const epoch = checkEpoch;
  const checkedOrderId = orderId;
  $('check').hidden = true; $('back').hidden = false;
  checking = true; clearTimeout(poll);
  try {
    const data = await api(`/api/payments/${encodeURIComponent(orderId)}`);
    // The user may have returned to the tariffs while this request was running.
    // A stale response must not replace the tariff screen with the old order.
    if (epoch !== checkEpoch || checkedOrderId !== orderId) return;
    if (data.status === 'succeeded') {
      $('resume').hidden = true;
      const date = data.ends_on?.split('-').reverse().join('.') || '';
      status('Оплата принята 🧡', `Подписка действует по ${date} включительно.`);
      $('check').hidden = true; $('back').hidden = true; $('close').hidden = !tg?.initData;
      clearSavedOrder();
    } else if (data.status === 'canceled') {
      $('resume').hidden = true;
      status('Оплата отменена', 'Деньги не списаны. Ты можешь вернуться к тарифам и попробовать снова.');
      $('check').hidden = true; $('back').hidden = false;
      clearSavedOrder();
    } else {
      const canResume = rememberConfirmation(data.confirmation_url);
      status('Оплата пока не завершена', canResume
        ? 'Мы пока не получили подтверждение оплаты. Ты можешь продолжить оплату или вернуться к тарифам.'
        : 'Мы пока не получили подтверждение оплаты. Ты можешь вернуться к тарифам.');
      $('check').hidden = true; $('back').hidden = false;
      poll = setTimeout(checkPayment, 5000);
    }
  } catch (e) {
    if (epoch !== checkEpoch || checkedOrderId !== orderId) return;
    $('resume').hidden = true;
    if (e.status === 404) {
      clearSavedOrder(); orderId = null;
      $('back').hidden = false; $('check').hidden = true;
    } else {
      $('back').hidden = false; $('check').hidden = false;
    }
    status('Пока не удалось проверить оплату',
      'Повторно платить не нужно. ' + paymentErrorText(e));
  } finally { checking = false; }
}
$('payment-form').addEventListener('submit', async event => {
  event.preventDefault(); error('');
  emailTouched = true;
  if (!validateEmail(true)) { emailInput.focus(); return; }
  if (preview) return;
  $('pay').disabled = true;
  try {
    // Reuse after an unknown network outcome rather than create a new charge.
    orderId = orderId || crypto.randomUUID();
    sessionStorage.setItem('yoga-order', orderId);
    const tariff = catalog.find(t => t.code === selected());
    const data = await api('/api/payments', {order_id:orderId, tariff_code:selected(),
      final_price:tariff.final_price, email:$('email').value.trim(),
      replace_open_order:replaceOpenOrder});
    replaceOpenOrder = false;
    orderId = data.order_id; sessionStorage.setItem('yoga-order', orderId);
    if (data.confirmation_url) {
      openConfirmation(data.confirmation_url);
    } else { status('Проверяем оплату', 'Это может занять немного времени.'); await checkPayment(); }
  } catch (e) {
    if (e.status === 409) { clearSavedOrder(); window.location.reload(); return; }
    error(e.message); updatePrice();
  }
});
$('check').addEventListener('click', checkPayment);
$('resume').addEventListener('click', event => {
  if (!confirmationUrl) { event.preventDefault(); return; }
  event.preventDefault();
  window.location.assign(confirmationUrl);
});
$('reload').addEventListener('click', () => window.location.reload());
$('close').addEventListener('click', () => tg?.close());
$('back').addEventListener('click', event => {
  event.currentTarget.blur();
  checkEpoch += 1;
  clearTimeout(poll); poll = null; orderId = null; replaceOpenOrder = true; clearSavedOrder();
  $('payment-status').hidden = true; $('checkout').hidden = false;
  $('back').hidden = true; $('check').hidden = false; updatePrice();
});
async function load() {
  try {
    const data = await api('/api/session');
    catalog = data.tariffs; preview = data.preview;
    emailInput.value = data.email;
    $('period-note').textContent = data.note; $('period-note').hidden = !data.note;
    if (data.offer_ends_on) {
      const date = data.offer_ends_on.split('-').reverse().join('.');
      $('early-user-note').hidden = false;
      $('offer-ends').textContent = `Специальные цены действуют до ${date} включительно\nтолько на первую покупку`;
      $('offer-ends').hidden = false;
    }
    $('offer').href = data.offer_url;
    for (const [index, tariff] of catalog.entries()) {
      const label = document.createElement('label'); label.className = 'tariff';
      const input = document.createElement('input'); input.type = 'radio'; input.name = 'tariff';
      input.value = tariff.code; input.checked = index === 0; input.addEventListener('change', updatePrice);
      label.append(input);
      const rows = [['tariff-title', tariff.title], ['tariff-price', money(tariff.final_price)]];
      const monthly = monthlyPrice(tariff);
      if (monthly) rows.push(['tariff-monthly', monthly]);
      for (const [className, text] of rows) {
        const span = document.createElement('span'); span.className = className; span.textContent = text;
        if (className === 'tariff-price' && tariff.final_price < tariff.base_price) {
          const basePrice = document.createElement('span');
          basePrice.className = 'tariff-base-price';
          basePrice.textContent = money(tariff.base_price);
          span.append(basePrice);
        }
        label.append(span);
      }
      $('tariffs').append(label);
    }
    updatePrice();
    // The returned UUID selects an order, never authorizes or confirms a payment.
    // The server checks Telegram identity, ownership and the provider status.
    orderId = returnedOrder || data.order_id || sessionStorage.getItem('yoga-order');
    if (orderId && !preview) {
      await checkPayment();
    } else {
      $('loading').hidden = true;
      $('checkout').hidden = false;
    }
  } catch (e) {
    $('loading-text').textContent = 'Не удалось загрузить данные. ' + e.message;
    $('loading-text').hidden = false;
    $('reload').hidden = false;
  }
}
load();
