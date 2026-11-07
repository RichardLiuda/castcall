"""招募须知（server/notice.py + /api/admin/notice）：清洗规则和后台接口。"""
import os,sys,unittest
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0,os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),'server'))
from helpers import Base
import config

class NoticeClean(unittest.TestCase):
  def test_normalize_drops_bad_kind_and_empty_text(s):
    import notice
    out=notice.normalize([{'kind':'must','text':'挡脸'},{'kind':'nope','text':'丢掉'},{'kind':'deny','text':'  '},'not a dict',{'kind':'warn'}])
    s.assertEqual(out,[{'kind':'must','text':'挡脸'}])
  def test_normalize_truncates_text_and_caps_count(s):
    import notice
    long='x'*200
    out=notice.normalize([{'kind':'info','text':long}]*20)
    s.assertEqual(len(out),notice.MAX_ITEMS)
    s.assertEqual(len(out[0]['text']),notice.TEXT_LEN)
  def test_compact_truncates_lead_and_cleans_items(s):
    import notice
    nt=notice.compact({'enabled':True,'lead':'x'*100,'items':[{'kind':'must','text':'挡脸'},{'kind':'bad','text':'丢'}]})
    s.assertEqual(nt,{'enabled':True,'lead':'x'*notice.LEAD_LEN,'items':[{'kind':'must','text':'挡脸'}]})
  def test_compact_rejects_non_dict(s):
    import notice
    with s.assertRaises(ValueError):notice.compact('nope')

class NoticeAdmin(Base):
  def test_default_is_disabled_and_empty(s):
    s.c.login()
    j=s.c.get('/api/admin/notice').json()
    s.assertEqual(j['notice'],{'enabled':False,'lead':'','items':[]})
  def test_requires_login(s):
    s.assertEqual(s.c.post('/api/admin/notice',{'enabled':True,'lead':'','items':[]}).status,401)
  def test_save_updates_config_and_public_site(s):
    s.c.login()
    body={'enabled':True,'lead':'自然感团片','items':[{'kind':'must','text':'挡脸出图'},{'kind':'deny','text':'公主病'},{'kind':'bad','text':'丢掉'}]}
    r=s.c.post('/api/admin/notice',body);s.assertEqual(r.status,200,r.text)
    s.assertEqual(r.json()['notice']['items'],[{'kind':'must','text':'挡脸出图'},{'kind':'deny','text':'公主病'}])
    s.assertEqual(config.C.site['notice']['lead'],'自然感团片')
    j=s.c.get('/api/admin/notice').json()
    s.assertEqual(j['notice']['items'],[{'kind':'must','text':'挡脸出图'},{'kind':'deny','text':'公主病'}])
    site=s.c.get('/site.js').text
    s.assertIn('挡脸出图',site)
  def test_disabled_notice_keeps_site_js_shape(s):
    site=s.c.get('/site.js').text
    s.assertIn('"notice": {"enabled": false, "lead": "", "items": []}',site)

if __name__=='__main__':
  unittest.main()
