#!/usr/bin/env python3
"""找立绘和封面：从 Bangumi（中文名最全）和 AniList（日文 / 罗马字）找候选图，下载进 uploads/。

  python3 server/artsearch.py names 名单.txt   # 名单预检：每个名字配不配得上图（不建站、不下载）
  python3 server/artsearch.py auto             # 缺封面的团找封面、缺立绘的角色找立绘，挑最可信的那张
  python3 server/artsearch.py auto --dry       # 只看会配哪张，不下载
  python3 server/artsearch.py auto --redo      # 已有的也重新找
  python3 server/artsearch.py search 古河渚    # 列出候选
  python3 server/artsearch.py roster CLANNAD Kanon   # 按作品的角色表生成一份名单（全部空缺），格式就是 init.py --import 要的
后台也能用：编辑角色 → 「找立绘」，编辑团 → 「找封面」，工具条「一键配图」。

匹配方式：先用团名在 Bangumi 找作品，再用角色名搜角色；同一个角色也出现在这部作品的角色表里，才算可靠，
否则退回「简体中文名完全相同」的那个；都没有就跳过（不乱配）。工作组（kind: crew）封面、立绘都不找。

Bangumi 的角色搜索匹配的是日文 name，「月宫亚由」搜不到「月宮あゆ」——所以搜索落空时会拿作品自己的
角色表（详情里的「简体中文名」/ 别名）再对一次，名单里的错字（美坂栎 / 美坂栞）差一个字也认，但会报出来。
网络抖动（502 / 超时）自动重试 4 次；缺图在后台点「一键配图」，已有的不会重下。"""
import json,os,re,sys,threading,time,urllib.parse
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import config,net
BGM='https://api.bgm.tv/v0/'
ANI='https://graphql.anilist.co'
HOSTS=('lain.bgm.tv','bgm.tv','s4.anilist.co','anilist.co')
PAUSE=.35                     # Bangumi 没写限速，但别一秒几十个请求
TRIES=3;BACKOFF=.7            # api.bgm.tv 会间歇性 502（代理 / 线路）：连着几次失败多半过一两秒就好了
# 熔断按线路分开算：Bangumi 断了 AniList 往往还通，不能因为一边成功就把另一边的失败计数清掉。
# 没有它，网络整个不通时一次配图会逐个角色重试，几分钟都跑不完。
BREAK={'n':{},'down':{}}
def _line(url):return 'ani' if 'anilist' in url else 'bgm'
def _transient(err):
  """值得重试的错：超时、连接被掐、429、5xx。404 这种是「真没有」，重试只是白等。"""
  e=str(err or '')
  if not e:return False
  if 'HTTP' in e:return any(x in e for x in ('429','500','502','503','504'))
  return True
def _req(url,body=None,**kw):
  k=_line(url)
  if BREAK['down'].get(k):return None,('AniList' if k=='ani' else 'Bangumi')+' 这次不通，已跳过'
  e=''
  for i in range(TRIES):
    d,e=net.request(url,body,**kw)
    if d is not None:BREAK['n'][k]=0;return d,e
    if not _transient(e) or i==TRIES-1:break
    time.sleep(BACKOFF*(i+1))
  if _transient(e):
    BREAK['n'][k]=BREAK['n'].get(k,0)+1
    if BREAK['n'][k]>=2:BREAK['down'][k]=True
  return None,e
def down():return bool(BREAK['down'].get('bgm') and BREAK['down'].get('ani'))
def _bgm(path,body=None):
  return _req(BGM+path,body,timeout=15)
def _cn(item):
  """Bangumi character / subject → (中文名, 其他名字...)"""
  names=[item.get('name_cn') or '']
  for b in item.get('infobox') or []:
    if b.get('key')=='简体中文名' and isinstance(b.get('value'),str):names.insert(0,b['value'])
    if b.get('key')=='别名' and isinstance(b.get('value'),list):names+=[x.get('v','') for x in b['value'] if isinstance(x,dict)]
  return [n.strip() for n in names if n and n.strip()]
def _norm(s):return re.sub(r'[\s·・.\-—_!！?？~～]','',(s or '').lower())
# 简体 → 日文常见写法。名单是中文打的（泽渡真琴），库里是日文（沢渡真琴），
# 不做这一步，Bangumi 一断就有一半名字永远对不上。
VAR=str.maketrans({'泽':'沢','宫':'宮','亚':'亜','樱':'桜','绘':'絵','铁':'鉄','广':'広','濑':'瀬',
  '实':'実','惠':'恵','边':'辺','龙':'竜','冈':'岡','岛':'島','纱':'紗','绪':'緒','叶':'葉',
  '风':'風','鸟':'鳥','剑':'剣','凉':'涼','丽':'麗','丰':'豊','誉':'誉','寿':'寿','场':'場',
  '当':'当','发':'発','对':'対','观':'観','馆':'館','归':'帰','气':'気','杂':'雑','战':'戦'})
def _vnorm(s):return _norm(s).translate(VAR)
def _img(images,*keys):
  for k in keys:
    if isinstance(images,dict) and images.get(k):return images[k]
  return ''
