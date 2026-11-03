import json,os,sys,unittest,urllib.parse
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from helpers import Base,Client,PW,edit_site
import config,store
def wf(p,t):
  with open(p,'w',encoding='utf-8') as f:f.write(t)
def signup_body(g,m,name='新人',contact='wx_new'):
  return {'name':name,'contact':contact,'work':g['name'],'character':m.get('character',''),'id':m['id']}

class Pages(Base):
  def test_index_renders_config(s):
    r=s.c.get('/');s.assertEqual(r.status,200);h=r.text
    s.assertIn('<title>示例 cos 团建 · 成员一览</title>',h)
    s.assertIn('data-mode=multi',h);s.assertIn('某某公园',h)
    s.assertNotIn('{{',h)
    s.assertNotIn('{{',h)
  def test_site_js_is_public_only(s):
    t=s.c.get('/site.js').text;s.assertTrue(t.startswith('window.SITE='))
    d=json.loads(t[len('window.SITE='):-1]);s.assertEqual(d['mode'],'multi');s.assertEqual(d['signupState'],'open')
    s.assertNotIn('server',d);s.assertNotIn('limits',d);s.assertNotIn('notion',d)
  def test_guestbook_section_can_be_switched_off(s):
    edit_site(lambda j:j['guestbook'].update(enabled=False))
    s.assertNotIn('id=guestbook',s.c.get('/').text);s.assertEqual(s.c.get('/api/guestbook').status,404)
  def test_static_and_traversal(s):
    s.assertEqual(s.c.get('/cbase.js').status,200)
    s.assertEqual(s.c.get('/covers/../../auth.json').status,404)
    s.assertEqual(s.c.get('/covers/%2e%2e/%2e%2e/auth.json').status,404)

class Auth(Base):
  def test_login_and_save_requires_session(s):
    d=s.roster();s.assertEqual(s.c.put('/api/data',d).status,401)
    s.assertEqual(s.c.login('wrong').status,401)
    s.assertEqual(s.c.login().status,200);s.assertTrue(s.c.get('/api/me').json()['auth'])
    d['groups'][0]['members'][0]['member']='改过';r=s.c.put('/api/data',d);s.assertEqual(r.status,200)
    s.assertEqual(s.roster()['groups'][0]['members'][0]['member'],'改过')
  def test_no_default_password(s):
    import server
    for pw in ('','admin','password','castcall'):s.assertFalse(server.check_pw(pw))
  def test_login_rate_limit(s):
    for _ in range(5):s.assertEqual(s.c.login('nope').status,401)
    s.assertEqual(s.c.login().status,429)
  def test_forwarded_header_ignored_unless_trusted(s):
    for i in range(5):s.c.req('POST','/api/login',{'password':'x'},headers={'CF-Connecting-IP':f'10.0.0.{i}'})
    s.assertEqual(s.c.req('POST','/api/login',{'password':PW},headers={'CF-Connecting-IP':'10.9.9.9'}).status,429)
  def test_forwarded_header_used_when_trusted(s):
    edit_site(lambda j:j['server'].update(trustProxyHeader='X-Forwarded-For'))
    for i in range(5):s.c.req('POST','/api/login',{'password':'x'},headers={'X-Forwarded-For':'10.0.0.1'})
    s.assertEqual(s.c.req('POST','/api/login',{'password':PW},headers={'X-Forwarded-For':'10.0.0.2'}).status,200)
  def test_uninitialized_server_goes_to_wizard(s):
    import server
    os.remove(config.C.AUTH)
    try:
      s.assertFalse(server.preflight());s.assertTrue(server.SETUP['token'])
      r=s.c.get('/');s.assertEqual(r.status,302);s.assertEqual(r.header('location'),'/setup')
      s.assertEqual(s.c.post('/api/login',{'password':PW}).status,409)
    finally:server.SETUP.update(token=None,instance=None)

