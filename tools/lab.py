#!/usr/bin/env python3
"""从零部署的实验室：干净沙盒 → 真走一遍部署 → 外部断言 → 留档。

castcall 的交付物是「AI 帮团长从零建站」，所以要回归的是**部署过程**，不是单个函数。
tests/test_api.py 管代码，这个工具管流程：

  python3 tools/lab.py smoke --via cli     init.py 从零建站，约 1 秒，不联网、不配图（默认）
  python3 tools/lab.py smoke --via wizard  server.py --prefill + 提交向导接口，走完首次收尾（真去配图）
  python3 tools/lab.py blind               dsh 扮演不知情的 AI：只给一句需求，看它能不能按 AGENTS.md 走通
  python3 tools/lab.py blind --no-agents   同上，但把 AGENTS.md 拿掉，只留 README（测文档自解释性）
  python3 tools/lab.py sandbox --port N    建一个沙盒交给别的 AI 会话去部署（记下代码指纹）
  python3 tools/lab.py check <沙盒>        对跑过的沙盒做同一套断言；先比指纹，跑的是旧代码会提醒
  python3 tools/lab.py list                历次结果 + 首次通过率

每次的结果落在 runs/<时间>-<场景>/：

  meta.json      场景、耗时、命令、环境
  report.json    断言明细（PASS / FAIL 逐条）+ 归因
  server.log     服务端输出
  events.jsonl   blind 模式的 dsh 事件流
  transcript.md  blind 模式的人类可读摘要

断言一律在**外部**做：AI 说「好了」不算数，要看 instance/ 里的文件和 /api/ 的返回。
沙盒跑完默认删掉，加 --keep 留着复查。
"""
import argparse,glob,json,os,re,shutil,socket,subprocess,sys,tempfile,time,urllib.error,urllib.request
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNS=os.path.join(ROOT,'runs')
EXCLUDE=['.git','instance','instance-*','runs','.venv','.venv-poster','.e2e-out','__pycache__','*.pyc','.DS_Store',
         'node_modules','poster/out','poster/cache','.claude','.workbuddy']
DSH=os.environ.get('DSH_BIN') or '/Applications/DeepSeek Harness.app/Contents/Resources/runtime/cli/bin/dsh'
NAMES='''## Kanon
> 光坂外景，妆造自理
月宫亚由 云果
泽渡真琴 小满
美坂栞
川澄舞
天野美汐
## 摄影 / 后勤
摄影 阿光
后勤 阿草
'''
PW='lab-password-1'

# ── 小工具 ──────────────────────────────────────────────────────────────
def now():return time.strftime('%Y-%m-%dT%H:%M:%S')
def free_port():
  s=socket.socket();s.bind(('127.0.0.1',0));p=s.getsockname()[1];s.close();return p
def jload(p,d=None):
  try:
    with open(p,encoding='utf-8') as f:return json.load(f)
  except (OSError,ValueError):return d
def jdump(p,o):
  os.makedirs(os.path.dirname(p),exist_ok=True)
  with open(p,'w',encoding='utf-8') as f:json.dump(o,f,ensure_ascii=False,indent=1)
def wait(fn,timeout,step=.25):
  """轮询直到 fn() 为真；超时返回 None。"""
  t0=time.time()
  while time.time()-t0<timeout:
    try:
      v=fn()
      if v:return v
    except Exception:pass
    time.sleep(step)
  return None

def sandbox(tag='run'):
  """复制一份干净仓库（不含 instance / .venv / .git）。改代码后没提交也不影响：直接拷工作区。"""
  d=tempfile.mkdtemp(prefix=f'castcall-lab-{tag}-')
  ex=sum([['--exclude',x] for x in EXCLUDE],[])
  subprocess.run(['rsync','-a',*ex,ROOT.rstrip('/')+'/',d],check=True)
  return d

# 沙盒指纹：只算「被测的代码和文档」，不算名单、.env、instance/ 这些每个沙盒本来就不同的东西
FP_FILES=('init.py','AGENTS.md','README.md','requirements-poster.txt')
FP_DIRS=('server','web','poster','tools','skills','docs')
FP_EXT=('.py','.js','.html','.css','.md','.txt','.json')
def fingerprint(root):
  """→ {相对路径: sha1 前 10 位}。用来回答「这个沙盒跑的是哪一版代码」。"""
  import hashlib
  out={}
  def add(rel):
    try:
      with open(os.path.join(root,rel),'rb') as f:out[rel]=hashlib.sha1(f.read()).hexdigest()[:10]
    except OSError:pass
  for f in FP_FILES:add(f)
  for d in FP_DIRS:
    for base,dirs,files in os.walk(os.path.join(root,d)):
      rb=os.path.relpath(base,root)
      dirs[:]=[x for x in dirs if x not in ('__pycache__','out','cache') and not x.startswith('.')]
      for f in files:
        if f.endswith(FP_EXT):add(os.path.join(rb,f))
  return out
def fp_id(fp):
  import hashlib
  return hashlib.sha1(json.dumps(fp,sort_keys=True).encode()).hexdigest()[:12]
def fp_diff(a,b):
  """两份指纹之间变了哪些文件（新增 / 删除 / 内容不同都算）。"""
  return sorted(k for k in set(a)|set(b) if a.get(k)!=b.get(k))
