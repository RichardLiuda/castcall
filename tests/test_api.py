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
  def test_health_reports_the_version(s):
    r=s.c.get('/api/health');s.assertEqual(r.status,200)
    d=json.loads(r.text)
    s.assertEqual(d['ok'],True)
    # 平台和文档都靠这一行确认线上跑的是哪版，格式得是 semver，不能是空串或 "dev"
    s.assertRegex(d['version'],r'^\d+\.\d+\.\d+(-[0-9A-Za-z.]+)?$')
    # 还没建站时走的是另一个出口——刚 clone 下来那一刻回来的正是它，不能漏
    import server
    for payload in (server.health_payload(),server.health_payload(True)):
      s.assertEqual(payload['ok'],True)
      s.assertRegex(payload['version'],r'^\d+\.\d+\.\d+(-[0-9A-Za-z.]+)?$')
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
  def test_favicon_is_drawn_from_the_title(s):
    """标签页图标默认按团名首字现画。写死一个图形的话，换个团名它也不变，
    团长在标签上看到一块陌生黄底，只会当成浏览器的默认图标（S1 里那个 R）。"""
    r=s.c.get('/favicon.svg');s.assertEqual(r.status,200)
    s.assertIn('image/svg+xml',r.header('Content-Type'))
    s.assertIn(f'>{config.C.site["event"]["title"][0]}</text>',r.text)
    s.assertIn('no-cache',r.header('Cache-Control'))
    s.assertEqual(s.c.get('/favicon.ico').text,r.text)     # 没有 <link rel=icon> 的页面会来问这个
    s.assertIn('href="/favicon.svg"',s.c.get('/').text)
  def test_favicon_works_before_first_setup(s):
    """全新实例打开向导时 roster.json 还不存在：图标取不到团色也不能 500。
    setup.html 会来问 /favicon.svg，一次 500 就写进 server.log（跑一遍向导才看得见）。"""
    p,bak=config.C.ROSTER,config.C.ROSTER+'.bak'
    os.rename(p,bak)
    try:
      r=s.c.get('/favicon.svg');s.assertEqual(r.status,200)
      s.assertIn('<svg',r.text);s.assertIn('fill="#e6b35a"',r.text)   # 没有团色就退回金色
    finally:os.replace(bak,p)
  def test_favicon_follows_the_accent_colour(s):
    edit_site(lambda j:j['brand'].update(accent='#223344'))
    s.assertIn('fill="#223344"',s.c.get('/favicon.svg').text)
    edit_site(lambda j:j['brand'].update(accent='#ffeecc'))
    s.assertIn('fill="#2b2115"',s.c.get('/favicon.svg').text)   # 浅底要配深字，否则白字看不见

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
    s.assertIn(f'apple-touch-icon href="/brand/{f}"',s.c.get('/').text)   # iOS「添加到主屏」不认 SVG 默认图标
    # 一图流页面把图标地址写死在 /favicon.svg 上：传了图以后这个地址也得换成那张，否则只有首页变
    r=s.c.get('/favicon.svg');s.assertEqual(r.body,s.PNG);s.assertIn('image/png',r.header('Content-Type'))
    s.assertEqual(s.c.req('POST','/api/admin/brand?slot=hero',raw=s.PNG).status,200)
    s.assertEqual(config.C.site['poster']['hero'],f)
    s.assertEqual(s.c.req('POST','/api/admin/brand?slot=logo&clear=1',raw=b'').status,200)
    s.assertNotIn('class=brandlogo',s.c.get('/').text)
    s.assertEqual(s.c.req('POST','/api/admin/brand?slot=accent',raw=s.PNG).status,400)
    s.assertEqual(s.c.req('POST','/api/admin/brand?slot=logo',raw=b'<svg onload=alert(1)>'+b' '*40).status,400)
  def test_upload_requires_login(s):
    s.assertEqual(s.c.req('POST','/api/admin/upload?kind=cover',raw=s.PNG).status,401)
  def test_picking_a_portrait_also_binds_the_name(s):
    """后台手选一张立绘 = 对这个名字的人工确认，要写进 art_bind.json。
    不写的话，名单核对下次还报「作品里没有这个名字」，换张图又得重新点一遍（S1 里的月宫亚由）。"""
    import artsearch
    old,oldc=artsearch.save_portrait,artsearch.save_cover
    artsearch.save_portrait=lambda g,c,url:'portraits/x.png'
    artsearch.save_cover=lambda g,url,lock:'covers/x.png'
    try:
      s.c.login()
      r=s.c.post('/api/admin/art/pick',{'kind':'portrait','url':'https://example.com/y.png','group':'示例作品 A','character':'主角','id':123,'name':'主人公'})
      s.assertEqual(r.status,200,r.text)
      s.assertEqual(s.c.post('/api/admin/art/pick',{'kind':'cover','url':'https://example.com/c.png','group':'示例作品 A'}).status,200)
    finally:artsearch.save_portrait,artsearch.save_cover=old,oldc
    p=os.path.join(config.C.UPLOADS,'art_bind.json')
    d={}
    if os.path.exists(p):
      with open(p,encoding='utf-8') as f:d=json.load(f)
    s.assertEqual((d['示例作品 A|主角']['id'],d['示例作品 A|主角']['by']),(123,'manual'))
    s.assertEqual(len(d),1,'封面不该往绑定表里写东西')

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
  DOC='<!doctype html><html><head></head><body><p>x</p></body></html>'
  def put(s,name,body=None):
    p=os.path.join(config.C.POSTER,name);wf(p,body or (s.DOC if name.endswith('.html') else 'x'));return p
  def test_poster_missing_is_404_not_500(s):
    s.assertEqual(s.c.get('/poster/master.html').status,404)
  def test_poster_page_gets_chrome(s):
    s.put('master.html')
    r=s.c.get('/poster/master.html');s.assertEqual(r.status,200);s.assertIn('kr-poster-chrome',r.text);s.assertIn('data-slug="castcall"',r.text)
    s.assertIn('posterlink-hdr',s.c.get('/').text)
  def test_stale_follows_the_files_that_feed_the_poster(s):
    """名册 / 站点 / 立绘任一改过 -> 过期；重新生成（master.html 变新）-> 不过期。
    只看这三个文件、不扫 uploads/ 整个目录：传一张没人用的图不该说海报旧了。"""
    import server,time
    mp=s.put('master.html');t0=time.time();os.utime(mp,(t0,t0))
    s.assertFalse(server.poster_status()['stale'])
    for k in ('ROSTER','SITE','MAP'):
      p=getattr(config.C,k)
      if not os.path.isfile(p):continue
      os.utime(p,(t0+5,t0+5))
      s.assertTrue(server.poster_status()['stale'],k+' 改过之后应该是旧的')
      os.utime(p,(t0-5,t0-5))
      s.assertFalse(server.poster_status()['stale'])
    os.utime(mp,(t0+60,t0+60));s.assertFalse(server.poster_status()['stale'])
  def test_stale_needs_a_poster_to_begin_with(s):
    """没生成过一图流时不算「过期」——那是「还没做」，后台该显示生成按钮不是「旧」。"""
    import server
    s.assertFalse(server.poster_status()['ready']);s.assertFalse(server.poster_status()['stale'])
  def test_cache_headers(s):
    """cache/ 里的裁切图名字就是内容 hash，永久缓存；导出的 jpg 只有 ?v= 对上 mtime 才 immutable。"""
    cache=os.path.join(config.C.POSTER,'cache');os.makedirs(cache,exist_ok=True)
    wf(os.path.join(cache,'abc123abc123.jpg'),'x')
    s.assertIn('immutable',s.c.get('/poster/cache/abc123abc123.jpg').header('cache-control'))
    jp=s.put('master.jpg');ts=int(os.path.getmtime(jp))
    s.assertIn('immutable',s.c.get(f'/poster/master.jpg?v={ts}').header('cache-control'))
    for q in ('','?v='+str(ts-1),'?v=hashed'):
      s.assertNotIn('immutable',s.c.get('/poster/master.jpg'+q).header('cache-control'),'不该永久缓存：'+q)
  def test_export_link_pins_the_file_mtime(s):
    """导出的 ?v= 是图自己的 mtime（不是 Date.now()）：同一版重复导出命中缓存，重新生成后 URL 自动变。"""
    s.put('master.html');jp=s.put('master.jpg');ts=int(os.path.getmtime(jp))
    h=s.c.get('/poster/master.html').text
    s.assertIn('window.POSTER_V=',h)
    v=json.loads(urllib.parse.unquote(h.split('window.POSTER_V=',1)[1].split(';',1)[0]))
    s.assertEqual(v['master'],ts)

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
  def test_names_check_needs_no_source(s):
    """向导的「核对名字」只发 names + title：少了 source 也要按粘贴处理。
    以前默认成「先空着」，于是每次都回 400「名单是空的」——按钮一直是废的，团长会以为名单没填进去。"""
    import artsearch
    old=artsearch.bind
    artsearch.bind=lambda parsed:{'net':True,'ok':1,'total':1,'near':[],'missing':[],'sources':['Bangumi'],
                                 'groups':[{'name':g['name'],'work':{},'items':{}} for g in parsed['groups']]}
    try:
      b=s.body();b.pop('source')
      r=s.c.post('/api/setup/names',b);s.assertEqual(r.status,200,r.text)
      s.assertEqual(r.json()['total'],1);s.assertIn('1 个角色',r.json()['line'])
      # 名单真的是空的时候，仍然要拦
      s.assertEqual(s.c.post('/api/setup/names',dict(b,names='')).status,400)
    finally:artsearch.bind=old
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

  def test_wizard_table_source_keeps_the_roster(s):
    import server,firstrun
    # 向导的表格编辑器提交 source=table。服务端以前只认 paste，于是整份名单被丢掉、
    # 建成「第一个角色」的默认空名册——页面上看着成功，名册却是空的。
    config.use(s.d);server.HITS.clear();server.SESS.clear();s.assertFalse(server.preflight())
    c=Client();b={'token':server.SETUP['token'],'mode':'single','title':'Kanon','source':'table',
      'names':'## Kanon\n> 外景\n古河渚 云果\n藤林杏','password':'pw-12345678'}
    try:
      s.assertEqual(c.post('/api/setup',b).status,200);firstrun.STATE['thread'].join(10)
      with open(config.C.ROSTER,encoding='utf-8') as f:d=json.load(f)
      g=d['groups'][0]
      s.assertEqual(g['name'],'Kanon');s.assertEqual(g['note'],'外景')
      s.assertEqual([(m['character'],m['member']) for m in g['members']],[('古河渚','云果'),('藤林杏','')])
      s.assertEqual(s.calls,['art',('poster',False)],'表格填的名单也要自动配图，不能因为 source 取值不同就跳过')
    finally:server.SETUP.update(token=None,instance=None)

