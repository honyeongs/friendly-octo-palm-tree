import assert from "node:assert/strict";
import {createServer} from "node:http";
import {readFile,mkdir,writeFile} from "node:fs/promises";
import {spawnSync} from "node:child_process";
import {fileURLToPath,pathToFileURL} from "node:url";
import {join,resolve,extname,sep} from "node:path";
const root=fileURLToPath(new URL("../../",import.meta.url));
const dist=join(root,"website/dist");
const config=JSON.parse(await readFile(join(dist,"site-config.json"),"utf8"));
const {chromium}=process.env.PLAYWRIGHT_MODULE ? await import(pathToFileURL(process.env.PLAYWRIGHT_MODULE).href) : await import("playwright");
const python=process.env.PYTHON || "python";
let server;
let base=process.env.SITE_URL;
if(!base){
 server=createServer(async(req,res)=>{
  try{
   const pathname=decodeURIComponent(new URL(req.url,"http://local").pathname);
   const file=resolve(dist,"."+ (pathname==="/" ? "/index.html" : pathname));
   if(!file.startsWith(resolve(dist)+sep)){res.writeHead(403);res.end();return;}
   const data=await readFile(file);
   res.setHeader("Content-Type",({".js":"text/javascript",".wasm":"application/wasm",".html":"text/html",".css":"text/css",".json":"application/json",".webmanifest":"application/manifest+json",".svg":"image/svg+xml",".png":"image/png"})[extname(file)] || "application/octet-stream");
   res.end(data);
  }catch{res.writeHead(404);res.end();}
 });
 await new Promise(done=>server.listen(0,"127.0.0.1",done));
 base="http://127.0.0.1:"+server.address().port;
}
base=base.replace(/\/$/,"");
const output=join(root,"test-results/website");
await mkdir(output,{recursive:true});
const browser=await chromium.launch({headless:true});
const checks=[];
const context=await browser.newContext({viewport:{width:1440,height:1000},acceptDownloads:true,locale:"ko-KR"});
const page=await context.newPage();
const errors=[],transfers=[],external=[];
context.on("request",request=>{
 if(!request.url().startsWith(base+"/")&&!request.url().startsWith("blob:")&&!request.url().startsWith("data:"))external.push(request.url());
 if(request.method()!=="GET")transfers.push(request.method());
});
page.on("pageerror",error=>errors.push(error.message));
page.on("dialog",()=>errors.push("Unexpected input execution"));
function mark(id){checks.push({id,status:"passed"});if(process.env.WEBSITE_VERBOSE)console.log(config.id+": "+id+" passed");}
async function text(id,value){await page.waitForFunction(({id,value})=>document.getElementById(id)?.textContent===value,{id,value},{timeout:90000});}
async function exported(){
 const event=page.waitForEvent("download");
 await page.locator("#export").click();
 const download=await event;
 return JSON.parse(await readFile(await download.path(),"utf8"));
}
function native(args){
 const run=spawnSync(python,["run.py",...args],{cwd:root,encoding:"utf8",timeout:30000,env:{...process.env,PYTHONPATH:join(root,"src")}});
 assert.ok([0,1].includes(run.status),"Native fixture analyzer failed");
 return JSON.parse(run.stdout);
}
async function runExample(){
 if(config.id==="inspector"){
  await page.locator(".example-button").click();
  await page.locator("#inspect").click();
  await text("message","검사 완료");
 }else if(config.id==="netsec"){
  await page.locator("#raw-example").click();
  assert.equal(await page.locator("#raw-analyze").isDisabled(),true,"Analyze must wait for the example download");
  await text("raw-status","합성 로그 선택됨");await page.locator("#raw-analyze").click();
  await text("raw-status","분석 완료 · 보고서 B");
 }else await text("status","분석 완료");
}
try{
 await page.goto(base+"/",{waitUntil:"networkidle"});
 await page.locator("#install-app").waitFor();
 if(config.id==="netsec")await page.evaluate(()=>{
  const original=window.fetch.bind(window);
  window.fetch=async(...args)=>{if(String(args[0]).includes("/samples/demo.log"))await new Promise(done=>setTimeout(done,500));return original(...args);};
 });
 await runExample();mark("browser-local-analysis");
 if(config.id==="inspector"){
  const report=await exported();
  const expected=native(["inspect","website/dist/samples/example.zip"]);
  expected.file.name="synthetic-example.zip";
  assert.deepEqual(report,expected);
  assert.equal(report.assessment.safe_to_open,null);
  await page.locator('[data-tab="members"]').click();assert.equal(await page.locator("#members tr").count(),3);
  const canary={name:"PRIVATE_CANARY.txt",mimeType:"text/plain",buffer:Buffer.from("INERT CONTENT")};
  await page.locator("#file").setInputFiles(canary);await page.locator("#expected").fill("0".repeat(64));
  await page.locator("#inspect").click();await text("message","검사 완료");
  assert.equal((await exported()).integrity.status,"mismatch");
  await page.locator("#reset").click();await runExample();
 }else if(config.id==="endpoint"){
  const report=await exported();
  assert.deepEqual(report,native(["analyze","samples/incident-chain.json"]));
  await page.locator("#file").setInputFiles(join(root,"samples/incident-chain.xml"));
  await text("status","분석 완료");
  assert.deepEqual(await exported(),native(["analyze","samples/incident-chain.xml"]));
  await page.locator('[data-view="processes"]').click();assert.equal(await page.locator("#process-list .process-row").count(),5);
  await page.locator('[data-view="validation"]').click();await page.waitForFunction(()=>document.querySelector("#validation-view")?.textContent.includes("18"));
  await page.locator("#file").setInputFiles({name:"PRIVATE_CANARY.xml",mimeType:"application/xml",buffer:Buffer.from('<!DOCTYPE Events [<!ENTITY x "INERT">]><Events>&x;</Events>')});
  await page.waitForFunction(()=>document.querySelector("#status").textContent.includes("올바르지"));
  assert.equal(await page.locator("#analysis").isHidden(),true);
  await page.locator("#reset").click();await text("status","분석 완료");await page.locator('[data-view="alerts"]').click();
 }else{
  const report=await exported();const expected=native(["analyze-ssh","samples/ssh/demo.log"]);expected.source="synthetic-ssh.log";assert.deepEqual(report,expected);
  await page.locator("#raw-log").setInputFiles(join(root,"samples/ssh/journal.jsonl"));
  await page.locator(".raw-input summary").click();
  await page.locator("#raw-pcap").setInputFiles(join(root,"samples/packets/demo.pcap"));
  await page.locator("#raw-ip").fill("192.0.2.100");await page.locator("#raw-analyze").click();await text("raw-status","분석 완료 · 보고서 B");
  const combined=await exported();assert.equal(combined.success_after_failures.length,1);assert.equal(combined.network.statistics.connection_attempts,6);
  await page.locator("#reset").click();await text("name-b","journal.jsonl");
  await runExample();
 }
 mark("native-python-parity-and-boundaries");
 const recovery=await page.evaluate(async()=>{
  const {callEngine}=await import("/engine-client.js");
  const controller=new AbortController();
  const pending=callEngine("/api/health",null,{},controller.signal);
  controller.abort();
  let aborted=false;try{await pending;}catch(error){aborted=error.name==="AbortError";}
  const response=await callEngine("/api/health");
  return {aborted,ready:response.data.status==="ready"};
 });
 assert.deepEqual(recovery,{aborted:true,ready:true});mark("worker-cancellation-and-recovery");
 const manifest=await page.evaluate(async()=>await(await fetch("/manifest.webmanifest")).json());
 assert.equal(manifest.display,"standalone");assert.equal(manifest.scope,"/");assert.equal(manifest.start_url,"/");
 assert.deepEqual(manifest.icons.map(x=>x.sizes),["192x192","512x512"]);
 for(const icon of manifest.icons){
  const response=await page.request.get(base+icon.src);assert.equal(response.status(),200);
 }
 const cdp=await context.newCDPSession(page);
 const appManifest=await cdp.send("Page.getAppManifest");
 assert.equal(appManifest.errors?.filter(error=>error.critical).length || 0,0);
 assert.ok(appManifest.data.includes("standalone"));mark("pwa-manifest-and-icons");
 const shortcutEvent=page.waitForEvent("download");await page.locator("#windows-shortcut").click();
 const shortcut=await shortcutEvent;assert.match(await readFile(await shortcut.path(),"utf8"),new RegExp(config.tools.find(t=>t.id===config.id).url.replace(/[.*+?^$()|[\]\\]/g,"\\$&")));
 mark("windows-shortcut-download");
 for(const [name,width,height] of [["desktop",1440,1000],["mobile",390,844],["compact",360,800]]){
  await page.setViewportSize({width,height});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,"Horizontal page overflow");
  assert.equal(await page.locator("img").evaluateAll(nodes=>nodes.every(n=>n.complete&&n.naturalWidth>0)),true);
  await page.locator(".other-tools summary").click();
  assert.ok(await page.locator("#other-tools").evaluate(node=>{const r=node.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth;}),"Tools menu outside viewport");
  await page.locator(".other-tools summary").click();
  await page.screenshot({path:join(output,name+".png"),fullPage:true});
 }
 mark("desktop-and-two-mobile-layouts");
 if(!(await page.locator("#install-app").getAttribute("data-ready"))){
  await page.locator("#install-app").click();await page.locator(".install-dialog").waitFor();
  assert.equal(await page.locator(".install-dialog a[download]").count(),2);
  await page.locator("#close-install").click();
 }
 mark("install-control");
 await page.waitForFunction(()=>document.querySelector("#offline-state")?.textContent==="오프라인 준비 완료",{},{timeout:90000});
 const cached=await page.evaluate(async()=>{const keys=await caches.keys();return(await Promise.all(keys.map(async key=>(await(await caches.open(key)).keys()).map(r=>r.url)))).flat();});
 assert.ok(cached.length>20);assert.equal(cached.some(url=>url.includes("PRIVATE_CANARY")||url.includes("/api/")),false);
 await context.setOffline(true);await page.reload();await page.locator("#install-app").waitFor();await runExample();
 mark("offline-reload-and-analysis");
 await context.setOffline(false);
 await page.locator("#session-clear").click();await page.waitForLoadState("networkidle");
 if(config.id==="inspector")assert.equal(await page.locator("#results").isHidden(),true);
 else if(config.id==="netsec")await text("name-b","journal.jsonl");
 else await text("status","분석 완료");
 mark("session-reset-no-input-persistence");
 assert.deepEqual(errors,[]);assert.deepEqual(transfers,[]);assert.deepEqual(external,[]);
 mark("no-input-network-transfer-or-page-errors");
 await writeFile(join(output,"summary.json"),JSON.stringify({app:config.id,checks,notes:["Synthetic fixtures only.","OS-level app installation still requires a user browser confirmation."]},null,2));
 console.log(config.id+": "+checks.length+" website checks passed");
}finally{
 await context.close();await browser.close();
 if(server){server.closeAllConnections();await new Promise(done=>server.close(done));}
}
