// static server with HTTP range support (python http.server lacks it)
const http=require('http'),fs=require('fs'),path=require('path');
const root=path.resolve(__dirname,'../..');
const types={'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.mp3':'audio/mpeg','.png':'image/png','.jpg':'image/jpeg','.webp':'image/webp','.woff2':'font/woff2'};
http.createServer((q,r)=>{let p;try{p=decodeURIComponent(q.url.split('?')[0]);}catch(e){r.writeHead(400);return r.end('bad url');}if(p.endsWith('/'))p+='index.html';const f=path.join(root,p);
 if(!(f===root||f.startsWith(root+path.sep))||!fs.existsSync(f)||fs.statSync(f).isDirectory()){r.writeHead(404);return r.end('nf');}
 const s=fs.statSync(f),t=types[path.extname(f)]||'application/octet-stream',rg=q.headers.range;
 if(rg){const m=/bytes=(\d*)-(\d*)/.exec(rg)||['','',''];const a=m[1]?+m[1]:0,b=m[2]?+m[2]:s.size-1;r.writeHead(206,{'Content-Type':t,'Accept-Ranges':'bytes','Content-Range':`bytes ${a}-${b}/${s.size}`,'Content-Length':b-a+1});fs.createReadStream(f,{start:a,end:b}).pipe(r);}
 else{r.writeHead(200,{'Content-Type':t,'Accept-Ranges':'bytes','Content-Length':s.size});fs.createReadStream(f).pipe(r);}
}).listen(8765,'127.0.0.1',()=>console.log('up on 127.0.0.1:8765'));   // loopback only: it serves the whole repo
