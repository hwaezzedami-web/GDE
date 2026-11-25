// End-to-end test: the iPhone web app (docs/) as the wife, the Android Java code as the husband,
// both against the Firebase emulator. Run from the repo root after starting:
//   firebase emulators:start --only auth,database   (rules: bouchra/firebase/database.rules.json)
//   python3 -m http.server 8080 --directory docs
// Usage: node bouchra/test/web-test.cjs <classpath> <screenshot-dir>
const { chromium } = require('playwright');
const { execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const CP = process.argv[2];
const SHOTS = process.argv[3];
const STATE = path.join(SHOTS, 'husband-state.json');
let pass = 0, fail = 0;
const check = (name, ok) => { console.log((ok ? '  PASS  ' : '  FAIL  ') + name); ok ? pass++ : fail++; };
const husband = (...args) => execFileSync('java', ['-Dfile.encoding=UTF-8', '-Dstdout.encoding=UTF-8', '-Dsun.stdout.encoding=UTF-8', '-cp', CP, 'HusbandCli', ...args], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'], env: { ...process.env, LC_ALL: 'C.UTF-8', LANG: 'C.UTF-8' } });
const dump = () => {
  const out = {};
  for (const line of husband('dump', STATE).split('\n')) {
    const i = line.indexOf('=');
    if (i > 0) out[line.slice(0, i)] = line.slice(i + 1);
  }
  return out;
};
async function until(fn, ms = 10000) {
  const end = Date.now() + ms;
  while (Date.now() < end) { try { if (await fn()) return true; } catch (e) {} await new Promise(r => setTimeout(r, 300)); }
  return false;
}

(async () => {
  fs.mkdirSync(SHOTS, { recursive: true });
  if (fs.existsSync(STATE)) fs.unlinkSync(STATE);

  console.log('== VAPID signature made by Android code, verified with browser crypto');
  {
    const { subtle } = globalThis.crypto;
    const kp = await subtle.generateKey({ name: 'ECDSA', namedCurve: 'P-256' }, true, ['sign', 'verify']);
    const jwk = await subtle.exportKey('jwk', kp.privateKey);
    const jwt = husband('jwt', 'https://web.push.apple.com', jwk.d).trim();
    const [h, b, s] = jwt.split('.');
    const ok = await subtle.verify({ name: 'ECDSA', hash: 'SHA-256' }, kp.publicKey,
      Buffer.from(s, 'base64url'), Buffer.from(h + '.' + b));
    const claims = JSON.parse(Buffer.from(b, 'base64url').toString());
    check('ES256 signature valid', ok);
    check('claims: aud, sub, exp within 24h', claims.aud === 'https://web.push.apple.com' && claims.sub.startsWith('https://')
      && claims.exp > Date.now() / 1000 && claims.exp < Date.now() / 1000 + 86400);
  }

  console.log('== husband (Android code) creates an invite');
  const setup = husband('setup', STATE);
  const invite = (setup.match(/INVITE=(.*)/) || [])[1].replace(/\\n/g, '\n');
  const code = (setup.match(/CODE=(\d{6})/) || [])[1];
  check('invite created', !!code && invite.includes('BOUCHRA:') && invite.includes('github.io/GDE'));

  const browser = await chromium.launch();
  const ctx = await browser.newContext({
    viewport: { width: 393, height: 852 }, deviceScaleFactor: 1, isMobile: true, hasTouch: true, locale: 'ar',
    userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1'
  });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  page.on('console', m => { if (m.type() === 'error' && !/EventSource|net::ERR|Failed to load resource/.test(m.text())) errors.push(m.text()); });
  await page.goto('http://127.0.0.1:8080/?emu=127.0.0.1');
  await page.screenshot({ path: path.join(SHOTS, '1-setup.png') });

  console.log('== wife signs up and joins with the pasted invite');
  const fields = page.locator('#main input');
  await fields.nth(1).fill('bouchra' + Date.now() + '@test.com');
  await fields.nth(2).fill('secret2');
  await fields.nth(3).fill(invite);
  await page.getByText('✨ إنشاء حساب وربط').click();
  check('chat opens after joining', await until(async () => await page.locator('#msgs').count() > 0, 15000));
  let d = dump();
  check('husband sees wife as partner', d.PARTNER && d.PARTNER.length > 5);
  check('wife profile written with role wife', /"role":"wife"/.test(d.PROFILES));
  check('husband got "joined" notification', /join/.test(d.INBOX));

  console.log('== chat');
  await page.locator('.composer textarea').fill('أحبك يا زوجي ❤️');
  await page.locator('.send').click();
  check('husband receives wife message', await until(() => /أحبك يا زوجي/.test(dump().MESSAGES), 8000));
  check('husband inbox gets message notification', /"kind":"msg"/.test(dump().INBOX));
  husband('send', STATE, 'وأنا أحبكِ يا بشرى 🌹');
  check('wife sees husband message live', await until(async () => (await page.locator('#msgs').innerText()).includes('وأنا أحبكِ يا بشرى'), 8000));
  check('read receipt sent for husband message', await until(() => {
    const m = JSON.parse(dump().MESSAGES);
    return Object.values(m).some(x => x.text.includes('وأنا أحبكِ') && x.read === true);
  }, 8000));
  check('wife inbox notification consumed (deleted) by web app', await until(async () => {
    const r = await page.evaluate(async () => { const s = JSON.parse(localStorage.getItem('bouchra-emu')); const t = s.token;
      const res = await fetch(`http://127.0.0.1:9000/couples/${s.cid}/inbox/${s.uid}.json?ns=demo-bouchra-default-rtdb&auth=${t}`); return res.json(); });
    return r === null;
  }, 8000));
  await page.getByText('💗 اشتقت لك').click();
  check('"miss you" message sent', await until(() => /"type":"miss"/.test(dump().MESSAGES), 8000));
  check('partner name shown in header', (await page.locator('#pName').innerText()).includes('أحمد'));
  await page.screenshot({ path: path.join(SHOTS, '2-chat.png') });

  console.log('== shopping (shared with Android format)');
  await page.locator('nav button', { hasText: 'المشتريات' }).click();
  check('husband\'s existing item visible', await until(async () => (await page.locator('#main').innerText()).includes('طماطم'), 8000));
  await page.locator('#main input.field').first().fill('حليب');
  await page.locator('#main input.field').first().press('Enter');
  check('wife item reaches husband', await until(() => /حليب/.test(dump().SHOPPING), 8000));
  check('item id format matches Android (i<id> key, numeric id)', /"i\d{15,}":\{[^}]*"id":\d{15,}/.test(dump().SHOPPING));
  husband('addshop', STATE, 'خبز');
  check('husband item appears live for wife', await until(async () => (await page.locator('#main').innerText()).includes('خبز'), 8000));
  await page.locator('.item', { hasText: 'طماطم' }).locator('button').first().click();
  check('wife marks bought → husband sees bought', await until(() => {
    const s = JSON.parse(dump().SHOPPING); return Object.values(s).some(x => x.text === 'طماطم' && x.bought === true);
  }, 8000));
  await page.screenshot({ path: path.join(SHOTS, '3-shopping.png') });

  console.log('== coupons, together, dreams, my reminders');
  await page.locator('nav button', { hasText: 'الكوبونات' }).click();
  await page.getByText('💝 استعمال').first().click();
  await page.locator('#sheet button', { hasText: 'نعم' }).click();
  check('coupon redeemed → husband sees used', await until(() => /"used":true/.test(dump().COUPONS), 8000));
  await page.screenshot({ path: path.join(SHOTS, '4-coupons.png') });
  await page.locator('nav button', { hasText: 'معاً' }).click();
  check('together counter uses husband\'s wedding date', await until(async () => /سنوات|سنة/.test(await page.locator('.hero').first().innerText()), 5000));
  await page.screenshot({ path: path.join(SHOTS, '5-together.png') });
  await page.locator('nav button', { hasText: 'أحلامنا' }).click();
  await page.waitForTimeout(400);
  await page.screenshot({ path: path.join(SHOTS, '6-dreams.png') });
  await page.locator('nav button', { hasText: 'تذكيراتي' }).click();
  check('wife reminders listed', (await page.locator('#main').innerText()).includes('قبّليه'));
  await page.locator('#main .card .btn', { hasText: 'تم ✓' }).first().click();
  check('reminder done → husband notified', await until(() => /"kind":"done"/.test(dump().INBOX), 8000));
  await page.screenshot({ path: path.join(SHOTS, '7-reminders.png') });

  console.log('== reload keeps her signed in and linked');
  await page.reload();
  check('still linked after reload', await until(async () => await page.locator('nav button').count() === 6, 8000));

  check('no JavaScript errors', errors.length === 0);
  if (errors.length) console.log(errors.join('\n'));
  await browser.close();
  console.log(`\nRESULT: ${pass} passed, ${fail} failed`);
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