def assert_fingerprint(rep,repo,lab):
  """check 时对一次：沙盒建好以后，主仓库的代码改没改过、沙盒里的代码被动没动过。
  前者 = 这版跑的是旧代码，结论不代表现在（R2 就是这么「差点以为修好了」）；
  后者 = 部署的 AI 自己改了代码——可能是修 bug，也可能是绕过断言，都要人看一眼。"""
  rec=(lab or {}).get('fp')
  if not rec:rep.note('这个沙盒没有指纹（建于加指纹之前）：没法确认它跑的是哪一版代码');return
  rep.d['fingerprint']={'sandbox':fp_id(rec)}
  main=fp_diff(rec,fingerprint(ROOT))
  if main:
    rep.note(f'⚠ 建沙盒之后主仓库改过 {len(main)} 个文件（{"、".join(main[:5])}{"…" if len(main)>5 else ""}）：'
             '这版跑的是旧代码，结论不代表现在的代码。要验新代码就重新建沙盒')
  rep.d['fingerprint']['main_changed']=main
  mine=[f for f in fp_diff(rec,fingerprint(repo)) if f!='AGENTS.md' or not lab.get('no_agents')]
  if mine:
    rep.note(f'⚠ 沙盒里有 {len(mine)} 个代码 / 文档文件被部署的 AI 改过（{"、".join(mine[:5])}{"…" if len(mine)>5 else ""}）：'
             '看一眼 diff，是修了真 bug（该搬回主仓库）还是绕过了断言')
  rep.d['fingerprint']['sandbox_changed']=mine

def find_password(text):
  """从 AI 的汇报里猜管理密码：取带字母和数字、8 位以上的那段。"""
  for m in re.finditer(r'[A-Za-z0-9!@#$%^&*_.\-]{8,40}',text or ''):
    s=m.group(0)
    if any(c.isdigit() for c in s) and any(c.isalpha() for c in s):return s
  return None

class Http:
  """带 cookie 的极简客户端。"""
  def __init__(s,base):s.base=base;s.cookie=''
  def __call__(s,path,method='GET',body=None,timeout=120):
    data=json.dumps(body,ensure_ascii=False).encode() if body is not None else None
    r=urllib.request.Request(s.base+path,data=data,method=method)
    if data:r.add_header('Content-Type','application/json')
    if s.cookie:r.add_header('Cookie',s.cookie)
    try:
      with urllib.request.urlopen(r,timeout=timeout) as f:
        c=f.headers.get('Set-Cookie') or '';st,text=f.status,f.read().decode('utf-8','replace')
    except urllib.error.HTTPError as e:
      c=e.headers.get('Set-Cookie') or '';st,text=e.code,e.read().decode('utf-8','replace')
    except Exception as e:return 0,'',str(e)
    if c.startswith('cc_s='):s.cookie=c.split(';')[0]
    return st,text

class Report:
  def __init__(s,scenario):
    s.d={'scenario':scenario,'started':now(),'steps':[],'ok':True,'cause':'','notes':[]};s.t0=time.time()
  def step(s,name,ok,detail=''):
    s.d['steps'].append({'step':name,'ok':bool(ok),'detail':str(detail)[:500]})
    s.d['ok']&=bool(ok)
    print(('PASS ' if ok else 'FAIL ')+name+(f'  · {detail}' if detail else ''),flush=True)
    return ok
  def note(s,msg):s.d['notes'].append(msg);print('  · '+msg,flush=True)
  def save(s,out):
    s.d['duration']=round(time.time()-s.t0,1)
    jdump(os.path.join(out,'report.json'),s.d)
    print('\n'+('ALL PASS' if s.d['ok'] else 'SOME FAILED')+f"  ({s.d['duration']}s) → {out}",flush=True)
    return s.d['ok']

def mkrun(scenario):
  out=os.path.join(RUNS,time.strftime('%Y%m%d-%H%M%S')+'-'+scenario)
  os.makedirs(out,exist_ok=True);return out

# ── 起服务 ──────────────────────────────────────────────────────────────
def serve(repo,port,extra=(),logfile=None,env=None):
  e=dict(os.environ,CASTCALL_INSTANCE=os.path.join(repo,'instance'),CASTCALL_PORT=str(port),**(env or {}))
  logf=open(logfile or os.path.join(repo,'server.log'),'w',encoding='utf-8')
  p=subprocess.Popen([sys.executable,os.path.join(repo,'server','server.py'),*extra],cwd=repo,env=e,
                     stdout=logf,stderr=subprocess.STDOUT,text=True)
  ok=wait(lambda:Http(f'http://127.0.0.1:{port}')('/api/health')[0]==200,30)
  if not ok:
    p.terminate()
    tail=''
    try:tail=open(logf.name,encoding='utf-8').read()[-800:]
    except OSError:pass
    raise SystemExit('服务没起来：\n'+tail)
  return p,logf

def stop(p,logf):
  try:p.terminate();p.wait(10)
  except Exception:
    try:p.kill()
    except Exception:pass
  try:logf.close()
  except Exception:pass

# ── 断言：只看外部可见的结果 ────────────────────────────────────────────
def find_instance(repo):
  for c in [os.path.join(repo,'instance')]+sorted(glob.glob(os.path.join(repo,'instance*')),reverse=True):
    if os.path.exists(os.path.join(c,'roster.json')):return c
  return None

def counts(r):
  """(团数, 席位数, 空缺数)。工作组不算团。"""
  gs=r.get('groups') or []
  n=sum(len(g.get('members') or []) for g in gs)
  o=sum(1 for g in gs for m in (g.get('members') or []) if not m.get('member'))
  return len([g for g in gs if g.get('kind')!='crew']),n,o

