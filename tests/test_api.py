import json,os,sys,unittest
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
  def test_preflight_refuses_without_auth(s):
    import server
    import contextlib,io
    os.remove(config.C.AUTH)
    with contextlib.redirect_stderr(io.StringIO()) as err:s.assertFalse(server.preflight())
    s.assertIn('init.py',err.getvalue())

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

if __name__=='__main__':unittest.main()
