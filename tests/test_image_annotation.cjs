// Exercises shipped gallery, separate editor surface and explicit draft handoff.
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const http = require('node:http'), fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
(async () => {
  let browser, server;
  try {
    browser = await chromium.launch({headless: true, ...(process.env.CHROME_PATH ? {executablePath: process.env.CHROME_PATH} : {}), args: ['--in-process-gpu', '--disable-gpu']});
    const fixture = await browser.newPage();
    const png = Buffer.from(await fixture.evaluate(() => { const canvas = document.createElement('canvas'); canvas.width = 800; canvas.height = 600; const ctx = canvas.getContext('2d'); ctx.fillStyle = '#f0f3ff'; ctx.fillRect(0, 0, 800, 600); ctx.fillStyle = '#3352df'; ctx.fillRect(200, 120, 400, 360); return canvas.toDataURL('image/png').split(',')[1]; }), 'base64'); await fixture.close();
    const resources = {render: {id: 'render', name: 'generated-front.png', mime_type: 'image/png', size: png.length, resource_url: '/api/resources/render'}, side: {id: 'side', name: 'generated-side.png', mime_type: 'image/png', size: png.length, resource_url: '/api/resources/side'}};
    const bytes = {render: png, side: png}, actions = [], errors = [];
    const state = {thread_id: 'image-thread', project_root: 'C:/Blender', ready: true, busy: false, status: 'Connected', messages: [], tool_calls: [{id: 'generated-tool', tool_name: 'render.generate', arguments: {}, status: 'completed', seq: 1, content: [{type: 'image', resource_id: 'render'}, {type: 'image', resource_id: 'side'}]}], approvals: [], models: [], settings: {}, context: {}, artifacts: Object.values(resources), attachments: [], image_markup: null, capabilities: {can_annotate_images: true, can_upload_attachments: true, max_attachment_bytes: 8388608}};
    server = http.createServer(async (req, res) => {
      if (req.url.startsWith('/api/')) {
        assert.equal(req.headers['x-codex-token'], 'image-token');
        if (req.url.startsWith('/api/resources/')) { const id = req.url.split('/').pop(); assert(bytes[id]); res.setHeader('Content-Type', resources[id]?.mime_type || 'application/octet-stream'); res.end(bytes[id]); return; }
        res.setHeader('Content-Type', 'application/json');
        if (req.url === '/api/state') { res.end(JSON.stringify(state)); return; }
        let body = ''; for await (const chunk of req) body += chunk; const command = JSON.parse(body); actions.push(command);
        if (command.action === 'image_markup/open') { state.image_markup = {active: true, id: 'editor-' + actions.length, thread_id: state.thread_id, generation: 1, resources: command.resource_ids.map(id => resources[id])}; for (const resource of state.image_markup.resources) if (!state.attachments.some(item => item.id === resource.id)) state.attachments.push(resource); }
        if (command.action === 'image_markup/close') state.image_markup = null;
        if (command.action === 'image_markup/commit') {
          assert.equal(command.id, state.image_markup.id); assert.equal(command.source_resource_id, 'render');
          assert.deepEqual(command.comments, [{number: 1, text: 'Make this edge softer'}]);
          const annotated = {id: 'annotated', name: 'generated-front-annotated.png', mime_type: 'image/png', resource_url: '/api/resources/annotated'};
          const comments = {id: 'comments', name: 'generated-front-comments.txt', mime_type: 'text/plain', resource_url: '/api/resources/comments'};
          resources.annotated = annotated; resources.comments = comments; bytes.annotated = Buffer.from(command.png_base64, 'base64'); bytes.comments = Buffer.from('Pin 1: Make this edge softer'); state.attachments.push(annotated, comments); if (!command.keep_open) state.image_markup = null;
        }
        if (command.action === 'send') { state.messages.push({id: 'accepted', role: 'You', text: command.text, attachments: command.attachment_ids}); }
        res.end(JSON.stringify({ok: true, image_markup: state.image_markup})); return;
      }
      const file = {'/': 'index.html', '/app.js': 'app.js', '/styles.css': 'styles.css'}[req.url]; if (!file) { res.statusCode = 404; res.end(); return; }
      res.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html'); res.end(fs.readFileSync(path.join(__dirname, '../blender_codex/web', file)));
    });
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve)); const origin = `http://127.0.0.1:${server.address().port}`;
    const chat = await browser.newPage({viewport: {width: 480, height: 900}}), editor = await browser.newPage({viewport: {width: 1150, height: 780}});
    for (const page of [chat, editor]) { page.setDefaultTimeout(8000); page.on('pageerror', error => errors.push(error.message)); }
    const imageContent = state.tool_calls[0].content;
    state.tool_calls[0].tool_name = 'imageGeneration'; state.tool_calls[0].kind = 'imageGeneration'; state.tool_calls[0].status = 'running'; state.tool_calls[0].content = [];
    await chat.goto(origin + '/#token=image-token');
    await chat.getByText('Bild wird erstellt', {exact: true}).waitFor();
    assert.notEqual(await chat.locator('.image-generation-symbol').evaluate(node => getComputedStyle(node).animationName), 'none');
    await chat.emulateMedia({reducedMotion: 'reduce'});
    assert.equal(await chat.locator('.image-generation-symbol').evaluate(node => getComputedStyle(node).animationName), 'none');
    await chat.emulateMedia({reducedMotion: 'no-preference'});
    await chat.screenshot({path: path.join(__dirname, '../.runtime/image-generation-running-tested.png')});
    state.tool_calls[0].status = 'interrupted'; await chat.getByText('Bilderstellung abgebrochen', {exact: true}).waitFor();
    state.tool_calls[0].status = 'failed'; state.tool_calls[0].error = 'Actual provider failure'; await chat.getByText('Bild konnte nicht erstellt werden', {exact: true}).waitFor();
    state.tool_calls[0].status = 'completed'; state.tool_calls[0].error = null; state.tool_calls[0].content = imageContent;
    await chat.getByText('Bild erstellt', {exact: true}).waitFor();
    const thumbnail = chat.locator('.generated-image-interaction img[alt="generated-front.png"]'); await thumbnail.waitFor();
    await thumbnail.dblclick(); await chat.waitForTimeout(500);
    assert.equal(actions.filter(item => item.action === 'image_markup/open').length, 1); assert.equal(actions.filter(item => item.action === 'send').length, 0);
    assert.equal(state.attachments[0].id, 'render');
    await editor.goto(origin + '/#token=image-token&surface=image-editor');
    const canvas = editor.getByRole('img', {name: 'Original: generated-front.png'}); await canvas.waitFor();
    const layer = editor.locator('canvas'); await layer.waitFor(); const box = await layer.boundingBox();
    await editor.mouse.click(box.x + box.width * .4, box.y + box.height * .4);
    await editor.getByRole('textbox', {name: 'Kommentar zu Pin 1: generated-front.png'}).fill('Make this edge softer');
    await editor.getByRole('button', {name: 'Stift', exact: true}).click();
    await editor.mouse.move(box.x + box.width * .2, box.y + box.height * .6); await editor.mouse.down(); await editor.mouse.move(box.x + box.width * .7, box.y + box.height * .6, {steps: 6}); await editor.mouse.up();
    assert.equal(await editor.locator('.image-annotation-stage').getAttribute('data-mark-count'), '1');
    await editor.screenshot({path: path.join(__dirname, '../.runtime/image-annotation-tested.png')});
    await editor.getByRole('button', {name: 'In Chat übernehmen', exact: true}).click(); await editor.waitForTimeout(450);
    assert.equal(actions.filter(item => item.action === 'send').length, 0); assert.notDeepEqual(bytes.annotated, png); assert.deepEqual(bytes.render, png);
    await chat.getByRole('button', {name: /Remove file.*generated-front-comments.txt/}).waitFor();
    await chat.locator('[data-composer-input]').fill('Apply these changes'); await chat.waitForTimeout(150); await chat.getByRole('button', {name: 'Send message', exact: true}).click();
    await chat.waitForTimeout(350); const sent = actions.find(item => item.action === 'send'); assert(sent.attachment_ids.includes('render') && sent.attachment_ids.includes('annotated') && sent.attachment_ids.includes('comments'));
    // Multiple actual resources can be compared. Thread switch unmounts every
    // editor layer; no old canvas or comments survive into another session.
    state.image_markup = {active: true, id: 'comparison', thread_id: state.thread_id, generation: 1, resources: [resources.render, resources.side]};
    await editor.locator('.image-annotation-pane').nth(1).waitFor(); assert.equal(await editor.locator('.image-annotation-pane').count(), 2);
    await editor.getByRole('button', {name: 'Bildansicht schließen: generated-side.png'}).click(); assert.equal(await editor.locator('.image-annotation-pane').count(), 1);
    state.thread_id = 'different-thread'; state.image_markup = null; state.artifacts = []; state.attachments = [];
    await editor.getByText('Keine aktive Bildannotation in diesem Chat.', {exact: true}).waitFor(); assert.equal(await editor.locator('canvas').count(), 0);
    assert.equal(errors.length, 0, errors.join('\n'));
    fs.writeFileSync(path.join(__dirname, '../.runtime/image-annotation-receipt.json'), JSON.stringify({result: 'PASS', checked: ['image generation actual running/success/error/cancel states', 'reduced-motion removes animation', 'real resource double-click', 'no automatic send', 'authenticated original load', 'numbered pin/comment association', 'drawing', 'immutable original', 'annotated PNG + comments draft handoff', 'explicit normal chat send with handles', 'two views', 'close single view', 'thread isolation'], actions: actions.map(item => item.action)}, null, 2)); console.log('IMAGE_ANNOTATION_PASS');
  } finally { if (browser) await browser.close(); if (server) await new Promise(resolve => server.close(resolve)); }
})().catch(error => { console.error(error); process.exitCode = 1; });
