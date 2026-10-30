#!/usr/bin/env python3
"""找立绘和封面：从 Bangumi（中文名最全）和 AniList（日文 / 罗马字）找候选图，下载进 uploads/。

  python3 server/artsearch.py auto             # 缺封面的团找封面、缺立绘的角色找立绘，挑最可信的那张
  python3 server/artsearch.py auto --dry       # 只看会配哪张，不下载
  python3 server/artsearch.py auto --redo      # 已有的也重新找
  python3 server/artsearch.py search 古河渚    # 列出候选
后台也能用：编辑角色 → 「找立绘」，编辑团 → 「找封面」，工具条「一键配图」。

匹配方式：先用团名在 Bangumi 找作品，再用角色名搜角色；同一个角色也出现在这部作品的角色表里，才算可靠，
否则退回「简体中文名完全相同」的那个；都没有就跳过（不乱配）。工作组（kind: crew）不找立绘。"""
import json,os,re,sys,threading,time,urllib.parse
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import config,net
BGM='https://api.bgm.tv/v0/'
ANI='https://graphql.anilist.co'
HOSTS=('lain.bgm.tv','bgm.tv','s4.anilist.co','anilist.co')
PAUSE=.35                     # Bangumi 没写限速，但别一秒几十个请求
def _bgm(path,body=None):
  return net.request(BGM+path,body,timeout=15)
def _cn(item):
  """Bangumi character / subject → (中文名, 其他名字...)"""
  names=[item.get('name_cn') or '']
  for b in item.get('infobox') or []:
    if b.get('key')=='简体中文名' and isinstance(b.get('value'),str):names.insert(0,b['value'])
    if b.get('key')=='别名' and isinstance(b.get('value'),list):names+=[x.get('v','') for x in b['value'] if isinstance(x,dict)]
  return [n.strip() for n in names if n and n.strip()]
def _norm(s):return re.sub(r'[\s·・.\-—_!！?？~～]','',(s or '').lower())
def _img(images,*keys):
  for k in keys:
    if isinstance(images,dict) and images.get(k):return images[k]
  return ''
# ── search ────────────────────────────────────────────────────────────────
def subjects(q,limit=6):
  d,e=_bgm(f'search/subjects?limit={limit}',{'keyword':q})
  if d is None:return [],e
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
def characters(q,limit=8):
  d,e=_bgm(f'search/characters?limit={limit}',{'keyword':q})
  if d is None:return [],e
  out=[]
  for c in d.get('data') or []:
    u=_img(c.get('images'),'large','medium')
    if not u:continue
    names=_cn(c)
    out.append({'source':'Bangumi','id':c.get('id'),'title':names[0] if names else c.get('name'),'sub':c.get('name'),'url':u,
      'thumb':_img(c.get('images'),'medium','grid','large'),'exact':_norm(q) in {_norm(n) for n in names+[c.get('name') or '']}})
  return out,None
def anilist_characters(q,limit=6):
  d,e=net.request(ANI,{'query':'query($s:String,$n:Int){Page(perPage:$n){characters(search:$s){id name{full native} image{large medium}}}}','variables':{'s':q,'n':limit}},timeout=15)
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
  d,e=net.request(ANI,{'query':'query($s:String,$n:Int){Page(perPage:$n){media(search:$s){id title{romaji native} coverImage{extraLarge large} bannerImage}}}','variables':{'s':q,'n':limit}},timeout=15)
  if d is None:return [],e
  out=[]
  for m in ((d.get('data') or {}).get('Page') or {}).get('media') or []:
    for u,t in ((m.get('bannerImage'),'横幅'),((m.get('coverImage') or {}).get('extraLarge'),'封面')):
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
    a.sort(key=lambda x:(not x['exact'],x['type'] not in (2,4)));res=a+b
  else:
    a,e=characters(q);errs+=[e] if e else []
    if group and a:
      ss,_=subjects(group,3);ids=set()
      for s in ss[:2]:
        got,_=subject_chars(s['id']);ids|=got
      for x in a:x['inwork']=x['id'] in ids
      a.sort(key=lambda x:(not x.get('inwork'),not x['exact']))
    b,e=anilist_characters(q);errs+=[e] if e else []
    res=a+b
  return res,('；'.join(errs) if errs and not res else None)
