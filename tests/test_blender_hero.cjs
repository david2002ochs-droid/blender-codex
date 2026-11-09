// Actual production bundle, explicit backend fixture; no model or Blender start.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const root=path.resolve(__dirname,'..');
(async()=>{
 let browser,server; const actions=[],errors=[],screenshots=[];
 const state={thread_id:'hero-fixture',project_root:'C:/Blender',ready:true,busy:false,status:'Connected',messages:[],tool_calls:[],reasoning:[],approvals:[],context:{},settings:{},models:[],attachments:[],artifacts:[],threads:[],capabilities:{can_upload_attachments:true,max_attachment_bytes:8388608}};
 try {
  server=http.createServer(async(req,res)=>{
   if(req.url.startsWith('/api/')){
    assert.equal(req.headers['x-codex-token'],'hero-test');res.setHeader('Content-Type','application/json');
    if(req.url==='/api/state'){res.end(JSON.stringify(state));return;}
    let body='';for await(const c of req)body+=c;const command=JSON.parse(body);actions.push(command);res.end('{"ok":true}');return;
   }
   const file={'/':'index.html','/app.js':'app.js','/styles.css':'styles.css'}[req.url];if(!file){res.statusCode=404;res.end();return;}
   res.setHeader('Content-Type',file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html');res.end(fs.readFileSync(path.join(root,'blender_codex/web',file)));
  });
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH,args:['--disable-gpu','--in-process-gpu']});
  const page=await browser.newPage();page.on('pageerror',e=>errors.push(e.message));page.setDefaultTimeout(8000);
  for(const width of [240,430,684]){
   await page.setViewportSize({width,height:900});await page.goto(`http://127.0.0.1:${server.address().port}/#token=hero-test`);
   await page.locator('[data-blender-hero]').waitFor();
   assert.equal(await page.getByRole('button',{name:/^(Connect|Disconnect)$/}).count(),0);
   assert.equal(await page.locator('[class*="Brand_columns"], [class*="Brand_selection"]').count(),0);
   const geometry=await page.locator('[data-blender-hero]').evaluate(el=>{const a=el.getBoundingClientRect(),w=el.querySelector('.blender-hero-wordmark').getBoundingClientRect(),t=el.querySelector('.blender-hero-tagline').getBoundingClientRect();return{center:a.x+a.width/2,word:w.x+w.width/2,tag:t.x+t.width/2,overflow:document.documentElement.scrollWidth>innerWidth}});
   assert(Math.abs(geometry.center-geometry.word)<1&&Math.abs(geometry.center-geometry.tag)<1);assert.equal(geometry.overflow,false);
   const file=`.runtime/blender-hero-${width}-tested.png`;await page.screenshot({path:path.join(root,file),fullPage:true});screenshots.push(file);
  }
  await page.getByRole('button',{name:'Open sidebar',exact:true}).click();await page.getByRole('button',{name:'Settings',exact:true}).click();
  await page.getByRole('dialog').waitFor();const save=page.getByRole('button',{name:'Save settings',exact:true});assert.equal(await save.isEnabled(),true);
  state.busy=true;await page.getByText('Finish or stop the current response before saving connection settings.',{exact:true}).waitFor();assert.equal(await save.isDisabled(),true);
  state.busy=false;await page.waitForTimeout(400);await save.click();await page.getByRole('dialog').waitFor({state:'detached'});
  assert(actions.some(x=>x.action==='settings'));assert(!actions.some(x=>['connect','disconnect'].includes(x.action)));
  assert.deepEqual(errors,[]);
  const hash=f=>crypto.createHash('sha256').update(fs.readFileSync(path.join(root,f))).digest('hex');
  fs.writeFileSync(path.join(root,'.runtime/blender-hero-receipt.json'),JSON.stringify({status:'BLENDER_HERO_PASS',testedAt:new Date().toISOString(),appJsSha256:hash('blender_codex/web/app.js'),cssSha256:hash('blender_codex/web/styles.css'),screenshots,evidence:'actual production build with explicit backend fixture; backend auto-connect tested by integration owner',errors},null,2));
  console.log('BLENDER_HERO_PASS');
 }finally{if(browser)await browser.close();if(server)await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1;});
