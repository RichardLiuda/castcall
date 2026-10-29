#!/usr/bin/env python3
"""可选的 Notion 适配器。本地 sqlite 永远先写；这里只做「推一份过去」和「把 Notion 里的审核结果拉回来」。

  python3 server/notion.py check     # 检查 token、库是否共享、列名和列类型
  python3 server/notion.py push      # 立刻把名册改动推过去（服务器里每 15 分钟自动推一次）
  python3 server/notion.py push --all   # 第一次接上名册库：把现有的每个席位都推过去
  python3 server/notion.py sync      # 跑一轮：补推报名/留言，拉审核结果

只要 .env 里有 NOTION_TOKEN 和对应的 NOTION_*_DB，服务器就会自动启用；三个库各自独立，可以只接一个。
库 ID 直接复制 Notion 链接里那串 32 位字符就行：新版 API（2025-09-03）会自动换算成 data source，
老的 workspace 回落到 2022-06-28 的 database 接口。教程见 docs/notion.md。"""
import json,os,re,sys,threading,time,urllib.error,urllib.request
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import config,roster,store,review
API='https://api.notion.com/v1/'
NEW,OLD='2025-09-03','2022-06-28'
def call(path,body=None,method='GET',version=NEW,timeout=20):
  """→ (json, None) or (None, 'HTTP 404 object_not_found: …'). Never raises."""
  data=json.dumps(body,ensure_ascii=False).encode() if body is not None else None
  req=urllib.request.Request(API+path,data=data,method=method)
  req.add_header('Authorization','Bearer '+config.C.notion_token());req.add_header('Content-Type','application/json');req.add_header('Notion-Version',version)
  try:
    with urllib.request.urlopen(req,timeout=timeout) as r:return json.loads(r.read().decode('utf-8','replace') or '{}'),None
  except urllib.error.HTTPError as e:
    try:d=json.loads(e.read().decode('utf-8','replace'))
    except Exception:d={}
    return None,f"HTTP {e.code} {d.get('code','')}: {str(d.get('message',''))[:160]}"
  except Exception as e:return None,repr(e)[:160]
UUID=re.compile(r'[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}')
def dash(x):
  """A bare id, a dashed id, or a whole Notion link → dashed id. The ?v= part of a link is a view, not the database."""
  m=UUID.findall((x or '').strip().split('?')[0])
  x=m[-1].replace('-','') if m else (x or '').strip()
  return '-'.join([x[0:8],x[8:12],x[12:16],x[16:20],x[20:32]]) if len(x)==32 else x

# ── where each database lives ─────────────────────────────────────────────
class Target:
  """One configured database: how to create pages in it and query it, plus its column types."""
  def __init__(s,kind,version,parent,query,types):s.kind,s.version,s.parent,s.query,s.types=kind,version,parent,query,types
_TG={};_TG_LOCK=threading.Lock()
def target(kind,fresh=False):
  """Resolve NOTION_<KIND>_DB. Returns (Target, None) or (None, why). Cached; fresh=True re-reads the schema."""
  key=(kind,config.C.notion_db(kind))
  with _TG_LOCK:
    if not fresh and key in _TG:return _TG[key],None
  raw=config.C.notion_db(kind)
  if not config.C.notion_token():return None,'没配 NOTION_TOKEN'
  if not raw:return None,f'没配 NOTION_{kind.upper()}_DB'
  i=dash(raw);errs=[]
  d,e=call(f'databases/{i}',version=NEW)          # 新版：database → data_sources[0]
  ds=None
  if d is not None:ds=((d.get('data_sources') or [{}])[0] or {}).get('id')
  else:errs.append('databases(2025) → '+e)
  if not ds:
    d2,e2=call(f'data_sources/{i}',version=NEW)    # 填的本来就是 data source id
    if d2 is not None:ds=i
    else:errs.append('data_sources → '+e2)
  t=None
  if ds:
    d3,e3=call(f'data_sources/{ds}',version=NEW)
    if d3 is not None:t=Target(kind,NEW,{'type':'data_source_id','data_source_id':ds},f'data_sources/{ds}/query',{k:v.get('type') for k,v in (d3.get('properties') or {}).items()})
    else:errs.append('data_sources schema → '+e3)
  if not t:
    d4,e4=call(f'databases/{i}',version=OLD)
    if d4 is not None and d4.get('properties'):
      t=Target(kind,OLD,{'database_id':i},f'databases/{i}/query',{k:v.get('type') for k,v in d4['properties'].items()})
    else:errs.append('databases(2022) → '+(e4 or 'no properties'))
  if not t:return None,' | '.join(errs)
  with _TG_LOCK:_TG[key]=t
  return t,None

