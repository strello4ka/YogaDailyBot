// Run with NODE_PATH pointing to the installed Playwright package directory.
// All API responses are mocked; this test never creates payments.
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright');

const staticDir = path.join(__dirname, '..', 'app', 'miniapp', 'static');
const files = {'/': ['index.html', 'text/html'], '/app.js': ['app.js', 'application/javascript'],
  '/styles.css': ['styles.css', 'text/css']};
const server = http.createServer((req, res) => {
  const file = files[new URL(req.url, 'http://localhost').pathname];
  if (!file) { res.writeHead(404).end(); return; }
  res.writeHead(200, {'Content-Type': file[1]});
  res.end(fs.readFileSync(path.join(staticDir, file[0])));
});
const order = '11111111-1111-4111-8111-111111111111';
const session = {tariffs: [{code:'month',title:'1 месяц',days:30,amount:35000}],
  email:'u@example.org',note:'',offer_url:'https://example.org',preview:false,order_id:null};

(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  let browser;
  try {
    browser = await chromium.launch({headless:true,
      ...(process.env.UI_TEST_BROWSER ? {channel:process.env.UI_TEST_BROWSER} : {})});
    for (const scenario of [
      {name:'fresh', checkout:true},
      {name:'returned success without storage', returned:true, status:'succeeded',title:'Оплата принята 🧡'},
      {name:'saved success', saved:true, status:'succeeded',title:'Оплата принята 🧡'},
      {name:'pending',returned:true,status:'pending',title:'Проверяем оплату'},
      {name:'canceled',returned:true,status:'canceled',title:'Оплата не завершена'},
      {name:'session failure',failed:true},
    ]) {
      const page = await browser.newPage({viewport:{width:390,height:844}});
      const errors = [];
      page.on('pageerror', e => errors.push(e.message));
      await page.addInitScript(({order,saved}) => {
        window.Telegram={WebApp:{initData:'mock',ready(){},expand(){},close(){}}};
        if(saved) sessionStorage.setItem('yoga-order',order);
        window.checkoutShown=false;
        new MutationObserver(() => {
          const checkout=document.getElementById('checkout');
          if(checkout && !checkout.hidden) window.checkoutShown=true;
        }).observe(document,{childList:true,subtree:true,attributes:true,attributeFilter:['hidden']});
      }, {order,saved:scenario.saved});
      await page.route('https://telegram.org/**', route => route.fulfill({body:''}));
      let releaseSession, releasePayment;
      const sessionGate = new Promise(resolve => releaseSession=resolve);
      const paymentGate = new Promise(resolve => releasePayment=resolve);
      await page.route('**/test-api/session', async route => {
        await sessionGate;
        await route.fulfill({status:scenario.failed ? 503 : 200,contentType:'application/json',
          body:JSON.stringify(scenario.failed ? {error:'Временно недоступно'} : session)});
      });
      await page.route('**/test-api/payments/*', async route => {
        assert.equal(new URL(route.request().url()).pathname.split('/').pop(),order);
        await paymentGate;
        await route.fulfill({contentType:'application/json',body:JSON.stringify({
          status:scenario.status,ends_on:'2026-12-31',
          confirmation_url:scenario.status==='pending' ? 'https://yookassa.ru/checkout' : null})});
      });
      await page.goto(`http://127.0.0.1:${server.address().port}/?test=1` +
        (scenario.returned ? `&checkout_order=${order}` : ''),{waitUntil:'domcontentloaded'});
      assert.equal(await page.locator('#checkout').isVisible(),false);
      assert.equal(await page.locator('#loading').isVisible(),true);
      releaseSession();
      if(scenario.checkout) {
        await page.locator('#checkout').waitFor({state:'visible'});
      } else if(scenario.failed) {
        await page.locator('#reload').waitFor({state:'visible'});
        assert.equal(await page.locator('#checkout').isVisible(),false);
        assert.equal(await page.evaluate(() => window.checkoutShown),false);
        if(scenario.status === 'pending') {
          assert.equal(await page.locator('#resume').isVisible(),true);
          assert.equal(await page.locator('#resume').getAttribute('href'),'https://yookassa.ru/checkout');
        }
      } else {
        await page.locator('#payment-status').waitFor({state:'visible'});
        assert.equal(await page.locator('#checkout').isVisible(),false);
        releasePayment();
        await page.waitForFunction(title => document.getElementById('status-title').textContent===title,
          scenario.title);
        assert.equal(await page.evaluate(() => window.checkoutShown),false);
        if(scenario.status !== 'pending') {
          assert.equal(await page.evaluate(() => new URL(location.href).searchParams.has('checkout_order')),false);
        }
        if(scenario.status === 'canceled') {
          await page.locator('#back').click();
          assert.equal(await page.locator('#checkout').isVisible(),true);
        }
      }
      assert.deepEqual(errors,[]);
      console.log('PASS',scenario.name);
      await page.close();
    }
  } finally {
    if(browser) await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(e => {console.error(e); process.exitCode=1;});