# ── search ────────────────────────────────────────────────────────────────
def subjects(q,limit=6):
  d,e=_bgm(f'search/subjects?limit={limit}',{'keyword':q})
  if d is None:
    # Bangumi 不通（代理 / 限流 / 被墙）时退到 AniList：标题是日文或罗马字，但封面和横幅够用
    a,e2=anilist_media(q,limit)
    if a:return a,None
    return [],e2        # AniList 答了但没这部作品 = 没找到，不是错；AniList 也失败才算错
  out=[]
  for s in d.get('data') or []:
    u=_img(s.get('images'),'large','common')
    if not u:continue
    out.append({'source':'Bangumi','id':s.get('id'),'title':s.get('name_cn') or s.get('name'),'sub':s.get('name') if s.get('name_cn') else '',
      'url':u,'thumb':_img(s.get('images'),'medium','common','large'),'type':s.get('type'),'exact':_norm(q) in (_norm(s.get('name')),_norm(s.get('name_cn')))})
  return out,None
def subject_chars(sid):
  d,e=_bgm(f'subjects/{int(sid)}/characters')
  return {c.get('id') for c in (d or []) if isinstance(c,dict)},e
# ── 中文名索引：搜索只认日文名，这里补一条 ──────────────────────────────────
# Bangumi 的角色搜索匹配的是日文 name：「月宫亚由」搜不到「月宮あゆ」、「泽渡真琴」搜不到「沢渡真琴」，
# 于是名单里总有几个配不上图（同一个 Kanon 团，川澄舞、天野美汐能配上，另外两个配不上）。
# 作品自己的角色表里有全部角色 id，角色详情里带「简体中文名」和别名，所以在搜索落空时按中文名再对一次。
def index_path():return os.path.join(config.C.UPLOADS,'art_index.json')
def _load_index():
  try:
    with open(index_path(),encoding='utf-8') as f:return json.load(f)
  except (OSError,ValueError):return {}
def _save_index(d):
  try:
    os.makedirs(config.C.UPLOADS,exist_ok=True);tmp=index_path()+'.tmp'
    with open(tmp,'w',encoding='utf-8') as f:json.dump(d,f,ensure_ascii=False)
    os.replace(tmp,index_path())
  except OSError:pass
def char_names(cid,url=''):
  """角色 id → (候选名, 立绘 url)。名字缓存在 uploads/art_index.json：第二次（甚至断网时）不用再问一遍。"""
  idx=_load_index();k=str(cid)
  if k in idx:return idx[k].get('names') or [],idx[k].get('url') or url
  d,e=_bgm(f'characters/{int(cid)}')
  if d is None:return [],url
  names=_cn(d)
  if d.get('name') and d['name'] not in names:names.append(d['name'])
  u=_img(d.get('images'),'large','medium') or url
  idx[k]={'names':names,'url':u};_save_index(idx)
  return names,u
def work_index(sid,limit=60):
  """作品角色表 → {归一化名: 候选}。只在搜索落空时才建，一个角色一次详情请求（主角优先，最多 limit 个）。"""
  d,e=_bgm(f'subjects/{int(sid)}/characters')
  if not isinstance(d,list):return {},e or '角色表读不到'
  out={};n=0
  for c in sorted([x for x in d if isinstance(x,dict)],key=lambda x:RELATION.get(x.get('relation'),9)):
    if n>=limit:break
    names,url=char_names(c.get('id'),_img(c.get('images'),'large','medium'))
    if not url:continue
    n+=1
    for nm in names:
      e={'source':'Bangumi','id':c.get('id'),'title':nm,'sub':'作品角色表','url':url,'thumb':url,'exact':True}
      for k in (_norm(nm),_vnorm(nm)):out.setdefault(k,e)
  return out,None
def index_lookup(idx,ch,used=()):
  """查表：原样 → 变体字（泽/沢）→ 错别字兜底。三种都不中才是真没有。"""
  for k in (_norm(ch),_vnorm(ch)):
    h=idx.get(k)
    if h and h['url'] not in used:return h
  for key in (_norm(ch),_vnorm(ch)):
    nk=near_key(key,idx,used)
    if nk:return idx[nk]
  return None
def anilist_work(q,limit=24):
  """AniList 的作品角色表。Bangumi 不通时用它兜底：只有日文 / 罗马字名，
  所以只认「写法相同」或「简体变日文写法相同」（泽渡真琴 → 沢渡真琴），不改写假名的仍然对不上。"""
  d,e=_req(ANI,{'query':'query($s:String,$n:Int){Media(search:$s,type:ANIME){id title{romaji native}'
                'characters(perPage:$n){nodes{id name{full native} image{large medium}}}}}',
                'variables':{'s':q,'n':limit}},timeout=15)
  if d is None:return {},None,e
  m=(d.get('data') or {}).get('Media')
  if not m:return {},None,'AniList 没找到这部作品'
  t=m.get('title') or {}
  work={'source':'AniList','id':m.get('id'),'title':t.get('native') or t.get('romaji'),'sub':'AniList','exact':True}
  idx={}
  for c in ((m.get('characters') or {}).get('nodes') or []):
    nm=c.get('name') or {};url=_img(c.get('image'),'large','medium')
    if not url:continue
    for n in (nm.get('native'),nm.get('full')):
      if not n:continue
      ent={'source':'AniList','id':f"anilist:{c.get('id')}",'title':nm.get('native') or n,'sub':'AniList 角色表','url':url,'thumb':url,'exact':True}
      for k in (_norm(n),_vnorm(n)):idx.setdefault(k,ent)
  return idx,work,None