# ── property values ───────────────────────────────────────────────────────
def rich(v):
  v=v or '';return [{'type':'text','text':{'content':v[i:i+2000]}} for i in range(0,len(v),2000)] or [{'type':'text','text':{'content':''}}]
def value(typ,v):
  """Shape a plain value for a column of type typ. None = this column type is not writable from here."""
  v='' if v is None else v
  if typ=='title':return {'title':rich(str(v))}
  if typ=='rich_text':return {'rich_text':rich(str(v))}
  if typ=='select':return {'select':{'name':str(v)} if v!='' else None}
  if typ=='status':return {'status':{'name':str(v)} if v!='' else None}
  if typ=='multi_select':return {'multi_select':[{'name':str(v)}] if v!='' else []}
  if typ=='number':
    try:n=float(v)
    except (TypeError,ValueError):return {'number':None}
    return {'number':int(n) if n==int(n) else n}
  if typ=='url':return {'url':str(v) or None}
  if typ=='checkbox':return {'checkbox':bool(v)}
  if typ=='date':return {'date':{'start':str(v)} if v!='' else None}
  if typ in ('email','phone_number'):return {typ:str(v) or None}
  return None
def plain(p):
  """Read any common property back as text."""
  if not isinstance(p,dict):return ''
  t=p.get('type')
  if t in ('title','rich_text'):return ''.join(x.get('plain_text','') for x in (p.get(t) or []) if isinstance(x,dict))
  if t in ('select','status'):return ((p.get(t) or {}).get('name') or '') if isinstance(p.get(t),dict) else ''
  if t=='number':return '' if p.get('number') is None else str(p['number'])
  if t=='date':return ((p.get('date') or {}).get('start') or '') if isinstance(p.get('date'),dict) else ''
  if t in ('url','email','phone_number'):return p.get(t) or ''
  if t=='created_time':return p.get('created_time') or ''
  return ''
def cols(kind):return config.C.site['notion']['columns'][kind]
def st(key):return config.C.site['notion']['status'][key]
def props(t,flat):
  """{逻辑字段: 值} → Notion properties, using the column names from site.json and the real column types."""
  out={};c=cols(t.kind)
  for field,v in flat.items():
    name=c.get(field)
    if not name or name not in t.types:continue
    p=value(t.types[name],v)
    if p is not None:out[name]=p
  return out
def query_all(t):
  out=[];cursor=None
  for _ in range(50):
    q={'page_size':100}
    if cursor:q['start_cursor']=cursor
    d,e=call(t.query,q,'POST',t.version)
    if d is None:return None,e
    out+= [p for p in d.get('results') or [] if isinstance(p,dict) and not p.get('in_trash') and not p.get('archived')]
    if not d.get('has_more') or not d.get('next_cursor'):break
    cursor=d['next_cursor']
  return out,None
def field(page,kind,f):return plain((page.get('properties') or {}).get(cols(kind).get(f,'')))

# A row may be pushed by the request that created it and by the retry loop at the same time; without this the
# slower one would create a second Notion page for it.
_INFLIGHT=set();_IF_LOCK=threading.Lock()
def once(kind,i,fn):
  with _IF_LOCK:
    if (kind,i) in _INFLIGHT:return None
    _INFLIGHT.add((kind,i))
  try:return fn()
  finally:
    with _IF_LOCK:_INFLIGHT.discard((kind,i))

# ── signups ───────────────────────────────────────────────────────────────
SIG_STATUS={'pending':'pending','approved':'approved','rejected':'rejected'}
def push_signup(r):
  """Create (first time) or update the Notion row of local signup r. Returns page id or None."""
  return once('signup',r['id'],lambda:_push_signup(store.signup(r['id']) or r))
def _push_signup(r):
  t,e=target('signup')
  if not t:return None
  flat={'name':r['name'],'contact':r['contact'],'group':r['grp'],'character':r['character'],'id':r['seat'],'status':st(r['status'])}
  pid=store.page_of('signup',r['id'])
  if pid:
    d,e=call(f'pages/{pid}',{'properties':props(t,flat)},'PATCH',t.version)
  else:
    d,e=call('pages',{'parent':t.parent,'properties':props(t,flat)},'POST',t.version)
    if d is not None and d.get('id'):store.set_page('signup',r['id'],d['id']);pid=d['id']
  if d is None:roster.log('notion signup push fail',r['id'],e);return None
  return pid