class Saving(Base):
  def test_save_chain_backup_outbox(s):
    s.c.login();d=s.roster();d['groups'][1]['members'][0]['member']='换人'
    s.assertEqual(s.c.put('/api/data',d).status,200)
    s.assertTrue(any(f.startswith('roster-') for f in os.listdir(config.C.BACKUPS)))
    items,top=store.pending_roster();s.assertEqual(len(items),1);s.assertEqual(items[0]['rec']['member'],'换人')
  def test_invalid_roster_rejected(s):
    s.c.login();d=s.roster();d['groups'][0]['color']='red'
    s.assertEqual(s.c.put('/api/data',d).status,400)
    d=s.roster();d['groups'][1]['name']=d['groups'][0]['name'];s.assertEqual(s.c.put('/api/data',d).status,400)
    d=s.roster();d['groups'][0]['cover']='../x.jpg';s.assertEqual(s.c.put('/api/data',d).status,400)

class Signups(Base):
  def test_signup_review_seats_member(s):
    g,m=s.vacant();r=s.c.post('/api/cast-signup',signup_body(g,m));s.assertEqual(r.status,200,r.text)
    s.assertEqual(store.signups('pending')[0]['seat'],m['id'])
    s.assertEqual(dict((x['id'],x) for gg in s.roster()['groups'] for x in gg['members'])[m['id']].get('member',''),'',  'roster untouched before review')
    s.c.login();i=store.signups('pending')[0]['id']
    r=s.c.post(f'/api/admin/signups/{i}',{'action':'approve'});s.assertEqual(r.status,200,r.text)
    seat=dict((x['id'],x) for gg in s.roster()['groups'] for x in gg['members'])[m['id']]
    s.assertEqual(seat['member'],'新人')
    s.assertEqual(s.c.post('/api/cast-signup',signup_body(g,m,'别人','wx2')).status,409)
    r=s.c.post(f'/api/admin/signups/{i}',{'action':'reject'});s.assertEqual(r.status,200)
    seat=dict((x['id'],x) for gg in s.roster()['groups'] for x in gg['members'])[m['id']];s.assertEqual(seat['member'],'')
  def test_duplicate_within_window(s):
    g,m=s.vacant()
    s.assertFalse(s.c.post('/api/cast-signup',signup_body(g,m)).json()['duplicate'])
    s.assertTrue(s.c.post('/api/cast-signup',signup_body(g,m)).json()['duplicate'])
    s.assertEqual(len(store.signups()),1)
  def test_approve_never_overwrites(s):
    g,m=s.vacant()
    s.c.post('/api/cast-signup',signup_body(g,m,'甲','a1'));s.c.post('/api/cast-signup',signup_body(g,m,'乙','b2'))
    s.c.login();ids=sorted(x['id'] for x in store.signups())
    s.assertEqual(s.c.post(f'/api/admin/signups/{ids[0]}',{'action':'approve'}).status,200)
    r=s.c.post(f'/api/admin/signups/{ids[1]}',{'action':'approve'});s.assertEqual(r.status,409);s.assertIn('甲',r.json()['message'])
  def test_closed_group_and_window(s):
    d=s.roster();closed=[g for g in d['groups'] if g.get('signup')=='closed'][0]
    m=closed['members'][0];m2=dict(m,member='')
    r=s.c.post('/api/cast-signup',signup_body(closed,m2));s.assertEqual(r.status,400)
    edit_site(lambda j:j['signup'].update(closesAt='2000-01-01T00:00:00+08:00'))
    g,m=s.vacant();r=s.c.post('/api/cast-signup',signup_body(g,m));s.assertEqual(r.status,400);s.assertIn('截止',r.json()['error'])
  def test_contact_pattern_and_legacy_field(s):
    edit_site(lambda j:j['signup'].update(contactLabel='QQ',contactPattern='[1-9][0-9]{4,11}'))
    g,m=s.vacant();b=signup_body(g,m,contact='abc');s.assertEqual(s.c.post('/api/cast-signup',b).status,400)
    b=signup_body(g,m);b.pop('contact');b['wechat']='123456'
    s.assertEqual(s.c.post('/api/cast-signup',b).status,200)
  def test_stale_seat(s):
    g,m=s.vacant();b=signup_body(g,m);b['character']='别的角色'
    s.assertEqual(s.c.post('/api/cast-signup',b).status,409)
  def test_signup_rate_limit(s):
    g,m=s.vacant()
    for i in range(8):s.c.post('/api/cast-signup',signup_body(g,m,f'人{i}',f'c{i}'))
    s.assertEqual(s.c.post('/api/cast-signup',signup_body(g,m,'再来','x')).status,429)
  def test_admin_requires_login(s):
    s.assertEqual(s.c.get('/api/admin/signups').status,401)
    s.assertEqual(s.c.post('/api/admin/signups/1',{'action':'approve'}).status,401)

