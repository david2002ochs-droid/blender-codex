'use strict';
const http=require('node:http'), fs=require('node:fs'), path=require('node:path');
const root=path.resolve(__dirname,'../..');
const html=fs.readFileSync(path.join(__dirname,'index.html'));
const server=http.createServer((req,res)=>{
  if(req.headers.host!==`127.0.0.1:${server.address().port}`){res.writeHead(403);res.end();return;}
  if(req.method!=='GET'){res.writeHead(405);res.end();return;}
  res.setHeader('Cache-Control','no-store');res.setHeader('X-Content-Type-Options','nosniff');
  if(req.url==='/health'){res.setHeader('Content-Type','application/json');res.end(JSON.stringify({app:'blender-test-recorder',pid:process.pid}));return;}
  if(req.url!=='/'){res.writeHead(404);res.end();return;}
  res.setHeader('Content-Type','text/html; charset=utf-8');
  res.setHeader('Content-Security-Policy',"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; media-src blob:; connect-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'");
  res.setHeader('Permissions-Policy','microphone=(), camera=(), display-capture=(self)');
  res.end(html);
});
server.listen(0,'127.0.0.1',()=>{
  const dir=path.join(root,'.runtime');fs.mkdirSync(dir,{recursive:true});
  const state={app:'blender-test-recorder',pid:process.pid,url:`http://127.0.0.1:${server.address().port}/`,started_at:new Date().toISOString()};
  fs.writeFileSync(path.join(dir,'screen-recorder-server.json'),JSON.stringify(state,null,2));
  console.log(state.url);
});