def parse_names(text):
  """独立解析名单，不借 server/importer——期望值不该由被测代码算出来。→ (团数, 席位数, 空缺数)"""
  groups=[];cur=None
  for line in text.splitlines():
    s=line.strip()
    if not s or s.startswith('>'):continue
    if s.startswith('##'):
      name=s.lstrip('#').strip()
      cur={'crew':bool(re.search(r'摄影|后勤|妆娘|staff',name,re.I)),'members':[]}
      groups.append(cur);continue
    if cur is None:continue
    parts=re.split(r'[\s|:：\t]+',s,maxsplit=1)
    cur['members'].append(parts[1] if len(parts)>1 else '')
  n=sum(len(g['members']) for g in groups);o=sum(1 for g in groups for m in g['members'] if not m)
  return len([g for g in groups if not g['crew']]),n,o

FILL={'height':'165','age':'22','gender':'女','city':'深圳','experience':'两次','note':'lab 测试'}
def signup_extra(fields):
  """按这个站的报名表填一份能过的额外信息。样片（sample）要真文件、填不了，所以不在这里——
  它必填时上面的断言会单独说明，而不是把 400 记成「不能报名」。"""
  return {k:FILL[k] for k in fields if k in FILL}
def assert_site(rep,inst,base,exp,pw=None):
  """一套部署是否真的成立：文件、名册、页面、报名、后台、安全。pw 为 None 时跳过登录（AI 自己设的密码未知）。"""
  rep.step('instance/ 建出来了',bool(inst),inst or '没有 roster.json')
  if not inst:return
  rep.step('site.json / auth.json 都在',all(os.path.exists(os.path.join(inst,f)) for f in ('site.json','auth.json')))
  r=jload(os.path.join(inst,'roster.json'),{})
  got=counts(r)
  rep.step('名册和名单一致',got==exp,f'{got} vs 期望 {exp}')
  st,html=Http(base)('/')
  rep.step('首页 200',st==200,f'HTTP {st}')
  title=(jload(os.path.join(inst,'site.json'),{}).get('event') or {}).get('title') or ''
  rep.step('首页有活动名',bool(title) and title in html,title)
  c=Http(base);st,txt=c('/api/data')
  rep.step('/api/data 和 roster.json 一致',st==200 and counts(json.loads(txt or '{}'))==got,f'HTTP {st}')
  # 报名：挑一个空缺提交，再确认它进了待审
  # 团长把某些项设成必填时（身高、样片…），不带这些字段发过去必然 400。
  # 以前 lab 只发 CN + 联系方式，于是「必填项拦住了空提交」这个**正确行为**被记成 FAIL。
  vac=[(g['name'],m['character'],m.get('id')) for g in r.get('groups') or [] for m in g.get('members') or [] if not m.get('member')]
  fields=[f.get('key') if isinstance(f,dict) else f for f in ((jload(os.path.join(inst,'site.json'),{}).get('signup') or {}).get('fields') or [])]
  sent=False
  if vac:
    g,ch,mid=vac[0]
    st,txt=c('/api/cast-signup',method='POST',body={'name':'lab 测试','contact':'wx_lab','work':g,'character':ch,'id':mid,'extra':signup_extra(fields)})
    ok=st==200
    rep.step('空缺能报名',ok,f'{g}/{ch} HTTP {st} {txt[:120]}')
    rep.step('报名落库（castcall.db）',os.path.exists(os.path.join(inst,'castcall.db')))
    sent=ok
    if not ok and '样片' in txt:rep.note('这个站把样片设成必填；lab 只发 JSON、不带文件，所以这次没报进去')
  else:rep.step('空缺能报名',False,'名单里没有空缺')
  # 后台
  st,_=c('/api/admin/signups')
  rep.step('未登录挡住后台',st==401,f'HTTP {st}')
  if pw:
    c2=Http(base);st,_=c2('/api/login',method='POST',body={'password':pw})
    rep.step('密码能登录',st==200,f'HTTP {st}')
    if sent:
      st,txt=c2('/api/admin/signups')
      rep.step('后台读得到待审',st==200 and 'lab 测试' in txt,f'HTTP {st}')
    else:rep.note('上面没报进去，跳过「后台读得到待审」——那不是后台的问题')
  else:
    c2=Http(base);st,_=c2('/api/login',method='POST',body={'password':'definitely-not-it'})
    rep.step('错密码进不去',st!=200,f'HTTP {st}')
    rep.note('不知道这次的密码，跳过「能登录」——要验就把 AI 汇报的密码传给 --password')
  # 首次收尾
  fr=jload(os.path.join(inst,'firstrun.pending'))
  rep.step('firstrun 收尾跑完了',fr is None,'' if fr is None else f'还留着 {fr}')
  return True

def assert_poster(rep,inst,want):
  """一图流：master（发群）+ portrait（手机网页）两张都在。

  portrait 是为了修「竖屏里横条只占 42% 屏高，网页再居中，卡片看着被挤到屏幕下半截」。
  所以只查文件存在没用——画布得比 master 窄、卡片列数得 ≤3，否则等于又生成了一张横图。"""
  p=os.path.join(inst or '','poster','master.html')
  has=os.path.exists(p)
  if not want:
    rep.note('一图流没要求（--poster 才检查）' if not has else '一图流意外存在');return
  rep.step('一图流生成了',has,p or '没有 master.html')
  if not has:return
  q=os.path.join(inst,'poster','portrait.html')
  ok=os.path.exists(q)
  rep.step('手机竖版页面生成了',ok,q if ok else '没有 portrait.html：手机打开 /poster/ 会退回横条')
  if not ok:return
  try:h=open(q,encoding='utf-8').read()
  except OSError as e:rep.step('手机竖版页面读得到',False,repr(e));return
  # 别写死 class="portrait"：单团阵容版的 body 是 class="portrait lu-page"，写死就量不到宽度，
  # 这条断言从此只会红、不再判任何东西（11-14 阵容版上线后就这样哑了两小时）。
  m=re.search(r'<body class="[^"]*\bportrait\b[^"]*" style="width:(\d+)px',h)
  w=int(m.group(1)) if m else 0
  rep.step('竖版画布比横版窄',0<w<2000,f'{w or "量不到"}px（master 是 2400）')
  cols=[int(x) for x in re.findall(r'--cols:(\d+)',h)]
  rep.step('竖版卡片列数 ≤3',bool(cols) and max(cols)<=3,cols or '没找到 --cols')

