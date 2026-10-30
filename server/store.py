"""Local database (sqlite3, stdlib). Always written first; Notion, when configured, only mirrors it.

Tables
  signups    公开报名：pending → approved / rejected（后台或 Notion 审核）
  guestbook  留言：approved（显示）/ hidden / pending（先审后发时）
  outbox     名册变更队列：网页保存和报名落座各记一条，推 Notion 用 acked 标记
  notion     本地记录 → Notion page id（名册行、报名、留言共用，按 kind 区分）
  photos     成员上传的本人照片：pending → approved / rejected；同一席位新照片通过后旧的变 replaced

A fresh connection per call with a busy timeout: the server is threaded and sqlite serialises writers itself,
so no file lock (the keyroster version used fcntl and did not run on Windows)."""
import datetime,json,os,sqlite3,time
import config
SCHEMA='''
create table if not exists signups(
  id integer primary key autoincrement,
  seat text not null, grp text not null, character text not null default '',
  name text not null, contact text not null,
  status text not null default 'pending', source text not null default '',
  created text not null, decided text not null default '', note text not null default '');
create index if not exists signups_seat on signups(seat,status);
create table if not exists guestbook(
  id integer primary key autoincrement,
  name text not null, body text not null,
  status text not null default 'approved', created text not null, source text not null default '');
create table if not exists outbox(
  seq integer primary key autoincrement,
  ts text not null, op text not null, rid text not null, rec text not null, acked integer not null default 0);
create table if not exists photos(
  id integer primary key autoincrement,
  seat text not null, grp text not null, character text not null default '', member text not null,
  file text not null, status text not null default 'pending', created text not null, decided text not null default '');
create index if not exists photos_seat on photos(seat,status);
create table if not exists notion(
  kind text not null, local text not null, page text not null, primary key(kind,local));
'''
def now():return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]+'Z'
def db():
  os.makedirs(os.path.dirname(config.C.DB),exist_ok=True)
  c=sqlite3.connect(config.C.DB,timeout=10,isolation_level=None)
  c.row_factory=sqlite3.Row;c.execute('pragma journal_mode=wal');c.executescript(SCHEMA);return c
def rows(c,q,*a):return [dict(r) for r in c.execute(q,a)]

# ── signups ────────────────────────────────────────────────────────────────
DUP_WINDOW=600
def add_signup(seat,grp,character,name,contact,source='网页'):
  """→ (row, duplicate). The same seat + name + contact inside 10 min is a retry, not a second signup:
  the existing row comes back and nothing is inserted (kept in the db, so it survives a restart)."""
  c=db()
  try:
    c.execute('begin immediate')
    since=(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(seconds=DUP_WINDOW)).strftime('%Y-%m-%dT%H:%M:%S')
    old=c.execute("select * from signups where seat=? and name=? and contact=? and status='pending' and created>=? order by id desc limit 1",(seat,name,contact,since)).fetchone()
    if old:c.execute('commit');return dict(old),True
    cur=c.execute('insert into signups(seat,grp,character,name,contact,created,source) values(?,?,?,?,?,?,?)',(seat,grp,character,name,contact,now(),source))
    r=c.execute('select * from signups where id=?',(cur.lastrowid,)).fetchone();c.execute('commit');return dict(r),False
  except Exception:
    try:c.execute('rollback')
    except Exception:pass
    raise
  finally:c.close()
def signups(status=None,limit=500):
  c=db()
  try:
    if status:return rows(c,'select * from signups where status=? order by id desc limit ?',status,limit)
    return rows(c,'select * from signups order by id desc limit ?',limit)
  finally:c.close()
def signup(i):
  c=db()
  try:r=c.execute('select * from signups where id=?',(int(i),)).fetchone();return dict(r) if r else None
  finally:c.close()
def set_signup(i,status,source='后台',note=''):
  c=db()
  try:c.execute('update signups set status=?,decided=?,source=?,note=? where id=?',(status,now(),source,note,int(i)))
  finally:c.close()
def counts():
  c=db()
  try:
    s={r['status']:r['n'] for r in c.execute('select status,count(*) n from signups group by status')}
    g={r['status']:r['n'] for r in c.execute('select status,count(*) n from guestbook group by status')}
    p={r['status']:r['n'] for r in c.execute('select status,count(*) n from photos group by status')}
    return {'signups':s,'guestbook':g,'photos':p}
  finally:c.close()

