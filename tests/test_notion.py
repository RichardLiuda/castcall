"""Notion adapter against an in-memory fake of the REST API (no network).

The fake speaks both versions the adapter knows: 2025-09-03 (databases → data_sources) and the 2022-06-28
database_id fallback, so both resolution paths are exercised."""
import os,sys,threading,unittest,uuid
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from helpers import Base,edit_site
import config,store,notion,review
SCHEMA={
 'roster':{'角色':'title','成员':'rich_text','团':'select','排序':'number','状态':'select','记录ID':'rich_text'},
 'signup':{'CN':'title','联系方式':'rich_text','团':'rich_text','角色':'rich_text','记录ID':'rich_text','状态':'select'},
 'guestbook':{'CN':'title','内容':'rich_text','状态':'select','时刻':'rich_text'},
}
def text(p):
  t=next(iter(k for k in p if k!='type'),None)
  v=p[t]
  if t in ('title','rich_text'):return ''.join(x['text']['content'] for x in v)
  if t in ('select','status'):return (v or {}).get('name','')
  return v
def back(typ,v):
  if typ in ('title','rich_text'):return {'type':typ,typ:[{'plain_text':v}]}
  if typ=='select':return {'type':'select','select':{'name':v} if v else None}
  if typ=='number':return {'type':'number','number':v}
  return {'type':typ}
class FakeNotion:
  def __init__(s,old_only=False):
    s.db={};s.pages={};s.calls=[];s.old_only=old_only
    for kind,cols in SCHEMA.items():
      i=uuid.uuid4().hex;s.db[i]={'kind':kind,'ds':uuid.uuid4().hex,'cols':cols}
  def id_of(s,kind):return next(i for i,d in s.db.items() if d['kind']==kind)
  def ds(s,x):return next((d for d in s.db.values() if d['ds']==x.replace('-','')),None)
  def __call__(s,path,body=None,method='GET',version=notion.NEW,timeout=20):
    s.calls.append((method,path,version))
    p=path.split('/');strip=lambda x:x.replace('-','')
    if path=='users/me':return {'name':'test-bot'},None
    if p[0]=='databases' and len(p)==2 and method=='GET':
      d=s.db.get(strip(p[1]))
      if not d:return None,'HTTP 404 object_not_found: no'
      if version==notion.NEW:
        if s.old_only:return None,'HTTP 400 validation_error: old workspace'
        return {'data_sources':[{'id':d['ds']}]},None
      return {'properties':{k:{'type':t} for k,t in d['cols'].items()}},None
    if p[0]=='data_sources' and len(p)==2:
      d=s.ds(p[1])
      if not d or s.old_only:return None,'HTTP 404 object_not_found: no'
      return {'properties':{k:{'type':t} for k,t in d['cols'].items()}},None
    if path=='pages' and method=='POST':
      par=body['parent'];d=s.ds(par['data_source_id']) if 'data_source_id' in par else s.db[strip(par['database_id'])]
      pid=str(uuid.uuid4());s.pages[pid]={'db':d,'props':{k:text(v) for k,v in body['properties'].items()},'archived':False}
      return {'id':pid},None
    if p[0]=='pages' and method=='PATCH':
      pg=s.pages.get(p[1])
      if not pg:return None,'HTTP 404 object_not_found: page'
      if body.get('archived'):pg['archived']=True
      pg['props'].update({k:text(v) for k,v in (body.get('properties') or {}).items()})
      return {'id':p[1]},None
    if p[-1]=='query':
      d=s.ds(p[1]) if p[0]=='data_sources' else s.db[strip(p[1])]
      res=[{'id':pid,'archived':pg['archived'],'properties':{k:back(d['cols'].get(k),v) for k,v in pg['props'].items()}} for pid,pg in s.pages.items() if pg['db'] is d]
      return {'results':res,'has_more':False},None
    return None,f'HTTP 400 unhandled {method} {path}'
  def rows(s,kind):return [pg for pg in s.pages.values() if pg['db']['kind']==kind and not pg['archived']]
  def set_status(s,kind,status,pred=lambda pg:True):
    for pg in s.rows(kind):
      if pred(pg):pg['props']['状态']=status

