const {chromium}=require('playwright-core');
const pages=['superior-ice/index.html','meridian/index.html','listen/index.html'];
(async()=>{const b=await chromium.launch({executablePath:(process.env.CHROME||'/opt/pw-browsers/chromium'),args:['--no-sandbox','--autoplay-policy=no-user-gesture-required']});
for(const p of pages){console.log('\n=====',p);
 // 404 + mp3 failures
 let c=await b.newContext({viewport:{width:1280,height:900}});let pg=await c.newPage();
 pg.on('response',r=>r.status()>=400&&console.log('  HTTP',r.status(),r.url().replace('http://localhost:8765','')));
 pg.on('requestfailed',r=>console.log('  reqfail',r.failure().errorText,r.url().replace('http://localhost:8765','')));
 await pg.goto('http://localhost:8765/'+p,{waitUntil:'networkidle'});await pg.waitForTimeout(1200);
 // keyboard walk
 const stops=[];await pg.evaluate(()=>document.body.focus());
 for(let i=0;i<60;i++){await pg.keyboard.press('Tab');const s=await pg.evaluate(()=>{const e=document.activeElement;if(!e||e===document.body)return null;const cs=getComputedStyle(e);const r=e.getBoundingClientRect();return{tag:e.tagName.toLowerCase(),id:e.id,role:e.getAttribute('role'),name:(e.getAttribute('aria-label')||e.textContent||e.title||'').trim().replace(/\s+/g,' ').slice(0,50),ol:cs.outlineStyle+' '+cs.outlineWidth,shadow:cs.boxShadow!=='none',vis:r.width>0&&r.height>0&&r.bottom>0&&r.top<innerHeight}});if(!s)break;stops.push(s);}
 console.log('  tab stops:',stops.length);const seen=new Set();stops.forEach((s,i)=>{const k=s.tag+s.id+s.name;if(seen.has(k)){console.log('   (cycle at',i,')');return}seen.add(k);});
 console.log('  ',stops.map(s=>`${s.tag}${s.id?'#'+s.id:''}${s.role?'['+s.role+']':''}"${s.name}"${(s.ol.startsWith('none')||s.ol.startsWith('0'))&&!s.shadow?' NOFOCUSRING':''}${s.vis?'':' OFFSCREEN'}`).join('\n   '));
 // reflow 320 and 640 (200% zoom equivalent)
 for(const w of [640,320]){await pg.setViewportSize({width:w,height:800});await pg.waitForTimeout(500);const o=await pg.evaluate(()=>({sw:document.documentElement.scrollWidth,cw:document.documentElement.clientWidth}));console.log(`  @${w}px scrollWidth=${o.sw} clientWidth=${o.cw} ${o.sw>o.cw+1?'HORIZONTAL SCROLL':'ok'}`);}
 await c.close();
 // forced colors + reduced motion
 c=await b.newContext({viewport:{width:1280,height:900},forcedColors:'active',reducedMotion:'reduce'});pg=await c.newPage();await pg.goto('http://localhost:8765/'+p,{waitUntil:'networkidle'});await pg.waitForTimeout(800);
 await pg.screenshot({path:p.split('/')[0]+'_forced.png'});await c.close();
}
await b.close();})();
