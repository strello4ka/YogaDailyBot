"use strict";
const $ = id => document.getElementById(id);
const tg = window.Telegram?.WebApp;
// This switch selects a route only; the local server authenticates every request.
const testCheckout = new URLSearchParams(window.location.search).get('test') === '1';
const money = value => new Intl.NumberFormat('ru-RU', {maximumFractionDigits: 0}).format(value / 100) + ' ₽';
const tariffMonths = {month: 1, quarter: 3, half_year: 6, year: 12};
function monthlyPrice(tariff) {
  const months = tariffMonths[tariff.code];
  if (months === 1) return 'в месяц';
  return `${money(tariff.amount / months)} в месяц`;
}
let catalog = [], preview = false, orderId = null, poll = null, checking = false;
let initData = tg?.initData || sessionStorage.getItem('yoga-init-data') || '';
if (tg?.initData) sessionStorage.setItem('yoga-init-data', tg.initData);
tg?.ready();
tg?.expand();

async function api(path, body = {}) {
  const endpoint = testCheckout ? path.replace(/^\/api\//, '/test-api/') : path;
  const response = await fetch(endpoint, {method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({...body, init_data:initData}), signal:AbortSignal.timeout(20000)});
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
  $('pay').textContent = tariff ? `Оплатить · ${money(tariff.amount)}` : 'Выбери период';
  $('pay').disabled = preview || !tariff;
}
function status(title, text) {
  $('checkout').hidden = true; $('payment-status').hidden = false;
  $('status-title').textContent = title; $('status-text').textContent = text;
}
async function checkPayment() {
  if (checking || !orderId) return;
  checking = true; $('check').disabled = true; clearTimeout(poll);
  try {
    const data = await api(`/api/payments/${encodeURIComponent(orderId)}`);
    $('resume').hidden = true;
    if (data.status === 'succeeded') {
      const date = data.ends_on?.split('-').reverse().join('.') || '';
      status('Оплата принята 🧡', `Подписка действует по ${date} включительно.`);
      $('check').hidden = true; $('close').hidden = !tg?.initData;
      sessionStorage.removeItem('yoga-order');
    } else if (data.status === 'canceled') {
      status('Оплата не завершена', 'Попробуй ещё раз или выбери другой способ оплаты.');
      $('check').hidden = true; $('back').hidden = false;
      sessionStorage.removeItem('yoga-order');
    } else {
      status('Проверяем оплату', 'Если ты уже оплатил, повторно платить не нужно.');
      if (data.confirmation_url) {
        const url = new URL(data.confirmation_url);
        if (url.protocol === 'https:') { $('resume').href = url.href; $('resume').hidden = false; }
      }
      poll = setTimeout(checkPayment, 5000);
    }
  } catch (e) {
    if (e.status === 404) {
      sessionStorage.removeItem('yoga-order'); orderId = null;
      $('back').hidden = false; $('check').hidden = true;
    }
    status('Пока не удалось проверить оплату', 'Повторно платить не нужно. ' + e.message);
  } finally { checking = false; $('check').disabled = false; }
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
    const data = await api('/api/payments', {order_id:orderId, tariff_code:selected(), email:$('email').value.trim()});
    orderId = data.order_id; sessionStorage.setItem('yoga-order', orderId);
    if (data.confirmation_url) {
      const url = new URL(data.confirmation_url);
      if (url.protocol !== 'https:') throw new Error('Некорректная ссылка оплаты');
      window.location.assign(url.href);
    } else { status('Проверяем оплату', 'Это может занять немного времени.'); await checkPayment(); }
  } catch (e) { error(e.message); updatePrice(); }
});
$('check').addEventListener('click', checkPayment);
$('close').addEventListener('click', () => tg?.close());
$('back').addEventListener('click', () => {
  clearTimeout(poll); orderId = null;
  $('payment-status').hidden = true; $('checkout').hidden = false;
  $('back').hidden = true; $('check').hidden = false; updatePrice();
});
async function load() {
  try {
    const data = await api('/api/session');
    catalog = data.tariffs; preview = data.preview;
    emailInput.value = data.email;
    $('period-note').textContent = data.note; $('period-note').hidden = !data.note;
    $('offer').href = data.offer_url;
    for (const [index, tariff] of catalog.entries()) {
      const label = document.createElement('label'); label.className = 'tariff';
      const input = document.createElement('input'); input.type = 'radio'; input.name = 'tariff';
      input.value = tariff.code; input.checked = index === 0; input.addEventListener('change', updatePrice);
      label.append(input);
      for (const [className, text] of [['tariff-title',tariff.title], ['tariff-price',money(tariff.amount)], ['tariff-monthly',monthlyPrice(tariff)]]) {
        const span = document.createElement('span'); span.className = className; span.textContent = text; label.append(span);
      }
      $('tariffs').append(label);
    }
    updatePrice();
    orderId = data.order_id || sessionStorage.getItem('yoga-order');
    if (orderId && !preview) await checkPayment();
  } catch (e) { error(e.message); }
}
load();