# ── pick / download ───────────────────────────────────────────────────────
def allowed(url):
  try:h=urllib.parse.urlparse(url).hostname or ''
  except Exception:return False
  return urllib.parse.urlparse(url).scheme=='https' and any(h==x or h.endswith('.'+x) for x in HOSTS)
def fetch(url):
  """Download a candidate image → bytes. Only the image hosts of the two sites (this is not a generic fetcher)."""
  if not allowed(url):raise ValueError('只能下载 Bangumi / AniList 的图片')
  b,e=net.request(url,raw=True,limit=8_000_000,headers={'Accept':'image/*'},timeout=25)
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
  pick=next((c for c in inwork if c['exact']),None) or (inwork[0] if inwork else None) or (next((c for c in cs if c['exact']),None) if not work_ids else None)
  if not pick and not cs:
    a,_=anilist_characters(character);pick=next((c for c in a if c['exact']),None)
  return pick,None
def auto(lock=None,dry=False,redo=False,covers=True,portraits=True,log=print):
  """One pass over the roster. Returns a summary dict. Network errors skip the item, never abort the run."""
  import roster,server
  lock=lock or threading.Lock();d=roster.load();m=server.jload(config.C.MAP,{})
  rep={'covers':0,'portraits':0,'skipped':[],'errors':[]}
  for g in d['groups']:
    work,_=subjects(g['name'],4);time.sleep(PAUSE)
    work.sort(key=lambda x:(not x['exact'],x['type'] not in (2,4)))
    top=work[0] if work else None
    if covers and (redo or not g.get('cover')):
      if top:
        log(f"封面 {g['name']} ← {top['title']}（{top['source']}）")
        if dry:rep['covers']+=1
        else:
          try:save_cover(g['name'],top['url'],lock);rep['covers']+=1
          except Exception as e:rep['errors'].append(f"{g['name']} 封面：{e}")
      else:rep['skipped'].append(f"{g['name']} 封面：没找到这部作品")
    if not portraits or (g.get('kind') or 'cast')=='crew':continue
    ids=set()
    for s in work[:2]:
      got,_=subject_chars(s['id']);ids|=got;time.sleep(PAUSE)
    for mb in g['members']:
      ch=(mb.get('character') or '').strip()
      if not ch or (not redo and f"{g['name']}|{ch}" in m):continue
      pick,e=best_portrait(g['name'],ch,ids)
      if e:rep['errors'].append(f'{ch}：{e}');continue
      if not pick:rep['skipped'].append(f"{g['name']} / {ch}：没有可靠的匹配");continue
      log(f"立绘 {g['name']} / {ch} ← {pick['title']}（{pick['source']}）")
      if dry:rep['portraits']+=1
      else:
        try:
          with lock:save_portrait(g['name'],ch,pick['url'])
          rep['portraits']+=1
        except Exception as ex:rep['errors'].append(f'{ch}：{ex}')
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
  ap=argparse.ArgumentParser(description='找立绘和封面');ap.add_argument('cmd',choices=('auto','search'));ap.add_argument('q',nargs='?')
  ap.add_argument('--instance',default=os.environ.get('CASTCALL_INSTANCE') or os.path.join(config.ROOT,'instance'))
  ap.add_argument('--dry',action='store_true');ap.add_argument('--redo',action='store_true')
  ap.add_argument('--covers-only',action='store_true');ap.add_argument('--portraits-only',action='store_true');ap.add_argument('--group',default='')
  o=ap.parse_args(a);config.use(o.instance)
  if o.cmd=='search':
    res,e=search('cover' if o.covers_only else 'portrait',o.q or '',o.group)
    for r in res:print(f"[{r['source']}] {r['title']} / {r['sub']}{' ✓作品内' if r.get('inwork') else ''}\n    {r['url']}")
    if e:print(e)
    return 0
  rep=auto(dry=o.dry,redo=o.redo,covers=not o.portraits_only,portraits=not o.covers_only)
  print(f"\n{'（--dry）' if o.dry else ''}封面 {rep['covers']} 张、立绘 {rep['portraits']} 张。")
  for x in rep['skipped']:print('  跳过',x)
  for x in rep['errors']:print('  出错',x)
  return 1 if rep['errors'] and not (rep['covers'] or rep['portraits']) else 0
if __name__=='__main__':sys.exit(main(sys.argv[1:]))