class Guestbook(Base):
  def test_post_moderation(s):
    s.assertEqual(s.c.post('/api/guestbook',{'CN':'','内容':'你好'}).status,200)
    items=s.c.get('/api/guestbook').json()['items'];s.assertEqual(items[0]['CN'],'匿名');s.assertEqual(items[0]['内容'],'你好')
    s.c.login();i=items[0]['id']
    s.assertEqual(s.c.post(f'/api/admin/guestbook/{i}',{'action':'hide'}).status,200)
    s.assertEqual(s.c.get('/api/guestbook').json()['items'],[])
    s.c.post(f'/api/admin/guestbook/{i}',{'action':'show'});s.assertEqual(len(s.c.get('/api/guestbook').json()['items']),1)
  def test_honeypot(s):
    s.assertEqual(s.c.post('/api/guestbook',{'内容':'spam','website':'http://x'}).status,200)
    s.assertEqual(store.notes(),[])
  def test_validation(s):
    s.assertEqual(s.c.post('/api/guestbook',{'内容':''}).status,400)
    s.assertEqual(s.c.post('/api/guestbook',{'内容':'x'*501}).status,400)
class GuestbookPre(Base):
  site={'guestbook':{'moderation':'pre'}}
  def test_pre_moderation(s):
    r=s.c.post('/api/guestbook',{'内容':'等审核'});s.assertTrue(r.json()['pending'])
    s.assertEqual(s.c.get('/api/guestbook').json()['items'],[])
    s.c.login();i=store.notes()[0]['id'];s.c.post(f'/api/admin/guestbook/{i}',{'action':'approve'})
    s.assertEqual(len(s.c.get('/api/guestbook').json()['items']),1)

