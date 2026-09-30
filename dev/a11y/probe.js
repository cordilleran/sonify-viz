const {chromium}=require('playwright-core');const fs=require('fs');const axeSrc=fs.readFileSync(require.resolve('axe-core/axe.min.js'),'utf8');
(async()=>{const b=await chromium.launch({executablePath:(process.env.CHROME||'/opt/pw-browsers/chromium'),args:['--no-sandbox']});
const c=await b.newContext({viewport:{width:1280,height:1000}});
// 1 contrast pairs across the three pages
const pairs={};
for(const p of ['superior-ice','meridian','listen']){const pg=await c.newPage();await pg.goto(`http://localhost:8765/${p}/index.html`,{waitUntil:'networkidle'});await pg.waitForTimeout(1200);await pg.evaluate(axeSrc);
 const r=await pg.evaluate(()=>axe.run(document,{runOnly:['color-contrast']}));
 for(const v of r.violations)for(const n of v.nodes){const d=n.any[0].data;const k=`${d.fgColor} on ${d.bgColor}`;pairs[p+' | '+k]=pairs[p+' | '+k]||{ratio:d.contrastRatio,need:d.expectedContrastRatio,n:0,ex:n.target.join(' ').slice(0,50)};pairs[p+' | '+k].n++;}
 // 2 seek slider value text, canvases
 console.log('\n##',p);
 console.log(' seek:',await pg.evaluate(()=>{const s=document.querySelector('input[type=range]');return s?`aria-valuetext=${s.getAttribute('aria-valuetext')} value=${s.value}`:'none'}));
 console.log(' canvases:',await pg.evaluate(()=>[...document.querySelectorAll('canvas')].map(e=>`#${e.id} hidden=${e.getAttribute('aria-hidden')} label=${(e.getAttribute('aria-label')||'').slice(0,70)||'NONE'} tabindex=${e.getAttribute('tabindex')} role=${e.getAttribute('role')}`)));
 await pg.close();}
console.log('\n=== failing contrast pairs (page | fg on bg)');Object.entries(pairs).sort((a,b)=>a[1].ratio-b[1].ratio).forEach(([k,v])=>console.log(`${v.ratio}:1 (needs ${v.need}) x${v.n}  ${k}  e.g. ${v.ex}`));
// 3 does canvas#over do anything on keys?
const pg=await c.newPage();await pg.goto('http://localhost:8765/superior-ice/index.html',{waitUntil:'networkidle'});await pg.waitForTimeout(1500);
const before=await pg.evaluate(()=>document.getElementById('focusT')?.textContent);
await pg.locator('#over').focus();for(const k of ['ArrowRight','ArrowDown','Enter']){await pg.keyboard.press(k);}
const after=await pg.evaluate(()=>document.getElementById('focusT')?.textContent);
console.log('\ncanvas#over arrow/enter changes focus text?',before!==after);
await b.close();})();
