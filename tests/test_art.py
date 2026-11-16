"""Art finder against a fake Bangumi / AniList (no network)."""
import os,sys,time,unittest,urllib.parse
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from helpers import Base
import config,net,artsearch
PNG=b'\x89PNG\r\n\x1a\n'+b'\x00'*64
def ch(i,cn,jp):return {'id':i,'name':jp,'images':{'large':f'https://lain.bgm.tv/pic/crt/l/{i}.jpg','medium':f'https://lain.bgm.tv/r/400/{i}.jpg'},'infobox':[{'key':'简体中文名','value':cn}]}
CHARS={'主角':[ch(1,'主角','しゅじんこう'),ch(9,'主角','別作品の主人公')],'青梅竹马':[ch(2,'青梅竹马','おさななじみ')],'学生会长':[ch(99,'学生会长','他作の会長')]}
class Fake:
  def __init__(s):s.calls=[]
  def __call__(s,url,body=None,method=None,headers=None,timeout=20,raw=False,limit=None):
    s.calls.append(url)
    if raw:return (PNG,None) if 'lain.bgm.tv' in url or 'anilist.co' in url else (None,'nope')
    if 'search/subjects' in url:
      return {'data':[{'id':500,'name':body['keyword'],'name_cn':body['keyword'],'type':4,'images':{'large':'https://lain.bgm.tv/pic/cover/l/500.jpg','medium':'https://lain.bgm.tv/pic/cover/m/500.jpg'}}]},None
    if url.endswith('/subjects/500/characters'):return [{'id':2,'relation':'配角','name':'おさななじみ'},{'id':1,'relation':'主角','name':'しゅじんこう'},{'id':7,'relation':'客串','name':'ゲスト'}],None
    if '/v0/characters/' in url:return next((c for v in CHARS.values() for c in v if url.endswith('/characters/'+str(c['id']))),None),None
    if 'search/characters' in url:return {'data':CHARS.get(body['keyword'],[])},None
    if 'graphql.anilist.co' in url:return {'data':{'Page':{'characters':[],'media':[]}}},None
    return None,'HTTP 404'