def _lev(a,b):
  """编辑距离，长度差超过 1 直接判不同（名单里的名字都很短，够用）。"""
  if abs(len(a)-len(b))>1:return 9
  prev=list(range(len(b)+1))
  for i,ca in enumerate(a,1):
    cur=[i]
    for j,cb in enumerate(b,1):cur.append(min(prev[j]+1,cur[j-1]+1,prev[j-1]+(ca!=cb)))
    prev=cur
  return prev[-1]
def near_key(norm,idx,used=()):
  """错别字兜底（美坂栎 / 美坂栞）：只差一个字且候选唯一才认，两个以上就当没找到——宁可空着，不配错图。"""
  if len(norm)<2:return ''
  hits=[k for k in idx if idx[k]['url'] not in used and _lev(norm,k)==1]
  return hits[0] if len(hits)==1 else ''
def characters(q,limit=8):
  d,e=_bgm(f'search/characters?limit={limit}',{'keyword':q})
  if d is None:
    a,e2=anilist_characters(q,limit)
    if a:return a,None
    return [],e2
  out=[]
  for c in d.get('data') or []:
    u=_img(c.get('images'),'large','medium')
    if not u:continue
    names=_cn(c)
    out.append({'source':'Bangumi','id':c.get('id'),'title':names[0] if names else c.get('name'),'sub':c.get('name'),'url':u,
      'thumb':_img(c.get('images'),'medium','grid','large'),'exact':_norm(q) in {_norm(n) for n in names+[c.get('name') or '']}})
  return out,None
def anilist_characters(q,limit=6):
  d,e=_req(ANI,{'query':'query($s:String,$n:Int){Page(perPage:$n){characters(search:$s){id name{full native} image{large medium}}}}','variables':{'s':q,'n':limit}},timeout=15)
  if d is None:return [],e
  out=[]
  for c in ((d.get('data') or {}).get('Page') or {}).get('characters') or []:
    u=(c.get('image') or {}).get('large')
    if not u or u.endswith('/default.jpg'):continue
    n=c.get('name') or {}
    out.append({'source':'AniList','id':c.get('id'),'title':n.get('native') or n.get('full'),'sub':n.get('full'),'url':u,'thumb':(c.get('image') or {}).get('medium') or u,
      'exact':_norm(q) in (_norm(n.get('native')),_norm(n.get('full')))})
  return out,None
def anilist_media(q,limit=6):
  d,e=_req(ANI,{'query':'query($s:String,$n:Int){Page(perPage:$n){media(search:$s){id title{romaji native} coverImage{extraLarge large} bannerImage}}}','variables':{'s':q,'n':limit}},timeout=15)
  if d is None:return [],e
  out=[]
  for m in ((d.get('data') or {}).get('Page') or {}).get('media') or []:
    # 竖版封面在前：一键配图拿第一张，横幅（约 5:1）铺满整屏会被放大成一条糊掉的局部
    for u,t in (((m.get('coverImage') or {}).get('extraLarge'),'封面'),(m.get('bannerImage'),'横幅')):
      if u:out.append({'source':'AniList','id':m.get('id'),'title':(m.get('title') or {}).get('native') or (m.get('title') or {}).get('romaji'),'sub':t,'url':u,'thumb':u,'exact':False})
  return out,None
def search(kind,q,group=''):
  """Candidates for the admin picker: [{source,title,sub,url,thumb}]. Errors are reported, not raised."""
  q=(q or '').strip()
  if not q:return [],'没有关键词'
  errs=[]
  if kind=='cover':
    a,e=subjects(q);errs+=[e] if e else []
    b,e=anilist_media(q);errs+=[e] if e else []
    a.sort(key=lambda x:(not x['exact'],x.get('type') not in (2,4)));res=a+b
  else:
    a,e=characters(q);errs+=[e] if e else []
    if group and a:
      ss,_=subjects(group,3);ids=set()
      for s in ss[:2]:
        if s.get('source')!='Bangumi':continue
        got,_=subject_chars(s['id']);ids|=got
      for x in a:x['inwork']=x['id'] in ids
      a.sort(key=lambda x:(not x.get('inwork'),not x['exact']))
    b,e=anilist_characters(q);errs+=[e] if e else []
    res=a+b
  return res,('；'.join(errs) if errs and not res else None)
# ── roster from a work's character list ───────────────────────────────────
RELATION={'主角':0,'配角':1}     # 客串不进招募名单
def work_roster(q,limit=20,main_only=False,log=lambda *a:None):
  """作品名 → (显示的作品名, [角色名...], 来源说明)。Bangumi：作品角色表按 主角 → 配角 排，逐个取简体中文名；
  Bangumi 不通时退到 AniList（只有日文 / 罗马字名）。找不到作品返回 (q, [], 原因)。"""
  d,e=_bgm('search/subjects?limit=6',{'keyword':q})
  if d is not None:
    ss=[s for s in d.get('data') or [] if s.get('type') in (2,4)] or (d.get('data') or [])
    ss.sort(key=lambda s:_norm(q) not in (_norm(s.get('name')),_norm(s.get('name_cn'))))
    if not ss:return q,[],'Bangumi 没找到这部作品'
    s=ss[0];title=s.get('name_cn') or s.get('name') or q;time.sleep(PAUSE)
    cs,e=_bgm(f"subjects/{int(s['id'])}/characters")
    if cs is None:return title,[],f'Bangumi 角色表读不到（{e}）'
    cs=[c for c in cs if isinstance(c,dict) and c.get('relation') in RELATION and (not main_only or c.get('relation')=='主角')]
    cs.sort(key=lambda c:RELATION[c['relation']]);out=[]
    for c in cs[:limit]:
      time.sleep(PAUSE);full,_=_bgm(f"characters/{int(c['id'])}")
      name=(_cn(full)[0] if full and _cn(full) else '') or c.get('name') or ''
      log(f"  {c['relation']} {name}")
      if name and name not in out:out.append(name)
    return title,out,f"Bangumi #{s['id']}（{s.get('name')}）"
  r,e2=_req(ANI,{'query':'query($s:String,$n:Int){Media(search:$s){id title{native romaji} characters(sort:[ROLE,RELEVANCE],perPage:$n){edges{role node{name{native full}}}}}}',
                        'variables':{'s':q,'n':limit}},timeout=15)
  m=((r or {}).get('data') or {}).get('Media')
  if not m:return q,[],f'Bangumi 连不上（{e}），AniList '+('也没找到' if r is not None else f'也连不上（{e2}）')
  es=[x for x in ((m.get('characters') or {}).get('edges') or []) if not main_only or x.get('role')=='MAIN']
  out=[]
  for x in es:
    n=((x.get('node') or {}).get('name') or {});n=n.get('native') or n.get('full') or ''
    if n and n not in out:out.append(n)
  t=(m.get('title') or {});return t.get('native') or t.get('romaji') or q,out,f"AniList #{m['id']}（Bangumi 连不上，名字是日文 / 罗马字，请改成中文再导入）"