class Uploads(Base):
  PNG=b'\x89PNG\r\n\x1a\n'+b'\x00'*64
  def test_upload_cover_and_portrait(s):
    s.c.login()
    r=s.c.req('POST','/api/admin/upload?kind=cover',raw=s.PNG);s.assertEqual(r.status,200,r.text);f=r.json()['file']
    s.assertTrue(f.endswith('.png'));s.assertEqual(s.c.get('/covers/'+f).status,200)
    r=s.c.req('POST','/api/admin/upload?kind=portrait&group=%E7%A4%BA%E4%BE%8B%E4%BD%9C%E5%93%81%20A&character=%E4%B8%BB%E8%A7%92',raw=s.PNG);s.assertEqual(r.status,200)
    chars=s.c.get('/chars.js').text;s.assertIn('示例作品 A|主角',chars)
    s.assertEqual(s.c.req('POST','/api/admin/upload?kind=cover',raw=b'<svg onload=alert(1)>'+b' '*40).status,400)
  def test_brand_slots(s):
    s.assertEqual(s.c.get('/api/admin/brand').status,401)
    s.assertEqual(s.c.req('POST','/api/admin/brand?slot=logo',raw=s.PNG).status,401)
    s.c.login()
    st=s.c.get('/api/admin/brand').json()['slots'];s.assertEqual(st['logo']['url'],'')
    r=s.c.req('POST','/api/admin/brand?slot=logo',raw=s.PNG);s.assertEqual(r.status,200,r.text);f=r.json()['file']
    s.assertEqual(r.json()['slots']['logo']['file'],f);s.assertEqual(s.c.get('/brand/'+f).status,200)
    s.assertIn(f'/brand/{f}',s.c.get('/').text)                    # site.json 热加载，页面立刻带上 logo
    s.assertEqual(s.c.req('POST','/api/admin/brand?slot=favicon',raw=s.PNG).status,200)
    s.assertIn(f'rel=icon href="/brand/{f}"',s.c.get('/').text)
    s.assertEqual(s.c.req('POST','/api/admin/brand?slot=hero',raw=s.PNG).status,200)
    s.assertEqual(config.C.site['poster']['hero'],f)
    s.assertEqual(s.c.req('POST','/api/admin/brand?slot=logo&clear=1',raw=b'').status,200)
    s.assertNotIn('class=brandlogo',s.c.get('/').text)
    s.assertEqual(s.c.req('POST','/api/admin/brand?slot=accent',raw=s.PNG).status,400)
    s.assertEqual(s.c.req('POST','/api/admin/brand?slot=logo',raw=b'<svg onload=alert(1)>'+b' '*40).status,400)
  def test_upload_requires_login(s):
    s.assertEqual(s.c.req('POST','/api/admin/upload?kind=cover',raw=s.PNG).status,401)

class Single(Base):
  mode='single'
  def test_single_mode_and_signup(s):
    s.assertIn('data-mode=single',s.c.get('/').text)
    g,m=s.vacant();s.assertEqual(s.c.post('/api/cast-signup',signup_body(g,m)).status,200)
    s.c.login();i=store.signups()[0]['id'];s.assertEqual(s.c.post(f'/api/admin/signups/{i}',{'action':'approve'}).status,200)
  def test_mode_override(s):
    edit_site(lambda j:j.update(mode='multi'))
    s.assertIn('data-mode=multi',s.c.get('/').text)

class Poster(Base):
  def test_poster_missing_is_404_not_500(s):
    s.assertEqual(s.c.get('/poster/master.html').status,404)
  def test_poster_page_gets_chrome(s):
    wf(os.path.join(config.C.POSTER,'master.html'),'<!doctype html><html><head></head><body><p>x</p></body></html>')
    r=s.c.get('/poster/master.html');s.assertEqual(r.status,200);s.assertIn('kr-poster-chrome',r.text);s.assertIn('data-slug="castcall"',r.text)
    s.assertIn('posterlink-hdr',s.c.get('/').text)

class Examples(unittest.TestCase):
  def test_init_example_seeds_demo_content(s):
    import contextlib,io,shutil,tempfile,store,roster
    from helpers import ROOT
    sys.path.insert(0,ROOT);import init
    d=tempfile.mkdtemp(prefix='castcall-seed-')
    try:
      with contextlib.redirect_stdout(io.StringIO()):s.assertEqual(init.main(['--instance',d,'--example','key-single','--password','x'*10,'--yes']),0)
      r=roster.load();s.assertTrue(all(g.get('cover') for g in r['groups']))
      s.assertTrue(os.path.isfile(os.path.join(config.C.UPLOADS,'covers',r['groups'][0]['cover'])))
      s.assertEqual(len(store.notes('approved')),6);pend=store.signups('pending');s.assertGreaterEqual(len(pend),3)
      seats={m['id']:m for g in r['groups'] for m in g['members']}
      s.assertTrue(all(not seats[x['seat']].get('member') for x in pend),'signups only target vacant seats')
    finally:shutil.rmtree(d,ignore_errors=True)
  def test_every_example_roster_is_valid(s):
    import glob,roster
    from helpers import ROOT,rj
    fs=glob.glob(os.path.join(ROOT,'examples','roster.*.json'));s.assertGreaterEqual(len(fs),4)
    for f in fs:
      d=rj(f)
      with s.subTest(f=os.path.basename(f)):
        roster.validate(d)
        s.assertTrue(all(not m.get('id') for g in d['groups'] for m in g['members']),'examples carry no ids')