class Art(Base):
  def setUp(s):
    super().setUp();s.fake=Fake();s._req=net.request;net.request=s.fake;artsearch.PAUSE=0
  def tearDown(s):net.request=s._req;super().tearDown()
  def test_auto_matches_only_inside_the_work(s):
    import server
    rep=artsearch.auto(log=lambda *a:None)
    m=server.jload(config.C.MAP,{})
    g='示例作品 A'
    s.assertIn(f'{g}|主角',m);s.assertIn(f'{g}|青梅竹马',m)
    s.assertNotIn(f'{g}|学生会长',m,'a same-named character from another work is not used')
    s.assertTrue(any('学生会长' in x for x in rep['skipped']))
    gs=s.roster()['groups']
    s.assertTrue(all(gg.get('cover') for gg in gs if gg.get('kind')!='crew'))
    s.assertTrue(any(gg.get('kind')=='crew' for gg in gs))
    s.assertFalse(any(gg.get('cover') for gg in gs if gg.get('kind')=='crew'),'crew groups get no cover (their name is not a work)')
    s.assertFalse(any('摄影' in k for k in m),'crew groups get no portraits')
    s.assertFalse(any('摄影' in u for u in s.fake.calls),'crew group names are never searched')
  def test_bind_probes_bangumi_once(s):
    """探测出 Bangumi 不通以后，别的团不该再各等一次超时——向导里那一步会一直停在「正在核对…」。
    实测同一份 5 人名单：每团重试 45 秒，探一次就熔断 13 秒，结论完全一样。"""
    calls=[]
    def fake(url,body=None,**kw):
      calls.append(url)
      if 'bgm.tv' in url:return None,'timed out'      # Bangumi 整个不通
      return s.fake(url,body,**kw)
    net.request=fake
    old=dict(artsearch.BREAK['down'])
    try:
      artsearch.BREAK.update(n={},down={})
      rep=artsearch.bind([{'name':'作品甲','members':[{'character':'主角'}]},{'name':'作品乙','members':[{'character':'主角'}]}])
      bgm=[u for u in calls if 'bgm.tv' in u]
      s.assertEqual(len(bgm),1,'只探测一次：'+repr(bgm))
      s.assertFalse(rep['bangumi'])
    finally:
      # 熔断是模块级状态：留成「Bangumi 不通」会让后面的用例也跳过 Bangumi
      artsearch.BREAK.update(n={},down=old)
  def test_dry_writes_nothing(s):
    import server
    rep=artsearch.auto(dry=True,log=lambda *a:None);s.assertGreater(rep['portraits'],0)
    s.assertEqual(server.jload(config.C.MAP,{}),{});s.assertFalse(any(g.get('cover') for g in s.roster()['groups']))
  def test_roster_from_work(s):
    text,notes=artsearch.roster_text(['作品甲'],log=lambda *a:None)
    s.assertEqual(text,'## 作品甲\n主角\n青梅竹马\n','main roles first, Chinese names, no cameos')
    import importer;d=importer.parse(text,'t');s.assertEqual([m['member'] for m in d['groups'][0]['members']],['',''])
    s.assertIn('Bangumi #500',notes[0])
    text,_=artsearch.roster_text(['作品甲'],main_only=True,log=lambda *a:None);s.assertEqual(text,'## 作品甲\n主角\n')
  def test_thumb_proxy_caches_and_refuses_other_hosts(s):
    """配图面板的缩略图走服务器（国内线路直连 lain.bgm.tv 会是 ERR_SSL_PROTOCOL_ERROR），取一次就缓存。"""
    s.assertEqual(s.c.get('/api/admin/art/thumb?u=https://lain.bgm.tv/pic/crt/l/a.jpg').status,401)
    s.c.login()
    u='https://lain.bgm.tv/pic/crt/l/thumb-cache-test.jpg'
    q='/api/admin/art/thumb?u='+urllib.parse.quote(u,safe='')
    r=s.c.get(q);s.assertEqual(r.status,200,str(r.status)+' '+r.body[:80].decode('utf-8','replace'));s.assertEqual(r.body,PNG)
    s.assertEqual(r.header('content-type'),'image/png')
    s.assertEqual(s.fake.calls.count(u),1)
    s.assertEqual(s.c.get(q).body,PNG);s.assertEqual(s.fake.calls.count(u),1)   # 第二次不再下载
    s.assertEqual(s.c.get('/api/admin/art/thumb?u='+urllib.parse.quote('https://evil.example/a.jpg',safe='')).status,400)
    _req=net.request
    net.request=lambda *a,**k:(None,'Connection timed out')
    try:s.assertEqual(s.c.get('/api/admin/art/thumb?u='+urllib.parse.quote('https://lain.bgm.tv/pic/crt/l/down.jpg',safe='')).status,502)
    finally:net.request=_req
  def test_only_image_hosts(s):
    s.assertTrue(artsearch.allowed('https://lain.bgm.tv/pic/x.jpg'));s.assertTrue(artsearch.allowed('https://s4.anilist.co/file/x.png'))
    for u in ('http://lain.bgm.tv/x.jpg','https://evil.example/x.jpg','https://lain.bgm.tv.evil.example/x','file:///etc/passwd','https://127.0.0.1/x'):s.assertFalse(artsearch.allowed(u),u)
  def test_admin_search_and_pick(s):
    s.assertEqual(s.c.get('/api/admin/art/search?kind=portrait&q=主角').status,401)
    s.c.login()
    r=s.c.get('/api/admin/art/search?kind=portrait&q=%E4%B8%BB%E8%A7%92&group=%E7%A4%BA%E4%BE%8B%E4%BD%9C%E5%93%81%20A');s.assertEqual(r.status,200,r.text)
    it=r.json()['items'];s.assertTrue(it[0]['inwork'])
    r=s.c.post('/api/admin/art/pick',{'kind':'portrait','url':it[0]['url'],'group':'示例作品 A','character':'主角'});s.assertEqual(r.status,200,r.text)
    s.assertIn('示例作品 A|主角',s.c.get('/chars.js').text)
    s.assertEqual(s.c.post('/api/admin/art/pick',{'kind':'cover','url':'https://evil.example/a.jpg','group':'示例作品 A'}).status,400)
    r=s.c.post('/api/admin/art/pick',{'kind':'cover','url':'https://lain.bgm.tv/pic/cover/l/500.jpg','group':'示例作品 A'});s.assertEqual(r.status,200,r.text)
    s.assertTrue(s.roster()['groups'][0]['cover'])
