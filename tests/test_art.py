"""Art finder against a fake Bangumi / AniList (no network)."""
import os,sys,unittest
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
if __name__=='__main__':unittest.main()