class Importer(unittest.TestCase):
  def test_text_formats(s):
    import importer
    d=importer.parse('## A团\n> 说明\n1. 古河渚 云果\n冈崎朋也\n藤林杏：糖球圆\n- 春原阳平 | 待定\n## 摄影\n摄影 阿光')
    s.assertEqual([g['name'] for g in d['groups']],['A团','摄影'])
    s.assertEqual(d['groups'][0]['note'],'说明');s.assertEqual(d['groups'][1].get('kind'),'crew')
    s.assertEqual([(m['character'],m['member']) for m in d['groups'][0]['members']],[('古河渚','云果'),('冈崎朋也',''),('藤林杏','糖球圆'),('春原阳平','')])
    s.assertEqual(importer.parse('古河渚\t云果','我们')['groups'][0]['name'],'我们')
    s.assertRaises(ValueError,importer.parse,'\n\n## 空团\n')
  def test_csv(s):
    import importer
    d=importer.parse('团,角色,CN\nCLANNAD,古河渚,云果\nCLANNAD,冈崎朋也,\nKanon,月宫亚由,大圆\n')
    s.assertEqual([(g['name'],len(g['members'])) for g in d['groups']],[('CLANNAD',2),('Kanon',1)])
  def test_merge_never_overwrites(s):
    import importer
    base={'groups':[{'name':'A','color':'#111111','members':[{'character':'x','member':'甲'},{'character':'y','member':''}]}]}
    ag,ar,fl=importer.merge(base,importer.parse('## A\nx 乙\ny 丙\nz\n## B\nw'))
    s.assertEqual((ag,ar,fl),(1,2,1));s.assertEqual(base['groups'][0]['members'][0]['member'],'甲');s.assertEqual(base['groups'][0]['members'][1]['member'],'丙')

class Wizard(unittest.TestCase):
  def setUp(s):
    import tempfile,server
    s.dir=tempfile.mkdtemp(prefix='castcall-wz-');config.use(s.dir);server.HITS.clear();server.SESS.clear();server.bg=lambda fn:fn()
    s.assertFalse(server.preflight());s.tok=server.SETUP['token'];s.c=Client()
  def tearDown(s):
    import shutil,server
    server.SETUP.update(token=None,instance=None);shutil.rmtree(s.dir,ignore_errors=True)
  def body(s,**k):
    b={'token':s.tok,'mode':'single','title':'测试团片','date':'2026-12-12','start':'2026-12-12T11:00:00+08:00','location':'公园',
       'contact':'微信 abc','contactLabel':'QQ','source':'paste','names':'古河渚 云果\n冈崎朋也','password':'pw-12345678'};b.update(k);return b
  def test_wizard_flow(s):
    s.assertEqual(s.c.get('/setup').status,200)
    s.assertEqual(s.c.post('/api/setup',s.body(token='wrong')).status,403)
    pv=s.c.post('/api/setup/preview',s.body());s.assertEqual(pv.status,200);s.assertIn('1 已定',pv.json()['summary'])
    r=s.c.post('/api/setup',s.body());s.assertEqual(r.status,200,r.text)
    s.assertTrue(s.c.get('/api/me').json()['auth'],'wizard logs the admin in')
    import roster
    d=roster.load();s.assertEqual([m['member'] for m in d['groups'][0]['members']],['云果',''])
    site=config.C.site;s.assertEqual(site['event']['title'],'测试团片');s.assertEqual(site['signup']['contactLabel'],'QQ')
    s.assertEqual(s.c.get('/').status,200)
    s.assertEqual(s.c.post('/api/setup',s.body()).status,404,'wizard closes after the first success')
  def test_wizard_multi_blank_and_example(s):
    r=s.c.post('/api/setup',s.body(mode='multi',source='blank'));s.assertEqual(r.status,200,r.text)
    s.assertEqual(config.C.site['mode'],'multi')
  def test_wizard_example(s):
    r=s.c.post('/api/setup',s.body(source='example',example='key-single'));s.assertEqual(r.status,200,r.text)
    import store;s.assertGreaterEqual(len(store.signups('pending')),3)
  def test_short_password(s):
    s.assertEqual(s.c.post('/api/setup',s.body(password='short')).status,400)