class SignupFields(Base):
  """团长选的报名额外字段：身高 / 年龄 / 性别 / 样片 / 自定义题，可选填可必填。"""
  PNG=b'\x89PNG\r\n\x1a\n'+b'\x00'*64
  def setfields(s,spec):
    import fields;edit_site(lambda j:j['signup'].update(fields=fields.parse_spec(spec)))
  def test_parse_and_validate(s):
    import fields as F
    fs=F.parse_spec('身高,样片*，年龄、性别,想出的妆面*')
    s.assertEqual([f['key'] for f in fs],['height','sample','age','gender','q1'])
    n=F.normalize(fs);s.assertEqual([f['required'] for f in n],[False,True,False,False,True]);s.assertEqual(n[4]['label'],'想出的妆面')
    ok=lambda f:True
    s.assertEqual(F.validate(fs,{'sample':'0123456789ab.png','q1':'淡妆','height':165},ok),{'sample':'0123456789ab.png','q1':'淡妆','height':'165'})
    for bad,msg in (({'q1':'x'},'请上传样片'),({'sample':'0123456789ab.png'},'请填写想出的妆面'),
                    ({'sample':'0123456789ab.png','q1':'x','height':'abc'},'身高要填数字'),({'sample':'0123456789ab.png','q1':'x','height':'400'},'身高不太对'),
                    ({'sample':'0123456789ab.png','q1':'x','gender':'不知道'},'性别选项不对'),({'sample':'../etc/passwd','q1':'x'},'样片没传上来')):
      with s.assertRaises(ValueError) as c:F.validate(fs,bad,ok)
      s.assertIn(msg,str(c.exception))
    s.assertEqual(F.normalize([{'key':'nope'},{'key':'BAD KEY'},{'key':'q9'},'height']),[dict(F.PRESETS['height'],key='height',required=False)],'bad entries dropped')
  def test_signup_with_extra_and_sample(s):
    s.setfields('身高,样片*,性别')
    s.assertIn('"fields": [{"label": "身高"',s.c.get('/site.js').text)
    g,m=s.vacant()
    s.assertEqual(s.c.post('/api/cast-signup',signup_body(g,m)).status,400,'required sample missing')
    r=s.c.req('POST','/api/signup-sample',raw=s.PNG);s.assertEqual(r.status,200,r.text);f=r.json()['file']
    s.assertEqual(s.c.get('/samples/'+f).status,404,'samples are not public')
    b=dict(signup_body(g,m),extra={'sample':f,'height':'168','gender':'女'})
    r=s.c.post('/api/cast-signup',b);s.assertEqual(r.status,200,r.text)
    row=store.signups()[0];s.assertEqual(json.loads(row['extra']),{'height':'168','sample':f,'gender':'女'})
    s.c.login();s.assertEqual(s.c.get('/samples/'+f).status,200)
    j=s.c.get('/api/admin/signups').json();s.assertEqual([x['key'] for x in j['fields']],['height','sample','gender'])
    import fields;s.assertEqual(fields.text(fields.parse_spec('身高,样片*,性别'),json.loads(row['extra'])),'身高 168cm · 样片 已上传 · 性别 女')
  def test_sample_endpoint_off_without_image_field(s):
    s.assertEqual(s.c.req('POST','/api/signup-sample',raw=s.PNG).status,404)
    s.setfields('身高')
    s.assertEqual(s.c.req('POST','/api/signup-sample',raw=s.PNG).status,404)
  def test_no_fields_keeps_old_behaviour(s):
    g,m=s.vacant();s.assertEqual(s.c.post('/api/cast-signup',signup_body(g,m)).status,200)
    s.assertEqual(json.loads(store.signups()[0]['extra']),{})
  def test_admin_edit_fields(s):
    s.assertEqual(s.c.post('/api/admin/signup-fields',{'fields':[]}).status,401)
    s.c.login()
    j=s.c.get('/api/admin/signup-fields').json();s.assertIn('sample',[p['key'] for p in j['presets']]);s.assertEqual(j['fields'],[])
    r=s.c.post('/api/admin/signup-fields',{'fields':[{'key':'age','required':True},{'key':'q3','label':'擅长','type':'text'}]})
    s.assertEqual(r.status,200,r.text);s.assertEqual(config.C.site['signup']['fields'],[{'key':'age','required':True},{'key':'q3','label':'擅长','type':'text'}])
    s.assertEqual(s.c.post('/api/admin/signup-fields',{'fields':[{'key':f'q{i}','label':'x'} for i in range(1,9)]}).status,400)
  def test_old_db_gets_extra_column(s):
    import sqlite3
    c=sqlite3.connect(config.C.DB);c.execute('drop table if exists signups')
    c.execute("create table signups(id integer primary key autoincrement,seat text not null,grp text not null,character text not null default '',name text not null,contact text not null,status text not null default 'pending',source text not null default '',created text not null,decided text not null default '',note text not null default '')")
    c.commit();c.close();store.MIGRATED.clear()
    g,m=s.vacant();s.assertEqual(s.c.post('/api/cast-signup',signup_body(g,m)).status,200)
    s.assertEqual(store.signups()[0]['extra'],'{}')

