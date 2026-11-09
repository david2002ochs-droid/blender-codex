// Tests the actual production bundle. Fixtures exist only in this test server.
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const http = require('node:http'), fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
(async () => {
  let browser, server;
  try {
    const actions = [], errors = [], resourcesRead = [];
    let rejectNextSend = false;
    const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jN8sAAAAASUVORK5CYII=', 'base64');
    const resources = {
      picture: {id: 'picture', name: 'result.png', mime_type: 'image/png', size: png.length, resource_url: '/api/resources/picture', width: 1, height: 1},
      document: {id: 'document', name: 'result.txt', mime_type: 'text/plain', size: 18, resource_url: '/api/resources/document'},
      office: {id: 'office', name: 'result.docx', mime_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', size: 4, resource_url: '/api/resources/office'},
    };
    const state = {thread_id: 'test-thread', project_root: 'C:/Blender', ready: true, busy: false, status: 'Connected', error: '', activity: '',
      messages: [{id: 'user-item', role: 'You', text: 'Inspect the selection', seq: 1}, {id: 'assistant-item', role: 'Codex', text: '**Cube** is selected. <img src=x onerror=alert(1)>', seq: 4}],
      tool_calls: [{id: 'tool-item-1', tool_name: 'blender.inspect', arguments: {selected: true}, status: 'completed', seq: 2, content: [{type: 'text', text: 'Cube inspected'}]},
        {id: 'tool-item-2', tool_name: 'blender.change', arguments: {height: 2}, status: 'failed', seq: 3, content: [{type: 'text', text: 'User denied operation'}], error: 'Denied'}],
      approvals: [], context: {filepath: 'test.blend', active_object: {name: 'Cube'}, selected_objects: [{name: 'Cube'}]}, settings: {codex_path: 'codex', mcp_command: '', mcp_args: '[]'},
      threads: [{id: 'test-thread', title: 'Inspect the selection', updated_at: 2000, project: 'C:/Blender'}, {id: 'previous-thread', title: 'Previous Blender chat', updated_at: 1000, project: 'C:/Blender'}], active_thread_id: 'test-thread',
      artifacts: Object.values(resources), attachments: [], models: [], capabilities: {history: true, can_draw: true, can_attach_view: true, can_upload_attachments: true, max_attachment_bytes: 8388608}};
    server = http.createServer(async (request, response) => {
      if (request.url.startsWith('/api/')) {
        assert.equal(request.headers['x-codex-token'], 'test-token');
        if (request.url.startsWith('/api/resources/')) {
          const id = request.url.split('/').pop(); resourcesRead.push(id);
          response.setHeader('Content-Type', resources[id]?.mime_type || 'application/octet-stream');
          response.end(id === 'picture' ? png : Buffer.from(id === 'document' ? 'Real file contents' : 'PK00')); return;
        }
        response.setHeader('Content-Type', 'application/json');
        if (request.url === '/api/state') { response.end(JSON.stringify(state)); return; }
        let body = ''; for await (const chunk of request) body += chunk;
        const command = JSON.parse(body); actions.push(command);
        if (command.action === 'send' && rejectNextSend) { rejectNextSend = false; response.statusCode = 400; response.end(JSON.stringify({error: 'Model does not support images'})); return; }
        if (command.action === 'send') {
          state.busy = true;
          state.messages.push({id: 'accepted-user-' + actions.length, role: 'You', text: command.text, seq: 5});
          state.messages.push({id: 'streaming-answer-' + actions.length, role: 'Codex', text: 'Streaming answer', seq: 6 + actions.length});
        }
        if (command.action === 'stop') state.busy = false;
        if (command.action === 'markup_cancel') state.markup_active = false;
        if (command.action === 'draw') state.markup_active = true;
        if (['new_chat', 'threads/new'].includes(command.action)) { state.thread_id = state.active_thread_id = 'new-authoritative-thread'; state.messages = []; state.tool_calls = []; state.attachments = []; }
        if (command.action === 'threads/open') { state.thread_id = state.active_thread_id = command.thread_id; state.messages = [{id: 'restored-item', role: 'Codex', text: 'Authoritative restored transcript', seq: 1}]; state.tool_calls = []; }
        if (command.action === 'threads/rename') state.threads.find(row => row.id === command.thread_id).title = command.title;
        if (command.action === 'set_mode') state.collaboration_mode = command.mode;
        if (command.action === 'goal/set') state.goal = {...state.goal, ...command};
        if (command.action === 'goal/clear') state.goal = null;
        if (command.action === 'export_chat') { const resource = {id: 'export', name: 'chat.json', mime_type: 'application/json', resource_url: '/api/resources/export'}; resources.export = resource; response.end(JSON.stringify({ok: true, resource})); return; }
        if (command.action === 'select_model') { state.selected_model = command.model_id; if (command.reasoning_effort) state.reasoning_effort = command.reasoning_effort; }
        if (command.action === 'set_permission_mode') state.permission_mode = command.permission_mode;
        if (command.action === 'upload_attachment') {
          const attachment = {id: 'uploaded-note', name: command.name, mime_type: command.mime_type, size: Buffer.from(command.data_base64, 'base64').length, resource_url: '/api/resources/uploaded-note'};
          state.attachments.push(attachment); response.end(JSON.stringify({ok: true, attachment})); return;
        }
        if (['approve', 'respond'].includes(command.action)) state.approvals = [];
        response.end(JSON.stringify({ok: true})); return;
      }
      const file = {'/': 'index.html', '/app.js': 'app.js', '/styles.css': 'styles.css'}[request.url];
      if (!file) { response.statusCode = 404; response.end(); return; }
      response.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html');
      response.setHeader('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' blob: data:; font-src 'self' data:; base-uri 'none'; object-src 'none'");
      response.end(fs.readFileSync(path.join(__dirname, '../blender_codex/web', file)));
    });
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    browser = await chromium.launch({headless: true, ...(process.env.CHROME_PATH ? {executablePath: process.env.CHROME_PATH} : {}), args: ['--in-process-gpu', '--disable-gpu'], timeout: 15000});
    const chat = await browser.newPage({viewport: {width: 430, height: 900}}), markup = await browser.newPage({viewport: {width: 900, height: 64}});
    for (const page of [chat, markup]) { page.setDefaultTimeout(8000); page.on('pageerror', error => { errors.push(error.message); console.error('Browser:', error.stack); }); }
    const origin = `http://127.0.0.1:${server.address().port}`;
    await chat.goto(origin + '/#token=test-token'); await markup.goto(origin + '/#token=test-token&surface=markup');
    try { await chat.getByText('blender.inspect', {exact: true}).waitFor(); } catch (error) { console.error(await chat.locator('body').innerText()); throw error; }
    assert.equal(await markup.getByRole('button').count(), 0, 'Permanent upper toolbar is removed');
    assert.equal(await chat.locator('[data-chat-call-id]').count(), 2);
    assert.deepEqual(await chat.locator('[data-chat-node-key]').evaluateAll(nodes => nodes.map(node => node.getAttribute('data-chat-node-key'))), ['user-item', 'tool-item-1', 'tool-item-2', 'assistant-item']);
    assert.equal(await chat.locator('[data-chat-flow] img[src=x]').count(), 0);
    const call = chat.locator('[data-chat-call-id]').first();
    await call.locator('[role="button"][aria-expanded]').click();
    await chat.getByText('Cube inspected', {exact: true}).waitFor();
    const input = chat.locator('[data-composer-input]'); await input.fill('Message from real Lexical');
    await chat.waitForTimeout(400); assert.equal(await input.innerText(), 'Message from real Lexical');
    await chat.getByRole('button', {name: 'Send message', exact: true}).click();
    await chat.getByRole('button', {name: 'Stop generating', exact: true}).waitFor();
    assert(actions.some(command => command.action === 'send' && command.text === 'Message from real Lexical'));
    state.messages.find(message => message.id.startsWith('streaming-answer-')).text = 'Streaming final answer';
    await chat.getByText('Streaming final answer', {exact: true}).waitFor();
    await chat.getByRole('button', {name: 'Stop generating', exact: true}).click();
    await chat.getByRole('button', {name: 'Send message', exact: true}).waitFor();
    await input.fill('Keep sidebar draft'); await chat.waitForTimeout(350);
    await chat.getByRole('button', {name: 'Add files or run commands', exact: true}).click();
    await chat.getByRole('option').filter({hasText: /^Zeichnen/}).click();
    await chat.waitForTimeout(300);
    assert(actions.some(command => command.action === 'draw')); assert(state.markup_active);
    const stopsBeforeEscape = actions.filter(command => command.action === 'stop').length;
    await input.press('Escape'); await chat.waitForTimeout(300);
    assert(actions.some(command => command.action === 'markup_cancel'));
    assert.equal(actions.filter(command => command.action === 'stop').length, stopsBeforeEscape);
    assert.equal(await input.innerText(), 'Keep sidebar draft');
    await chat.getByRole('button', {name: 'Send message', exact: true}).click(); await chat.waitForTimeout(300);
    assert(actions.some(command => command.action === 'send' && command.text === 'Keep sidebar draft' && command.include_view === true));
    state.busy = false;
    state.approvals = [{request_id: 42, kind: 'approval', text: 'Run this real correlated action?'}];
    await chat.getByText('Run this real correlated action?', {exact: true}).waitFor();
    await chat.getByRole('button', {name: 'Reject', exact: true}).click();
    await chat.waitForTimeout(300); assert(actions.some(command => command.action === 'approve' && command.request_id === 42 && command.approved === false));
    state.approvals = [{request_id: 'form-1', kind: 'form', text: 'Choose transform', schema: {type: 'object', properties: {height: {type: 'number', title: 'Height'}}, required: ['height']}}];
    await chat.getByLabel('Height', {exact: true}).fill('2');
    await chat.getByRole('button', {name: 'Allow once', exact: true}).click();
    await chat.waitForTimeout(300); assert(actions.some(command => command.action === 'respond' && command.request_id === 'form-1' && command.values.height === 2));
    state.approvals = [{request_id: 'question-1', kind: 'questions', text: 'Choose scope', questions: [{id: 'scope', header: 'Scope', question: 'Which objects?', options: [{label: 'Selected', description: 'Only selection'}]}]}];
    await chat.getByLabel('Scope', {exact: true}).selectOption('Selected');
    await chat.getByRole('button', {name: 'Allow once', exact: true}).click();
    await chat.waitForTimeout(300); assert(actions.some(command => command.action === 'respond' && command.request_id === 'question-1' && command.answers.scope[0] === 'Selected'));
    state.models = [{id: 'catalog-a', displayName: 'Catalog A', supportedReasoningEfforts: [{reasoningEffort: 'medium'}, {reasoningEffort: 'high'}], defaultReasoningEffort: 'medium'}, {id: 'catalog-b', displayName: 'Catalog B'}];
    state.selected_model = 'catalog-a'; state.reasoning_effort = 'medium'; state.capabilities.can_select_model = true;
    state.permission_mode = 'full_access'; state.permission_modes = [{id: 'full_access', label: 'Full Access'}, {id: 'read_only', label: 'Read Only'}]; state.capabilities.can_set_permission_mode = true;
    await chat.getByRole('button', {name: /^Select model, current/}).click();
    await chat.getByRole('menuitem').filter({hasText: /^Model/}).click();
    await chat.getByRole('menuitemradio', {name: 'Catalog B', exact: true}).click();
    await chat.waitForTimeout(300); assert(actions.some(command => command.action === 'select_model' && command.model_id === 'catalog-b'));
    await chat.getByRole('button', {name: /^Access mode, current:/}).click();
    await chat.getByRole('menuitem', {name: 'Read Only', exact: true}).click();
    await chat.waitForTimeout(300); assert(actions.some(command => command.action === 'set_permission_mode' && command.permission_mode === 'read_only'));
    const fileChooser = chat.waitForEvent('filechooser');
    await chat.getByRole('button', {name: 'Add files or run commands', exact: true}).click();
    await chat.getByRole('option').filter({hasText: /^File/}).click();
    await (await fileChooser).setFiles({name: 'note.txt', mimeType: 'text/plain', buffer: Buffer.from('Explicit attachment')});
    await chat.getByText('note.txt', {exact: true}).waitFor();
    await chat.waitForTimeout(300); assert(actions.some(command => command.action === 'upload_attachment' && command.mime_type === 'text/plain'));
    await input.fill('Retain on backend error'); rejectNextSend = true;
    await chat.getByRole('button', {name: 'Send message', exact: true}).click();
    await chat.getByRole('alert').filter({hasText: 'Model does not support images'}).waitFor();
    assert.equal(await input.innerText(), 'Retain on backend error');
    await chat.getByRole('button', {name: /result.txt/}).click();
    await chat.getByText('Real file contents', {exact: true}).waitFor();
    await chat.getByRole('button', {name: 'Close preview', exact: true}).click();
    await chat.getByRole('button', {name: 'Add files or run commands', exact: true}).click();
    await chat.getByRole('listbox', {name: 'Trigger suggestions'}).waitFor();
    await chat.getByRole('option').filter({hasText: 'Permission'}).click();
    await chat.getByRole('listbox', {name: '/permission matches'}).waitFor();
    await chat.getByRole('option', {name: /Read Only/}).click();
    await chat.waitForTimeout(300);
    assert(actions.filter(command => command.action === 'set_permission_mode').length >= 2);
    await chat.getByRole('button', {name: 'Add files or run commands', exact: true}).click();
    await chat.getByRole('option').filter({hasText: 'Model'}).click();
    await chat.getByRole('option', {name: /Catalog A/}).click();
    await chat.waitForTimeout(300); assert.equal(state.selected_model, 'catalog-a');
    await input.fill('Draft before history switch'); await chat.waitForTimeout(150);
    await chat.getByRole('button', {name: 'Open sidebar', exact: true}).click();
    await chat.locator('[data-row-key="session:previous-thread"]').waitFor();
    await chat.locator('[data-row-key="session:previous-thread"]').hover();
    await chat.locator('[data-row-key="session:previous-thread"]').getByRole('button').click();
    await chat.getByRole('menuitem', {name: 'Rename', exact: true}).click();
    await chat.getByRole('textbox', {name: 'Session name', exact: true}).fill('Renamed Blender chat');
    await chat.getByRole('button', {name: 'Rename', exact: true}).click();
    await chat.waitForTimeout(300); assert(actions.some(command => command.action === 'threads/rename' && command.thread_id === 'previous-thread' && command.title === 'Renamed Blender chat'));
    await chat.locator('[data-row-key="session:previous-thread"]').click();
    await chat.getByText('Authoritative restored transcript', {exact: true}).waitFor();
    assert.equal((await input.innerText()).trim(), '');
    assert(actions.some(command => command.action === 'threads/open' && command.thread_id === 'previous-thread'));
    await chat.getByRole('button', {name: 'Open sidebar', exact: true}).click();
    await chat.waitForTimeout(450);
    await chat.screenshot({path: path.join(__dirname, '../.runtime/deepblick-shell-history-expanded-tested.png')});
    await chat.locator('[data-row-key="session:test-thread"]').click();
    await chat.waitForTimeout(400); assert.equal(await input.innerText(), 'Draft before history switch');
    await chat.getByRole('button', {name: 'Open sidebar', exact: true}).click();
    await chat.getByRole('button', {name: 'Search sessions', exact: true}).click();
    await chat.getByPlaceholder('Search session names', {exact: true}).fill('Renamed');
    await chat.getByText('Renamed Blender chat', {exact: true}).first().waitFor();
    await chat.getByRole('button', {name: 'Collapse sidebar', exact: true}).click();
    await chat.screenshot({path: path.join(__dirname, '../.runtime/deepblick-shell-history-tested.png')});
    await chat.getByRole('button', {name: 'New session', exact: true}).last().click();
    await chat.waitForTimeout(400);
    assert.equal(await chat.locator('[data-chat-node-key]').count(), 0);
    await chat.getByRole('button', {name: /result.docx/}).click();
    await chat.getByText('This format has no preview in the Blender integration. Download the original file to open it in a supported application.', {exact: true}).waitFor();
    await chat.getByRole('button', {name: 'Close preview', exact: true}).click();
    await chat.getByRole('button', {name: /result.png/}).click();
    await chat.locator('img[src^="blob:"]').first().waitFor();
    assert(resourcesRead.includes('document') && resourcesRead.includes('picture'));
    await chat.getByRole('button', {name: 'Close preview', exact: true}).click();
    for (const width of [240, 380, 600]) { await chat.setViewportSize({width, height: 900}); assert(await chat.evaluate(() => document.documentElement.scrollWidth <= innerWidth)); }
    await chat.setViewportSize({width: 430, height: 900}); await chat.screenshot({path: path.join(__dirname, '../.runtime/deepblick-tested-chat.png')});
    assert.equal(errors.length, 0, errors.join('\n'));
    assert.equal(await chat.getByRole('button', {name: 'UI markieren', exact: true}).count(), 0);
    assert.equal(await chat.locator('.blender-chat').evaluate(node => getComputedStyle(node).borderTopLeftRadius), '12px');
    assert.equal(await chat.locator('[class*="AppFrame_sidebarCol"]').evaluate(node => Math.round(node.getBoundingClientRect().width)), 0, 'Collapsed history must reserve no permanent icon rail');
    await chat.getByText('Your AI partner for Blender.', {exact: true}).waitFor();
    state.artifacts = []; await chat.waitForTimeout(300);
    const heroBox = await chat.locator('[data-composer-card]').boundingBox();
    assert(heroBox.y > 150 && heroBox.y < 650, 'Original hero composer should be centered in a new conversation');
    const emptyFile = chat.waitForEvent('filechooser');
    await chat.getByRole('button', {name: 'Add files or run commands', exact: true}).click();
    await chat.getByRole('option').filter({hasText: /^File/}).click();
    await (await emptyFile).setFiles({name: 'hero-note.txt', mimeType: 'text/plain', buffer: Buffer.from('New-chat original file flow')});
    await chat.getByText('hero-note.txt', {exact: true}).waitFor(); await chat.waitForTimeout(300);
    assert.equal(await chat.locator('[class*="Toast_toast"]').count(), 0, 'Accepted file intake must not emit an empty error toast');
    await chat.screenshot({path: path.join(__dirname, '../.runtime/deepblick-newchat-attachment-tested.png')});
    await chat.getByRole('button', {name: /Remove file.*hero-note.txt/}).click();
    assert.equal(await chat.getByText('hero-note.txt', {exact: true}).count(), 0);
    state.ready = false;
    await chat.waitForTimeout(300); const newCount = actions.filter(command => ['new_chat', 'threads/new'].includes(command.action)).length;
    await chat.getByRole('button', {name: 'New session', exact: true}).click();
    await chat.waitForTimeout(300); assert.equal(actions.filter(command => ['new_chat', 'threads/new'].includes(command.action)).length, newCount, 'Connection handshake must not create a second thread');
    state.ready = true; Object.assign(state.capabilities, {can_goal: true, can_plan: true, can_compact: true, can_export: true});
    state.collaboration_modes = [{mode: 'default', name: 'Default'}, {mode: 'plan', name: 'Plan'}]; state.collaboration_mode = 'default';
    await chat.waitForTimeout(300);
    const plus = chat.getByRole('button', {name: 'Add files or run commands', exact: true});
    await plus.click(); await chat.getByRole('option').filter({hasText: /^Plan/}).click();
    await chat.getByRole('option', {name: 'Plan', exact: true}).click(); await chat.waitForTimeout(300);
    assert(actions.some(command => command.action === 'set_mode' && command.mode === 'plan'));
    await plus.click(); await chat.getByRole('option').filter({hasText: /^Goal/}).click();
    await chat.getByRole('textbox', {name: 'Goal objective', exact: true}).fill('Create a clean Blender asset');
    await chat.getByRole('button', {name: 'Save goal', exact: true}).click(); await chat.waitForTimeout(300);
    assert(actions.some(command => command.action === 'goal/set' && command.objective === 'Create a clean Blender asset' && !Object.hasOwn(command, 'token_budget')));
    await plus.click(); await chat.getByRole('option').filter({hasText: /^Compact/}).click(); await chat.waitForTimeout(300);
    assert(actions.some(command => command.action === 'compact'));
    await plus.click(); await chat.getByRole('option').filter({hasText: /^Export/}).click();
    const exported = chat.waitForEvent('download'); await chat.getByRole('option', {name: 'JSON', exact: true}).click(); await exported;
    assert(actions.some(command => command.action === 'export_chat' && command.format === 'json'));
    const receipt = {result: 'PASS', productionComponents: ['AppFrame', 'SidebarRoot/HeaderLeadingControls', 'WorkspaceBrowser/Rows', 'ConversationMainPanel/Header/SessionHeader', 'ConversationContent/ConversationSession/DefaultConversationViews', 'HeroShell/DeepblickHero', 'RenameSessionMenuItem/SessionRenameDialog', 'InputTriggerController/MenuView', 'PopupSelectController/PopupSelectView', 'ChatView', 'InputBar/Lexical', 'ToolCallTree/GenericToolCard', 'ApprovalPanel', 'ModelSelect', 'PermissionSelect', 'ComposerAttachments', 'MessageImages', 'Modal/CodeBlock'], checked: ['zero-width collapsed history/no permanent rail', 'no permanent upper toolbar', 'original centered newchat composition', 'original Plus File chooser/attachment/remove in newchat', 'connection-handshake newthread guard', 'Plus Zeichnen + Escape draft preservation', 'explicit view inclusion in normal Send', 'original shell/history expansion', 'real thread open/new/rename', 'indexed-title search', 'per-thread draft restoration', 'Plus permission/model/goal/plan/compact/export action adapters', 'streaming', 'two tool calls', 'cross-item event order', 'tool input/result', 'stop', 'denied approval', 'flat form', 'question response', 'actual catalog/model action', 'permission action', 'file upload', 'failed-send draft retention', 'new-thread reset', 'authenticated image/text loads', 'Office fallback', '240/380/600px'], actions: actions.map(command => command.action)};
    fs.writeFileSync(path.join(__dirname, '../.runtime/deepblick-frontend-receipt.json'), JSON.stringify(receipt, null, 2));
    console.log('DEEPBLICK_FRONTEND_CONTRACT_PASS');
  } finally { if (browser) await browser.close(); if (server) await new Promise(resolve => server.close(resolve)); }
})().catch(error => { console.error(error); process.exitCode = 1; });
