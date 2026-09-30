// Full-page screenshots of each piece (standalone and ?embed) at 1280 and 390 px, for before/after comparison.
// Usage: node shots.js <outdir> [piece,piece]   then: python compare_shots.py <dirA> <dirB>
const {chromium}=require('playwright-core');const fs=require('fs');const out=process.argv[2];fs.mkdirSync(out,{recursive:true});
(async()=>{const b=await chromium.launch({executablePath:process.env.CHROME||'/opt/pw-browsers/chromium',args:['--no-sandbox']});
for(const p of (process.argv[3]?process.argv[3].split(','):['superior-ice','meridian','listen']))for(const q of ['','?embed'])for(const w of [1280,390]){
 const c=await b.newContext({viewport:{width:w,height:900},reducedMotion:'reduce'});const pg=await c.newPage();
 await pg.goto(`http://localhost:8765/${p}/index.html${q}`,{waitUntil:'networkidle'});await pg.waitForTimeout(2500);
 await pg.screenshot({path:`${out}/${p}_${q?'embed':'standalone'}_${w}.png`,fullPage:true});await c.close();}
await b.close();})();