class InitNameCheck(unittest.TestCase):
  """init.py --import 的名单核对。log 回调以前写成 lambda *x:print('  '+x)：x 是 tuple，
  内核第一次心跳就 TypeError，然后被 except 吞成「没核对成」——预检静默失效，CLI 看起来一切正常。
  零上下文会话跑出来才发现（S1）。"""
  def test_import_check_prints_and_survives_multi_arg_log(s):
    import artsearch,contextlib,io,shutil,tempfile
    from helpers import ROOT
    sys.path.insert(0,ROOT);import init
    d=tempfile.mkdtemp(prefix='castcall-nc-');names=os.path.join(d,'名单.txt')
    with open(names,'w',encoding='utf-8') as f:f.write('## Kanon\n泽渡真琴 小满\n美坂栞\n')
    old=artsearch.bind;seen=[]
    def fake(roster,log=print,**k):
      log('核对 Kanon（2 个角色）…');log('第二行','第二段')   # 多参数也要能吃
      seen.append(1)
      return {'net':True,'ok':1,'total':2,'near':[],'missing':['美坂栞'],'groups':[]}
    artsearch.bind=fake
    try:
      with contextlib.redirect_stdout(io.StringIO()) as out:
        rc=init.main(['--instance',d,'--import',names,'--password','x'*10,'--yes','--no-poster'])
    finally:artsearch.bind=old;shutil.rmtree(d,ignore_errors=True)
    o=out.getvalue()
    s.assertEqual(rc,0,o);s.assertTrue(seen,'核对根本没跑');s.assertIn('核对 Kanon',o);s.assertIn('第二段',o)
    s.assertIn('找不到    美坂栞',o);s.assertNotIn('没核对成',o)