def roster_text(works,limit=20,main_only=False,log=print):
  """几部作品 → importer 格式的文本（每部一个 ## 团，角色全部空缺）+ 每部的来源说明"""
  lines,notes=[],[]
  for q in works:
    log(f'查 {q}…');title,names,src=work_roster(q,limit,main_only,log=log)
    notes.append(f'{q} → {title}：{len(names)} 个角色，来源 {src}')
    if names:lines+=[f'## {title}',*names,'']
  return '\n'.join(lines).strip()+'\n' if lines else '',notes

# ── 名单预检：名单一定下来就确认「这些名字都配得上图」 ─────────────────────
# 名字对不上图，原来要等建完站、配图跑完、少了几张立绘才发现——太晚了。
# 这里在名单刚确定时就把每个名字绑到一个确定的 Bangumi 角色 id：绑上了以后配图直接按 id 取图，
# 不再搜索。这不只是快——搜索会随排序、网络、同名词变化而漂，id 不会。
BIND='art_bind.json'
RUN='art_bind_run.json'         # 核对这一次的记录：没有它，「没跑核对」和「跑了但断网」看起来一模一样
def bind_path():return os.path.join(config.C.UPLOADS,BIND)
def bind_run_path():return os.path.join(config.C.UPLOADS,RUN)
def bind_run_save(rep):
  try:
    os.makedirs(config.C.UPLOADS,exist_ok=True)
    # 没绑上的逐条记「什么状态 + 拿哪张表判的」。
    # 只记数量的话，事后分不清「名单写错了」和「这张表本来就查不到」——
    # Bangumi 不通时 AniList 的表只有日文名，汉字被改写成假名的（月宫亚由 / 月宮あゆ）必然 missing，
    # 那不是名单的问题，是那张表认不出。补救办法完全不同（改名单 vs 等网络好了重跑）。
    un={}
    for g in rep.get('groups') or []:
      src=(g.get('work') or {}).get('source') or ''
      for ch,it in (g.get('items') or {}).items():
        if it.get('state')=='ok':continue
        un[f"{g.get('name')}|{ch}"]={'state':it.get('state') or '','src':src}
    rec={'at':time.strftime('%Y-%m-%d %H:%M:%S'),'net':bool(rep.get('net',True)),'bangumi':bool(rep.get('bangumi',True)),
         'total':rep.get('total',0),'ok':rep.get('ok',0),'bound':rep.get('bound',0),
         'near':len(rep.get('near') or []),'missing':len(rep.get('missing') or []),
         'unknown':len(rep.get('unknown') or []),'sources':rep.get('sources') or [],'unbound':un}
    tmp=bind_run_path()+'.tmp'
    with open(tmp,'w',encoding='utf-8') as f:json.dump(rec,f,ensure_ascii=False)
    os.replace(tmp,bind_run_path())
  except OSError:pass
def bind_run_load():
  try:
    with open(bind_run_path(),encoding='utf-8') as f:d=json.load(f)
    return d if isinstance(d,dict) else None
  except (OSError,ValueError):return None
def bind_load():
  try:
    with open(bind_path(),encoding='utf-8') as f:d=json.load(f)
    return d if isinstance(d,dict) else {}
  except (OSError,ValueError):return {}
def bind_save(d):
  try:
    os.makedirs(config.C.UPLOADS,exist_ok=True);tmp=bind_path()+'.tmp'
    with open(tmp,'w',encoding='utf-8') as f:json.dump(d,f,ensure_ascii=False,indent=1)
    os.replace(tmp,bind_path())
  except OSError:pass
def bind_key(group,character):return f'{group}|{character}'
def bind_one(group,character):
  """这个名字之前绑定过吗 → {id,name,url}。配图时先查这里，命中就不再搜。"""
  return bind_load().get(bind_key(group,character)) or None
def bind_manual(group,character,id,name,url):
  """人工在后台点了一张立绘：顺手把这个名字绑到那个角色。
  不绑的后果是「人工确认」只存在于一张图上——名字仍然是没绑的状态，下次名单核对还是报「找不到这个名字」，
  换个团/换张图又要重新点。S1 那版里月宫亚由就是这样（图配上了，绑定表里没有）。"""
  if not (id and name and url):return False
  d=bind_load();d[bind_key(group,character)]={'id':id,'name':name,'url':url,'group':group,'character':character,'by':'manual'}
  bind_save(d);return True