class ImportCLI(Base):
  def test_import_merge_and_replace(s):
    import contextlib,io,tempfile
    from helpers import ROOT
    sys.path.insert(0,os.path.join(ROOT,'tools'));imp=__import__('import')
    f=os.path.join(s.dir,'n.txt')
    with open(f,'w',encoding='utf-8') as fh:fh.write('## 新团\n角色甲 小甲\n角色乙\n')
    with contextlib.redirect_stdout(io.StringIO()):s.assertEqual(imp.main([f,'--instance',s.dir]),0)
    names=[g['name'] for g in s.roster()['groups']];s.assertIn('新团',names);s.assertGreater(len(names),1)
    with contextlib.redirect_stdout(io.StringIO()):s.assertEqual(imp.main([f,'--instance',s.dir,'--replace']),0)
    s.assertEqual([g['name'] for g in s.roster()['groups']],['新团'])

if __name__=='__main__':unittest.main()

class Photos(Base):
  PNG=b'\x89PNG\r\n\x1a\n'+b'\x00'*64
  def seated(s):
    import roster
    for g in roster.load()['groups']:
      for m in g['members']:
        if (m.get('member') or '').strip():return g,m
  def up(s,m,name=None,raw=None):
    q=urllib.parse.urlencode({'seat':m['id'],'name':m['member'] if name is None else name})
    return s.c.req('POST','/api/photo?'+q,raw=raw or s.PNG)
  def test_photos_flow(s):
    g,m=s.seated()
    s.assertEqual(s.up(m).status,404)                                  # 默认关
    edit_site(lambda j:j.setdefault('photos',{}).update(enabled=True))
    s.assertEqual(s.up(m,name='别人').status,403)
    s.assertEqual(s.up(m,raw=b'<svg onload=alert(1)>'+b' '*40).status,400)
    r=s.up(m);s.assertEqual(r.status,200,r.text);s.assertTrue(r.json()['pending'])
    s.assertNotIn(m['id'],s.c.get('/chars.js').text.split('window.PHOTOS=')[1])   # 待审不显示
    f=store.photos()[0]['file'];s.assertEqual(s.c.get('/photos/'+f).status,404)    # 待审的文件也不公开
    s.c.login();i=store.photos()[0]['id']
    s.assertEqual(s.c.get('/photos/'+f).status,200)                               # 审核时能看
    s.assertEqual(s.c.post(f'/api/admin/photos/{i}',{'action':'approve'}).status,200)
    s.assertEqual(s.c.get('/api/admin/counts').json()['photos'],{'approved':1})
    s.c.post('/api/logout',{})
    s.assertIn(f'"{m["id"]}": "photos/{f}?v=',s.c.get('/chars.js').text)
    s.assertEqual(s.c.get('/photos/'+f).status,200)
    # 第二张通过后，第一张退成 replaced
    edit_site(lambda j:j['photos'].update(moderation='post'))
    s.assertFalse(s.up(m,raw=s.PNG+b'\x01').json()['pending'])
    st=[p['status'] for p in store.photos()];s.assertEqual(st,['approved','replaced'])
    # 席位换了人：旧照片不挂到新人头上
    import roster
    d=roster.load();roster.seat(d,m['id'])[1]['member']='新来的';import json as J
    with open(config.C.ROSTER,'w',encoding='utf-8') as fh:J.dump(d,fh,ensure_ascii=False)
    s.assertNotIn(m['id'],s.c.get('/chars.js').text.split('window.PHOTOS=')[1])
  def test_vacant_seat_and_config(s):
    import roster
    edit_site(lambda j:j.setdefault('photos',{}).update(enabled=True))
    v=next(m for g in roster.load()['groups'] for m in g['members'] if not (m.get('member') or '').strip())
    s.assertEqual(s.c.req('POST','/api/photo?'+urllib.parse.urlencode({'seat':v['id'],'name':''}),raw=s.PNG).status,400)
    s.assertEqual(s.c.post('/api/admin/photos/config',{'enabled':False}).status,401)
    s.c.login()
    r=s.c.post('/api/admin/photos/config',{'enabled':False,'moderation':'post'});s.assertEqual(r.status,200)
    s.assertEqual(r.json()['config'],{'enabled':False,'moderation':'post'})
    s.assertIn('"photos": {"enabled": false',s.c.get('/site.js').text)