def unbound_kind(run,key):
  """一个没绑上的名字是哪种没绑上——这决定该改名单还是等网络，两者补救办法完全不同：

    roster  判它的作品角色表里确实没有这个名字 → 名单写错了，重试多少次都配不上
    weak    判它的表是 AniList 的（Bangumi 不通），只有日文名：汉字被改写成假名的（月宫亚由 / 月宮あゆ）
            必然查不到。**不能算名单写错**，网络好了重跑一次就可能对上
    net     核对时网络断了（state=unknown）：既没通过也没否定
    none    这版根本没核对：说不清是名单还是下载

  11-12 实测：同一份名单，Bangumi 通时 5/5，不通时 4/5，而那 1 个被判成「名单问题」——
  名字是对的，只是那张表认不出。少了这一层，断言会把网络的锅算到团长头上。"""
  if run is None:return 'none'
  if not run.get('net',True):return 'net'
  u=(run.get('unbound') or {}).get(key) or {}
  src=u.get('src') or ((run.get('sources') or [''])[0])
  if u.get('state')=='unknown':return 'net'
  return 'weak' if src and 'Bangumi' not in src else 'roster'

def assert_bind(rep,inst):
  """名单里的每个名字都要绑到确定的角色（uploads/art_bind.json）。
  这条查的不是「图配上了没」——图没配上可能只是网络抖动，重试就好；名字对不上作品里的角色，则永远配不上。
  前者是运气，后者是名单本身的问题，必须在这里分开。"""
  r=jload(os.path.join(inst or '','roster.json'),{}) or {}
  want=[(g.get('name') or '',(m.get('character') or '').strip())
        for g in r.get('groups') or [] if (g.get('kind') or 'cast')!='crew'
        for m in g.get('members') or [] if (m.get('character') or '').strip()]
  if not want:rep.note('没有要配图的角色，跳过名单绑定检查');return
  d=jload(os.path.join(inst or '','uploads','art_bind.json'),None)
  run=jload(os.path.join(inst or '','uploads','art_bind_run.json'),None)
  if run and not run.get('net',True):
    # 核对跑了，但两个库都连不上。这不是名单的问题，别让它看起来像「名字配不上」。
    rep.note(f"名单预检跑了但没结果：Bangumi{'通' if run.get('bangumi') else '不通'}、AniList 也不通（{run.get('at')}）");return
  if d is None:
    if run:rep.note(f"名单预检跑了但一个名字都没绑上（{run.get('at')}，ok={run.get('ok')}/{run.get('total')}）");return
    rep.note(f'这版没跑名单预检（没有 uploads/art_bind.json）：{len(want)} 个角色的名字没核对过，配不配得上图靠运气');return
  bad=[f'{g}/{c}' for g,c in want if not (d.get(f'{g}|{c}') or {}).get('id')]
  kinds={f'{g}/{c}':unbound_kind(run,f'{g}|{c}') for g,c in want if not (d.get(f'{g}|{c}') or {}).get('id')}
  why=[]
  for k,msg in (('roster','作品角色表里确实没有这个名字（改名单或后台手选）'),
                ('weak','没法确认：判它的是 AniList 的表，只有日文名，写法不同的查不到（网络好了重跑 names）'),
                ('net','核对时网络断了，没法判断（网络好了重跑 names）'),
                ('none','这版没核对过，说不清是名单还是下载')):
    xs=[n for n,v in kinds.items() if v==k]
    if xs:why.append(f'{len(xs)} 个{msg}：{"、".join(xs[:6])}')
  if bad and not any(v=='roster' for v in kinds.values()) and not rep.d['cause']:rep.d['cause']='env'
  src='、'.join(run.get('sources') or []) if run else ''
  tail=f'（来源 {src}{"，Bangumi 不通" if run and not run.get("bangumi") else ""}' if src else ''
  if run and tail:
    # 核对自动绑定几个 / 之后人工补几个，要分开说：人工补的那几个换个团就不成立了。
    # 每条自己有 by（auto / manual）就按它数；老数据没有这个字段，用那次核对的 bound 折算——
    # 只按 by 数会把老数据全算成「人工」，只按 bound 数会在核对范围变小时虚报。
    bys=[(d.get(f'{g}|{c}') or {}).get('by') for g,c in want]
    auto=sum(1 for b in bys if b=='auto')
    loose=bys.count(None)
    if loose:auto+=max(0,min(int(run.get('bound') or run.get('ok') or 0)-auto,loose))
    extra=len(want)-len(bad)-auto
    if extra>0:tail+=f"，{auto} 个自动、{extra} 个人工确认"
    tail+='）'
  rep.step(f'名单里 {len(want)} 个名字都绑到了角色（{len(want)-len(bad)}/{len(want)}）{tail}',not bad,
           '；'.join(why) or '、'.join(bad[:8]))

