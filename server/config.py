"""Paths and site settings. Everything an instance owns lives under one directory (CASTCALL_INSTANCE, default ./instance):

  site.json      活动信息 / 报名 / 留言 / 安全设置（init.py 生成，手改也行）
  roster.json    名册（网页保存会改它，不要进 git）
  castcall.db    sqlite：报名、留言、名册变更队列
  auth.json      管理密码（PBKDF2）
  uploads/       封面 covers/、立绘 portraits/、map.json
  poster/        一图流产物
  backups/       每次保存前的名册快照
  logs/

site.json 只需写想改的字段，其余用 DEFAULTS。环境变量（或仓库根目录 / instance 里的 .env）可以覆盖
监听地址、端口和 Notion 设置，方便 systemd / docker 不改文件就换配置。"""
import copy,json,os
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB=os.path.join(ROOT,'web')
# 对外版本号，发版时改这一处（同时记进 CHANGELOG.md、打同名 tag）。
# /api/health 会带出去，线上出问题时先问这一行，能确认跑的是哪版。
VERSION='0.1.0-beta'
DEFAULTS={
  'mode':'auto',            # auto: 1 个团按单团显示，多于 1 个按多团；single / multi 强制
  'event':{
    'title':'cos 团建',
    'subtitle':'成员一览',
    'date':'',              # 页面上显示的日期文字，比如 2026-12-12
    'startAt':'',           # 倒计时开始的时间，带时区：2026-12-12T11:00:00+08:00；留空就不显示倒计时
    'endAt':'',             # 过了这个时间倒计时票根消失；留空 = startAt 之后 12 小时
    'location':'',
    'organizer':'',
    'contact':{'label':'','value':''},   # 缺人看板底部的联系方式，比如 {"label":"微信","value":"abc123"}
  },
  'signup':{
    'enabled':True,
    'opensAt':'',           # 留空 = 一直开放
    'closesAt':'',
    'contactLabel':'微信',   # 报名表第二个输入框的名字（微信 / QQ / 邮箱）
    'contactPattern':'',    # 可选，JS/Python 都能用的正则，比如 QQ 号 ^[1-9][0-9]{4,11}$
    'note':'提交后等审核，不会直接占上这个席位。',
    'fields':[],            # 额外要填的：身高 / 年龄 / 性别 / 样片…，见 server/fields.py 和 docs/config.md
  },
  'notice':{               # 招募须知：要求 / 不接受 / 补充 / 风险，见 server/notice.py 和 docs/config.md
    'enabled':False,
    'lead':'',             # 一句话定调
    'items':[],            # [{"kind":"must"/"deny"/"warn"/"info","text":"..."}]
  },
  'guestbook':{
    'enabled':True,
    'moderation':'post',    # post：先显示，后台可隐藏；pre：后台通过后才显示
  },
  'photos':{                # 成员（coser）上传自己的照片，显示在角色卡和详情里
    'enabled':False,
    'moderation':'pre',     # pre：后台通过后才显示；post：先显示，后台可撤下
  },
  'poster':{
    'enabled':True,
    'slug':'castcall',      # 导出图片的文件名前缀
    'hero':'',              # uploads/brand/ 下的一张大图，铺在海报标题和底部；留空用默认天空渐变
  },
  'brand':{
    'logo':'',              # uploads/ 下的图片文件名，显示在标题前面；留空不显示
    'accent':'',            # 主题色，比如 #e6b35a；留空用默认金色
    'favicon':'',           # uploads/brand/ 下的图标文件名；留空用内置图标
  },
  'server':{
    'host':'127.0.0.1',
    'port':5510,
    'trustProxyHeader':'',  # 前面有反向代理时，取客户端 IP 的请求头，比如 X-Forwarded-For / CF-Connecting-IP；直接暴露在公网时必须留空
    'sessionDays':7,
  },
  'limits':{                # 每个 IP 每 windowSec 秒最多几次
    'windowSec':600,'login':5,'signup':8,'guestbook':8,'photo':6,'sample':10,
  },
  'notion':{                # 只有列名映射放这里；token 和库 ID 放 .env（见 docs/notion.md）
    'syncEvery':20,         # 秒：拉审核结果、补推失败的报名和留言
    'rosterEvery':900,      # 秒：把名册改动推到 Notion
    'columns':{
      'roster':{'character':'角色','member':'成员','group':'团','order':'排序','status':'状态','id':'记录ID'},
      'signup':{'name':'CN','contact':'联系方式','group':'团','character':'角色','id':'记录ID','status':'状态','extra':'补充信息'},
      'guestbook':{'name':'CN','text':'内容','status':'状态','time':'时刻'},
    },
    'status':{'pending':'待审','approved':'已通过','rejected':'已拒绝','hidden':'已隐藏'},
  },
}
class Config:
  def __init__(s,instance):
    s.INSTANCE=os.path.abspath(instance)
    s.SITE=os.path.join(s.INSTANCE,'site.json');s.ROSTER=os.path.join(s.INSTANCE,'roster.json')
    s.DB=os.path.join(s.INSTANCE,'castcall.db');s.AUTH=os.path.join(s.INSTANCE,'auth.json')
    s.UPLOADS=os.path.join(s.INSTANCE,'uploads');s.MAP=os.path.join(s.UPLOADS,'map.json')
    s.POSTER=os.path.join(s.INSTANCE,'poster');s.BACKUPS=os.path.join(s.INSTANCE,'backups');s.LOGS=os.path.join(s.INSTANCE,'logs')
    s.env=load_env([os.path.join(ROOT,'.env'),os.path.join(s.INSTANCE,'.env')])
    s._site=None;s._mt=None
  def getenv(s,k,d=''):
    v=os.environ.get(k)
    return (v if v is not None else s.env.get(k,d)).strip()
  @property
  def site(s):
    """site.json merged over DEFAULTS. Re-read when the file changes, so edits apply without a restart."""
    try:mt=os.path.getmtime(s.SITE)
    except OSError:mt=None
    if s._site is None or mt!=s._mt:
      raw={}
      if mt is not None:
        with open(s.SITE,encoding='utf-8') as f:raw=json.load(f)
      s._site=merge(copy.deepcopy(DEFAULTS),raw);s._mt=mt
    return s._site
  def host(s):
    """托管平台（Docker、多数 PaaS、WorkBuddy 之类的在线应用）只给一个 PORT 环境变量，并要求监听 0.0.0.0。
    这时 site.json 里的 127.0.0.1 会让服务绑在回环上、外面访问不到，所以有 PORT 时默认放开；CASTCALL_HOST 显式给的值仍然优先。"""
    h=s.getenv('CASTCALL_HOST') or s.site['server']['host']
    if h in ('127.0.0.1','localhost','::1') and not s.getenv('CASTCALL_HOST') and os.environ.get('PORT'):return '0.0.0.0'
    return h
  def port(s):return int(s.getenv('CASTCALL_PORT') or os.environ.get('PORT') or s.site['server']['port'])
  def hosted(s):return bool(os.environ.get('PORT'))   # 平台给了 PORT = 跑在托管平台上，前面一定有一层代理
  def proxy_header(s):return s.getenv('CASTCALL_TRUST_PROXY') or s.site['server']['trustProxyHeader']
  def notion_token(s):return s.getenv('NOTION_TOKEN')
  def notion_db(s,kind):return s.getenv('NOTION_'+kind.upper()+'_DB')
  def notion_on(s,kind=None):
    if not s.notion_token():return False
    return bool(s.notion_db(kind)) if kind else any(s.notion_db(k) for k in ('roster','signup','guestbook'))
  def public(s):
    """The part of site.json the browser may see (/site.js). Never put secrets in site.json."""
    t=s.site;return {'mode':t['mode'],'event':t['event'],'brand':t['brand'],
      'signup':{**{k:t['signup'][k] for k in ('enabled','opensAt','closesAt','contactLabel','contactPattern','note')},'fields':__import__('fields').normalize(t['signup'].get('fields'))},
      'notice':{'enabled':bool(t['notice']['enabled']),'lead':t['notice']['lead'],'items':__import__('notice').normalize(t['notice'].get('items'))},
      'guestbook':{'enabled':t['guestbook']['enabled'],'moderation':t['guestbook']['moderation']},
      'poster':{'enabled':t['poster']['enabled'],'slug':t['poster']['slug']},
      'photos':{'enabled':bool(t['photos']['enabled']),'moderation':t['photos']['moderation']}}
def merge(base,over):
  for k,v in (over or {}).items():
    if isinstance(v,dict) and isinstance(base.get(k),dict):merge(base[k],v)
    else:base[k]=v
  return base
def load_env(paths):
  """Minimal .env reader: KEY=value lines, # comments, optional quotes. Process env always wins (see getenv)."""
  out={}
  for p in paths:
    try:lines=open(p,encoding='utf-8').read().splitlines()
    except OSError:continue
    for ln in lines:
      ln=ln.strip()
      if not ln or ln.startswith('#') or '=' not in ln:continue
      k,v=ln.split('=',1);k=k.strip().removeprefix('export ').strip();v=v.strip()
      if len(v)>=2 and v[0]==v[-1] and v[0] in '"\'':v=v[1:-1]
      out[k]=v
  return out
C=Config(os.environ.get('CASTCALL_INSTANCE') or os.path.join(ROOT,'instance'))
def use(instance):
  """Point the whole process at another instance directory (tests, scripts)."""
  global C
  C=Config(instance);return C