class SignupFieldsSetup(unittest.TestCase):
  def test_init_fields_flag(s):
    import contextlib,io,shutil,tempfile
    from helpers import ROOT
    sys.path.insert(0,ROOT);import init
    d=tempfile.mkdtemp(prefix='castcall-fl-')
    try:
      with contextlib.redirect_stdout(io.StringIO()) as out:rc=init.main(['--instance',d,'--password','x'*10,'--yes','--no-poster','--fields','身高,样片*'])
      s.assertEqual(rc,0);s.assertIn('报名表：CN、微信、身高、样片（必填）',out.getvalue())
      s.assertEqual(config.C.site['signup']['fields'],[{'key':'height'},{'key':'sample','required':True}])
    finally:shutil.rmtree(d,ignore_errors=True)
  def test_wizard_fields(s):
    import shutil,tempfile,server
    d=tempfile.mkdtemp(prefix='castcall-flw-');config.use(d);server.HITS.clear();server.SESS.clear()
    try:
      s.assertFalse(server.preflight());c=Client()
      s.assertIn('height',[p['key'] for p in c.get('/api/setup/fields').json()['presets']])
      r=c.post('/api/setup',{'token':server.SETUP['token'],'mode':'single','title':'t','source':'blank','password':'pw-12345678','fields':[{'key':'gender'},{'key':'q1','label':'妆面','type':'text','required':True}]})
      s.assertEqual(r.status,200,r.text)
      s.assertEqual(config.C.site['signup']['fields'],[{'key':'gender'},{'key':'q1','required':True,'label':'妆面','type':'text'}])
    finally:server.SETUP.update(token=None,instance=None);shutil.rmtree(d,ignore_errors=True)

