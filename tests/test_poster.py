"""一图流里的工作组（摄影 / 后勤）卡片。

它没有立绘位。以前跟 coser 用同一套卡，空着的 16:10 图位里摆一个满屏相机线稿，
职务前再摆一个——一卡两个图标，成品像三张没传完的图。现在没照片的席位走 credit()
的名牌，只有真传了工作照才回到照片卡。这里盯住这条分岔，免得下次重构又并回去。
"""
import json,os,shutil,sys,tempfile,unittest
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)));sys.path.insert(0,ROOT)
try:
  from PIL import Image
  from poster.build import Build
  HAS_PIL=True
except Exception:
  HAS_PIL=False

@unittest.skipUnless(HAS_PIL,'一图流要 Pillow；没装就跳过（它是可选依赖）')
class CrewCard(unittest.TestCase):
  def setUp(s):
    s.d=tempfile.mkdtemp(prefix='castcall-poster-')
    os.makedirs(os.path.join(s.d,'uploads'),exist_ok=True)
    shutil.copy(os.path.join(ROOT,'examples','roster.multi.example.json'),os.path.join(s.d,'roster.json'))
    with open(os.path.join(s.d,'site.json'),'w',encoding='utf-8') as f:json.dump({},f)
  def tearDown(s):shutil.rmtree(s.d,ignore_errors=True)
  def crew(s):
    b=Build(s.d)
    return b,[g for g in b.D['groups'] if b.crew(g)][0]
  def test_no_photo_is_a_nameplate(s):
    b,g=s.crew()
    for m in g['members']:
      h=b.card(g,m,True)
      s.assertIn('card crew',h)
      s.assertNotIn('class="art"',h,'名牌不该带图位')
      s.assertNotIn('class="cam"',h,'名牌里不该再有相机占位')
  def test_nameplate_carries_name_and_role(s):
    b,g=s.crew();m=g['members'][0]
    h=b.card(g,m,True)
    s.assertIn(m['member'],h);s.assertIn(m['character'],h)
  def test_vacant_seat_says_recruiting(s):
    b,g=s.crew();m=dict(g['members'][1]);m['member']=''
    h=b.card(g,m,True)
    s.assertIn('vac',h);s.assertIn('招募中',h);s.assertIn(m['character'],h)
  def test_uploaded_photo_keeps_the_picture_card(s):
    b,g=s.crew();m=g['members'][0]
    from PIL import Image
    os.makedirs(os.path.join(s.d,'uploads','portraits'),exist_ok=True)
    Image.new('RGB',(40,50),'white').save(os.path.join(s.d,'uploads','portraits','w.jpg'))
    with open(os.path.join(s.d,'uploads','map.json'),'w',encoding='utf-8') as f:
      json.dump({f'{g["name"]}|{m["character"]}':'portraits/w.jpg'},f,ensure_ascii=False)
    h=Build(s.d).card(g,m,True)
    s.assertIn('card ph',h)
    s.assertIn('class="art"',h)
  def test_only_crew_gets_the_cw_class(s):
    import re
    b,_=s.crew()
    body=''.join(b.section(g,2,8,cw=True) for g in b.D['groups'])
    cls=re.findall(r'<section class="([^"]*)"',body)
    s.assertEqual(sum('cw' in c.split() for c in cls),1,'cw 是给工作组名牌用的，coser 的段不该带')
    s.assertEqual(sum('cr' in c.split() for c in cls),1,'cr 同理，只标工作组段')