def assert_art(rep,inst,want):
  """配图覆盖率：每个要配图的角色都有立绘、每个团都有封面（工作组不算）。
  以前只有 assert_poster 判 master.html 在不在，少三张立绘也能 ALL PASS，是人眼看出来的。

  少了的逐个归因，和 assert_bind 的原则一致——归对了才知道该改名单还是该重试：
    名字没绑上        → 再分四种（见 unbound_kind）：名单对不上 / 那张表认不出 / 网络断了 / 没核对
    绑上了但没有图    → 下载那一步失败，多半是网络，后台「一键配图」重试就好
  want=False（这一版本来就没让它配图）时只记一笔，不判失败。"""
  r=jload(os.path.join(inst or '','roster.json'),{}) or {}
  up=os.path.join(inst or '','uploads')
  m=jload(os.path.join(up,'map.json'),{}) or {}
  binds=jload(os.path.join(up,'art_bind.json'),{}) or {}
  run=jload(os.path.join(up,'art_bind_run.json'),None)
  cast=[g for g in r.get('groups') or [] if (g.get('kind') or 'cast')!='crew']
  chars=[(g.get('name') or '',(mb.get('character') or '').strip()) for g in cast
         for mb in g.get('members') or [] if (mb.get('character') or '').strip()]
  if not chars:rep.note('没有要配图的角色，跳过配图覆盖率');return
  has=lambda rel:bool(rel) and os.path.isfile(os.path.join(up,rel))
  miss=[(g,c) for g,c in chars if not has(m.get(f'{g}|{c}'))]
  nocover=[g.get('name') or '' for g in cast if not has('covers/'+g['cover'] if g.get('cover') else '')]
  got=len(chars)-len(miss)
  if not want:
    rep.note(f'配图没要求（立绘 {got}/{len(chars)}、封面 {len(cast)-len(nocover)}/{len(cast)}）');return
  nodl=[];roster=[];weak=[];net=[];none=[]
  for g,c in miss:
    if (binds.get(f'{g}|{c}') or {}).get('id'):nodl.append(f'{g}/{c}');continue
    {'roster':roster,'weak':weak,'net':net,'none':none}[unbound_kind(run,f'{g}|{c}')].append(f'{g}/{c}')
  why=[]
  if roster:why.append(f"名单里对不上 {len(roster)} 个（作品角色表里确实没有这个名字，改名单或后台手选）：{'、'.join(roster[:6])}")
  if nodl:why.append(f"绑上了但图没下来 {len(nodl)} 个（多半是网络，后台「一键配图」重试）：{'、'.join(nodl[:6])}")
  if weak:why.append(f"没法确认 {len(weak)} 个（Bangumi 不通，判它的是 AniList 的表，只有日文名；网络好了重跑 names）：{'、'.join(weak[:6])}")
  if net:why.append(f"核对时网络断了，{len(net)} 个没法判断（网络好了重跑 names）：{'、'.join(net[:6])}")
  if none:why.append(f"{len(none)} 个没核对过（这版没跑名单预检，说不清是名单还是下载）：{'、'.join(none[:6])}")
  rep.step(f'立绘配齐（{got}/{len(chars)}）',not miss,'；'.join(why))
  rep.step(f'封面配齐（{len(cast)-len(nocover)}/{len(cast)}）',not nocover,'、'.join(nocover[:6]))
  # 缺的全都能用环境解释（下载失败 / 那张表认不出 / 核对时断网）、没有一个名字真的对不上：归环境。
  # 「没核对过」不算环境——那是这版没走预检，该看代码或文档，不能被网络的解释盖过去。
  offline=run is not None and not run.get('net',True)
  if (miss or nocover) and not roster and not none and (nodl or weak or net or offline) and not rep.d['cause']:rep.d['cause']='env'

# ── smoke：脚本扮演团长 ─────────────────────────────────────────────────
def host_poster_env():
  """沙盒按 EXCLUDE 不带 .venv-poster，可团长自己的机器上是带着的——不把宿主的解释器
  指过去，`--poster` 每一次都会因为「这台机器还没装依赖」而假失败（11-14 复现过一次）。"""
  py=os.path.join(ROOT,'.venv-poster','bin','python')
  e={}
  if os.path.exists(py) and not os.environ.get('CASTCALL_POSTER_PYTHON'):e['CASTCALL_POSTER_PYTHON']=py
  if not os.environ.get('CASTCALL_CHROME'):
    for c in ('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',):
      if os.path.exists(c):e['CASTCALL_CHROME']=c;break
  return e

