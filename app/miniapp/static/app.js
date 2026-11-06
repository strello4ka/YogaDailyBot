"use strict";
const $ = id => document.getElementById(id);
const tg = window.Telegram?.WebApp;
const launchParams = new URLSearchParams(window.location.search);
// This switch selects a route only; the local server authenticates every request.
const testCheckout = launchParams.get('test') === '1';
const browserPaymentReturn = launchParams.get('payment_return') === '1';
function clearSavedOrder() {
  sessionStorage.removeItem('yoga-order');
  const url = new URL(window.location.href);
  url.searchParams.delete('payment_return');
  window.history.replaceState(null, '', url.href);
}
const money = value => new Intl.NumberFormat('ru-RU', {maximumFractionDigits: 0}).format(value / 100) + ' ₽';
const tariffMonths = {month: 1, quarter: 3, half_year: 6, year: 12};
const PAYMENT_CREATION_TIMEOUT_MS = 30000;
function monthlyPrice(tariff) {
  const months = tariffMonths[tariff.code];
  if (months === 1) return '';
  return `${money(tariff.final_price / months)} в месяц`;
}
let catalog = [], preview = false, orderId = null, poll = null, checking = false;
let confirmationUrl = '', paymentCreationStartedAt = null;
let resumeLoaderTimeout = null;
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
  pay.classList.remove('is-busy');
  pay.removeAttribute('aria-disabled');
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
  $('pay').removeAttribute('aria-label');
}
function showButtonLoader(element, ariaLabel = 'Загрузка') {
  const loader = document.createElement('span');
  loader.className = 'button-loader';
  loader.setAttribute('aria-hidden', 'true');
  element.replaceChildren(loader);
  element.setAttribute('aria-label', ariaLabel);
  element.classList.add('is-busy');
  element.setAttribute('aria-disabled', 'true');
  if ('disabled' in element) element.disabled = true;
}
function showPayLoader() {
  const pay = $('pay');
  showButtonLoader(pay, 'Переходим к оплате');
  pay.disabled = true;
}
function creationWaitExpired() {
  return paymentCreationStartedAt !== null &&
    Date.now() - paymentCreationStartedAt >= PAYMENT_CREATION_TIMEOUT_MS;
}
function stopCreationWait() {
  clearTimeout(poll); poll = null; paymentCreationStartedAt = null;
  $('loading').hidden = true;
  $('payment-status').hidden = true;
  $('checkout').hidden = false;
  error('Упс… что-то пошло не так');
  updatePrice();
}
function status(title, text) {
  $('loading').hidden = true;
  $('checkout').hidden = true; $('payment-status').hidden = false;
  $('payment-status').classList.toggle('waiting', title === 'Ожидаем оплату');
  $('status-title').textContent = title;
  $('status-text').textContent = text || '';
  $('status-text').hidden = !text;
  $('resume').hidden = true;
  $('tariffs-button').hidden = true;
  $('close').hidden = true;
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
function restoreResumeButton() {
  clearTimeout(resumeLoaderTimeout); resumeLoaderTimeout = null;
  const resume = $('resume');
  resume.textContent = 'Вернуться к оплате';
  resume.classList.remove('is-busy');
  resume.removeAttribute('aria-disabled');
}
function openConfirmation(value) {
  if (!rememberConfirmation(value)) throw new Error('invalid-payment-url');
  const target = confirmationUrl;
  // The bank deep links used by SBP cannot reliably leave Telegram's WebView.
  // Open YooKassa in the system browser and keep this Mini App alive so that
  // the user can return to the authenticated payment status in Telegram.
  if (tg?.openLink) {
    clearTimeout(poll);
    if (orderId) poll = setTimeout(checkPayment, 5000);
    tg.openLink(target);
    return;
  }
  // Browser fallback for local preview and clients without the Mini App API.
  clearTimeout(poll);
  poll = setTimeout(() => {
    if (confirmationUrl === target) {
      window.stop();
      stopCreationWait();
    }
  }, PAYMENT_CREATION_TIMEOUT_MS);
  window.location.assign(target);
}
function pressedTransition(element, callback, timeoutCallback = null) {
  if (element.classList.contains('is-busy')) return;
  showButtonLoader(element, 'Загрузка');
  tg?.HapticFeedback?.impactOccurred?.('light');
  if (timeoutCallback) {
    clearTimeout(resumeLoaderTimeout);
    resumeLoaderTimeout = setTimeout(timeoutCallback, PAYMENT_CREATION_TIMEOUT_MS);
  }
  window.setTimeout(callback, 110);
}
async function checkPayment() {
  if (checking || !orderId) return;
  checking = true; clearTimeout(poll);
  try {
    const data = await api(`/api/payments/${encodeURIComponent(orderId)}`);
    if (data.status === 'succeeded') {
      paymentCreationStartedAt = null;
      $('resume').hidden = true;
      const date = data.ends_on?.split('-').reverse().join('.') || '';
      status('Оплата принята 🧡', `Подписка действует по ${date} включительно.`);
      $('close').hidden = !tg?.initData;
      clearSavedOrder();
    } else if (data.status === 'canceled') {
      paymentCreationStartedAt = null;
      clearTimeout(poll); poll = null; clearSavedOrder(); orderId = null;
      confirmationUrl = '';
      status('❌ Оплата не прошла', 'Попробуй ещё раз');
      $('tariffs-button').hidden = false;
    } else if (data.status === 'created') {
      if (paymentCreationStartedAt === null) paymentCreationStartedAt = Date.now();
      if (creationWaitExpired()) { stopCreationWait(); return; }
      $('loading').hidden = true;
      $('payment-status').hidden = true;
      $('checkout').hidden = false;
      showPayLoader();
      poll = setTimeout(checkPayment, 2000);
    } else {
      const canResume = rememberConfirmation(data.confirmation_url);
      if (canResume) paymentCreationStartedAt = null;
      else {
        if (paymentCreationStartedAt === null) paymentCreationStartedAt = Date.now();
        if (creationWaitExpired()) { stopCreationWait(); return; }
      }
      status('Ожидаем оплату', '');
      if (canResume) {
        restoreResumeButton();
        $('resume').hidden = false;
      }
      poll = setTimeout(checkPayment, 5000);
    }
  } catch (e) {
    if (e.status === 404) {
      clearSavedOrder(); orderId = null;
      confirmationUrl = '';
      $('payment-status').hidden = true;
      $('checkout').hidden = false;
      updatePrice();
    } else {
      if (!confirmationUrl && $('payment-status').hidden) {
        if (creationWaitExpired()) {
          stopCreationWait();
          return;
        }
        $('loading').hidden = true;
        $('checkout').hidden = false;
        showPayLoader();
      } else {
        if (!confirmationUrl && paymentCreationStartedAt === null) {
          paymentCreationStartedAt = Date.now();
        }
        if (!confirmationUrl && creationWaitExpired()) {
          stopCreationWait();
          return;
        }
        const canResume = rememberConfirmation(confirmationUrl);
        status('Ожидаем оплату', '');
        if (canResume) {
          restoreResumeButton();
          $('resume').hidden = false;
        }
      }
      poll = setTimeout(checkPayment, 5000);
    }
  } finally { checking = false; }
}
$('payment-form').addEventListener('submit', async event => {
  event.preventDefault(); error('');
  emailTouched = true;
  if (!validateEmail(true)) { emailInput.focus(); return; }
  if (preview) return;
  paymentCreationStartedAt = Date.now();
  showPayLoader();
  try {
    // Reuse after an unknown network outcome rather than create a new charge.
    orderId = orderId || crypto.randomUUID();
    sessionStorage.setItem('yoga-order', orderId);
    const tariff = catalog.find(t => t.code === selected());
    const data = await api('/api/payments', {order_id:orderId, tariff_code:selected(),
      final_price:tariff.final_price, email:$('email').value.trim()});
    orderId = data.order_id; sessionStorage.setItem('yoga-order', orderId);
    if (data.confirmation_url) {
      openConfirmation(data.confirmation_url);
    } else {
      await checkPayment();
    }
  } catch (e) {
    if (e.status === 409) { clearSavedOrder(); window.location.reload(); return; }
    paymentCreationStartedAt = null;
    error(e.message); updatePrice();
  }
});
$('resume').addEventListener('click', event => {
  if (!confirmationUrl) { event.preventDefault(); return; }
  event.preventDefault();
  const target = confirmationUrl;
  pressedTransition(event.currentTarget, () => openConfirmation(target), () => {
    restoreResumeButton();
  });
});
$('tariffs-button').addEventListener('click', () => {
  $('payment-status').hidden = true;
  $('checkout').hidden = false;
  updatePrice();
});
$('reload').addEventListener('click', () => {
  if ($('reload').dataset.action === 'close') tg?.close();
  else pressedTransition($('reload'), () => window.location.reload());
});
$('close').addEventListener('click', () => tg?.close());
async function load() {
  // The YooKassa return opens in an ordinary browser without Telegram auth.
  // It has one deliberately static state and must not call any API.
  if (browserPaymentReturn) {
    $('loading-title').textContent = 'Ожидаем оплату… Вернись в YogaDailyBot.';
    $('loading-title').classList.add('screen-state-title');
    $('loading-text').hidden = true;
    $('reload').hidden = true;
    return;
  }
  try {
    const data = await api('/api/session');
    catalog = data.tariffs; preview = data.preview;
    emailInput.value = data.email;
    $('period-note').textContent = data.note; $('period-note').hidden = !data.note;
    if (data.offer_ends_on) {
      const date = data.offer_ends_on.split('-').reverse().join('.');
      $('offer-ends').textContent = `Скидки для своих действуют до ${date} включительно\nтолько на первую покупку`;
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
      // Keep every price on the same baseline even when a tariff has no
      // secondary "per month" caption.
      rows.push(['tariff-monthly', monthly || '\u00a0']);
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
    orderId = data.order_id || sessionStorage.getItem('yoga-order');
    if (orderId && !preview) {
      await checkPayment();
    } else {
      $('loading').hidden = true;
      $('checkout').hidden = false;
    }
  } catch (e) {
    // Do not introduce a separate technical-error screen. If the checkout
    // cannot be initialized, use the single agreed unavailable-session state.
    $('loading-title').textContent = 'Не удалось открыть тарифы';
    $('loading-title').classList.remove('screen-state-title');
    $('loading-text').textContent =
      'Открой тарифы заново через Меню → Подписка → Посмотреть тарифы.';
    $('reload').textContent = 'Закрыть';
    $('reload').dataset.action = 'close';
    $('loading-text').hidden = false;
    $('reload').hidden = false;
  }
}
load();