@unittest.skipUnless(HAS_PIL,'一图流要 Pillow；没装就跳过（它是可选依赖）')
class SingleLineup(unittest.TestCase):
  """单团一图流走 lineup()，不再套多团那套「白卡 + 标题条 + 卡片网格」。
  不开浏览器：把 render() 换掉，直接看生成的 HTML。"""
  def setUp(s):
    s.d=tempfile.mkdtemp(prefix='castcall-poster-')
    os.makedirs(os.path.join(s.d,'uploads'),exist_ok=True)
    with open(os.path.join(ROOT,'examples','roster.single.example.json'),encoding='utf-8') as f:s.R=json.load(f)
    s.R['groups'].append({'name':'摄影 / 后勤','kind':'crew','color':'#888888',
                          'members':[{'character':'摄影','member':'阿光'},{'character':'后勤','member':''}]})
    s.write({})
  def tearDown(s):shutil.rmtree(s.d,ignore_errors=True)
  def write(s,site):
    with open(os.path.join(s.d,'roster.json'),'w',encoding='utf-8') as f:json.dump(s.R,f,ensure_ascii=False)
    with open(os.path.join(s.d,'site.json'),'w',encoding='utf-8') as f:json.dump(site,f,ensure_ascii=False)
  def doc(s,cls='master'):
    b=Build(s.d);out={}
    b.render=lambda name,doc,w,h=None:out.setdefault(name,doc)
    b.web=lambda src,dst:None
    s.assertTrue(b.single(),'一个演出团 + 工作组仍算单团')
    b.lineup(cls);return out[cls]
  def test_no_multi_group_section(s):
    h=s.doc()
    s.assertNotIn('<section',h,'单团不该再出现多团的 section 白卡')
    s.assertNotIn('class="card',h,'单团的席位不是名牌卡')
    s.assertIn('lu-hero',h)
  def test_every_seat_and_vacancy(s):
    h=s.doc();cast=s.R['groups'][0]['members']
    s.assertEqual(h.count('class="lu-seat'),len(cast))
    vac=sum(1 for m in cast if not (m.get('member') or '').strip())
    s.assertEqual(h.count('lu-seat vac'),vac)
    s.assertIn(f'已定 {len(cast)-vac} / {len(cast)} 席',h)
  def test_crew_is_a_credit_line(s):
    h=s.doc()
    s.assertEqual(h.count('class="lu-credit'),2)
    s.assertIn('阿光',h);s.assertIn('lu-credit vac',h)
  def test_social_canvas_too(s):
    h=s.doc('social')
    s.assertIn('social lu-page',h);s.assertNotIn('<section',h)
  def test_kicker_does_not_repeat_group_name(s):
    s.write({'event':{'title':s.R['groups'][0]['name']}})
    h=s.doc()
    import re
    s.assertEqual(re.search(r'<div class="lu-kicker">(.*?)</div>',h).group(1),'')
  def test_no_date_place_no_footer(s):
    s.assertNotIn('class="lu-foot"',s.doc())
  def test_multi_is_not_single(s):
    shutil.copy(os.path.join(ROOT,'examples','roster.multi.example.json'),os.path.join(s.d,'roster.json'))
    s.assertFalse(Build(s.d).single())
  def test_columns_avoid_a_lonely_last_seat(s):
    for n in range(2,16):
      c=Build.lu_cols(n,5);last=n%c or c
      s.assertTrue(last>=c-1 or n<=c,(n,c))
    s.assertEqual(Build.lu_cols(9,5),5)
    s.assertEqual(Build.lu_cols(1,5),1)
class StaleWide(unittest.TestCase):
  """团数从多个掉到单个之后，上一轮的 wide.html 还躺在 instance/poster/ 里，
  /poster/ 的挑选脚本看见它就用它——桌面上打开还是旧的多团图，改了像没改。"""
  def setUp(s):
    s.d=tempfile.mkdtemp(prefix='castcall-poster-')
    os.makedirs(os.path.join(s.d,'uploads'),exist_ok=True)
    os.makedirs(os.path.join(s.d,'poster','cache'),exist_ok=True)
    shutil.copy(os.path.join(ROOT,'examples','roster.single.example.json'),os.path.join(s.d,'roster.json'))
    with open(os.path.join(s.d,'site.json'),'w',encoding='utf-8') as f:json.dump({},f)
  def tearDown(s):shutil.rmtree(s.d,ignore_errors=True)
  def pages(s):
    for n in ('wide.html','wide.jpg','master.html'):
      with open(os.path.join(s.d,'poster',n),'w',encoding='utf-8') as f:f.write('<html></html>')
  def test_single_drops_leftover_wide(s):
    s.pages();b=Build(s.d);s.assertTrue(b.single())
    b.prune(('master','social','portrait'))
    s.assertFalse(os.path.exists(os.path.join(s.d,'poster','wide.html')),'单团不该再留着多团的 wide.html')
    s.assertFalse(os.path.exists(os.path.join(s.d,'poster','wide.jpg')))
    s.assertTrue(os.path.exists(os.path.join(s.d,'poster','master.html')))
  def test_explicitly_built_wide_survives(s):
    s.pages();b=Build(s.d);b.prune(('master','wide','portrait'))
    s.assertTrue(os.path.exists(os.path.join(s.d,'poster','wide.html')),'这轮明确要了 wide 就不是遗留')
  def test_multi_keeps_wide(s):
    shutil.copy(os.path.join(ROOT,'examples','roster.multi.example.json'),os.path.join(s.d,'roster.json'))
    s.pages();b=Build(s.d);s.assertFalse(b.single())
    b.prune(('master','wide','portrait'))
    s.assertTrue(os.path.exists(os.path.join(s.d,'poster','wide.html')))

if __name__=='__main__':unittest.main()