class WizardPrefill(unittest.TestCase):
  """server.py --prefill 名单.txt：向导打开时名单已经填好（部署统一走网页向导）。"""
  def setUp(s):
    import tempfile,server
    s.d=tempfile.mkdtemp(prefix='castcall-pf-');config.use(s.d);server.HITS.clear();server.SESS.clear()
    s.assertFalse(server.preflight());s.c=Client()
  def tearDown(s):
    import shutil,server
    server.SETUP.update(token=None,instance=None,prefill=None);shutil.rmtree(s.d,ignore_errors=True)
  def write(s,text):
    p=os.path.join(s.d,'名单.txt')
    with open(p,'w',encoding='utf-8') as f:f.write(text)
    return p
  def test_prefill_needs_token_and_detects_mode(s):
    import server
    server.SETUP['prefill']=server.prefill(s.write('## Kanon\n月宫亚由 小满\n川澄舞\n## 摄影 / 后勤\n摄影 阿光\n'),'Kanon 团片')
    s.assertEqual(s.c.get('/api/setup/prefill?t=wrong').status,403)
    j=s.c.get('/api/setup/prefill?t='+server.SETUP['token']).json()
    s.assertEqual((j['title'],j['mode'],j['file']),('Kanon 团片','single','名单.txt'),'one work + crew is a single-group site')
    s.assertIn('川澄舞',j['names']);s.assertIn('3 个席位',j['summary'])
    s.assertEqual(server.prefill(s.write('## A\n甲\n## B\n乙\n'))['mode'],'multi')
  def test_bad_list_fails_at_startup(s):
    import contextlib,io,server
    p=s.write('')
    with contextlib.redirect_stderr(io.StringIO()) as err:rc=server.main(['--prefill',p])
    s.assertEqual(rc,1);s.assertIn('名单读不了',err.getvalue())
  def test_setup_code_is_six_digits(s):
    import server
    # 团长要照着终端抄六位数字，格式得稳定；口令写在 .setup-token 里，重启后不变
    s.assertRegex(server.SETUP['token'],r'^\d{6}$')
    with open(os.path.join(s.d,'.setup-token'),encoding='utf-8') as f:
      s.assertEqual(f.read().strip(),server.SETUP['token'])
  def test_old_long_token_is_still_honoured(s):
    import server
    # 0.1.0-beta 之前建的实例里存的是长串口令；升级后不能把人卡在向导外面
    with open(os.path.join(s.d,'.setup-token'),'w',encoding='utf-8') as f:f.write('AbCdEfGhIjKlMnOp')
    s.assertEqual(server.setup_token(config.use(s.d)),'AbCdEfGhIjKlMnOp')
  def test_preview_returns_editable_rows(s):
    import server
    # 向导的表格编辑器要把粘贴的名单摊成「团 / 角色 / CN」，一个格子一个输入框
    r=s.c.post('/api/setup/preview',{'token':server.SETUP['token'],'source':'paste',
      'names':'## Kanon\n> 光坂外景\n月宫亚由 云果\n川澄舞\n## 摄影 / 后勤\n摄影 阿光','title':'Kanon'})
    s.assertEqual(r.status,200,r.text)
    rows=r.json()['rows']
    s.assertEqual([g['name'] for g in rows],['Kanon','摄影 / 后勤'])
    s.assertEqual(rows[0]['note'],'光坂外景')
    s.assertEqual([(m['character'],m['member']) for m in rows[0]['members']],[('月宫亚由','云果'),('川澄舞','')])
    s.assertEqual(rows[1]['kind'],'crew','工作组要带 kind，表格里能标出来不配立绘')
  def test_wrong_setup_code_is_rate_limited(s):
    import server
    bad='000000' if server.SETUP['token']!='000000' else '111111'
    cap=int(config.C.site['limits'].get('setup') or 8)
    for _ in range(cap):s.assertEqual(s.c.get('/api/setup/prefill?t='+bad).status,403)
    # 六位数只有一百万种，不限次数就能枚举出预填的名单
    s.assertEqual(s.c.get('/api/setup/prefill?t='+bad).status,429)
  def test_firstrun_progress_needs_login(s):
    import server,helpers
    s.assertEqual(s.c.get('/api/admin/firstrun').status,302,'still in wizard mode')
    b={'token':server.SETUP['token'],'mode':'single','title':'t','source':'paste','names':'古河渚 云果','password':'pw-12345678'}
    s.assertEqual(s.c.post('/api/setup',b).status,200)
    import firstrun;firstrun.STATE['thread'].join(10)
    j=s.c.get('/api/admin/firstrun').json();s.assertEqual(j['stage'],'done');s.assertTrue(j['started']);s.assertIn('poster',j)
    s.assertEqual(Client().get('/api/admin/firstrun').status,401)

