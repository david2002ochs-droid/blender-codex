// Serves the actual compiled product. State comes from test_reasoning.py's real
// CodexClient -> SessionState replay, never a duplicate UI implementation.
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const http = require('node:http'), fs = require('node:fs'), path = require('node:path');
const assert = require('node:assert/strict'), crypto = require('node:crypto');
const root = path.resolve(__dirname, '..'), runtime = path.join(root, '.runtime');
const {states, evidence} = JSON.parse(fs.readFileSync(path.join(runtime, 'thinking-replay-states.json'), 'utf8'));
const hash = name => crypto.createHash('sha256').update(fs.readFileSync(path.join(root, name))).digest('hex');
(async () => {
  let browser, server, current = 'empty_running';
  const errors = [], screenshots = [];
  try {
    server = http.createServer((request, response) => {
      if (request.url === '/api/state') {
        assert.equal(request.headers['x-codex-token'], 'thinking-test-token');
        response.setHeader('Content-Type', 'application/json'); response.end(JSON.stringify(states[current])); return;
      }
      const file = {'/': 'index.html', '/app.js': 'app.js', '/styles.css': 'styles.css'}[request.url];
      if (!file) { response.statusCode = 404; response.end(); return; }
      response.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html');
      response.end(fs.readFileSync(path.join(root, 'blender_codex/web', file)));
    });
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    browser = await chromium.launch({headless: true, ...(process.env.CHROME_PATH ? {executablePath: process.env.CHROME_PATH} : {}), args: ['--in-process-gpu', '--disable-gpu']});
    const page = await browser.newPage({viewport: {width: 430, height: 900}});
    page.setDefaultTimeout(8000);
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(`http://127.0.0.1:${server.address().port}/#token=thinking-test-token`);
    const think = page.locator('[data-variant="think"]');
    const disclosure = () => think.locator('[role="button"][aria-expanded]');
    const capture = async name => {
      const file = `.runtime/thinking-${name}-tested.png`;
      await page.screenshot({path: path.join(root, file), fullPage: true}); screenshots.push(file);
    };
    await think.waitFor();
    assert.equal(await think.count(), 1);
    assert.equal(await think.getAttribute('data-state'), 'running');
    assert.equal(await disclosure().getAttribute('aria-expanded'), 'false');
    assert(!await page.locator('body').innerText().then(text => text.includes('PRIVATE_SENTINEL')));
    await capture('empty-running');

    current = 'streaming';
    await page.getByText('Inspecting the selection', {exact: true}).waitFor();
    await disclosure().click();
    assert.equal(await disclosure().getAttribute('aria-expanded'), 'true');
    current = 'streaming_next';
    await think.getByText('Public summary replay: checking object bounds.', {exact: false}).waitFor();
    assert.equal(await disclosure().getAttribute('aria-expanded'), 'true', 'streaming preserves disclosure');
    await capture('streaming-expanded');
    await disclosure().click();
    await page.getByText('Preparing the response', {exact: true}).waitFor();
    await capture('streaming-collapsed');

    current = 'completed';
    await page.getByText('Fixture response: the selection is ready.', {exact: true}).waitFor();
    await page.locator('[data-turn-process="fixture-turn"]').waitFor();
    assert.equal(await think.getAttribute('data-state'), 'ok');
    assert.equal(await think.count(), 1);
    assert.match(await page.locator('[data-turn-process="fixture-turn"]').innerText(), /Completed in/);
    await disclosure().click();
    await think.getByText('Summary complete.', {exact: false}).waitFor();
    const order = await page.locator('[data-chat-node-key]').evaluateAll(nodes => nodes.map(node => node.getAttribute('data-chat-node-key')));
    assert(order.indexOf('fixture-user') < order.findIndex(key => key.startsWith('reasoning:')));
    assert(order.findIndex(key => key.startsWith('reasoning:')) < order.indexOf('fixture-answer'));
    await capture('completed');
    current = 'restored';
    await page.waitForTimeout(550);
    assert.equal(await think.count(), 1);
    assert.equal(await disclosure().getAttribute('aria-expanded'), 'true');
    for (const [state, label] of [['failed', 'Failed'], ['interrupted', 'Stopped']]) {
      current = state;
      await page.locator('[data-turn-process="fixture-turn"]').filter({hasText: label}).waitFor();
      assert.equal(await think.getAttribute('data-state'), 'ok');
      assert.equal(await page.locator('[data-variant="think"][data-state="running"]').count(), 0);
      await capture(state);
    }
    current = 'history';
    await page.getByText('History public summary', {exact: true}).waitFor();
    assert.equal(await think.count(), 1);
    assert(!await page.locator('[data-turn-process="fixture-turn"]').innerText().then(text => text.includes(' in ')), 'missing duration is not fabricated');
    await capture('history');
    current = 'empty_completed';
    await think.waitFor({state: 'detached'});
    assert.equal(await page.getByText('History public summary', {exact: true}).count(), 0);
    current = 'large';
    await page.getByText('Summary preview truncated at the local display limit.', {exact: true}).waitFor();
    await think.waitFor();
    assert.equal(await think.count(), 1);
    await capture('large');
    await page.emulateMedia({reducedMotion: 'reduce'});
    current = 'streaming';
    await page.locator('[data-variant="think"][data-state="running"]').waitFor();
    const reducedAnimations = await think.evaluate(el => [el, ...el.querySelectorAll('*')].filter(node => {
      const css = getComputedStyle(node); return css.animationName !== 'none' && parseFloat(css.animationDuration) > 0.01;
    }).length);
    assert.equal(reducedAnimations, 0, 'original Think row respects reduced motion');
    assert.deepEqual(errors, []);
    const receipt = {status: 'THINKING_FRONTEND_PASS', evidence, testedAt: new Date().toISOString(), appJsSha256: hash('blender_codex/web/app.js'), cssSha256: hash('blender_codex/web/styles.css'), screenshots, errors};
    fs.writeFileSync(path.join(runtime, 'thinking-frontend-receipt.json'), JSON.stringify(receipt, null, 2));
    console.log('THINKING_FRONTEND_PASS');
  } finally {
    if (browser) await browser.close();
    if (server) await new Promise(resolve => server.close(resolve));
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