def cmd_smoke(a):
  out=mkrun('smoke-'+a.via)
  rep=Report('smoke-'+a.via)
  if a.poster:
    e=host_poster_env();os.environ.update(e)
    if e:rep.note('海报依赖用宿主机的：'+' '.join(f'{k}→{os.path.basename(v)}' for k,v in e.items()))
  repo=sandbox('smoke')
  names=a.names if a.names and os.path.exists(a.names) else NAMES
  open(os.path.join(repo,'名单.txt'),'w',encoding='utf-8').write(names)
  exp=parse_names(names)
  port=free_port();base=f'http://127.0.0.1:{port}/'
  meta={'scenario':rep.d['scenario'],'via':a.via,'port':port,'repo':repo,'names':names,'expect':exp,'code':fp_id(fingerprint(repo))}
  jdump(os.path.join(out,'meta.json'),meta)
  print(f'沙盒 {repo}\n名单 {exp[0]} 个团 / {exp[1]} 个席位 / {exp[2]} 个空缺\n',flush=True)
  p=None;logf=None
  try:
    if a.via=='cli':
      args=[sys.executable,os.path.join(repo,'init.py'),'--instance',os.path.join(repo,'instance'),
            '--title','Kanon 团片 2026','--import',os.path.join(repo,'名单.txt'),'--password',PW,'--yes']
      if not a.art:args.append('--no-art')
      if not a.poster:args.append('--no-poster')
      r=subprocess.run(args,cwd=repo,capture_output=True,text=True,timeout=a.timeout)
      meta['cmd']=' '.join(args[1:])
      rep.step('init.py 退出码 0',r.returncode==0,(r.stdout+r.stderr)[-400:])
      p,logf=serve(repo,port,logfile=os.path.join(out,'server.log'))
    else:
      p,logf=serve(repo,port,extra=['--prefill','名单.txt','--title','Kanon 团片 2026'],logfile=os.path.join(out,'server.log'))
      tok=''
      try:tok=open(os.path.join(repo,'instance','.setup-token'),encoding='utf-8').read().strip()
      except OSError:pass
      rep.step('向导验证码写出来了',bool(tok),(tok if len(tok)<=8 else tok[:8]+'…') if tok else '没有 .setup-token')
      c=Http(base)
      st,txt=c('/api/setup/preview',method='POST',body={'token':tok,'source':'paste','names':names,'title':'Kanon 团片 2026'})
      rep.step('向导能预览名单',st==200,f'HTTP {st} {txt[:120]}')
      st,txt=c('/api/setup',method='POST',body={'token':tok,'mode':'auto','title':'Kanon 团片 2026','date':'2026-12-12',
        'start':'2026-12-12T11:00:00+08:00','location':'某某公园','contact':'微信 lab_id','contactLabel':'微信',
        'source':'paste','names':names,'example':'','password':PW,'fields':[]})
      rep.step('向导提交成功',st==200,f'HTTP {st} {txt[:160]}')
      # 等首次收尾（配图 → 一图流）跑完
      done=wait(lambda:c('/api/admin/firstrun')[0]==200 and json.loads(c('/api/admin/firstrun')[1]).get('stage')=='done',a.timeout,1)
      rep.step('首次收尾跑完',bool(done),'超时' if not done else '')
      # stage=done 只代表「配方跑完了，一图流交给子进程了」。一图流是另一个进程，慢的时候
      # 十几秒才出图——这里不等它，就会在文件还没写出来的时候断言「一图流生成了」，
      # 于是每次 wizard + poster 都假失败，而沙盒里其实是好的（实测 01:33 断言、01:34 出图）。
      if a.poster:
        fin=wait(lambda:not os.path.exists(os.path.join(repo,'instance','firstrun.pending')),a.timeout,1)
        rep.step('一图流也跑完了（pending 清掉）',bool(fin),'还留着 firstrun.pending' if not fin else '')
    inst=find_instance(repo)
    assert_site(rep,inst,base,exp,PW)
    assert_bind(rep,inst)
    assert_art(rep,inst,a.art or a.via=='wizard')
    assert_poster(rep,inst,a.poster)
    if a.via=='wizard':
      log=''
      try:log=open(os.path.join(inst or '','logs','server.log'),encoding='utf-8').read()
      except OSError:pass
      rep.step('日志里有 firstrun 行','firstrun' in log,'')
  finally:
    if p:stop(p,logf)
    if not a.keep:shutil.rmtree(repo,ignore_errors=True)
    else:print('沙盒留在 '+repo,flush=True)
  rep.save(out)

# ── blind：dsh 扮演不知情的 AI ──────────────────────────────────────────
DEFAULT_TASK=('我们下周有个 Kanon 的 cos 团片要招人，名单我放在 名单.txt 了。'
              '帮我把招募页搭起来，搭好告诉我怎么打开看，还有管理密码是多少。')

def summarize(events):
  """从 dsh 的 jsonl 事件流里数出：回合、工具调用、错误、最终答复。"""
  turns=tools=0;errs=[];final='';cmds=[]
  for e in events:
    t=e.get('type')
    if t=='status' and e.get('phase')=='turn_end':turns+=1
    if t in ('tool_call','tool_use','tool'):tools+=1
    if t=='item' and e.get('item',{}).get('type') in ('tool_use','command'):
      tools+=1;c=(e['item'].get('input') or {});cmds.append(str(c.get('command') or c.get('cmd') or '')[:200])
    if t=='final':final=e.get('text') or ''
    if t=='error':errs.append(str(e.get('error'))[:200])
    if t=='status' and e.get('phase')=='turn_end':
      r=e.get('reason') or {}
      if r.get('kind')=='error':errs.append(str(r.get('error',{}).get('message'))[:300])
  return {'turns':turns,'tools':tools,'errors':errs,'final':final,'commands':[c for c in cmds if c]}

CAUSE={
 'env':(r'command not found|No such file or directory|ModuleNotFoundError|not installed|Playwright|Pillow|端口.*占用|Address already in use',),
 'code':(r'Traceback|Error in server|500 Internal',),
 'model':(r'cancel|give up|放弃',),
}
def guess_cause(s):
  """粗分类，给人看的提示，不是结论。"""
  blob=' '.join(s['errors'])+' '+s['final']
  for k,(pat,) in CAUSE.items():
    if re.search(pat,blob,re.I):return k
  return ''

