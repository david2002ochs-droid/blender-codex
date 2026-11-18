// Real MediaRecorder, synthetic canvas source: never captures the desktop.
const fs=require('node:fs'), path=require('node:path'), assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||path.join(__dirname,'../../tests/browser/node_modules/playwright'));
(async()=>{
  const state=JSON.parse(fs.readFileSync(path.resolve(__dirname,'../../.runtime/screen-recorder-server.json')));
  const browser=await chromium.launch({headless:true,executablePath:process.env.RECORDER_CHROMIUM});
  try{
    const context=await browser.newContext({acceptDownloads:true});
    const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.addInitScript(()=>{
      Object.defineProperty(navigator.mediaDevices,'getDisplayMedia',{value:async options=>{
        window.requestedCapture=options;
        if(window.rejectCapture)throw new DOMException('test refusal','NotAllowedError');
        const canvas=document.createElement('canvas');canvas.width=320;canvas.height=180;
        const ctx=canvas.getContext('2d');let n=0;
        const draw=()=>{ctx.fillStyle=n++%2?'#246899':'#b85a31';ctx.fillRect(0,0,320,180);};draw();
        const interval=setInterval(draw,60);const source=canvas.captureStream(15);window.testSource=source;
        source.getTracks()[0].addEventListener('ended',()=>clearInterval(interval));return source;
      }});
    });
    await page.goto(state.url);
    assert(await page.locator('#start').isDisabled());
    await page.evaluate(()=>window.rejectCapture=true);await page.click('#choose');
    await page.waitForFunction(()=>document.querySelector('#error').textContent.includes('abgebrochen'));
    assert(await page.locator('#start').isDisabled());
    await page.evaluate(()=>window.rejectCapture=false);await page.click('#choose');
    await page.waitForFunction(()=>!document.querySelector('#start').disabled);
    assert.equal(await page.evaluate(()=>window.requestedCapture.audio),false);
    assert.equal(await page.locator('body').getAttribute('data-recording'),'false');
    await page.click('#start');await page.waitForFunction(()=>document.body.dataset.recording==='true');
    assert(await page.locator('#choose').isDisabled());assert(await page.locator('#start').isDisabled());
    await page.waitForFunction(()=>document.querySelector('#timer').textContent!=='00:00');
    const downloadEvent=page.waitForEvent('download');await page.click('#stop');const file=await downloadEvent;
    const output=path.resolve(__dirname,'../../.runtime/recorder-synthetic-test.webm');await file.saveAs(output);
    const bytes=fs.readFileSync(output);assert(bytes.length>100);assert.equal(bytes.subarray(0,4).toString('hex'),'1a45dfa3');
    assert.equal(await page.locator('body').getAttribute('data-recording'),'false');
    assert(await page.locator('#stop').isDisabled());assert(await page.locator('#download').isVisible());
    const video=await page.evaluate(async()=>{const el=document.createElement('video');el.src=document.querySelector('#download').href;return await new Promise((resolve,reject)=>{el.onloadedmetadata=()=>resolve({width:el.videoWidth,height:el.videoHeight});el.onerror=()=>reject(new Error('Invalid video'));});});
    assert.deepEqual(video,{width:320,height:180});
    await page.click('#choose');await page.waitForFunction(()=>!document.querySelector('#start').disabled);await page.click('#start');
    await page.waitForTimeout(400);const endedDownload=page.waitForEvent('download');
    await page.evaluate(()=>window.testSource.getVideoTracks()[0].dispatchEvent(new Event('ended')));await endedDownload;
    assert.equal(await page.locator('body').getAttribute('data-recording'),'false');assert.deepEqual(errors,[]);
    await page.screenshot({path:path.resolve(__dirname,'../../.runtime/recorder-tested.png')});
    console.log('RECORDER_PASS: permission refusal, source preview, real WebM start/stop/download/metadata, source-ended finalization; synthetic source only.');
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
