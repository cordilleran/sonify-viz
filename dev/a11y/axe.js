const {chromium}=require('playwright-core');const fs=require('fs');const axeSrc=fs.readFileSync(require.resolve('axe-core/axe.min.js'),'utf8');
const pages=['superior-ice/index.html','meridian/index.html','listen/index.html'];
const sizes=[[1280,900],[390,844]];
(async()=>{const b=await chromium.launch({executablePath:(process.env.CHROME||'/opt/pw-browsers/chromium'),args:['--no-sandbox']});const out={};
for(const p of pages)for(const [w,h] of sizes){const c=await b.newContext({viewport:{width:w,height:h}});const pg=await c.newPage();const errs=[];pg.on('console',m=>m.type()==='error'&&errs.push(m.text()));pg.on('requestfailed',r=>errs.push('reqfail '+r.url()));
 await pg.goto('http://localhost:8765/'+p,{waitUntil:'networkidle'});await pg.waitForTimeout(1500);
 await pg.evaluate(axeSrc);const r=await pg.evaluate(()=>axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa','best-practice']}}));
 out[`${p}@${w}`]={errs,violations:r.violations.map(v=>({id:v.id,impact:v.impact,help:v.help,tags:v.tags.filter(t=>t.startsWith('wcag')&&!t.startsWith('wcag2a')||/^wcag\d{3,4}$/.test(t)),nodes:v.nodes.length,ex:v.nodes.slice(0,3).map(n=>n.target.join(' ')+' :: '+(n.failureSummary||'').split('\n').slice(1,3).join(' | '))})),incomplete:r.incomplete.map(v=>({id:v.id,nodes:v.nodes.length}))};
 await c.close();}
fs.writeFileSync('axe-results.json',JSON.stringify(out,null,1));
for(const [k,v] of Object.entries(out)){console.log('\n##',k,'console/req errors:',v.errs.length);v.errs.slice(0,3).forEach(e=>console.log('   ',e.slice(0,140)));v.violations.forEach(x=>console.log(`  [${x.impact}] ${x.id} x${x.nodes} ${x.tags.join(',')} — ${x.help}\n      ${x.ex[0]||''}`));console.log('  needs-review:',v.incomplete.map(i=>i.id+'x'+i.nodes).join(', '));}
await b.close();})();