class SurvivesKill(unittest.TestCase):
  """AI 助手的环境会在一轮对话结束时杀掉后台进程：口令要跨重启不变，收尾没跑完要能补上，--exit-after-setup 建完自己退出。"""
  def setUp(s):
    import tempfile,server,helpers,firstrun
    s.d=tempfile.mkdtemp(prefix='castcall-kill-');config.use(s.d);server.HITS.clear();server.SESS.clear();helpers.FIRSTRUN.clear()
    firstrun.STATE.update(thread=None,lines=[],stage='',finished=False)
  def tearDown(s):
    import shutil,server
    server.SETUP.update(token=None,instance=None,prefill=None);shutil.rmtree(s.d,ignore_errors=True)
  def test_token_survives_restart_and_is_removed_after_setup(s):
    import server
    s.assertFalse(server.preflight());t=server.SETUP['token']
    server.SETUP['token']=None;s.assertFalse(server.preflight());s.assertEqual(server.SETUP['token'],t,'same link after a restart')
    p=os.path.join(s.d,'.setup-token');s.assertEqual(oct(os.stat(p).st_mode&0o777),'0o600')
    b={'token':t,'mode':'single','title':'t','source':'blank','password':'pw-12345678'}
    s.assertEqual(Client().post('/api/setup',b).status,200);s.assertFalse(os.path.exists(p))
  def test_interrupted_firstrun_resumes(s):
    import server,firstrun,helpers
    s.assertFalse(server.preflight())
    b={'token':server.SETUP['token'],'mode':'single','title':'t','source':'paste','names':'古河渚 云果','password':'pw-12345678'}
    s.assertEqual(Client().post('/api/setup',b).status,200);firstrun.STATE['thread'].join(10)
    s.assertIsNone(firstrun.pending(),'marker removed once finished')
    # 模拟被杀：标记还在
    with open(firstrun.pending_path(),'w') as f:f.write('{"art":true,"poster":true}')
    helpers.FIRSTRUN.clear();firstrun.STATE.update(thread=None,finished=False)
    import contextlib,io
    old=server.make_server
    class Fake:
      server_address=('127.0.0.1',1)
      def serve_forever(self):pass
      def server_close(self):pass
    server.make_server=lambda *a,**k:Fake()
    try:
      with contextlib.redirect_stdout(io.StringIO()) as out:s.assertEqual(server.main([]),0)
    finally:server.make_server=old
    s.assertIn('没跑完，现在补上',out.getvalue());firstrun.STATE['thread'].join(10)
    s.assertEqual(helpers.FIRSTRUN,['art',('poster',False)]);s.assertIsNone(firstrun.pending())
  def test_exit_after_setup_on_built_instance(s):
    import contextlib,io,server,firstrun
    s.assertFalse(server.preflight())
    b={'token':server.SETUP['token'],'mode':'single','title':'t','source':'blank','password':'pw-12345678'}
    s.assertEqual(Client().post('/api/setup',b).status,200);firstrun.STATE['thread'].join(10)
    firstrun.STATE.update(thread=None)
    old=server.make_server
    class Fake:
      server_address=('127.0.0.1',1)
      def server_close(self):pass
    server.make_server=lambda *a,**k:Fake()
    try:
      with contextlib.redirect_stdout(io.StringIO()) as out:rc=server.main(['--exit-after-setup'])
    finally:server.make_server=old
    s.assertEqual(rc,0);s.assertIn('已经建好了',out.getvalue())
  def test_exit_when_built_waits_for_firstrun(s):
    import server,firstrun,threading,time as T
    calls=[];srv=type('S',(),{'shutdown':lambda self:calls.append('shutdown')})()
    firstrun.STATE['finished']=False
    real=T.sleep;T.sleep=lambda x:real(min(x,0.05))
    try:
      t=threading.Thread(target=server.exit_when_built,args=(srv,));t.start();real(0.3)
      s.assertEqual(calls,[],'still waiting while first-run work is going')
      firstrun.STATE['finished']=True;t.join(5)
    finally:T.sleep=real
    s.assertEqual(calls,['shutdown'])