class FirstRun(unittest.TestCase):
  """建站后默认：导入的名单先自动配图，再生成一图流；样例 / 空名册只生成一图流。"""
  def setUp(s):
    import tempfile,helpers;s.d=tempfile.mkdtemp(prefix='castcall-fr-');helpers.FIRSTRUN.clear();s.calls=helpers.FIRSTRUN
  def tearDown(s):
    import shutil;shutil.rmtree(s.d,ignore_errors=True)
  def init(s,*extra):
    import contextlib,io
    from helpers import ROOT
    sys.path.insert(0,ROOT);import init
    with contextlib.redirect_stdout(io.StringIO()) as out:rc=init.main(['--instance',s.d,'--password','x'*10,'--yes',*extra])
    return rc,out.getvalue()
  def names(s):
    p=os.path.join(s.d,'名单.txt');os.makedirs(s.d,exist_ok=True)
    with open(p,'w',encoding='utf-8') as f:f.write('## Kanon\n月宫亚由 小满\n川澄舞\n')
    return p
  def test_import_runs_art_then_poster(s):
    rc,out=s.init('--import',s.names(),'--title','Kanon 团片');s.assertEqual(rc,0,out)
    s.assertEqual(s.calls,['art',('poster',True)]);s.assertIn('配图：封面 0 张',out)
  def test_opt_out(s):
    rc,out=s.init('--import',s.names(),'--title','x','--no-art','--no-poster');s.assertEqual(rc,0,out);s.assertEqual(s.calls,[])
  def test_example_skips_art(s):
    rc,_=s.init('--example','key-single');s.assertEqual(rc,0);s.assertEqual(s.calls,[('poster',True)])
  def test_poster_fallbacks(s):
    import server,firstrun,helpers
    config.use(s.d);s.init('--no-poster')
    old=server.POSTER['ok']
    try:
      server.POSTER['ok']=False
      ok,msg=helpers.REAL_POSTER();s.assertFalse(ok);s.assertIn('requirements-poster.txt',msg)
      from helpers import edit_site;edit_site(lambda j:j['poster'].update(enabled=False))
      ok,msg=helpers.REAL_POSTER();s.assertFalse(ok);s.assertIn('关掉',msg)
    finally:server.POSTER['ok']=old
  def test_wizard_paste_runs_in_background(s):
    import server,firstrun
    config.use(s.d);server.HITS.clear();server.SESS.clear();s.assertFalse(server.preflight())
    c=Client();b={'token':server.SETUP['token'],'mode':'single','title':'t','source':'paste','names':'古河渚 云果','password':'pw-12345678'}
    try:
      s.assertEqual(c.post('/api/setup',b).status,200);firstrun.STATE['thread'].join(10)
      s.assertEqual(s.calls,['art',('poster',False)])
    finally:server.SETUP.update(token=None,instance=None)