def cmd_blind(a):
  if not os.path.exists(DSH):raise SystemExit('找不到 dsh：'+DSH+'\n设置 DSH_BIN 或装 DeepSeek Harness。')
  out=mkrun('blind')
  rep=Report('blind')
  repo=sandbox('blind')
  names=a.names if a.names and os.path.exists(a.names) else NAMES
  open(os.path.join(repo,'名单.txt'),'w',encoding='utf-8').write(names)
  if a.no_agents:
    for f in ('AGENTS.md',):
      try:os.remove(os.path.join(repo,f))
      except OSError:pass
  exp=parse_names(names)
  task=a.task or DEFAULT_TASK
  fp0=fingerprint(repo)
  jdump(os.path.join(out,'meta.json'),{'scenario':'blind','repo':repo,'task':task,'no_agents':a.no_agents,'expect':exp,'code':fp_id(fp0)})
  print(f'沙盒 {repo}\n任务：{task}\n期望：{exp[0]} 个团 / {exp[1]} 个席位 / {exp[2]} 个空缺\n',flush=True)
  cmd=[DSH,'headless','--json','--permission-mode','workspace-write','--approval-policy','never',task]
  t0=time.time();lines=[];stderr=''
  try:
    r=subprocess.run(cmd,cwd=repo,capture_output=True,text=True,timeout=a.timeout)
    lines=[l for l in r.stdout.splitlines() if l.strip()];stderr=r.stderr or ''
  except subprocess.TimeoutExpired as e:
    raw=e.stdout or ''
    if isinstance(raw,bytes):raw=raw.decode('utf-8','replace')
    lines=[l for l in raw.splitlines() if l.strip()]
    rep.step('AI 在超时内跑完',False,f'超过 {a.timeout}s')
  dur=round(time.time()-t0,1)
  if 'MISSING_CREDENTIAL' in stderr+'\n'.join(lines):
    shutil.rmtree(repo,ignore_errors=True);shutil.rmtree(out,ignore_errors=True)
    raise SystemExit('dsh 没有 API key。先 export DEEPSEEK_API_KEY=…（或在 Harness 的 Models 页配好），再跑一次。\n'
                     '  自检：'+DSH+' headless --json "回答一个字：好"')
  with open(os.path.join(out,'events.jsonl'),'w',encoding='utf-8') as f:f.write('\n'.join(lines))
  ev=[]
  for l in lines:
    try:ev.append(json.loads(l))
    except ValueError:pass
  s=summarize(ev)
  print(f'\nAI 用了 {s["turns"]} 个回合、{s["tools"]} 次工具调用，{dur}s\n',flush=True)
  open(os.path.join(out,'transcript.md'),'w',encoding='utf-8').write(
    f'# blind 跑（{now()}）\n\n- 任务：{task}\n- 回合：{s["turns"]}  工具：{s["tools"]}  耗时：{dur}s\n'
    f'- 错误：{s["errors"] or "无"}\n\n## 它跑过的命令\n\n```\n'+('\n'.join(s['commands'][:80]) or '（无）')+'\n```\n\n'
    f'## 最后答复\n\n{s["final"] or "（空）"}\n')
  rep.note(f"回合 {s['turns']}、工具 {s['tools']}、耗时 {dur}s、错误 {len(s['errors'])} 条")
  inst=find_instance(repo)
  port=free_port();base=f'http://127.0.0.1:{port}/'
  p=logf=None
  try:
    p,logf=serve(repo,port,logfile=os.path.join(out,'server.log'))
    assert_fingerprint(rep,repo,{'fp':fp0,'no_agents':a.no_agents})
    assert_site(rep,inst,base,exp,find_password(s['final']))
    assert_bind(rep,inst)
    assert_art(rep,inst,True)
    assert_poster(rep,inst,a.poster)
  except SystemExit as e:
    rep.step('AI 建完还能起服务',False,str(e)[:400])
  finally:
    if p:stop(p,logf)
    if not a.keep:shutil.rmtree(repo,ignore_errors=True)
    else:print('沙盒留在 '+repo,flush=True)
  rep.d['cause']=guess_cause(s) or rep.d['cause']
  rep.d['agent']={'turns':s['turns'],'tools':s['tools'],'errors':s['errors'][:5],'duration':dur,'final':s['final'][:600]}
  if rep.d['cause']:rep.note('粗判归因：'+{'env':'环境','code':'代码','model':'模型'}[rep.d['cause']]+'（要人工确认）')
  rep.save(out)

# ── sandbox / check：给并发会话（同时开多个 AI 对话）用 ──────────────────
def cmd_sandbox(a):
  """建干净沙盒、塞好名单，打印路径。之后让一个 AI 会话只在这条路径里干活。

  并发跑多个会话时给每个沙盒一个端口（写进 .env，server.py 认这个变量），
  否则它们会全去抢 5510——那是实验装置的问题，不是产品的问题。"""
  d=sandbox(a.label or 'swarm')
  text=open(a.names,encoding='utf-8').read() if a.names else NAMES
  open(os.path.join(d,'名单.txt'),'w',encoding='utf-8').write(text)
  if a.port:open(os.path.join(d,'.env'),'w',encoding='utf-8').write(f'CASTCALL_PORT={a.port}\n')
  if a.no_agents:
    try:os.remove(os.path.join(d,'AGENTS.md'))
    except OSError:pass
  jdump(os.path.join(d,'.lab.json'),{'created':now(),'expect':parse_names(text),'no_agents':a.no_agents,'port':a.port,
                                     'fp':fingerprint(d)})
  print(d)
  return True