class NotionAdapter(Base):
  old_only=False
  def setUp(s):
    super().setUp()
    s.fake=FakeNotion(s.old_only);s._call=notion.call;notion.call=s.fake;notion._TG.clear()
    os.environ['NOTION_TOKEN']='secret_test'
    for k in ('roster','signup','guestbook'):os.environ['NOTION_'+k.upper()+'_DB']=s.fake.id_of(k)
  def tearDown(s):
    notion.call=s._call;notion._TG.clear()
    for k in ('NOTION_TOKEN','NOTION_ROSTER_DB','NOTION_SIGNUP_DB','NOTION_GUESTBOOK_DB'):os.environ.pop(k,None)
    super().tearDown()
  def check(s):
    import contextlib,io
    with contextlib.redirect_stdout(io.StringIO()) as out:rc=notion.check()
    return rc,out.getvalue()
  def test_check_passes(s):
    rc,out=s.check();s.assertEqual(rc,0,out)
  def test_check_reports_missing_column(s):
    del SCHEMA['signup']['联系方式'];s.fake=FakeNotion(s.old_only);notion.call=s.fake
    try:
      for k in ('roster','signup','guestbook'):os.environ['NOTION_'+k.upper()+'_DB']=s.fake.id_of(k)
      rc,out=s.check();s.assertEqual(rc,1);s.assertIn('缺少列：联系方式',out)
    finally:SCHEMA['signup']['联系方式']='rich_text'
  def test_signup_round_trip(s):
    g,m=s.vacant()
    s.assertEqual(s.c.post('/api/cast-signup',{'name':'诺心','contact':'wx9','work':g['name'],'character':m['character'],'id':m['id']}).status,200)
    r=store.signups()[0];notion.push_signup(r)
    row=s.fake.rows('signup')[0]['props']
    s.assertEqual((row['CN'],row['联系方式'],row['记录ID'],row['状态']),('诺心','wx9',m['id'],'待审'))
    lock=threading.Lock()
    s.fake.set_status('signup','已通过');rep=notion.pull_signups(lock);s.assertEqual(rep['approved'],1)
    seat=[x for gg in s.roster()['groups'] for x in gg['members'] if x['id']==m['id']][0];s.assertEqual(seat['member'],'诺心')
    s.fake.set_status('signup','待审');rep=notion.pull_signups(lock);s.assertEqual(rep['reopened'],1)
    seat=[x for gg in s.roster()['groups'] for x in gg['members'] if x['id']==m['id']][0];s.assertEqual(seat['member'],'')
  def test_web_decision_is_not_undone_by_stale_notion(s):
    g,m=s.vacant()
    s.c.post('/api/cast-signup',{'name':'甲','contact':'a','work':g['name'],'character':m['character'],'id':m['id']})
    r=store.signups()[0];notion.push_signup(r)
    with threading.Lock():review.approve(r['id'])
    notion.pull_signups(threading.Lock())       # Notion still says 待审
    s.assertEqual(store.signup(r['id'])['status'],'approved')
  def test_unpushed_rows_are_retried(s):
    g,m=s.vacant();tok=os.environ.pop('NOTION_TOKEN')     # Notion down while people post
    s.c.post('/api/cast-signup',{'name':'乙','contact':'b','work':g['name'],'character':m['character'],'id':m['id']})
    s.c.post('/api/guestbook',{'内容':'hi'})
    os.environ['NOTION_TOKEN']=tok
    s.assertEqual(notion.retry_unpushed(),2);s.assertEqual(notion.retry_unpushed(),0)
  def test_guestbook_hide_in_notion(s):
    s.c.post('/api/guestbook',{'CN':'丙','内容':'留言'});n=store.notes()[0];notion.push_note(n)
    s.assertEqual(s.fake.rows('guestbook')[0]['props']['状态'],'已通过')
    s.fake.set_status('guestbook','已隐藏');notion.pull_notes()
    s.assertEqual(s.c.get('/api/guestbook').json()['items'],[])
  def test_roster_push_creates_updates_archives(s):
    s.c.login();d=s.roster();d['groups'][0]['members'][0]['member']='改名';s.c.put('/api/data',d)
    rep=notion.push_roster();s.assertEqual(rep['pushed'],1);s.assertEqual(rep['failed'],[])
    s.assertEqual(s.fake.rows('roster')[0]['props']['成员'],'改名')
    s.assertEqual(store.pending_roster()[0],[])
    gone=s.roster()['groups'][0]['members'][0]['id']
    d=s.roster();d['groups'][0]['members'].pop(0);s.c.put('/api/data',d);notion.push_roster()
    ids=[pg['props']['记录ID'] for pg in s.fake.rows('roster')]
    s.assertNotIn(gone,ids)                 # archived
    s.assertEqual(len(ids),len(d['groups'][0]['members']))   # the rest moved up one place: 排序 changed
  def test_full_push_seeds_every_seat(s):
    n=sum(len(g['members']) for g in s.roster()['groups'])
    rep=notion.push_roster(full=True);s.assertEqual(rep['pushed'],n);s.assertEqual(len(s.fake.rows('roster')),n)
    notion.push_roster(full=True);s.assertEqual(len(s.fake.rows('roster')),n)   # second run updates, no duplicates
  def test_concurrent_push_creates_one_page(s):
    tok=os.environ.pop('NOTION_TOKEN');s.c.post('/api/guestbook',{'内容':'一次'});os.environ['NOTION_TOKEN']=tok
    n=store.notes()[0];real=s.fake.__call__;entered,gate=threading.Event(),threading.Event()
    def held(*a,**k):
      if a[0]=='pages':entered.set();gate.wait(5)
      return real(*a,**k)
    notion.call=held
    t=threading.Thread(target=lambda:notion.push_note(n));t.start()
    s.assertTrue(entered.wait(5))            # first push is inside the create call
    s.assertIsNone(notion.push_note(n))      # the retry loop's push of the same row backs off
    gate.set();t.join(5)
    s.assertEqual(len(s.fake.rows('guestbook')),1)
  def test_no_token_means_local_only(s):
    os.environ.pop('NOTION_TOKEN')
    s.assertFalse(config.C.notion_on());s.assertIn('skip',notion.push_roster())
    s.assertEqual(s.c.post('/api/guestbook',{'内容':'本地'}).status,200);s.assertEqual(len(s.c.get('/api/guestbook').json()['items']),1)
  def test_dash_accepts_links(s):
    i='0123456789abcdef0123456789abcdef'
    s.assertEqual(notion.dash(f'https://www.notion.so/ws/Title-{i}?v=fedcba9876543210fedcba9876543210'),'01234567-89ab-cdef-0123-456789abcdef')
    s.assertEqual(notion.dash(i),'01234567-89ab-cdef-0123-456789abcdef')
class NotionOldAPI(NotionAdapter):
  """Workspaces without data sources: everything falls back to 2022-06-28 database_id."""
  old_only=True
  def test_uses_old_version(s):
    t,e=notion.target('signup');s.assertEqual(t.version,notion.OLD);s.assertIn('database_id',t.parent)
if __name__=='__main__':unittest.main()