def work_chars(idx,limit=12):
  """作品角色表（work_index 的返回）→ 去重后的角色列表，主角在前。给「这个名字找不到，你点点看是哪个」用。
  「月宫亚由」和「月宮あゆ」差三个字，任何自动相似度都不可靠——但人一眼就认出来了，所以让人点。"""
  seen=set();out=[]
  for v in idx.values():
    if v['url'] in seen:continue
    seen.add(v['url']);out.append({'id':v['id'],'name':v['title']})
    if len(out)>=limit:break
  return out
def bind_group(gname,chars,log=lambda *a:None):
  """一个团：找作品 → 读作品角色表 → 逐个名字判定。返回 (items, work, err)。

  items[角色名] = {'state':'ok'|'near'|'missing'|'unknown', 'id', 'name', 'url', 'why', 'suggest', 'candidates'}
    ok       精确命中（中文名 / 别名 / 日文名都算），绑到这个 id
    near     作品角色表里只差一个字且候选唯一 → 多半是名单写错了，给出 suggest
    missing  表里确实没有这个名字 → 附上该作品的角色列表（candidates），让人点一个
    unknown  网络不通 / 角色表读不到，没法判断（**不当作通过**）"""
  items={}
  ss,e=subjects(gname,4);time.sleep(PAUSE)
  if ss:ss.sort(key=lambda x:(not x['exact'],x.get('type') not in (2,4)))
  src=(next((s for s in ss if s.get('source')=='Bangumi'),None) or (ss[0] if ss else None))
  work={'source':src['source'],'id':src['id'],'title':src['title'],'sub':src.get('sub') or '','exact':bool(src.get('exact'))} if src else {}
  idx={}
  if src and src.get('source')=='Bangumi':idx,e=work_index(src['id'])
  if not idx:
    # Bangumi 不通（或角色表读不到）→ 退到 AniList 的角色表。
    # 只认写法相同 / 简体变日文相同（泽渡真琴 → 沢渡真琴），把汉字改写成假名的（月宮あゆ）仍然对不上，
    # 那种只能列候选让人点。但**能确认的就得确认**，不能整体报「没法核对」把 3 个对的也否掉。
    aidx,awork,aerr=anilist_work(gname)
    if aidx:idx=aidx;work=awork;e=''
    else:e=e or aerr
  if not idx:
    why=f'作品角色表读不到（{e}）' if e else '作品角色表是空的'
    return {ch:{'state':'unknown','why':why} for ch in chars},work,(e or '')
  used=set();cands=None
  for ch in chars:
    hit=next((idx[k] for k in (_norm(ch),_vnorm(ch)) if k in idx and idx[k]['url'] not in used),None)
    if hit:
      items[ch]={'state':'ok','id':hit['id'],'name':hit['title'],'url':hit['url']}
      used.add(hit['url']);continue
    nk=''
    for k in (_norm(ch),_vnorm(ch)):
      nk=near_key(k,idx,used)
      if nk:break
    if nk:
      h=idx[nk];items[ch]={'state':'near','id':h['id'],'name':h['title'],'url':h['url'],'suggest':h['title']}
      used.add(h['url']);continue
    if cands is None:cands=work_chars(idx)
    # 判「没有这个名」用的是哪张表，决定这句话该怎么读：AniList 只有日文名，
    # 中文名 / 汉字改写成假名的（月宫亚由 / 月宮あゆ）在这张表里必然查不到，那不是名单写错了。
    bgm=(work.get('source') or '')=='Bangumi'
    items[ch]={'state':'missing','why':'作品角色表里没有这个名字' if bgm
               else 'AniList 的角色表里没有这个名字（这张表只有日文名，可能只是写法不同）','candidates':cands}
  return items,work,''
def bangumi_ready(timeout=8):
  """Bangumi 通不通。预检前先问这一句：中文名只在 Bangumi 有（AniList 只有日文 / 罗马字），
  它不通就没法核对——让每个团各等一次 15 秒超时，用户在向导里会以为页面死了。"""
  try:d,_=net.request(BGM+'search/subjects?limit=1',{'keyword':'test'},timeout=timeout)
  except Exception:return False
  return d is not None
