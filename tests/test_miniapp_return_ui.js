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
const session = {tariffs: [{code:'month',title:'30 дней',days:30,amount:35000,
  base_price:35000,final_price:35000}],
  email:'u@example.org',note:'',offer_url:'https://example.org',preview:false,order_id:null};

(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  let browser;
  try {
    browser = await chromium.launch({headless:true,
      ...(process.env.UI_TEST_BROWSER ? {channel:process.env.UI_TEST_BROWSER} : {})});
    for (const scenario of [
      {name:'fresh', checkout:true},
      {name:'saved success', saved:true, status:'succeeded',title:'Оплата принята 🧡'},
      {name:'pending',saved:true,status:'pending',title:'Ожидаем оплату'},
      {name:'payment status failure',saved:true,paymentFailed:true,title:'Ожидаем оплату'},
      {name:'canceled stays visible in current session',saved:true,status:'canceled',title:'❌ Оплата не прошла'},
      {name:'invalid session',failed:true,statusCode:401},
      {name:'return without Telegram session',failed:true,statusCode:401,browserReturned:true},
      {name:'server failure',failed:true,statusCode:503},
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
        await route.fulfill({status:scenario.failed ? scenario.statusCode : 200,contentType:'application/json',
          body:JSON.stringify(scenario.failed ? {error:'Временно недоступно'} : session)});
      });
      await page.route('**/test-api/payments/*', async route => {
        assert.equal(new URL(route.request().url()).pathname.split('/').pop(),order);
        await paymentGate;
        await route.fulfill({status:scenario.paymentFailed ? 503 : 200,contentType:'application/json',
          body:JSON.stringify(scenario.paymentFailed ? {error:'Временно недоступно'} : {
            status:scenario.status,ends_on:'2026-12-31',
            confirmation_url:scenario.status==='pending' ? 'https://yookassa.ru/checkout' : null})});
      });
      await page.goto(`http://127.0.0.1:${server.address().port}/?test=1` +
        (scenario.browserReturned ? '&payment_return=1' : ''),
        {waitUntil:'domcontentloaded'});
      assert.equal(await page.locator('#checkout').isVisible(),false);
      assert.equal(await page.locator('#loading').isVisible(),true);
      const loadingStyle = await page.locator('#loading-title').evaluate(element => {
        const style = getComputedStyle(element);
        return {fontSize:style.fontSize,fontWeight:style.fontWeight};
      });
      assert.deepEqual(loadingStyle,{fontSize:'18px',fontWeight:'400'});
      if (!scenario.browserReturned) releaseSession();
      if (scenario.browserReturned) {
        assert.equal(await page.locator('#loading-title').textContent(),
          'Ожидаем оплату… Вернись в YogaDailyBot.');
        assert.equal(await page.locator('#loading-text').isVisible(),false);
        assert.equal(await page.locator('#reload').isVisible(),false);
        assert.equal(await page.locator('#checkout').isVisible(),false);
        assert.deepEqual(errors,[]);
        console.log('PASS',scenario.name);
        await page.close();
        continue;
      }
      if(scenario.checkout) {
        await page.locator('#checkout').waitFor({state:'visible'});
      } else if(scenario.failed) {
        await page.locator('#reload').waitFor({state:'visible'});
        assert.equal(await page.locator('#checkout').isVisible(),false);
        assert.equal(await page.evaluate(() => window.checkoutShown),false);
        assert.equal(await page.locator('#loading-title').textContent(),'Не удалось открыть тарифы');
        assert.equal(await page.locator('#loading-text').textContent(),
          'Открой тарифы заново через Меню → Подписка → Посмотреть тарифы.');
        assert.equal(await page.locator('#reload').textContent(),'Закрыть');
      } else {
        releasePayment();
        if(scenario.status === 'canceled') {
          await page.locator('#payment-status').waitFor({state:'visible'});
          assert.equal(await page.locator('#checkout').isVisible(),false);
          assert.equal(await page.locator('#status-title').textContent(),'❌ Оплата не прошла');
          assert.equal(await page.locator('#status-text').textContent(),'Попробуй ещё раз');
          assert.equal(await page.locator('#tariffs-button').textContent(),'Посмотреть тарифы');
          assert.equal(await page.locator('#tariffs-button').isVisible(),true);
          assert.equal(await page.evaluate(() => sessionStorage.getItem('yoga-order')),null);
          await page.locator('#tariffs-button').click();
          await page.locator('#checkout').waitFor({state:'visible'});
          assert.deepEqual(errors,[]);
          console.log('PASS',scenario.name);
          await page.close();
          continue;
        }
        await page.locator('#payment-status').waitFor({state:'visible'});
        assert.equal(await page.locator('#checkout').isVisible(),false);
        await page.waitForFunction(title => document.getElementById('status-title').textContent===title,
          scenario.title);
        assert.equal(await page.evaluate(() => window.checkoutShown),false);
        if(scenario.status === 'pending') {
          assert.equal(await page.locator('#resume').isVisible(),true);
          assert.equal(await page.locator('#resume').textContent(),'Вернуться к оплате');
          assert.equal(await page.locator('#status-text').textContent(),'');
          assert.equal(await page.locator('#checkout').isVisible(),false);
          const waitingLayout = await page.evaluate(() => {
            const title=document.getElementById('status-title');
            const resume=document.getElementById('resume');
            const style=getComputedStyle(title);
            return {fontSize:style.fontSize,fontWeight:style.fontWeight,
              gap:resume.getBoundingClientRect().top-title.getBoundingClientRect().bottom};
          });
          assert.equal(waitingLayout.fontSize,'18px');
          assert.equal(waitingLayout.fontWeight,'400');
          assert.ok(waitingLayout.gap >= 47);
          await page.route('https://yookassa.ru/checkout', async route => {
            await new Promise(resolve => setTimeout(resolve,400));
            await route.abort();
          });
          await page.locator('#resume').evaluate(element => element.click());
          await page.locator('#resume .button-loader').waitFor({state:'visible'});
          assert.equal(await page.locator('#resume').getAttribute('aria-disabled'),'true');
        }
        if(scenario.paymentFailed) {
          assert.equal(await page.locator('#status-text').textContent(),'');
          assert.equal(await page.locator('#resume').isVisible(),true);
          assert.equal(await page.locator('#resume').textContent(),'Вернуться к оплате');
        }
      }
      assert.deepEqual(errors,[]);
      console.log('PASS',scenario.name);
      await page.close();
    }

    const loaderPage = await browser.newPage({viewport:{width:390,height:844}});
    await loaderPage.addInitScript(() => {
      window.Telegram={WebApp:{initData:'mock',ready(){},expand(){},
        openLink(url){window.openedPaymentUrl=url;},close(){window.miniAppClosed=true;}}};
    });
    await loaderPage.route('https://telegram.org/**', route => route.fulfill({body:''}));
    await loaderPage.route('**/test-api/session', route => route.fulfill({status:200,
      contentType:'application/json',body:JSON.stringify(session)}));
    let releaseCreate;
    const createGate = new Promise(resolve => releaseCreate=resolve);
    await loaderPage.route('**/test-api/payments', async route => {
      await createGate;
      await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({
        order_id:order,confirmation_url:'https://yookassa.ru/checkout'})});
    });
    await loaderPage.route('https://yookassa.ru/**', route => route.fulfill({body:'checkout'}));
    await loaderPage.goto(`http://127.0.0.1:${server.address().port}/?test=1`);
    await loaderPage.locator('#checkout').waitFor({state:'visible'});
    await loaderPage.locator('#payment-form').evaluate(form => form.requestSubmit());
    await loaderPage.locator('#pay .button-loader').waitFor({state:'visible'});
    assert.equal(await loaderPage.locator('#pay').isDisabled(),true);
    assert.equal(await loaderPage.locator('#payment-status').isVisible(),false);
    releaseCreate();
    await loaderPage.waitForFunction(() => Boolean(window.openedPaymentUrl));
    assert.equal(await loaderPage.evaluate(() => window.openedPaymentUrl),'https://yookassa.ru/checkout');
    assert.equal(await loaderPage.evaluate(() => window.miniAppClosed === true),false);
    assert.equal(loaderPage.url().startsWith('http://127.0.0.1:'),true);
    console.log('PASS YooKassa opens externally and the Mini App stays open');
    await loaderPage.close();

    const timeoutPage = await browser.newPage({viewport:{width:390,height:844}});
    await timeoutPage.addInitScript(() => {
      window.Telegram={WebApp:{initData:'mock',ready(){},expand(){},close(){}}};
      const realNow=Date.now.bind(Date); let offset=0;
      Date.now=()=>realNow()+offset;
      window.advanceTestClock=value=>{ offset+=value; };
    });
    await timeoutPage.route('https://telegram.org/**', route => route.fulfill({body:''}));
    await timeoutPage.route('**/test-api/session', route => route.fulfill({status:200,
      contentType:'application/json',body:JSON.stringify(session)}));
    let releaseSlowCreate;
    const slowCreateGate = new Promise(resolve => releaseSlowCreate=resolve);
    await timeoutPage.route('**/test-api/payments**', async route => {
      const pathname = new URL(route.request().url()).pathname;
      if(pathname.endsWith('/payments')) {
        await slowCreateGate;
        await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({
          order_id:order,confirmation_url:null})});
      } else {
        await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({
          status:'created',confirmation_url:null})});
      }
    });
    await timeoutPage.goto(`http://127.0.0.1:${server.address().port}/?test=1`);
    await timeoutPage.locator('#checkout').waitFor({state:'visible'});
    await timeoutPage.locator('#payment-form').evaluate(form => form.requestSubmit());
    await timeoutPage.locator('#pay .button-loader').waitFor({state:'visible'});
    await timeoutPage.evaluate(() => window.advanceTestClock(31000));
    releaseSlowCreate();
    await timeoutPage.waitForFunction(() => !document.getElementById('error').hidden);
    assert.equal(await timeoutPage.locator('#error').textContent(),
      'Упс… что-то пошло не так');
    assert.equal(await timeoutPage.locator('#pay').isEnabled(),true);
    assert.equal(await timeoutPage.locator('#pay').textContent(),'Оплатить · 350 ₽');
    assert.equal(await timeoutPage.evaluate(() => sessionStorage.getItem('yoga-order')),order);
    console.log('PASS payment creation timeout safely restores pay button');
    await timeoutPage.close();

    const pendingWithoutUrlPage = await browser.newPage({viewport:{width:390,height:844}});
    await pendingWithoutUrlPage.addInitScript(({order}) => {
      window.Telegram={WebApp:{initData:'mock',ready(){},expand(){},close(){}}};
      const realNow=Date.now.bind(Date); let offset=0;
      Date.now=()=>realNow()+offset;
      window.advanceTestClock=value=>{ offset+=value; };
      sessionStorage.setItem('yoga-order',order);
    }, {order});
    await pendingWithoutUrlPage.route('https://telegram.org/**', route => route.fulfill({body:''}));
    await pendingWithoutUrlPage.route('**/test-api/session', route => route.fulfill({status:200,
      contentType:'application/json',body:JSON.stringify({...session,order_id:order})}));
    await pendingWithoutUrlPage.route('**/test-api/payments/*', route => route.fulfill({status:200,
      contentType:'application/json',body:JSON.stringify({status:'pending',confirmation_url:null})}));
    await pendingWithoutUrlPage.goto(`http://127.0.0.1:${server.address().port}/?test=1`);
    await pendingWithoutUrlPage.locator('#payment-status').waitFor({state:'visible'});
    await pendingWithoutUrlPage.waitForFunction(() => checking===false);
    await pendingWithoutUrlPage.evaluate(() => window.advanceTestClock(31000));
    await pendingWithoutUrlPage.evaluate(() => checkPayment());
    assert.equal(await pendingWithoutUrlPage.locator('#checkout').isVisible(),false);
    assert.equal(await pendingWithoutUrlPage.locator('#error').isVisible(),false);
    assert.equal(await pendingWithoutUrlPage.locator('#resume').isVisible(),true);
    assert.equal(await pendingWithoutUrlPage.locator('#resume').getAttribute('aria-disabled'),null);
    console.log('PASS pending payment without URL stays on the retryable waiting screen');
    await pendingWithoutUrlPage.close();

    for (const result of ['pending', 'succeeded', 'canceled']) {
      const retryPage = await browser.newPage({viewport:{width:390,height:844}});
      await retryPage.clock.install();
      await retryPage.addInitScript(({order}) => {
        sessionStorage.setItem('yoga-order',order);
        window.openedPaymentUrls=[];
        window.Telegram={WebApp:{initData:'mock',ready(){},expand(){},close(){},
          openLink(url){window.openedPaymentUrls.push(url);}}};
      }, {order});
      let statusCalls=0, creates=0, recovery=null;
      await retryPage.route('https://telegram.org/**', route => route.fulfill({body:''}));
      await retryPage.route('**/test-api/session', route => route.fulfill({json:session}));
      await retryPage.route('**/test-api/payments', route => {
        creates++;
        return route.fulfill({status:500,json:{error:'Must not create another payment'}});
      });
      await retryPage.route('**/test-api/payments/*', route => {
        statusCalls++;
        assert.equal(new URL(route.request().url()).pathname.split('/').pop(),order);
        return route.fulfill(recovery === null
          ? {status:503,json:{error:'Temporarily unavailable'}}
          : {json:{status:recovery,ends_on:'2026-12-31',
            confirmation_url:recovery==='pending' ? 'https://yookassa.ru/checkout' : null}});
      });
      await retryPage.goto(`http://127.0.0.1:${server.address().port}/?test=1`);
      await retryPage.locator('#resume').waitFor({state:'visible'});
      assert.equal(await retryPage.locator('#checkout').isVisible(),false);
      await retryPage.locator('#resume').click();
      await retryPage.clock.runFor(120);
      await retryPage.waitForFunction(() => checking===false);
      assert.equal(await retryPage.locator('#resume').getAttribute('aria-disabled'),'true');
      assert.equal(await retryPage.locator('#resume .button-loader').isVisible(),true);
      // Background checks must not release a clicked button prematurely.
      await retryPage.clock.runFor(5000);
      await retryPage.waitForFunction(() => checking===false);
      assert.equal(await retryPage.locator('#resume').getAttribute('aria-disabled'),'true');
      const callsBeforeDuplicate=statusCalls;
      await retryPage.locator('#resume').evaluate(element => element.click());
      await retryPage.clock.runFor(120);
      assert.equal(statusCalls,callsBeforeDuplicate);
      await retryPage.clock.fastForward(25000);
      assert.equal(await retryPage.locator('#resume').getAttribute('aria-disabled'),null);
      assert.equal(await retryPage.locator('#resume').textContent(),'Вернуться к оплате');
      assert.equal(await retryPage.locator('#checkout').isVisible(),false);
      recovery=result;
      await retryPage.locator('#resume').click();
      await retryPage.clock.runFor(120);
      if(result==='pending') {
        await retryPage.waitForFunction(() => window.openedPaymentUrls.length===1);
        assert.deepEqual(await retryPage.evaluate(() => window.openedPaymentUrls),
                         ['https://yookassa.ru/checkout']);
        await retryPage.clock.runFor(5000);
        await retryPage.waitForFunction(() => checking===false);
        assert.equal(await retryPage.locator('#resume').getAttribute('aria-disabled'),'true');
        await retryPage.clock.fastForward(25000);
        assert.equal(await retryPage.locator('#resume').getAttribute('aria-disabled'),null);
      } else {
        const title=result==='succeeded' ? 'Оплата принята 🧡' : '❌ Оплата не прошла';
        await retryPage.waitForFunction(title => document.getElementById('status-title').textContent===title,title);
        assert.deepEqual(await retryPage.evaluate(() => window.openedPaymentUrls),[]);
        assert.equal(await retryPage.locator('#resume').isVisible(),false);
        await retryPage.clock.fastForward(31000);
        assert.equal(await retryPage.locator('#resume').isVisible(),false);
      }
      assert.equal(creates,0);
      console.log('PASS status retry after timeout without a new payment:',result);
      await retryPage.close();
    }
  } finally {
    if(browser) await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(e => {console.error(e); process.exitCode=1;});
