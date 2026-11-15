"""tools/lab.py 自己的断言也要被测：断言判错了，比没有断言更糟（11-11 S1 就把必填项拦住空提交判成了 FAIL）。"""
import contextlib,io,json,os,shutil,sys,tempfile,unittest
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0,os.path.join(ROOT,'tools'))
import lab

def wt(p,t,mode='w'):
  os.makedirs(os.path.dirname(p),exist_ok=True)
  with open(p,mode,**({} if 'b' in mode else {'encoding':'utf-8'})) as f:f.write(t)
def wj(p,o):
  os.makedirs(os.path.dirname(p),exist_ok=True)
  with open(p,'w',encoding='utf-8') as f:json.dump(o,f,ensure_ascii=False)

class Fingerprint(unittest.TestCase):
  def setUp(s):
    s.d=tempfile.mkdtemp(prefix='castcall-fp-')
    for rel,t in (('init.py','x'),('server/a.py','a'),('web/b.js','b'),('名单.txt','名单'),('.env','P=1'),
                  ('instance/roster.json','{}'),('server/__pycache__/a.pyc','c'),('poster/out/x.html','o')):
      wt(os.path.join(s.d,rel),t)
  def tearDown(s):shutil.rmtree(s.d,ignore_errors=True)
  def test_only_code_counts(s):
    fp=lab.fingerprint(s.d)
    s.assertEqual(sorted(fp),['init.py','server/a.py','web/b.js'],'名单、.env、instance、缓存产物都不算代码')
  def test_diff(s):
    a=lab.fingerprint(s.d)
    wt(os.path.join(s.d,'名单.txt'),'改了名单');wt(os.path.join(s.d,'instance/roster.json'),'[]')
    s.assertEqual(lab.fp_diff(a,lab.fingerprint(s.d)),[],'部署时改名单、建 instance 是正常的，不是改代码')
    wt(os.path.join(s.d,'server/a.py'),'patched');os.remove(os.path.join(s.d,'web/b.js'))
    s.assertEqual(lab.fp_diff(a,lab.fingerprint(s.d)),['server/a.py','web/b.js'])
  def test_assert_notes_sandbox_edits(s):
    rep=lab.Report('t');fp=lab.fingerprint(s.d)
    wt(os.path.join(s.d,'server/a.py'),'patched')
    with contextlib.redirect_stdout(io.StringIO()):lab.assert_fingerprint(rep,s.d,{'fp':fp})
    s.assertEqual(rep.d['fingerprint']['sandbox_changed'],['server/a.py'])
    s.assertTrue(rep.d['ok'],'指纹只提醒，不判失败')
  def test_old_sandbox_without_fp(s):
    rep=lab.Report('t')
    with contextlib.redirect_stdout(io.StringIO()):lab.assert_fingerprint(rep,s.d,{})
    s.assertIn('没有指纹',rep.d['notes'][0])

class Kinds(unittest.TestCase):
  """没绑上的名字要分四种。11-12 实测过：同一份名单 Bangumi 通时 5/5、不通时 4/5，
  而那 1 个（月宫亚由 / 月宮あゆ）被判成了「名单问题」——把网络的锅算到团长头上。"""
  def test_four_kinds(s):
    s.assertEqual(lab.unbound_kind(None,'K|a'),'none')
    s.assertEqual(lab.unbound_kind({'net':False},'K|a'),'net')
    s.assertEqual(lab.unbound_kind({'net':True,'sources':['AniList']},'K|a'),'weak','老数据没有 unbound 字段：看那次核对的来源')
    s.assertEqual(lab.unbound_kind({'net':True,'sources':['Bangumi']},'K|a'),'roster')
    run={'net':True,'sources':['Bangumi','AniList'],'unbound':{'K|a':{'state':'missing','src':'AniList'}}}
    s.assertEqual(lab.unbound_kind(run,'K|a'),'weak','表是 AniList 的，「表里没有」不等于名单写错')
    run={'net':True,'sources':['Bangumi'],'unbound':{'K|a':{'state':'unknown','src':''}}}
    s.assertEqual(lab.unbound_kind(run,'K|a'),'net','部分名字 unknown（网络中途断）不能算名单问题')
    run={'net':True,'sources':['Bangumi'],'unbound':{'K|a':{'state':'missing','src':'Bangumi'}}}
    s.assertEqual(lab.unbound_kind(run,'K|a'),'roster')