def pull_signups(lock):
  """Notion 状态 → local decision. Only rows that came from this site (mapped page ids) are considered."""
  t,e=target('signup')
  if not t:return {'skip':e}
  pages,e=query_all(t)
  if pages is None:return {'error':e}
  rev={v:int(k) for k,v in store.pages('signup').items()};rep={'approved':0,'rejected':0,'reopened':0,'notes':[]}
  for p in pages:
    i=rev.get(p.get('id'))
    if i is None:continue
    r=store.signup(i)
    if not r:continue
    want=field(p,'signup','status').strip()
    with lock:
      if want==st('approved') and r['status']!='approved':
        ok,msg=review.approve(i,'Notion')
        if ok:rep['approved']+=1
        else:rep['notes'].append(f'#{i} {msg}')
      elif want==st('rejected') and r['status']!='rejected':
        review.revoke(i,'rejected','Notion');rep['rejected']+=1
      elif want==st('pending') and r['status']=='approved' and r['source']=='Notion':
        # 只撤回 Notion 自己通过的：后台点过的不被一张旧表格推翻
        review.revoke(i,'pending','Notion');rep['reopened']+=1
  return rep

# ── guestbook ─────────────────────────────────────────────────────────────
NOTE_STATUS=('approved','hidden','pending')
def push_note(n):
  return once('guestbook',n['id'],lambda:_push_note(n))
def _push_note(n):
  t,e=target('guestbook')
  if not t:return None
  flat={'name':n['name'],'text':n['body'],'status':st(n['status']),'time':n['created']}
  pid=store.page_of('guestbook',n['id'])
  if pid:d,e=call(f'pages/{pid}',{'properties':props(t,{'status':flat['status']})},'PATCH',t.version)
  else:
    d,e=call('pages',{'parent':t.parent,'properties':props(t,flat)},'POST',t.version)
    if d is not None and d.get('id'):store.set_page('guestbook',n['id'],d['id']);pid=d['id']
  if d is None:roster.log('notion note push fail',n['id'],e);return None
  return pid
def pull_notes():
  t,e=target('guestbook')
  if not t:return {'skip':e}
  pages,e=query_all(t)
  if pages is None:return {'error':e}
  rev={v:int(k) for k,v in store.pages('guestbook').items()};back={st(k):k for k in NOTE_STATUS};seen=set();n=0
  local={x['id']:x for x in store.notes(limit=100000)}
  for p in pages:
    i=rev.get(p.get('id'))
    if i is None or i not in local:continue
    seen.add(i);want=back.get(field(p,'guestbook','status').strip())
    if want and want!=local[i]['status']:store.set_note(i,want,'Notion');n+=1
  # 在 Notion 里删掉的行：本地也隐藏（不删，留底）
  for k,i in rev.items():
    if i in local and i not in seen and local[i]['status']!='hidden':store.set_note(i,'hidden','Notion');n+=1
  return {'changed':n}

# ── roster ────────────────────────────────────────────────────────────────
def push_roster(dry=False,full=False):
  """Push pending roster changes. Acks only when every item went through.
  full=True pushes every current seat (first time a roster database is connected) and archives pages of seats
  that no longer exist."""
  t,e=target('roster')
  if not t:return {'skip':e}
  items,top=store.pending_roster()
  try:d=roster.load();cur=roster.flat(d)
  except Exception as ex:return {'error':repr(ex)}
  if full:
    items=[{'seq':0,'op':'upsert','rid':k} for k in cur]+[{'seq':0,'op':'delete','rid':k} for k in store.pages('roster') if k not in cur]
  if not items:return {'pushed':0}
  kinds={g['name']:g.get('kind') or 'cast' for g in d['groups']}
  try:
    with open(config.C.MAP,encoding='utf-8') as f:ports=json.load(f)
  except Exception:ports={}
  done,bad=0,[]
  for it in items:
    rid=it['rid'];pid=store.page_of('roster',rid)
    if it['op']=='delete' or rid not in cur:
      if not pid:done+=1;continue
      if dry:done+=1;continue
      r,e=call(f'pages/{pid}',{'archived':True},'PATCH',t.version)
    else:
      rec=cur[rid];flat={'character':rec['character'] or '（无角色）','member':rec['member'],'group':rec['work'],'order':rec['order'],
        'status':roster.status_of(rec,ports,kinds.get(rec['work'],'cast')),'id':rid}
      if dry:done+=1;continue
      if pid:r,e=call(f'pages/{pid}',{'properties':props(t,flat)},'PATCH',t.version)
      else:
        r,e=call('pages',{'parent':t.parent,'properties':props(t,flat)},'POST',t.version)
        if r is not None and r.get('id'):store.set_page('roster',rid,r['id'])
    if r is None:bad.append((it['seq'],e))
    else:done+=1
  if not bad and not dry:store.ack_roster(top)
  return {'pushed':done,'failed':[f'seq {s}: {e}' for s,e in bad],'dry':dry}