# Bangumi 的角色搜索只匹配日文 name：中文名（月宫亚由 / 月宮あゆ）一律搜不到，
# 名单里再有个错字（美坂栎 / 美坂栞）就彻底没图。这两条走「作品角色表 + 中文名」，不联网。
JP={31:('月宮あゆ','月宫亚由'),32:('沢渡真琴','泽渡真琴'),33:('美坂栞','美坂栞')}
class FakeCN:
  def __init__(s):s.calls=[]
  def __call__(s,url,body=None,method=None,headers=None,timeout=20,raw=False,limit=None):
    s.calls.append(url)
    if raw:return (PNG,None) if ('lain.bgm.tv' in url or 'anilist.co' in url) else (None,'nope')
    if 'search/subjects' in url:
      return {'data':[{'id':900,'name':'カノン','name_cn':body['keyword'],'type':4,
        'images':{'large':'https://lain.bgm.tv/pic/cover/l/900.jpg','medium':'https://lain.bgm.tv/pic/cover/m/900.jpg'}}]},None
    if url.endswith('/subjects/900/characters'):
      return [{'id':i,'relation':'主角','name':jp,'images':{'large':f'https://lain.bgm.tv/pic/crt/l/{i}.jpg'}} for i,(jp,cn) in JP.items()],None
    if '/v0/characters/' in url:
      cid=int(url.rsplit('/',1)[-1])
      if cid not in JP:return None,'HTTP 404'
      return {'id':cid,'name':JP[cid][0],'images':{'large':f'https://lain.bgm.tv/pic/crt/l/{cid}.jpg'},
              'infobox':[{'key':'简体中文名','value':JP[cid][1]},{'key':'别名','value':[{'v':'あゆ'}] if cid==31 else []}]},None
    if 'search/characters' in url:return {'data':[]},None     # 中文名搜不到，日文名才搜得到
    if 'graphql.anilist.co' in url:return {'data':{'Page':{'characters':[],'media':[]}}},None
    return None,'HTTP 404'
class ArtChineseNames(Base):
  def setUp(s):
    super().setUp();s.fake=FakeCN();s._req=net.request;net.request=s.fake
    artsearch.PAUSE=0;artsearch.BACKOFF=0
    import roster as R
    d=R.load();d['groups']=[{'name':'示例作品 A','members':[{'character':n,'member':''} for n in ('月宫亚由','泽渡真琴','美坂栎')]}]
    R.ensure_ids(d);R.save(d,'测试')
  def tearDown(s):net.request=s._req;super().tearDown()
  def test_falls_back_to_chinese_names(s):
    import server
    rep=artsearch.auto(log=lambda *a:None)
    m=server.jload(config.C.MAP,{})
    for ch in ('月宫亚由','泽渡真琴'):s.assertIn(f'示例作品 A|{ch}',m,ch+'：搜不到时要退到作品角色表按中文名对')
    s.assertEqual(rep['viacn'],2)
  def test_typo_is_matched_but_reported(s):
    import server
    rep=artsearch.auto(log=lambda *a:None)
    s.assertIn('示例作品 A|美坂栎',server.jload(config.C.MAP,{}),'差一个字也要配上，不然一个错字废一个席位')
    s.assertEqual(len(rep['near']),1);s.assertIn('美坂栞',rep['near'][0],'配上了要说清楚认成了谁，用户才知道名单写错了')
  def test_near_match_refuses_when_ambiguous(s):
    import artsearch as A
    idx={'美坂栞':{'url':'u1'},'美坂椋':{'url':'u2'}}
    s.assertEqual(A.near_key('美坂栎',idx),'','两个候选都只差一个字：不猜，宁可空着')