def bind(roster_or_groups,log=lambda *a:None,skip_bound=False):
  """整份名单过一遍：每个角色名能不能配上图、配上哪个角色。落盘 uploads/art_bind.json。
  永不抛异常——网络不通时把角色记成 unknown（不算通过），让调用方自己决定要不要拦。
  skip_bound=True 时跳过已经绑过的角色：自动配图前顺手补一次，不会重复花钱。
  返回 {'groups':[{name,work,items}],ok,near,missing,unknown,total,bound,net}"""
  groups=roster_or_groups.get('groups') if isinstance(roster_or_groups,dict) else roster_or_groups
  BREAK.update(n={},down={})
  rep={'groups':[],'ok':0,'near':[],'missing':[],'unknown':[],'total':0,'bound':0,'net':True}
  store=bind_load()
  plan=[]
  for g in groups or []:
    name=(g.get('name') or '').strip()
    if not name or (g.get('kind') or 'cast')=='crew':continue
    chars=[]
    for m in g.get('members') or []:
      ch=(m.get('character') or '').strip()
      if ch and ch not in chars:chars.append(ch)
    if skip_bound:chars=[c for c in chars if not (store.get(bind_key(name,c)) or {}).get('url')]
    if chars:plan.append((name,chars))
  if not plan:return rep
  # Bangumi 不通也不再整体放弃：AniList 的角色表能确认写法相同的名字（泽渡真琴 / 沢渡真琴）。
  # 先探一次只是别让每个团各等一次超时；探不通就带着 AniList 继续。
  bgm=bangumi_ready()
  # 探过了就别再让每个团各等一次 15 秒超时：把结论交给熔断开关，后面的 subjects() 直接走 AniList。
  # 实测 5 个角色：不接这一步 45 秒（向导里一直显示「正在核对…」），接上以后十几秒。
  prev=dict(BREAK['down'])
  if not bgm:BREAK['down']['bgm']=True
  log('Bangumi 连不上，改用 AniList 的角色表核对（汉字改写假名的名字仍然对不上）' if not bgm else f'开始核对 {len(plan)} 个团')
  # 熔断是模块级状态：这次核对用完要还给原来的样子。不然向导里核一次，同进程的后台「找立绘」
  # 就再也不问 Bangumi 了——网站上去了也还是配不上图，只能重启。
  try:
    for name,chars in plan:
      log(f'核对 {name}（{len(chars)} 个角色）…')
      items,work,err=bind_group(name,chars,log=log)
      rep['groups'].append({'name':name,'work':work,'items':items,'error':err})
      for ch,it in items.items():
        rep['total']+=1;st=it.get('state')
        if st=='ok':rep['ok']+=1
        elif st=='near':rep['near'].append(f'{name} / {ch} → {it.get("suggest")}（名单里可能写错了）')
        elif st=='missing':rep['missing'].append(f'{name} / {ch}：{it.get("why") or "作品角色表里没有这个名字"}')
        else:rep['unknown'].append(f'{name} / {ch}：{it.get("why") or "没法核对"}')
        if it.get('id') and it.get('url'):
          store[bind_key(name,ch)]={'id':it['id'],'name':it.get('name') or ch,'url':it['url'],'group':name,'character':ch,'by':'auto'}
          rep['bound']+=1
  finally:BREAK['down']=prev
  # 全员都判不出来 = 网络在核对途中断了，而不是名字有问题。这两件事的补救办法完全不同，必须分开报。
  rep['net']=not (rep['total'] and len(rep['unknown'])==rep['total'])
  rep['bangumi']=bgm
  rep['sources']=sorted({(g.get('work') or {}).get('source') for g in rep['groups'] if (g.get('work') or {}).get('source')})
  if rep['bound']:bind_save(store)
  bind_run_save(rep)     # 留痕：分清「没跑核对」和「跑了但网络不通」，这两种的补救办法不一样
  return rep
def bind_line(rep):
  """一句话总结，给 firstrun 和向导用。"""
  tot=rep.get('total') or 0
  if not tot:
    return '' if rep.get('net',True) else '名单预检：Bangumi 和 AniList 都连不上，名字没法核对（不算通过）'
  if not rep.get('net',True):
    return '名单预检：现在 Bangumi 和 AniList 都连不上，名字没法核对（不算通过）。网络好了在后台点「一键配图」会自动再对一次'
  src='、'.join(rep.get('sources') or [])
  s=f"名单预检：{tot} 个角色里 {rep['ok']} 个能直接配上图"
  if src and 'Bangumi' not in src:s+=f"（Bangumi 不通，按 {src} 的角色表核对；汉字被改写成假名的名字它认不出）"
  if rep.get('near'):s+=f"，{len(rep['near'])} 个像写错了（{'、'.join(x.split('：')[0] for x in rep['near'][:3])}）"
  if rep.get('missing'):
    n=len(rep['missing'])
    s+=(f"，{n} 个在这张表里找不到（不代表名单写错了，可能只是写法不同）" if not rep.get('bangumi',True)
        else f"，{n} 个在作品里找不到")
  if rep.get('unknown'):s+=f"，{len(rep['unknown'])} 个没法判断"
  return s

# ── pick / download ───────────────────────────────────────────────────────
def allowed(url):
  try:h=urllib.parse.urlparse(url).hostname or ''
  except Exception:return False
  return urllib.parse.urlparse(url).scheme=='https' and any(h==x or h.endswith('.'+x) for x in HOSTS)
def fetch(url,limit=8_000_000,timeout=25):
  """Download a candidate image → bytes. Only the image hosts of the two sites (this is not a generic fetcher)."""
  if not allowed(url):raise ValueError('只能下载 Bangumi / AniList 的图片')
  b,e=net.request(url,raw=True,limit=limit,headers={'Accept':'image/*'},timeout=timeout)
  if b is None:raise ValueError('下载失败：'+e)
  return b
def save_portrait(group,character,url):
  import server
  name=server.save_upload('portraits',fetch(url));server.set_portrait(group,character,'portraits/'+name);return name
def save_cover(group,url,lock=None):
  import server,roster
  name=server.save_upload('covers',fetch(url))
  with (lock or threading.Lock()):
    d=roster.load();g=next((x for x in d['groups'] if x['name']==group),None)
    if not g:raise ValueError('没有这个团')
    g['cover']=name;roster.save(d,'配图')
  return name