class Art(unittest.TestCase):
  def setUp(s):
    s.inst=tempfile.mkdtemp(prefix='castcall-art-')
    wj(os.path.join(s.inst,'roster.json'),{'groups':[
      {'name':'Kanon','cover':'c1.jpg','members':[{'character':'川澄舞'},{'character':'美坂栞'},{'character':'月宫亚由'}]},
      {'name':'摄影 / 后勤','kind':'crew','members':[{'character':'摄影','member':'阿光'}]}]})
    up=os.path.join(s.inst,'uploads')
    for rel in ('covers/c1.jpg','portraits/p1.jpg'):
      wt(os.path.join(up,rel),b'x','wb')
    # 美坂栞 在 map 里但文件丢了——map 有记录不等于图在
    wj(os.path.join(up,'map.json'),{'Kanon|川澄舞':'portraits/p1.jpg','Kanon|美坂栞':'portraits/gone.jpg'})
    wj(os.path.join(up,'art_bind.json'),{'Kanon|川澄舞':{'id':1},'Kanon|美坂栞':{'id':2}})
  def tearDown(s):shutil.rmtree(s.inst,ignore_errors=True)
  def run_(s,want):
    rep=lab.Report('t')
    with contextlib.redirect_stdout(io.StringIO()):lab.assert_art(rep,s.inst,want)
    return rep
  def steps(s,rep):return {x['step']:x for x in rep.d['steps']}
  def test_classifies_missing(s):
    rep=s.run_(True);st=s.steps(rep)
    p=st['立绘配齐（1/3）'];s.assertFalse(p['ok'])
    s.assertIn('1 个没核对过',p['detail']);s.assertIn('月宫亚由',p['detail'])
    s.assertIn('绑上了但图没下来 1 个',p['detail']);s.assertIn('美坂栞',p['detail'])
    s.assertTrue(st['封面配齐（1/1）']['ok'],'工作组不该要封面')
    s.assertEqual(rep.d['cause'],'','没核对过 → 说不清是谁的问题，别急着归环境')
  def test_bangumi_down_is_not_roster(s):
    """Bangumi 不通时 AniList 认不出假名化写法——这是网络的锅，报告里不能写成名单问题。"""
    wj(os.path.join(s.inst,'uploads','art_bind_run.json'),
       {'net':True,'bangumi':False,'sources':['AniList'],'unbound':{'Kanon|月宫亚由':{'state':'missing','src':'AniList'}}})
    rep=s.run_(True);p=s.steps(rep)['立绘配齐（1/3）']
    s.assertIn('没法确认 1 个',p['detail']);s.assertNotIn('名单里对不上',p['detail'])
    s.assertEqual(rep.d['cause'],'env')
  def test_roster_problem_stays_roster(s):
    wj(os.path.join(s.inst,'uploads','art_bind_run.json'),
       {'net':True,'bangumi':True,'sources':['Bangumi'],'unbound':{'Kanon|月宫亚由':{'state':'missing','src':'Bangumi'}}})
    rep=s.run_(True);p=s.steps(rep)['立绘配齐（1/3）']
    s.assertIn('名单里对不上 1 个',p['detail']);s.assertEqual(rep.d['cause'],'')
  def test_partial_unknown_is_net(s):
    """核对途中断网：部分名字 unknown 时 net 仍是 true，不能因此判成名单问题。"""
    wj(os.path.join(s.inst,'uploads','art_bind_run.json'),
       {'net':True,'bangumi':True,'sources':['Bangumi'],'unbound':{'Kanon|月宫亚由':{'state':'unknown','src':''}}})
    rep=s.run_(True);p=s.steps(rep)['立绘配齐（1/3）']
    s.assertIn('网络断了',p['detail']);s.assertEqual(rep.d['cause'],'env')
  def test_all_download_failures_is_env(s):
    wj(os.path.join(s.inst,'uploads','art_bind.json'),{'Kanon|川澄舞':{'id':1},'Kanon|美坂栞':{'id':2},'Kanon|月宫亚由':{'id':3}})
    s.assertEqual(s.run_(True).d['cause'],'env')
  def test_not_wanted_is_note(s):
    rep=s.run_(False);s.assertTrue(rep.d['ok']);s.assertEqual(rep.d['steps'],[])
    s.assertIn('立绘 1/3',rep.d['notes'][0])
  def test_full(s):
    up=os.path.join(s.inst,'uploads')
    for n in ('gone','p3'):wt(os.path.join(up,'portraits',n+'.jpg'),b'x','wb')
    wj(os.path.join(up,'map.json'),{'Kanon|川澄舞':'portraits/p1.jpg','Kanon|美坂栞':'portraits/gone.jpg','Kanon|月宫亚由':'portraits/p3.jpg'})
    s.assertTrue(s.run_(True).d['ok'])

class PosterCanvas(unittest.TestCase):
  """「竖版画布比横版窄」这条断言靠正则在 body 标签上量宽度。体 markup 一改（单团阵容版
  给 body 加了 lu-page），写死的 class="portrait" 就量不到——断言从此只红不判，比没有更糟。"""
  def _inst(s,body_class,width):
    d=tempfile.mkdtemp(prefix='castcall-poster-')
    wt(os.path.join(d,'poster','master.html'),'<html></html>')
    wt(os.path.join(d,'poster','portrait.html'),
       f'<!doctype html><html><head></head><body class="{body_class}" style="width:{width}px;--c:#e07a5f">'
       '<div class="lu" style="--cols:3"></div></body></html>')
    s.addCleanup(shutil.rmtree,d,True)
    return d
  def _run(s,d):
    rep=lab.Report('t')
    with contextlib.redirect_stdout(io.StringIO()):lab.assert_poster(rep,d,True)
    return {x['step']:x for x in rep.d['steps']}
  def test_measures_lineup_body(s):
    st=s._run(s._inst('portrait lu-page',1200))
    s.assertTrue(st['竖版画布比横版窄']['ok'],'class="portrait lu-page" 也要能量到宽度')
    s.assertIn('1200px',st['竖版画布比横版窄']['detail'])
  def test_measures_plain_body(s):
    st=s._run(s._inst('portrait',1200))
    s.assertTrue(st['竖版画布比横版窄']['ok'],'多团版的 class="portrait" 也不能被改坏')
  def test_wide_portrait_still_red(s):
    st=s._run(s._inst('portrait lu-page',2400))
    s.assertFalse(st['竖版画布比横版窄']['ok'],'竖版真变成 2400 宽时必须红')

if __name__=='__main__':unittest.main()
