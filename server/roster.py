"""名册 roster.json：{"groups":[{name,color,cover?,kind?,lead?,contact?,note?,signup?,cover_focus?,members:[{id,character,member}]}]}

单团就是只有一个 group；模式（单团 / 多团）只影响页面呈现，这里的校验和保存链路完全一样。
保存链路沿用 keyroster：校验 → 补 id → diff 记进 outbox → 快照旧文件 → 原子写。"""
import json,os,re,secrets,shutil,time
import config,store
FIELDS=('work','order','character','member')
GROUP_OPT={'cover':str,'kind':str,'lead':str,'contact':str,'note':str,'signup':str,'cover_focus':list}
def load():
  with open(config.C.ROSTER,encoding='utf-8') as f:return json.load(f)
def newid():return 'r'+secrets.token_hex(4)
def ensure_ids(d,stamp=None):
  stamp=stamp or store.now();seen=set()
  for g in d['groups']:
    for m in g['members']:
      if not m.get('id') or m['id'] in seen:m['id']=newid()
      seen.add(m['id']);m.setdefault('updatedAt',stamp)
def flat(d):
  """id -> {id, work (= group name), order, character, member}"""
  out={}
  for g in d['groups']:
    for i,m in enumerate(g['members']):
      if m.get('id'):out[m['id']]={'id':m['id'],'work':g['name'],'order':i+1,'character':m.get('character',''),'member':m.get('member','')}
  return out
def diff(old,new):
  a,b=flat(old),flat(new);ch=[]
  for k,r in b.items():
    if k not in a or any(a[k][f]!=r[f] for f in FIELDS):ch.append(('upsert',k,r))
  for k,r in a.items():
    if k not in b:ch.append(('delete',k,r))
  return ch
def validate(d):
  assert isinstance(d,dict) and isinstance(d.get('groups'),list),'groups'
  names=set()
  for g in d['groups']:
    assert isinstance(g,dict),'group'
    assert isinstance(g.get('name'),str) and g['name'].strip() and len(g['name'])<60,'name'
    assert g['name'] not in names,'duplicate group';names.add(g['name'])
    assert re.fullmatch(r'#[0-9a-fA-F]{6}',g.get('color','')),'color'
    for k,t in GROUP_OPT.items():
      if k in g and g[k] is not None:assert isinstance(g[k],t),k
    for k in ('lead','contact'):assert len(g.get(k) or '')<80,k
    assert len(g.get('note') or '')<500,'note'
    assert (g.get('kind') or 'cast') in ('cast','crew'),'kind'
    assert (g.get('signup') or 'open') in ('open','closed'),'signup'
    if g.get('cover'):assert re.fullmatch(r'[\w.-]{1,80}',g['cover']) and '..' not in g['cover'],'cover'
    if g.get('cover_focus') is not None:
      f=g['cover_focus'];assert len(f)==4 and all(isinstance(v,(int,float)) and 0<=v<=1 for v in f),'cover_focus'
    assert isinstance(g.get('members'),list),'members'
    for m in g['members']:
      assert isinstance(m,dict),'member'
      assert isinstance(m.get('character',''),str) and isinstance(m.get('member',''),str),'member'
      assert len(m.get('character',''))<60 and len(m.get('member',''))<60,'member length'
      assert m.get('character') or m.get('member'),'empty seat'
def save(d,source='网页'):
  """Caller holds the server LOCK. Returns the list of changes."""
  C=config.C;old=load();ensure_ids(d);ch=diff(old,d);ts=store.now()
  idx={m['id']:m for g in d['groups'] for m in g['members']}
  for op,k,r in ch:
    if op=='upsert':idx[k]['updatedAt']=ts
  for g in d['groups']:
    g['count']=len(g['members'])
    for m in g['members']:m.pop('needsArt',None)
  try:store.log_roster(ch)
  except Exception as e:log('outbox error',repr(e))
  os.makedirs(C.BACKUPS,exist_ok=True)
  shutil.copy(C.ROSTER,os.path.join(C.BACKUPS,time.strftime('roster-%Y%m%d-%H%M%S-')+secrets.token_hex(2)+'.json'))
  prune_backups(C.BACKUPS,int(os.environ.get('CASTCALL_KEEP_BACKUPS') or 300))
  tmp=C.ROSTER+'.tmp'
  with open(tmp,'w',encoding='utf-8') as f:json.dump(d,f,ensure_ascii=False,indent=1)
  os.replace(tmp,C.ROSTER)
  return ch
def prune_backups(d,keep):
  try:fs=sorted(f for f in os.listdir(d) if f.startswith('roster-') and f.endswith('.json'))
  except OSError:return
  for f in fs[:-keep] if keep>0 else []:
    try:os.remove(os.path.join(d,f))
    except OSError:pass
def seat(d,rid):
  """(group, member) for a seat id, or (None, None)."""
  for g in d['groups']:
    for m in g['members']:
      if m.get('id')==rid:return g,m
  return None,None
def status_of(r,portraits,kind='cast'):
  if not (r.get('member') or '').strip():return '空缺'
  if r.get('character') and kind!='crew' and f"{r['work']}|{r['character']}" not in portraits:return '待配图'
  return '已定'
def log(*a):
  try:
    os.makedirs(config.C.LOGS,exist_ok=True)
    with open(os.path.join(config.C.LOGS,'server.log'),'a',encoding='utf-8') as f:f.write(time.strftime('%F %T ')+' '.join(map(str,a))+'\n')
  except Exception:pass