class Hosting(Base):
  """托管平台：PORT + 0.0.0.0、代理后的真实 IP、打包发布目录。"""
  def test_port_env_binds_all_interfaces(s):
    old={k:os.environ.pop(k,None) for k in ('PORT','CASTCALL_HOST','CASTCALL_PORT')}
    try:
      s.assertEqual((config.C.host(),config.C.port(),config.C.hosted()),('127.0.0.1',5510,False))
      os.environ['PORT']='8080';s.assertEqual((config.C.host(),config.C.port(),config.C.hosted()),('0.0.0.0',8080,True))
      os.environ['CASTCALL_HOST']='127.0.0.1';s.assertEqual(config.C.host(),'127.0.0.1','explicit CASTCALL_HOST wins')
      os.environ['CASTCALL_PORT']='9000';s.assertEqual(config.C.port(),9000)
    finally:
      for k,v in old.items():
        os.environ.pop(k,None)
        if v is not None:os.environ[k]=v
  def test_whoami(s):
    s.assertEqual(s.c.get('/api/admin/whoami').status,401)
    s.c.login();j=s.c.get('/api/admin/whoami',headers={'X-Forwarded-For':'1.2.3.4, 10.0.0.9'}).json()
    s.assertEqual((j['peer'],j['ip'],j['trustProxyHeader']),('127.0.0.1','127.0.0.1',''))
    s.assertEqual(j['headers'],{'X-Forwarded-For':'1.2.3.4, 10.0.0.9'})
    os.environ['CASTCALL_TRUST_PROXY']='X-Forwarded-For'
    try:s.assertEqual(s.c.get('/api/admin/whoami',headers={'X-Forwarded-For':'1.2.3.4, 10.0.0.9'}).json()['ip'],'10.0.0.9','rightmost hop = the one our proxy added')
    finally:os.environ.pop('CASTCALL_TRUST_PROXY',None)
  def test_bundle(s):
    import contextlib,io,shutil,tempfile
    from helpers import ROOT
    sys.path.insert(0,os.path.join(ROOT,'tools'));import bundle
    g,m=s.vacant();s.assertEqual(s.c.post('/api/cast-signup',signup_body(g,m)).status,200)
    with open(os.path.join(s.dir,'.env'),'w') as f:f.write('CASTCALL_CHROME=/Applications/Chrome\nNOTION_TOKEN=ntn_x\n')
    open(os.path.join(s.dir,'firstrun.pending'),'w').write('{}');open(os.path.join(s.dir,'.setup-token'),'w').write('x')
    config.use(s.dir)
    out=os.path.join(tempfile.mkdtemp(prefix='castcall-pub-'),'pub')
    try:
      with contextlib.redirect_stdout(io.StringIO()) as o:rc=bundle.main(['--instance',s.dir,'--out',out])
      s.assertEqual(rc,0,o.getvalue());t=o.getvalue()
      s.assertIn('报名 1 条',t);s.assertIn('整个覆盖',t);s.assertIn('CASTCALL_CHROME',t)
      s.assertTrue(os.path.isfile(os.path.join(out,'server','server.py')));s.assertFalse(os.path.exists(os.path.join(out,'tests')))
      di=os.path.join(out,'instance')
      for x in ('firstrun.pending','.setup-token','logs','.env'):s.assertFalse(os.path.exists(os.path.join(di,x)),x)
      env=open(os.path.join(out,'.env')).read();s.assertIn('NOTION_TOKEN=ntn_x',env);s.assertNotIn('CHROME',env)
      import sqlite3;c=sqlite3.connect(os.path.join(di,'castcall.db'));s.assertEqual(c.execute('select count(*) from signups').fetchone()[0],1);c.close()
      with contextlib.redirect_stdout(io.StringIO()):s.assertEqual(bundle.main(['--instance',s.dir,'--out',out]),0,'rebuilds its own dir')
      os.remove(os.path.join(out,'.castcall-bundle'))
      with s.assertRaises(SystemExit),contextlib.redirect_stdout(io.StringIO()):bundle.main(['--instance',s.dir,'--out',out])
    finally:shutil.rmtree(os.path.dirname(out),ignore_errors=True)