# ── guestbook ──────────────────────────────────────────────────────────────
def add_note(name,body,status,source='网页'):
  c=db()
  try:
    cur=c.execute('insert into guestbook(name,body,status,created,source) values(?,?,?,?,?)',(name,body,status,now(),source))
    return dict(c.execute('select * from guestbook where id=?',(cur.lastrowid,)).fetchone())
  finally:c.close()
def notes(status=None,limit=200):
  c=db()
  try:
    if status:return rows(c,'select * from guestbook where status=? order by id desc limit ?',status,limit)
    return rows(c,'select * from guestbook order by id desc limit ?',limit)
  finally:c.close()
def set_note(i,status,source='后台'):
  c=db()
  try:c.execute('update guestbook set status=?,source=? where id=?',(status,source,int(i)))
  finally:c.close()

# ── photos ─────────────────────────────────────────────────────────────────
def add_photo(seat,grp,character,member,file,status):
  c=db()
  try:
    c.execute('begin immediate')
    cur=c.execute('insert into photos(seat,grp,character,member,file,status,created) values(?,?,?,?,?,?,?)',(seat,grp,character,member,file,status,now()))
    if status=='approved':c.execute("update photos set status='replaced' where seat=? and status='approved' and id<>?",(seat,cur.lastrowid))
    r=dict(c.execute('select * from photos where id=?',(cur.lastrowid,)).fetchone());c.execute('commit');return r
  except Exception:
    try:c.execute('rollback')
    except Exception:pass
    raise
  finally:c.close()
def photos(limit=500):
  c=db()
  try:return rows(c,'select * from photos order by id desc limit ?',limit)
  finally:c.close()
def set_photo(i,status):
  """approve 时同一席位已通过的旧照片退成 replaced：每个席位最多一张在显示。"""
  c=db()
  try:
    c.execute('begin immediate')
    r=c.execute('select * from photos where id=?',(int(i),)).fetchone()
    if not r:c.execute('commit');return None
    if status=='approved':c.execute("update photos set status='replaced' where seat=? and status='approved' and id<>?",(r['seat'],r['id']))
    c.execute('update photos set status=?,decided=? where id=?',(status,now(),r['id']))
    r=dict(c.execute('select * from photos where id=?',(r['id'],)).fetchone());c.execute('commit');return r
  except Exception:
    try:c.execute('rollback')
    except Exception:pass
    raise
  finally:c.close()
def shown_photos():
  """{seat: (member, file)}：每个席位当前显示的那张。"""
  c=db()
  try:return {r['seat']:(r['member'],r['file']) for r in c.execute("select * from photos where status='approved' order by id")}
  finally:c.close()

# ── roster outbox ──────────────────────────────────────────────────────────
def log_roster(changes):
  """changes: [(op, id, rec)] from roster.diff()."""
  if not changes:return
  c=db();ts=now()
  try:
    c.execute('begin immediate')
    c.executemany('insert into outbox(ts,op,rid,rec) values(?,?,?,?)',[(ts,op,k,json.dumps(r,ensure_ascii=False)) for op,k,r in changes])
    c.execute('commit')
  finally:c.close()
def pending_roster():
  """Latest op per record that is not acked yet, oldest first, plus the highest seq they cover."""
  c=db()
  try:
    last={}
    for r in c.execute('select * from outbox where acked=0 order by seq'):last[r['rid']]=dict(r)
    items=sorted(last.values(),key=lambda r:r['seq'])
    top=c.execute('select max(seq) m from outbox where acked=0').fetchone()['m'] or 0
    for it in items:it['rec']=json.loads(it['rec'])
    return items,top
  finally:c.close()
def ack_roster(upto):
  c=db()
  try:c.execute('update outbox set acked=1 where seq<=?',(int(upto),))
  finally:c.close()

# ── notion page map ────────────────────────────────────────────────────────
def page_of(kind,local):
  c=db()
  try:r=c.execute('select page from notion where kind=? and local=?',(kind,str(local))).fetchone();return r['page'] if r else None
  finally:c.close()
def set_page(kind,local,page):
  c=db()
  try:c.execute('insert or replace into notion(kind,local,page) values(?,?,?)',(kind,str(local),page))
  finally:c.close()
def unmapped(kind,table,where=''):
  """Local rows of signups/guestbook that never reached Notion (to retry)."""
  c=db()
  try:return rows(c,f"select t.* from {table} t left join notion n on n.kind=? and n.local=cast(t.id as text) where n.page is null {where} order by t.id limit 50",kind)
  finally:c.close()
def pages(kind):
  c=db()
  try:return {r['local']:r['page'] for r in c.execute('select local,page from notion where kind=?',(kind,))}
  finally:c.close()
