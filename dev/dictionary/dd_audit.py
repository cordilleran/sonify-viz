import yaml,glob,os,collections,pyarrow.parquet as pq,pyarrow.compute as pc,json
files=['data/parquet/data-dict.yaml','data/climate/parquet/data-dict.yaml']+sorted(glob.glob('tracks/mapping/*/data-dict.yaml'))
G=collections.Counter();rows=[]
allkeys=collections.Counter()
for f in files:
    d=yaml.safe_load(open(f));base=os.path.dirname(f);T=d['tables']
    top=set(d.keys())
    for t in T:
        pf=os.path.join(base,t['source']['parquet']);tab=pq.read_table(pf);cols={c['name']:c for c in t['columns']}
        G['tables']+=1
        undocumented=[c for c in tab.column_names if c not in cols];ghost=[c for c in cols if c not in tab.column_names]
        if undocumented:rows.append((f,t['name'],'parquet columns not in dictionary',undocumented))
        if ghost:rows.append((f,t['name'],'dictionary columns not in parquet',ghost))
        if 'description' not in t:rows.append((f,t['name'],'table has no description',''))
        for c in t['columns']:
            G['cols']+=1;n=c['name'];ty=c.get('type','');allkeys.update(c.keys())
            con=c.get('constraints',[]) or []
            if 'description' not in c and ty!='enum':G['no_desc']+=1;rows.append((f,t['name'],'column no description',n))
            if ty.startswith('number') and 'units' not in c and 'quantity' in ty:rows.append((f,t['name'],'quantity without units',n))
            if ty.startswith('number') and 'quantity' not in ty:G['number_nonquantity']+=1
            if ty.startswith('number') and 'range' not in c:G['num_no_range']+=1;rows.append((f,t['name'],'numeric column without range',n))
            if 'required' not in con and 'primary_key' not in con and n in tab.column_names:
                nulls=tab.column(n).null_count
                if nulls>0 and 'missing' not in c and 'null' not in json.dumps(c).lower() and 'missing' not in json.dumps(c).lower() and 'gap' not in json.dumps(c).lower():
                    rows.append((f,t['name'],f'{nulls} nulls in data, no missing-value note',n))
            if 'required' in con and n in tab.column_names and tab.column(n).null_count>0:rows.append((f,t['name'],'marked required but has nulls',n))
            # range vs data
            if ty.startswith('number') and 'range' in c and n in tab.column_names:
                mm=pc.min_max(tab.column(n)).as_py()
                if mm['min'] is not None and (mm['min']<c['range'][0]-1e-9 or mm['max']>c['range'][1]+1e-9):rows.append((f,t['name'],f'data outside stated range {c["range"]}',f'{n}: {mm}'))
                elif mm['min'] is not None:
                    lo,hi=c['range'];span=hi-lo
                    if span>0 and (mm['max']-mm['min'])/span<0.25:G['loose_range']+=1;rows.append((f,t['name'],f'range loose: stated {c["range"]} vs data {[round(mm["min"],3),round(mm["max"],3)]}',n))
            if 'description' in c and len(str(c['description']).strip())<15:rows.append((f,t['name'],'very short description',n+': '+str(c['description'])))
print('files',len(files),dict(G));print('column keys used:',dict(allkeys))
by=collections.defaultdict(list)
for f,t,k,v in rows:by[k.split(' ')[0]+' '+' '.join(k.split(' ')[1:4]) if k.startswith('range loose') or 'nulls in data' in k or 'outside' in k else k].append((f.replace('/data-dict.yaml',''),t,v,k))
for k,v in by.items():
    print(f'\n## {k}  (n={len(v)})')
    for f,t,x,kk in v[:12]:print('  ',f.split('/')[-1] if 'mapping' in f else f,t,x if not ('loose' in kk or 'nulls' in kk or 'outside' in kk) else f'{x}  <- {kk}')
    if len(v)>12:print('   ...',len(v)-12,'more')