# ── automatic pass ────────────────────────────────────────────────────────
def best_portrait(group,character,work_ids):
  cs,e=characters(character);time.sleep(PAUSE)
  if e:return None,e
  inwork=[c for c in cs if c['id'] in work_ids]
  # 有作品 id 时只认本作品里的角色（不同作品的同名角色不乱配）；bangumi 不通、拿不到 id 时才退到全局同名
  pick=next((c for c in inwork if c['exact']),None) or (inwork[0] if inwork else None) or (next((c for c in cs if c['exact']),None) if not work_ids else None)
  if not pick and not cs:
    a,_=anilist_characters(character);pick=next((c for c in a if c['exact']),None)
  return pick,None
def auto(lock=None,dry=False,redo=False,covers=True,portraits=True,log=print):
  """One pass over the roster. Returns a summary dict. Network errors skip the item, never abort the run."""
  import roster,server
  lock=lock or threading.Lock();d=roster.load();m=server.jload(config.C.MAP,{})
  BREAK.update(n={},down={})     # 每次配图重新判断网络：上次断了不影响这次
  binds=bind_load()              # 名单预检时绑好的名字 → 直接按 id 取图，不再搜索
  rep={'covers':0,'portraits':0,'skipped':[],'errors':[],'viacn':0,'bound':0,'near':[],'notes':[]}
  for g in d['groups']:
    # 工作组（摄影 / 后勤…）不是作品：拿组名去搜只会配上同名的无关作品（实测「摄影 / 后勤」配到了《摄影师的复仇》）
    if (g.get('kind') or 'cast')=='crew':continue
    work,werr=subjects(g['name'],4);time.sleep(PAUSE)
    work.sort(key=lambda x:(not x['exact'],x.get('type') not in (2,4)))
    top=work[0] if work else None
    if covers and (redo or not g.get('cover')):
      if top:
        log(f"封面 {g['name']} ← {top['title']}（{top['source']}）")
        if dry:rep['covers']+=1
        else:
          try:save_cover(g['name'],top['url'],lock);rep['covers']+=1
          except Exception as e:rep['errors'].append(f"{g['name']} 封面：{e}")
      else:rep['skipped'].append(f"{g['name']} 封面："+('搜索失败（'+str(werr)+'）' if werr else '没找到这部作品'))
    if not portraits:continue
    ids=set()
    # 只有 Bangumi 的作品 id 能拿去查角色表；退到 AniList 时别把 anilist id 发给 bgm.tv
    for s in work[:2]:
      if s.get('source')!='Bangumi':continue
      got,_=subject_chars(s['id']);ids|=got;time.sleep(PAUSE)
    idx={};built=[False]
    def index():
      """搜索落空时才建这张表：要逐个问角色详情，全员一次就搜到的话没必要花这个钱。"""
      if built[0]:return idx
      built[0]=True
      src=next((s for s in work if s.get('source')=='Bangumi'),None)
      if not src:return idx
      got,err=work_index(src['id'])
      if err:rep['notes'].append(f"{g['name']} 角色表：{err}")
      idx.update(got);return idx
    used=set();pend=[]
    for mb in g['members']:
      if down():break
      ch=(mb.get('character') or '').strip()
      if not ch or (not redo and f"{g['name']}|{ch}" in m):continue
      b=binds.get(bind_key(g['name'],ch))
      if b and b.get('url'):
        # 名单确定时就绑好了：直接按 id 取图。不发搜索请求，也不会配上同名的另一个角色。
        pick=None
        hit={'source':'Bangumi','id':b.get('id'),'title':b.get('name') or ch,'sub':'名单预检','url':b['url'],'thumb':b['url'],'exact':True}
      else:
        pick,e=best_portrait(g['name'],ch,ids)
        if e:rep['errors'].append(f'{ch}：{e}');continue
        hit=pick or index().get(_norm(ch))     # 搜不到（月宫亚由 / 月宮あゆ）→ 作品角色表里按中文名对
      if not hit:pend.append(ch);continue
      log(f"立绘 {g['name']} / {ch} ← {hit['title']}（{hit['source']}）")
      if dry:rep['portraits']+=1;used.add(hit['url']);continue
      try:
        with lock:save_portrait(g['name'],ch,hit['url'])
        rep['portraits']+=1;used.add(hit['url'])
        if b and b.get('url'):rep['bound']+=1
        elif not pick:rep['viacn']+=1
      except Exception as ex:rep['errors'].append(f'{ch}：{ex}')
    # 名单里的错字（美坂栎 / 美坂栞）：同作品角色表里只差一个字、且候选唯一时才认，两个以上就当没找到
    miss=[]
    for ch in pend:
      k=near_key(_norm(ch),idx,used)
      if not k:miss.append(ch);continue
      hit=idx[k]
      log(f"立绘 {g['name']} / {ch} ← {hit['title']}（近似名，名单里可能写错了）")
      if dry:rep['portraits']+=1;used.add(hit['url']);continue
      try:
        with lock:save_portrait(g['name'],ch,hit['url'])
        rep['portraits']+=1;used.add(hit['url']);rep['near'].append(f'{ch}→{hit["title"]}')
      except Exception as ex:rep['errors'].append(f'{ch}：{ex}')
    for ch in miss:
      why=('网络不通，中文名索引没建起来（Bangumi 连不上）；网络好了在后台点「一键配图」重试' if BREAK['down'].get('bgm')
           else '搜不到，作品角色表里也没有相近的名字（后台「找立绘」手选）')
      rep['skipped'].append(f"{g['name']} / {ch}：{why}")
    if down():
      rep['errors'].append('网络不通（Bangumi / AniList 都连不上），剩下的这次不找了；网络好了在后台点「一键配图」，已有的不会重下')
      break
  return rep