def cmd_check(a):
  """对跑过的沙盒做外部断言。和 smoke / blind 用同一套检查，退出码 0 = 全过。"""
  repo=os.path.abspath(a.dir)
  if not os.path.isdir(repo):raise SystemExit('没有这个目录：'+repo)
  label=a.label or os.path.basename(repo.rstrip('/'))
  out=mkrun('check-'+label);rep=Report('check-'+label)
  names=NAMES
  for n in ('名单.txt','名单.csv'):
    p=os.path.join(repo,n)
    if os.path.exists(p):
      names=open(p,encoding='utf-8').read();break
  exp=parse_names(names)
  print(f'检查 {repo}\n期望 {exp[0]} 个团 / {exp[1]} 个席位 / {exp[2]} 个空缺\n',flush=True)
  inst=find_instance(repo)
  assert_fingerprint(rep,repo,jload(os.path.join(repo,'.lab.json'),{}))
  port=free_port();base=f'http://127.0.0.1:{port}/'
  p=logf=None
  try:
    p,logf=serve(repo,port,logfile=os.path.join(out,'server.log'))
    assert_site(rep,inst,base,exp,a.password)
    assert_bind(rep,inst)
    assert_art(rep,inst,not a.no_art)
    assert_poster(rep,inst,a.poster)
  except SystemExit as e:rep.step('还能起服务',False,str(e)[:500])
  finally:
    if p:stop(p,logf)
  jdump(os.path.join(out,'meta.json'),{'scenario':rep.d['scenario'],'repo':repo,'expect':exp})
  return rep.save(out)

# ── list ────────────────────────────────────────────────────────────────
def cmd_list(a):
  rows=[]
  for d in sorted(glob.glob(os.path.join(RUNS,'*'))):
    r=jload(os.path.join(d,'report.json'),{}) or {}
    rows.append((os.path.basename(d),r.get('ok'),r.get('duration'),r.get('cause'),(r.get('agent') or {}).get('turns')))
  if not rows:print('还没有跑过：python3 tools/lab.py smoke');return
  print(f"{'场景':34}{'结果':6}{'耗时':>8}{'回合':>5}  归因")
  for n,ok,dur,cause,turns in rows:
    tag='PASS' if ok else ('ERR' if ok is None else 'FAIL')
    print(f"{n:34}{tag:6}{(f'{dur}s' if dur else '-'):>8}{str(turns or '-'):>5}  {cause or ''}")
  done=[r for r in rows if r[1] is not None]
  if done:
    ok=sum(1 for r in done if r[1])
    print(f'\n完成 {len(done)} 次，通过 {ok} 次（{ok*100//len(done)}%）。ERR 是没跑完就中断的记录，不计入。')
  print('同一场景反复 FAIL 就打开它的 report.json，看哪一步先红。')

# ── main ────────────────────────────────────────────────────────────────
def main(argv):
  ap=argparse.ArgumentParser(description='从零部署的实验室')
  sub=ap.add_subparsers(dest='cmd',required=True)
  def common(p):
    p.add_argument('--names',help='自定义名单文件（默认内置一份 Kanon 小名单）')
    p.add_argument('--poster',action='store_true',help='要求生成一图流（需要 Pillow + Playwright）')
    p.add_argument('--keep',action='store_true',help='跑完保留沙盒')
    p.add_argument('--timeout',type=int,default=600)
  s=sub.add_parser('smoke',help='脚本扮演团长，从零建站并断言');common(s)
  s.add_argument('--via',choices=('cli','wizard'),default='cli',help='cli=init.py（快）；wizard=网页向导那条路')
  s.add_argument('--art',action='store_true',help='cli 模式下也自动配图（联网，慢）')
  s.set_defaults(func=cmd_smoke)
  s=sub.add_parser('blind',help='dsh 扮演不知情的 AI，看它能不能按文档走通');common(s)
  s.add_argument('--task',help='给 AI 的需求原文（默认是一句团长口吻的话）')
  s.add_argument('--no-agents',action='store_true',help='把 AGENTS.md 拿掉，只留 README')
  s.set_defaults(func=cmd_blind)
  s=sub.add_parser('sandbox',help='建一个干净沙盒，交给一个 AI 会话去部署（并发实验用）')
  s.add_argument('--label',help='标签，只影响临时目录名')
  s.add_argument('--names',help='名单文件（默认内置 Kanon 小名单）')
  s.add_argument('--port',type=int,help='写进沙盒的 .env，让这个站用指定端口（并发跑多个时必须给）')
  s.add_argument('--no-agents',action='store_true',help='拿掉 AGENTS.md')
  s.set_defaults(func=cmd_sandbox)
  s=sub.add_parser('check',help='对一个跑过的沙盒做外部断言')
  s.add_argument('dir',help='沙盒目录')
  s.add_argument('--label')
  s.add_argument('--password',help='管理密码；不给就跳过「能登录」那条')
  s.add_argument('--poster',action='store_true')
  s.add_argument('--no-art',action='store_true',help='这一版本来就没让它配图：配图覆盖率只记一笔，不算失败')
  s.set_defaults(func=cmd_check)
  s=sub.add_parser('list',help='历次结果和首次通过率');s.set_defaults(func=cmd_list)
  a=ap.parse_args(argv)
  if a.cmd=='list':return cmd_list(a)
  os.makedirs(RUNS,exist_ok=True)
  if getattr(a,'timeout',0)==600 and a.cmd=='blind':a.timeout=900
  return 0 if a.func(a) else 1
if __name__=='__main__':sys.exit(main(sys.argv[1:]))
