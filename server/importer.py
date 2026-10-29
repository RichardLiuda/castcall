"""名单导入：把团长手上现成的名单（群公告、Excel 复制出来的表格、CSV）变成名册。

文本格式（最常见，直接从群里复制）：

  ## CLANNAD                 ← 「#」或「##」开头是团名；没有团名行就全算一个团
  古河渚 云果                 ← 角色 + CN（空格、Tab、冒号、竖线、破折号都能隔开）
  冈崎朋也                    ← 只有角色 = 空缺，可以报名
  1. 藤林杏：糖球圆           ← 行首的序号、项目符号会被去掉
  摄影：阿光

CSV / TSV（第一行是表头）：认 团 / 作品 / group、角色 / character / role、CN / 成员 / member / coser 这几列，
没有「团」列就全算一个团。

parse() 只产出 {"groups":[...]}，不碰磁盘；merge() 把它并进已有名册。网页向导、tools/import.py 和 agent 都用这里。"""
import csv,io,re
PALETTE=['#e07a5f','#3d8bd9','#7b61c4','#2a9d8f','#e0a32c','#c94a4a','#5fa84a','#d9578c','#4a6fc9','#8a6d3b','#1fa39a','#9a6cc4']
CREW_WORDS=('摄影','后勤','妆娘','化妆','场务','工作人员','staff','crew')
SEP=re.compile(r'\s*(?:[:：|｜\t]|\s—\s|\s-\s|\s–\s)\s*|\s+')
BULLET=re.compile(r'^\s*(?:[-*•·]|\d+[.、)）]|[（(]\d+[)）])\s*')
HEAD=re.compile(r'^\s*#{1,3}\s*(.+?)\s*#*\s*$')
COLS={'group':('团','团名','作品','group','work','series'),'character':('角色','character','role','岗位'),
      'member':('cn','成员','member','coser','昵称','名字')}
def _col(h):
  h=(h or '').strip().lower()
  for k,names in COLS.items():
    if h in names:return k
  return None
def _crew(name):
  n=name.lower();return any(w in n for w in CREW_WORDS)
def _clean(s,n=59):return re.sub(r'\s+',' ',(s or '').strip())[:n]
def _group(name,i):
  g={'name':_clean(name) or f'团 {i+1}','color':PALETTE[i%len(PALETTE)],'members':[]}
  if _crew(g['name']):g['kind']='crew'
  return g
def parse_csv(text):
  sample=text[:2000];dialect=csv.Sniffer().sniff(sample,delimiters=',\t;') if any(c in sample for c in ',\t;') else csv.excel
  rows=list(csv.reader(io.StringIO(text),dialect))
  if not rows:return {'groups':[]}
  idx={_col(h):i for i,h in enumerate(rows[0]) if _col(h)}
  if 'character' not in idx and 'member' not in idx:return None
  groups={};order=[]
  for r in rows[1:]:
    get=lambda k:_clean(r[idx[k]]) if k in idx and idx[k]<len(r) else ''
    ch,mem,gn=get('character'),get('member'),get('group') or '我们的团'
    if not ch and not mem:continue
    if gn not in groups:groups[gn]=_group(gn,len(order));order.append(gn)
    groups[gn]['members'].append({'character':ch,'member':mem})
  return {'groups':[groups[n] for n in order]}
def looks_csv(text):
  first=next((l for l in text.splitlines() if l.strip()),'')
  return bool(re.search(r'[,\t;]',first)) and any(_col(c) for c in re.split(r'[,\t;]',first))
def parse(text,default_group='我们的团'):
  """Text or CSV → {'groups':[...]} (no ids). Raises ValueError when nothing usable is in it."""
  text=(text or '').replace('\r\n','\n').replace('\r','\n').lstrip('﻿')
  if looks_csv(text):
    d=parse_csv(text)
    if d and d['groups']:return d
  groups=[];cur=None
  for raw in text.split('\n'):
    line=raw.strip()
    if not line:continue
    m=HEAD.match(line)
    if m:cur=_group(m.group(1),len(groups));groups.append(cur);continue
    if line.startswith('>'):            # 「> 说明」写进团说明
      if cur is not None:cur['note']=((cur.get('note')+'\n') if cur.get('note') else '')+line[1:].strip()
      continue
    line=BULLET.sub('',line)
    parts=[p for p in SEP.split(line,maxsplit=1) if p]
    if not parts:continue
    ch=_clean(parts[0]);mem=_clean(parts[1]) if len(parts)>1 else ''
    if mem in ('待定','空','空缺','缺','?','？','-','—','tbd','TBD'):mem=''
    if cur is None:cur=_group(default_group,0);groups.append(cur)
    cur['members'].append({'character':ch,'member':mem})
  groups=[g for g in groups if g['members']]
  if not groups:raise ValueError('没有读到任何角色：每行写一个角色，后面跟 CN（空着就是空缺）')
  return {'groups':groups}
def merge(base,new):
  """Fold `new` into roster `base` (in place). Same group name → add missing roles; a vacant role gets the
  new CN. Existing CNs are never overwritten. Returns (added_groups, added_roles, filled)."""
  ag=ar=fl=0
  by={g['name']:g for g in base['groups']}
  for ng in new['groups']:
    g=by.get(ng['name'])
    if not g:
      ng=dict(ng);ng['color']=PALETTE[len(base['groups'])%len(PALETTE)];base['groups'].append(ng);by[ng['name']]=ng;ag+=1;ar+=len(ng['members']);continue
    for m in ng['members']:
      old=next((x for x in g['members'] if m['character'] and x.get('character')==m['character']),None)
      if old is None:g['members'].append(m);ar+=1
      elif m['member'] and not (old.get('member') or '').strip():old['member']=m['member'];fl+=1
  return ag,ar,fl
def summary(d):
  n=sum(len(g['members']) for g in d['groups']);v=sum(1 for g in d['groups'] for m in g['members'] if not m.get('member'))
  return f"{len(d['groups'])} 个团、{n} 个席位（{n-v} 已定、{v} 空缺）"