AUTO={'thread':None,'rep':None,'at':0.0}
def auto_bg(lock):
  t=AUTO['thread']
  if t and t.is_alive():return False
  def run():
    try:AUTO['rep']=auto(lock,log=lambda *a:None)
    except Exception as e:AUTO['rep']={'errors':[repr(e)]}
  AUTO.update(rep=None,at=time.time(),thread=threading.Thread(target=run,daemon=True));AUTO['thread'].start();return True
def auto_status():
  t=AUTO['thread'];return {'running':bool(t and t.is_alive()),'report':AUTO['rep'],'startedAt':AUTO['at']}
def main(a):
  import argparse
  ap=argparse.ArgumentParser(description='找立绘和封面');ap.add_argument('cmd',choices=('names','auto','search','roster'));ap.add_argument('q',nargs='*')
  ap.add_argument('--instance',default=os.environ.get('CASTCALL_INSTANCE') or os.path.join(config.ROOT,'instance'))
  ap.add_argument('--dry',action='store_true');ap.add_argument('--redo',action='store_true')
  ap.add_argument('--covers-only',action='store_true');ap.add_argument('--portraits-only',action='store_true');ap.add_argument('--group',default='')
  ap.add_argument('--limit',type=int,default=20,help='roster：每部作品最多几个角色（主角在前）');ap.add_argument('--main',action='store_true',help='roster：只要主角')
  ap.add_argument('-o','--out',help='roster：名单写进这个文件（默认打印）')
  o=ap.parse_args(a);o.q=' '.join(o.q) if o.cmd=='search' else o.q
  if o.cmd=='roster':
    if not o.q:ap.error('roster 后面跟作品名，几部就写几个：roster CLANNAD Kanon')
    text,notes=roster_text(o.q,o.limit,o.main,log=lambda *x:print(*x,file=sys.stderr))
    for n in notes:print(n,file=sys.stderr)
    if not text:return 1
    if o.out:
      with open(o.out,'w',encoding='utf-8') as f:f.write(text)
      print(f'名单写进了 {o.out}：角色全部空缺。给用户过目、补上 CN / 摄影后勤后，再 init.py --import',file=sys.stderr)
    else:print(text,end='')
    return 0
  config.use(o.instance)
  if o.cmd=='names':
    if not o.q:ap.error('names 后面跟名单文件：names 名单.txt（- 表示从标准输入读）')
    import importer
    try:text=sys.stdin.read() if o.q[0]=='-' else open(o.q[0],encoding='utf-8-sig').read()
    except OSError as e:ap.error(str(e))
    try:r=importer.parse(text,'我们的团')
    except ValueError as e:ap.error(str(e))
    rep=bind(r,log=lambda *x:print(*x,file=sys.stderr))
    for g in rep['groups']:
      w=g.get('work') or {}
      tag=('（'+w['title']+'）' if w.get('title') else '')+('' if w.get('exact',True) else '　← 团名不是精确的作品名，先确认是不是这部')
      print(f"\n【{g['name']}】{tag}")
      for ch,it in g['items'].items():
        st=it.get('state')
        if st=='ok':
          same=_norm(it.get('name') or '')==_norm(ch)
          print(f"  ✓ {ch}"+('' if same else f" → {it['name']}"))
        elif st=='near':print(f"  ⚠ {ch} → {it.get('suggest')}　名单里可能写错了，改成这个名字就配得上")
        elif st=='missing':
          print(f"  ✗ {ch}　{it.get('why')}")
          cs=it.get('candidates') or []
          if cs:print('      作品里是这些：'+'、'.join(c['name'] for c in cs[:10]))
        else:print(f"  ? {ch}　{it.get('why')}")
    print('\n'+bind_line(rep))
    if rep['near'] or rep['missing'] or not rep['net']:
      if not rep.get('bangumi',True):
        print('  上面这些是 AniList 的角色表认不出的（多半只是中文名 / 假名写法不同，不是写错）：'
              '网络好了重跑一次，或建站后在后台「找立绘」手选。')
      else:
        print('  改好名字再导入；不想改也行，建站后在后台「找立绘」手选。')
    return 0 if rep['total'] and rep['ok']==rep['total'] else 1
  if o.cmd=='search':
    res,e=search('cover' if o.covers_only else 'portrait',o.q or '',o.group)
    for r in res:print(f"[{r['source']}] {r['title']} / {r['sub']}{' ✓作品内' if r.get('inwork') else ''}\n    {r['url']}")
    if e:print(e)
    return 0
  rep=auto(dry=o.dry,redo=o.redo,covers=not o.portraits_only,portraits=not o.covers_only)
  print(f"\n{'（--dry）' if o.dry else ''}封面 {rep['covers']} 张、立绘 {rep['portraits']} 张。")
  if rep.get('viacn'):print(f"  其中 {rep['viacn']} 个按中文名在作品角色表里对上（搜索只认日文名）")
  for x in rep.get('near') or []:print('  近似名',x)
  for x in rep.get('notes') or []:print('  注意',x)
  for x in rep['skipped']:print('  跳过',x)
  for x in rep['errors']:print('  出错',x)
  return 1 if rep['errors'] and not (rep['covers'] or rep['portraits']) else 0
if __name__=='__main__':sys.exit(main(sys.argv[1:]))
