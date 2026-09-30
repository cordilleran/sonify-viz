// Runs axe-core and a keyboard walk on each piece in three modes: standalone, ?embed, and inside an iframe wrapper.
// Usage: node check.js [label]   (server.js must be running on 8765). Prints a compact table and writes check-<label>.json
const {chromium}=require('playwright-core');const fs=require('fs'),path=require('path');
const axeSrc=fs.readFileSync(require.resolve('axe-core/axe.min.js'),'utf8');
const label=process.argv[2]||'run';const pieces=['superior-ice','meridian','listen'];
const modes={standalone:p=>`/${p}/index.html`,embed:p=>`/${p}/index.html?embed`,iframe:p=>`/dev/a11y/wrapper.html?p=${p}`};
(async()=>{const b=await chromium.launch({executablePath:process.env.CHROME||'/opt/pw-browsers/chromium',args:['--no-sandbox']});const out={};
for(const p of pieces)for(const [m,url] of Object.entries(modes))for(const w of [1280,390]){
 const c=await b.newContext({viewport:{width:w,height:900}});const pg=await c.newPage();
 await pg.goto('http://localhost:8765'+url(p),{waitUntil:'networkidle'});await pg.waitForTimeout(1500);
 const target=m==='iframe'?pg.frames().find(f=>f!==pg.mainFrame()):pg;
 await target.evaluate(axeSrc);
 const r=await target.evaluate(()=>axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa','best-practice']}}));
 const rules={};r.violations.forEach(v=>rules[v.id]=v.nodes.length);
 // tab walk: count stops until focus leaves or cycles
 await pg.evaluate(()=>document.body.focus());const seen=[];
 for(let i=0;i<70;i++){await pg.keyboard.press('Tab');const s=await pg.evaluate(()=>{const f=document.querySelector('iframe');let e=document.activeElement;if(e&&e.tagName==='IFRAME'&&e.contentDocument)e=e.contentDocument.activeElement;return e&&e!==document.body?(e.tagName+'#'+e.id+'|'+(e.getAttribute('aria-label')||e.textContent||'').trim().slice(0,30)):null});if(!s||seen.includes(s)&&seen.length>3&&s===seen[0])break;seen.push(s);}
 out[`${p}|${m}|${w}`]={rules,tabStops:seen.length};await c.close();}
fs.writeFileSync(`check-${label}.json`,JSON.stringify(out,null,1));
console.log('piece|mode|width | tabstops | failing rules (nodes)');
for(const [k,v] of Object.entries(out))console.log(k.padEnd(28),String(v.tabStops).padStart(3),' ',Object.entries(v.rules).map(([a,n])=>`${a}(${n})`).join(' ')||'none');
await b.close();})();