# 名单预检：名单刚定下来就要知道「这些名字配不配得上图」，而不是等配图跑完发现少了几张。
# 绑定了的角色，配图时直接按 id 取图、不再搜索——搜索结果会漂，id 不会。
class ArtBind(Base):
  def setUp(s):
    super().setUp();s.fake=FakeCN();s._req=net.request;net.request=s.fake
    artsearch.PAUSE=0;artsearch.BACKOFF=0
  def tearDown(s):net.request=s._req;super().tearDown()
  def roster_of(s,chars):
    import roster as R
    d=R.load();d['groups']=[{'name':'示例作品 A','members':[{'character':c,'member':''} for c in chars]}]
    R.ensure_ids(d);R.save(d,'测试');return d
  def test_every_name_gets_a_verdict(s):
    r=artsearch.bind(s.roster_of(['月宫亚由','泽渡真琴','美坂栎','不存在的人']),log=lambda *a:None)
    it=r['groups'][0]['items']
    s.assertEqual(it['月宫亚由']['state'],'ok','中文名和日文名不同也要对上（这就是预检的价值）')
    s.assertEqual(it['月宫亚由']['name'],'月宫亚由')
    s.assertEqual(it['泽渡真琴']['state'],'ok')
    s.assertEqual(it['美坂栎']['state'],'near');s.assertEqual(it['美坂栎']['suggest'],'美坂栞')
    s.assertEqual(it['不存在的人']['state'],'missing')
    cs=it['不存在的人'].get('candidates') or []
    s.assertTrue(cs,'找不到时要摆出作品里的角色名，让人一眼认出是哪个（月宫亚由 / 月宮あゆ 自动对不上）')
    s.assertIn('月宫亚由',[c['name'] for c in cs])
    s.assertEqual((r['ok'],r['total'],r['bound']),(2,4,3))
    s.assertEqual(r['groups'][0]['work']['id'],900)
  def test_bind_is_saved_and_spares_the_search(s):
    import server
    s.roster_of(['月宫亚由'])
    s.assertEqual(artsearch.bind(s.roster_of(['月宫亚由']),log=lambda *a:None)['ok'],1)
    s.assertIn('示例作品 A|月宫亚由',artsearch.bind_load(),'绑定要落盘，不然下次还得重算')
    s.fake.calls.clear()
    rep=artsearch.auto(log=lambda *a:None)
    s.assertEqual(rep['bound'],1,'走的是绑定，不是搜索')
    s.assertFalse(any('search/characters' in u for u in s.fake.calls),'绑定了就不该再搜角色')
    s.assertIn('示例作品 A|月宫亚由',server.jload(config.C.MAP,{}))
  def test_network_down_is_not_a_pass(s):
    net.request=lambda *a,**k:(None,'HTTP 502')
    t0=time.time()
    r=artsearch.bind({'groups':[{'name':'Kanon','members':[{'character':'月宫亚由','member':''}]}]},log=lambda *a:None)
    s.assertFalse(r['net']);s.assertEqual(r['ok'],0,'两个库都连不上，不能算「配得上图」')
    s.assertEqual(r['groups'][0]['items']['月宫亚由']['state'],'unknown','判不出来就说判不出来，不许记成 missing')
    s.assertIn('连不上',artsearch.bind_line(r))
    s.assertLess(time.time()-t0,12,'两边都断了要尽快收尾，不能让用户干等')
    s.assertTrue(artsearch.bind_run_load(),'核对跑过就要留痕，否则「没跑」和「断网」分不清')
  def test_simplified_variant_hits_japanese_name(s):
    idx={'沢渡真琴':{'url':'u1','id':'anilist:1','title':'沢渡真琴'}}
    s.assertEqual(artsearch.index_lookup(idx,'泽渡真琴')['title'],'沢渡真琴','泽→沢：中文名单要能对上日文写法')
    s.assertIsNone(artsearch.index_lookup(idx,'月宫亚由'),'改写成假名的（月宮あゆ）不该硬猜，留给人工确认')
  def test_crew_groups_are_not_checked(s):
    r=artsearch.bind({'groups':[{'name':'摄影 / 后勤','kind':'crew','members':[{'character':'摄影','member':'阿光'}]}]},log=lambda *a:None)
    s.assertEqual(r['groups'],[],'工作组不是作品，别拿组名去搜')
    s.assertEqual(r['total'],0)
if __name__=='__main__':unittest.main()