# ── one round, as run by the server thread ────────────────────────────────
def retry_unpushed():
  n=0
  if config.C.notion_on('signup'):
    for r in store.unmapped('signup','signups'):n+=bool(push_signup(r))
  if config.C.notion_on('guestbook'):
    for x in store.unmapped('guestbook','guestbook'):n+=bool(push_note(x))
  return n
def sync_once(lock):
  rep={}
  if config.C.notion_on('signup'):rep['signups']=pull_signups(lock)
  if config.C.notion_on('guestbook'):rep['guestbook']=pull_notes()
  rep['retried']=retry_unpushed()
  return rep
def loop(lock):
  last_roster=0.0
  while True:
    n=config.C.site['notion']
    try:
      if config.C.notion_on():
        rep=sync_once(lock)
        if any(v for k,v in rep.items() if k!='retried' and isinstance(v,dict) and (v.get('approved') or v.get('rejected') or v.get('reopened') or v.get('changed') or v.get('error'))) or rep.get('retried'):
          roster.log('notion sync',json.dumps(rep,ensure_ascii=False))
        if config.C.notion_on('roster') and time.time()-last_roster>=float(n.get('rosterEvery') or 900):
          last_roster=time.time();r=push_roster()
          if r.get('pushed') or r.get('failed') or r.get('error'):roster.log('notion roster',json.dumps(r,ensure_ascii=False))
    except Exception as e:roster.log('notion loop err',repr(e))
    time.sleep(float(n.get('syncEvery') or 20))

# ── CLI ───────────────────────────────────────────────────────────────────
def check():
  """Human-readable report. Exit 0 when every configured database is usable."""
  C=config.C;ok=True;out=[]
  if not C.notion_token():
    print('NOTION_TOKEN 没配：Notion 适配器关闭，网站只用本地数据库。');return 0
  me,e=call('users/me')
  out.append(('token',me is not None,(me or {}).get('name') or e))
  if me is None:ok=False
  for kind,label in (('roster','名册'),('signup','报名'),('guestbook','留言')):
    if not C.notion_db(kind):out.append((label,None,f'NOTION_{kind.upper()}_DB 没配，跳过'));continue
    t,e=target(kind,fresh=True)
    if not t:out.append((label,False,'打不开这个库：'+e+'\n      → 多半是没把库共享给 integration（库右上角 ··· → 连接 → 选你的 integration）'));ok=False;continue
    miss=[];wrong=[]
    for f,name in cols(kind).items():
      if name not in t.types:miss.append(name)
      elif value(t.types[name],'x') is None:wrong.append(f'{name}({t.types[name]})')
    good=not miss and not wrong;ok&=good
    msg=f'API {t.version}'+(f'，缺少列：{"、".join(miss)}' if miss else '')+(f'，列类型写不进去：{"、".join(wrong)}' if wrong else '')
    if kind in ('signup','guestbook'):
      sname=cols(kind)['status'];styp=t.types.get(sname)
      if styp not in (None,'select','status'):msg+=f'，「{sname}」应该是选择（select）类型';ok=False;good=False
    out.append((label,good,msg))
  for name,good,msg in out:print(('  ✓ ' if good else '  - ' if good is None else '  ✗ ')+name+'：'+str(msg))
  print('全部可用。' if ok else '有问题，按上面的提示改完再跑一次。')
  return 0 if ok else 1
def main(a):
  if not a or a[0] in ('-h','--help'):print(__doc__);return 0
  if a[0]=='check':return check()
  if a[0]=='push':
    r=push_roster(dry='--dry' in a,full='--all' in a);print(json.dumps(r,ensure_ascii=False,indent=1));return 1 if r.get('failed') or r.get('error') else 0
  if a[0]=='sync':print(json.dumps(sync_once(threading.Lock()),ensure_ascii=False,indent=1));return 0
  print(__doc__);return 2
if __name__=='__main__':sys.exit(main(sys.argv[1:]))
