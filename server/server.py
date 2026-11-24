#!/usr/bin/env python3
"""castcall server: static files + JSON API, stdlib only.

  python3 init.py              # 第一次：生成 instance/（活动信息、管理密码、示例名册）
  python3 server/server.py     # 启动，默认 http://127.0.0.1:5510

公开接口：GET /api/data /api/guestbook /api/health · POST /api/cast-signup /api/guestbook
后台接口（登录后）：PUT /api/data · /api/admin/{signups,guestbook,upload,portrait,poster}"""
import hashlib,hmac,html,json,os,re,secrets,subprocess,sys,threading,time,urllib.parse
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from http.cookies import SimpleCookie
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import config,fields,notice,roster,review,setup,shots,store
from config import ROOT,WEB,VERSION
LOCK=threading.Lock();SESS={};HITS={}
SETUP={'token':None,'instance':None,'prefill':None}   # set while the instance is not initialized: the first-run wizard needs this token
# prefill：server.py --prefill 名单.txt 带进来的名单 / 活动名，向导打开时预填（同样要口令才读得到）
log=roster.log

def health_payload(setup_mode=False):
  """两个出口（还没建站 / 已经建站）都从这里取。以前各写各的，加了版本号就只加了一半：
  刚 clone 下来那一刻回来的恰恰是没版本的那个，而这正是最需要确认「跑的是哪版」的时候。"""
  d={'ok':True,'version':VERSION}
  if setup_mode:d['setup']=True
  return d

# ── auth ──────────────────────────────────────────────────────────────────
def check_pw(p):
  a=jload(config.C.AUTH,None)
  if not a:return False
  h=hashlib.pbkdf2_hmac('sha256',p.encode(),bytes.fromhex(a['salt']),int(a.get('iter',200000))).hex()
  return hmac.compare_digest(h,a['hash'])
from setup import set_password   # re-exported: tests and older scripts call server.set_password

# ── uploads (covers, portraits, logo) ─────────────────────────────────────
UP_DIRS=('covers','portraits','brand','photos','shots','mshots')
def jload(p,d):
  try:
    with open(p,encoding='utf-8') as f:return json.load(f)
  except Exception:return d
def readf(p):
  with open(p,encoding='utf-8',errors='replace') as f:return f.read()
def imgv():
  """{'covers/x.jpg':[mtime,0]} for every uploaded image: lets the page cache them forever under ?v=<mtime>.
  (Second slot is keyroster's AVIF variant; uploads are served as-is, so it is always 0.)"""
  V={}
  for d in UP_DIRS:
    try:es=list(os.scandir(os.path.join(config.C.UPLOADS,d)))
    except OSError:continue
    for e in es:
      if e.name.lower().endswith(('.jpg','.jpeg','.png','.webp','.gif','.svg')):V[d+'/'+e.name]=[int(e.stat().st_mtime),0]
  return V
def charsjs():
  m=jload(config.C.MAP,{});I=imgv()
  m2={k:v+'?v='+str(I[v][0]) if v in I else v for k,v in m.items()}
  return 'window.CHARS='+json.dumps(m2,ensure_ascii=False)+';window.CHARPOS={};window.IMGV='+json.dumps(I,ensure_ascii=False,separators=(',',':'))+';window.PHOTOS='+json.dumps(photos_shown(I),ensure_ascii=False)+';window.MSHOTS='+json.dumps(mshots_shown(I),ensure_ascii=False)+';'
def photos_shown(I=None):
  """{seat id: 'photos/x.jpg?v=..'}：开关开着、照片已通过、而且席位上还是上传的那个人（换人后旧照片不挂到新人头上）。"""
  if not config.C.site['photos']['enabled']:return {}
  I=I or imgv();cur={m.get('id'):(m.get('member') or '').strip() for g in roster.load()['groups'] for m in g['members']}
  out={}
  for seat,(member,f) in store.shown_photos().items():
    p='photos/'+f
    if cur.get(seat)==member and p in I:out[seat]=p+'?v='+str(I[p][0])
  return out
def mshots_shown(I=None):
  """{seat id: [{'f':'mshots/x.jpg?v=..','c':图注}]}：跟本人照片同一个开关；只给席位上还是上传者本人的（换人后不挂到新人头上）。"""
  if not config.C.site['photos']['enabled']:return {}
  I=I or imgv();cur={m.get('id'):(m.get('member') or '').strip() for g in roster.load()['groups'] for m in g['members']}
  out={}
  for seat,lst in store.shown_mshots().items():
    for member,f,cap in lst:
      p='mshots/'+f
      if cur.get(seat)==member and p in I:out.setdefault(seat,[]).append({'f':p+'?v='+str(I[p][0]),'c':cap})
  return out
def sniff(b):
  if b[:3]==b'\xff\xd8\xff':return 'jpg'
  if b[:8]==b'\x89PNG\r\n\x1a\n':return 'png'
  if b[:4]==b'RIFF' and b[8:12]==b'WEBP':return 'webp'
  if b[:6] in (b'GIF87a',b'GIF89a'):return 'gif'
  return None
def save_upload(kind,data):
  ext=sniff(data)
  if not ext:raise ValueError('只支持 jpg / png / webp / gif')
  d=os.path.join(config.C.UPLOADS,kind);os.makedirs(d,exist_ok=True)
  name=hashlib.sha1(data).hexdigest()[:12]+'.'+ext;p=os.path.join(d,name)
  if not os.path.exists(p):
    with open(p+'.tmp','wb') as f:f.write(data)
    os.replace(p+'.tmp',p)
  return name
def set_portrait(group,character,path):
  m=jload(config.C.MAP,{});k=f'{group}|{character}'
  if path:m[k]=path
  else:m.pop(k,None)
  os.makedirs(config.C.UPLOADS,exist_ok=True);tmp=config.C.MAP+'.tmp'
  with open(tmp,'w',encoding='utf-8') as f:json.dump(m,f,ensure_ascii=False,indent=1)
  os.replace(tmp,config.C.MAP)

# 站点素材：后台「站点素材」面板换的三张图，文件放 uploads/brand/，文件名写回 site.json（按 mtime 热加载，不用重启）
BRAND_SLOTS={'logo':('brand','logo'),'favicon':('brand','favicon'),'hero':('poster','hero')}
def brand_state():
  out={}
  for k,(sec,key) in BRAND_SLOTS.items():
    f=config.C.site[sec].get(key) or '';fp=os.path.join(config.C.UPLOADS,'brand',f)
    ok=bool(f) and re.fullmatch(r'[\w.-]+',f) and os.path.isfile(fp)
    out[k]={'file':f,'url':f'/brand/{f}?v={int(os.path.getmtime(fp))}'} if ok else {'file':'','url':''}
  return out
def set_brand(slot,name):site_set(*BRAND_SLOTS[slot],name)   # name '' = back to the default
def site_set(sec,key,val):
  """Write one field into site.json (the raw file, not the merged view)."""
  j=jload(config.C.SITE,{})
  j.setdefault(sec,{})[key]=val;tmp=config.C.SITE+'.tmp'
  with open(tmp,'w',encoding='utf-8') as f:json.dump(j,f,ensure_ascii=False,indent=1)
  os.replace(tmp,config.C.SITE)

# ── page rendering ────────────────────────────────────────────────────────
def etag(b):return '"'+hashlib.sha1(b).hexdigest()[:16]+'"'
def mode(d=None):
  m=config.C.site.get('mode') or 'auto'
  if m in ('single','multi'):return m
  # 工作组（摄影 / 后勤 / 妆娘…）不是「另一个团」：一部作品 + 若干 crew 组仍然是单团。
  try:gs=(d or roster.load())['groups']
  except Exception:gs=[]
  n=sum(1 for g in gs if (g.get('kind') or 'cast')!='crew')
  return 'single' if n==1 else 'multi'
def poster_ready():return os.path.isfile(os.path.join(config.C.POSTER,'master.html'))
def sitejs():
  p=config.C.public();d=roster.load();p['mode']=mode(d);p['signupState']=review.window_state()
  p['posterReady']=poster_ready() and p['poster']['enabled']
  return 'window.SITE='+json.dumps(p,ensure_ascii=False)+';'
def gen_js(p):
  if p=='/data.js':return ('window.ROSTER='+json.dumps(roster.load(),ensure_ascii=False)+';').encode()
  if p=='/site.js':return sitejs().encode()
  return charsjs().encode()
GEN=('/data.js','/chars.js','/site.js')
def preload(d,n=4):
  """<link rel=preload> for the first covers: they are only referenced from JS-built markup, so the browser finds them late."""
  I=imgv();o=''
  for g in [g for g in d['groups'] if g.get('cover')][:n]:
    k='covers/'+g['cover'];v=I.get(k)
    if v:o+=f'<link rel=preload as=image href="{k}?v={v[0]}" fetchpriority=high>'
  return o
def index_html():
  C=config.C;s=C.site;e=s['event'];d=roster.load();E=lambda x:html.escape(str(x or ''),quote=True)
  h=readf(os.path.join(WEB,'index.html'))
  logo=s['brand'].get('logo') or ''
  logo_tag=f'<img class=brandlogo src="/brand/{E(logo)}" alt="">' if logo and re.fullmatch(r'[\w.-]+',logo) and os.path.isfile(os.path.join(C.UPLOADS,'brand',logo)) else ''
  accent=s['brand'].get('accent') or ''
  style=f'<style>:root{{--gold-2:{accent}}}</style>' if re.fullmatch(r'#[0-9a-fA-F]{6}',accent) else ''
  poster=f'<a class="poster-mini go" id=posterlink-hdr href=/poster/>一图流</a>' if s['poster']['enabled'] and poster_ready() else ''
  date=f'<span class=di></span><span class=dd>{E(e.get("date"))}</span>' if e.get('date') else ''
  loc=f'<span class=loc><span class=li></span>{E(e.get("location"))}</span>' if e.get('location') else ''
  fav=s['brand'].get('favicon') or ''
  # apple-touch-icon 不认 SVG：只在团长自己传了图标时给，否则 iOS「添加到主屏」还是拿网页截图凑
  apple=f'<link rel=apple-touch-icon href="/brand/{E(fav)}">' if fav and re.fullmatch(r'[\w.-]+',fav) else ''
  rep={'{{title}}':E(e.get('title')),'{{subtitle}}':E(e.get('subtitle')),'{{logo}}':logo_tag,'{{date}}':date,'{{loc}}':loc,
       '{{location}}':E(e.get('location')),'{{poster}}':poster,'{{mode}}':mode(d),'{{head}}':style,'{{appleicon}}':apple,
       '{{favicon}}':'/brand/'+E(fav) if fav else '/favicon.svg'}
  for k,v in rep.items():h=h.replace(k,v)
  if not date and not loc:h=h.replace('<span class=dd>· <b id=tot>','<span class=dd><b id=tot>')   # 没日期没地点时，人数前面不要孤零零一个「·」
  if not s['guestbook']['enabled']:h=re.sub(r'<section id=guestbook.*?</section>','',h,flags=re.S)
  G={p:gen_js(p) for p in GEN}
  def v(m):
    n=m.group(2);f=os.path.join(WEB,n)
    t=etag(G['/'+n]).strip('"') if '/'+n in G else int(os.path.getmtime(f)) if os.path.exists(f) else int(time.time())
    return f'{m.group(1)}{n}?v={t}'
  h=re.sub(r'((?:href|src)=)([\w.-]+\.(?:css|js))(?=[\s>])',v,h)
  return h.replace('<link rel=stylesheet',preload(d)+'<link rel=stylesheet',1).encode()

# ── poster ────────────────────────────────────────────────────────────────
POSTER={'proc':None,'rc':None,'at':0.0,'ok':None}
def poster_python():
  """CASTCALL_POSTER_PYTHON，没设就用仓库里按 docs/poster.md 建的 .venv-poster，再没有就用当前 Python。"""
  v=os.path.join(ROOT,'.venv-poster','Scripts' if os.name=='nt' else 'bin','python.exe' if os.name=='nt' else 'python')
  return config.C.getenv('CASTCALL_POSTER_PYTHON') or (v if os.path.isfile(v) else sys.executable)
def poster_available():
  """Cached: can the poster interpreter import Pillow and Playwright? (They are optional, see requirements-poster.txt.)"""
  if POSTER['ok'] is None:
    try:POSTER['ok']=subprocess.run([poster_python(),'-c','import PIL,playwright'],capture_output=True,timeout=20).returncode==0
    except Exception:POSTER['ok']=False
  return POSTER['ok']
def poster_build():
  p=POSTER['proc']
  if p and p.poll() is None:return False
  os.makedirs(config.C.LOGS,exist_ok=True)
  out=open(os.path.join(config.C.LOGS,'poster.log'),'w',encoding='utf-8')
  args,env=poster_cmd()
  with out:POSTER.update(proc=subprocess.Popen(args,stdout=out,stderr=subprocess.STDOUT,start_new_session=True,env=env),at=time.time(),rc=None)
  return True
def poster_cmd():
  """(argv, env) for poster/build.py on this instance. Shared with firstrun.py (init.py runs it in the foreground)."""
  args=[poster_python(),os.path.join(ROOT,'poster','build.py'),'--instance',config.C.INSTANCE]
  # portrait 是手机网页那版（1200 宽、2 列），漏掉它 /poster/ 在竖屏上只能退回横条
  args+=['master','social','portrait'] if mode()=='single' else ['master','wide','portrait']
  env=dict(os.environ,CASTCALL_INSTANCE=config.C.INSTANCE)
  if config.C.getenv('CASTCALL_CHROME'):env['CASTCALL_CHROME']=config.C.getenv('CASTCALL_CHROME')   # .env values are not in os.environ
  return args,env
def poster_sources():
  """改动会进一图流的文件：名册（含团名 / 颜色 / 封面）、站点（活动信息、品牌、hero）、立绘映射。
  看着像是少扫了 uploads/，但换封面写 roster.json、换立绘写 map.json、换 logo/hero 写 site.json，
  这三个就够了；扫整个目录会把「传了一张没人用的图」也算成过期。"""
  return (config.C.ROSTER,config.C.SITE,config.C.MAP)
def poster_stale():
  """一图流比名册旧：名册改过了还没重新生成。没生成过不算过期——那是 ready 的事，不是 stale。"""
  f=os.path.join(config.C.POSTER,'master.html')
  if not os.path.isfile(f):return False
  t=os.path.getmtime(f)
  return any(os.path.isfile(p) and os.path.getmtime(p)>t for p in poster_sources())
def poster_reason(tail):
  """poster.log 的结尾 → 团长看得懂的一句话（原因 + 怎么办）。认不出来就给最后一行报错原文。"""
  if not tail:return ''
  if "Executable doesn't exist" in tail or 'playwright install' in tail:
    return '服务器上缺一图流用的浏览器（Playwright 升级后要重新下载）。在服务器上运行：.venv-poster/bin/playwright install chromium（国内下不动就在前面加 PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.npmmirror.com/binaries/playwright ），装好后再点一次。'
  if 'No module named' in tail:
    m=re.search(r"No module named '([\w.]+)'",tail)
    return f'服务器上缺 Python 依赖{(" "+m.group(1)) if m else ""}：运行 pip install -r requirements-poster.txt 后再点一次。'
  if 'Timeout' in tail or 'timed out' in tail:return '生成超时了，多半是图片太多或机器太慢。稍后再点一次试试。'
  if 'No space left' in tail:return '服务器磁盘满了，清理一下再试。'
  ln=[x.strip() for x in tail.strip().splitlines() if x.strip() and not x.strip().startswith(('File ','^','╔','║','╚'))]
  return ('出错了：'+ln[-1][:160]) if ln else ''
def poster_status():
  p=POSTER['proc'];run=bool(p and p.poll() is None)
  if p and not run:POSTER['rc']=p.returncode
  try:tail=readf(os.path.join(config.C.LOGS,'poster.log'))[-1500:]
  except OSError:tail=''
  return {'available':poster_available(),'running':run,'rc':POSTER['rc'],'startedAt':POSTER['at'],'ready':poster_ready(),
          'stale':poster_stale(),'log':tail,'reason':poster_reason(tail) if POSTER['rc'] not in (None,0) else ''}
POSTER_BACK=(
'<div class="kr-poster-chrome" role="navigation" aria-label="海报工具">'
'<a class="kr-poster-back" href="/">返回名单</a>'
'<a class="kr-poster-export" id="kr-poster-export" href="/poster/master.jpg" download="poster-master.jpg">导出图片</a>'
'</div>'
'<style>'
'.kr-poster-chrome{position:fixed;z-index:9999;top:12px;left:12px;display:flex;flex-direction:column;align-items:stretch;gap:8px;transform-origin:top left;zoom:normal}'
'.kr-poster-chrome a{display:inline-flex;align-items:center;justify-content:center;box-sizing:border-box;width:112px;height:40px;padding:0;'
'border:2px solid #1d2a3a;border-radius:999px;background:#fffef8;color:#1d2a3a;font:800 13px/1 system-ui,sans-serif;letter-spacing:.04em;text-decoration:none;'
'box-shadow:2px 2px 0 #1d2a3a;opacity:.96;white-space:nowrap;flex-shrink:0}'
'.kr-poster-chrome a.kr-poster-export{background:#1d2a3a;color:#fffef8}'
'.kr-poster-chrome a:active{box-shadow:1px 1px 0 #1d2a3a}'
'</style>'
'<script>(function(){'
'var chrome=document.querySelector(".kr-poster-chrome");if(!chrome)return;'
'function hoist(){var b=document.body;if(!b)return;var nodes=[chrome],sib=chrome.nextElementSibling,taken=0;'
'while(sib&&taken<2&&(sib.tagName==="STYLE"||(sib.tagName==="SCRIPT"&&sib.id!=="kr-poster-fit"))){nodes.push(sib);taken++;sib=sib.nextElementSibling;}'
'var scale=document.getElementById("kr-poster-scale"),clip=document.getElementById("kr-poster-clip");'
'var trapped=(scale&&scale.contains(chrome))||(clip&&clip.contains(chrome));if(!trapped&&b.firstElementChild===chrome)return;'
'var ref=b.firstChild;nodes.forEach(function(n){b.insertBefore(n,ref);ref=n.nextSibling;});}'
'function place(){hoist();var vv=window.visualViewport;var s=(vv&&vv.scale)||1;if(!(s>0)||!isFinite(s))s=1;'
'var ox=(vv&&vv.offsetLeft)||0,oy=(vv&&vv.offsetTop)||0;'
'chrome.style.position="fixed";chrome.style.zIndex="9999";chrome.style.transformOrigin="top left";chrome.style.transform="scale("+(1/s)+")";'
'chrome.style.left=(ox+12)+"px";chrome.style.top=(oy+12)+"px";}'
# 导出跟着当前页面走：看的是哪一版，下的就是哪一版。
# 以前只认 wide（其余一律 master.jpg），于是竖版页面点「导出图片」拿到的还是 2400×1255 的横条——
# 团长看着满屏的竖版，下载下来却是同一张老横图，只能得出「改了没用」这个结论。
'var ex=document.getElementById("kr-poster-export"),path=location.pathname;'
'var slug=document.documentElement.dataset.slug||"poster";'
'var n=/\\/poster\\/wide/i.test(path)?"wide.jpg":(/\\/poster\\/portrait/i.test(path)?"portrait.jpg":"master.jpg"),fname=slug+"-"+n;'
# ?v= 用文件的 mtime 而不是 Date.now()：同一个 mtime 才能命中 end_headers 里那条 immutable。
# 名册改了 -> 重新生成 -> mtime 变了 -> URL 变了，不会拿到旧图；没改 -> 重复导出直接走缓存。
'if(ex){var V=window.POSTER_V||{};ex.href="/poster/"+n+"?v="+(V[n.split(".")[0]]||0);ex.setAttribute("download",fname);'
'ex.addEventListener("click",function(e){e.preventDefault();fetch(ex.href).then(function(r){if(!r.ok)throw 0;return r.blob()})'
'.then(function(blob){var a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download=fname;document.body.appendChild(a);a.click();a.remove();'
'setTimeout(function(){URL.revokeObjectURL(a.href)},1500)}).catch(function(){location.href=ex.href})});}'
'place();if(window.visualViewport){visualViewport.addEventListener("resize",place);visualViewport.addEventListener("scroll",place)}'
'addEventListener("resize",place);addEventListener("scroll",place,{passive:true});addEventListener("load",place);'
'})();</script>'
)
def poster_versions():
  """{master: mtime, wide: mtime, social: mtime, portrait: mtime}：导出链接的 ?v= 用图自己的 mtime。
  同一版重复导出命中 immutable 那条缓存；名册改了重新生成、mtime 一变 URL 就变，不会给旧图。"""
  out={}
  for n in ('master','wide','social','portrait'):
    f=os.path.join(config.C.POSTER,n+'.jpg')
    if os.path.isfile(f):out[n]=int(os.path.getmtime(f))
  return out
def poster_page(name):
  f=os.path.join(config.C.POSTER,name)
  if not os.path.isfile(f):return None
  h=readf(f)
  slug=re.sub(r'[^\w-]','',config.C.site['poster'].get('slug') or 'poster') or 'poster'
  h=re.sub(r'<html([^>]*)>',lambda m:f'<html{m.group(1)} data-slug="{slug}">',h,count=1)
  back=POSTER_BACK.replace('<script>(function(){','<script>window.POSTER_V='+json.dumps(poster_versions())+';</script><script>(function(){',1)
  m=re.search(r'<body[^>]*>',h,re.I)
  h=h[:m.end()]+back+h[m.end():] if m else h+back
  return h.encode()
def poster_chooser():
  """按屏幕形状挑版式：竖屏（高比宽大）走 portrait，宽屏走 wide，其余 master。

  以前只有 master / wide 两个选择，而且「单团」直接写死 master：2400×1255 的横条
  在竖屏里按宽缩放只剩 42% 屏高，网页再竖直居中，卡片就被挤到屏幕下半截去了。
  portrait.html 是 1200 宽的竖版（一个团占满一行、卡片 2 列），高度能铺满一屏。
  旧实例还没重新生成时文件不存在，回落到 master —— 不能让 /poster/ 直接 404。"""
  have={n:os.path.isfile(os.path.join(config.C.POSTER,n+'.html')) for n in ('master','wide','portrait')}
  js=("location.replace('/poster/'+(function(){var w=innerWidth,h=innerHeight;"
      "var P=%s,W=%s;"%(str(have['portrait']).lower(),str(have['wide']).lower())+
      "if(P&&h>w*1.05)return 'portrait';"
      "if(W&&w>=900)return 'wide';return 'master';})()+'.html'+location.search+location.hash)")
  return f'<!doctype html><html lang=zh><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>一图流</title><link rel=icon href="/favicon.svg" type="image/svg+xml"><script>{js}</script><p style="font:600 14px/1.5 system-ui,sans-serif;margin:24px"><a href="/poster/master.html">一图流</a> · <a href="/">返回名单</a></p>'.encode()

# ── HTTP ──────────────────────────────────────────────────────────────────
def favicon_svg():
  """浏览器标签页图标：拿团名首字现画一个，底色取站点的主题色。

  以前这里是一段写死的图形（一个长得像 R 的占位）：团名改成「Kanon 团片」，
  标签上还是那块黄底加一个陌生字母，团长只会当成浏览器的默认图标。
  现在不传图也有「自己的」图标；团长在「站点素材」里传了图标就用那张（见 index_html）。"""
  s=config.C.site;ev=s.get('event') or {};br=s.get('brand') or {}
  ch=''.join(str(ev.get('title') or ev.get('subtitle') or '团').split())[:1] or '团'
  fill=str(br.get('accent') or '')
  if not re.fullmatch(r'#[0-9a-fA-F]{6}',fill):       # 没设主题色就跟第一个团的颜色，再没有才用金色
    fill=''
    try:groups=roster.load().get('groups') or []
    except (OSError,ValueError):groups=[]   # 向导还没建站：roster.json 不存在，图标照样要能画
    for g in groups:
      c=str(g.get('color') or '')
      if re.fullmatch(r'#[0-9a-fA-F]{6}',c):fill=c;break
    fill=fill or '#e6b35a'
  r,g,b=(int(fill[i:i+2],16) for i in (1,3,5))
  ink='#2b2115' if 0.299*r+0.587*g+0.114*b>=150 else '#fff8ec'   # 亮底配深字，暗底配米白
  # 拉丁字母只有半高（cap height ≈ 0.72em），可以再大一号；汉字占满 em 框，同样的字号就顶出去了。
  # 基线按各自的视觉中心反推，否则字会往上飘（汉字尤其明显）。
  fs,dy=(24.5,.36) if ord(ch[0])<0x2000 else (20.4,.375)
  return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
          f'<rect width="32" height="32" rx="7.5" fill="{fill}"/>'
          f'<text x="16" y="{16+fs*dy:.1f}" text-anchor="middle" font-size="{fs}" font-weight="700" '
          f"font-family=\"system-ui,'PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif\" "
          f'fill="{ink}">{html.escape(ch)}</text></svg>').encode()
class H(SimpleHTTPRequestHandler):
  protocol_version='HTTP/1.1';timeout=60
  def __init__(s,*a,**k):super().__init__(*a,directory=WEB,**k)
  def log_message(s,f,*a):pass
  def translate_path(s,path):
    """/covers/ /portraits/ /brand/ come from instance/uploads, /poster/ from instance/poster, the rest from web/."""
    p=urllib.parse.unquote(path.split('?',1)[0].split('#',1)[0])
    for pre,base in (('/covers/',os.path.join(config.C.UPLOADS,'covers')),('/portraits/',os.path.join(config.C.UPLOADS,'portraits')),
                     ('/brand/',os.path.join(config.C.UPLOADS,'brand')),('/photos/',os.path.join(config.C.UPLOADS,'photos')),('/samples/',os.path.join(config.C.UPLOADS,'samples')),('/shots/',os.path.join(config.C.UPLOADS,'shots')),('/mshots/',os.path.join(config.C.UPLOADS,'mshots')),('/poster/',config.C.POSTER)):
      if p.startswith(pre):
        # 成员照片只公开正在显示的那张；待审 / 被拒的只有登录后（审核时）能看
        if pre=='/samples/' and not s.tok():return os.path.join(base,'__nope__')   # 报名样片：只给后台看
        if pre=='/photos/' and not s.tok() and 'photos/'+p[len(pre):] not in {v.split('?')[0] for v in photos_shown().values()}:return os.path.join(base,'__nope__')
        if pre=='/mshots/' and not s.tok() and 'mshots/'+p[len(pre):] not in {x['f'].split('?')[0] for v in mshots_shown().values() for x in v}:return os.path.join(base,'__nope__')
        rel=os.path.normpath(p[len(pre):]).lstrip(os.sep)
        if rel.startswith('..'):return os.path.join(base,'__nope__')
        return os.path.join(base,rel)
    return super().translate_path(path)
  def end_headers(s):
    p,_,q=s.path.partition('?')
    if s.path.startswith('/api') or p.endswith(('.html','/')):
      s.send_header('Cache-Control','no-store')
    elif p.startswith('/poster/cache/'):
      # 立绘裁切图的名字就是内容 hash（build.py 的 bust()），换图必换名：可以永远缓存。
      # 以前这里跟导出的 master.jpg 一起 no-store，团长每次翻海报都在重下几十张缩略图。
      s.send_header('Cache-Control','public, max-age=31536000, immutable')
    elif p in GEN:s.send_header('Cache-Control',getattr(s,'_cc','no-cache'))
    elif p.startswith('/favicon') or p.endswith(('.css','.js','.jpg','.jpeg','.png','.svg','.webp','.gif')):
      # ?v= 与文件 mtime 一致 -> 永久缓存（改了文件 v 就变）；否则 revalidate。
      # 导出的 master.jpg / wide.jpg 也走这条：POSTER_BACK 的下载链接带 ?v=<时间戳>，
      # 同一版重复导出能命中缓存，名册改了 mtime 变、v 对不上就重新下。
      v=re.search(r'(?:^|&)v=(\d+)',q);f=s.translate_path(p)
      ok=v and os.path.isfile(f) and int(os.path.getmtime(f))==int(v.group(1))
      s.send_header('Cache-Control','public, max-age=31536000, immutable' if ok else 'no-cache')
    s.send_header('X-Content-Type-Options','nosniff')
    super().end_headers()
  def ip(s):
    """Client IP for rate limits. A forwarded header is only believed when site.json names it (server.trustProxyHeader):
    anyone can send CF-Connecting-IP, so trusting it by default let a script dodge every limit, login included."""
    h=config.C.proxy_header()
    if h:
      v=(s.headers.get(h) or '').split(',')[-1].strip()
      if v:return v
    return s.client_address[0]
  def limited(s,kind):
    L=config.C.site['limits'];win=float(L.get('windowSec') or 600);cap=int(L.get(kind) or 8)
    ip=s.ip();now=time.time();hits=[t for t in HITS.get((kind,ip),[]) if now-t<win];HITS[(kind,ip)]=hits
    return hits,cap,now
  def tok(s):
    c=SimpleCookie(s.headers.get('Cookie',''));t=c['cc_s'].value if 'cc_s' in c else ''
    e=SESS.get(t);return t if e and e>time.time() else None
  def send(s,code,b,ctype,extra=()):
    s.send_response(code);s.send_header('Content-Type',ctype);s.send_header('Content-Length',len(b))
    for k,v in extra:s.send_header(k,v)
    s.end_headers()
    if s.command!='HEAD':s.wfile.write(b)
  def js(s,code,obj,cookie=None):
    s.send(code,json.dumps(obj,ensure_ascii=False).encode(),'application/json; charset=utf-8',[('Set-Cookie',cookie)] if cookie else [])
  def body(s,cap=2_000_000):
    n=int(s.headers.get('Content-Length',0) or 0)
    if n>=cap:s.close_connection=True;raise AssertionError('too large')
    return json.loads(s.rfile.read(n) or b'{}')
  def small(s,lo,hi):
    """Read a small public JSON body, or None after answering 400 (bad size / not JSON)."""
    try:n=int(s.headers.get('Content-Length',0) or 0)
    except ValueError:n=-1
    if n<lo or n>hi:s.close_connection=True;s.js(400,{'error':'提交格式不对'});return None
    try:return json.loads(s.rfile.read(n))
    except Exception:s.js(400,{'error':'提交格式不对'});return None
  def do_HEAD(s):return s.do_GET()
  def do_GET(s):
    p=s.path.split('?')[0]
    if SETUP['token'] and s.setup_get(p):return
    if p in ('/','/index.html'):return s.send(200,index_html(),'text/html; charset=utf-8')
    if p in GEN:
      # ?v=<content hash> from index.html: immutable when it still matches, else revalidate via ETag
      b=gen_js(p);e=etag(b);s._cc='public, max-age=31536000, immutable' if s.path.endswith('?v='+e.strip('"')) else 'no-cache'
      if e in (s.headers.get('If-None-Match') or ''):s.send_response(304);s.send_header('ETag',e);s.send_header('Content-Length','0');return s.end_headers()
      return s.send(200,b,'application/javascript; charset=utf-8',[('ETag',e)])
    # 按团名现画，改完团名不用重新构建；.ico 也回同一份（导出的一图流没有 <link rel=icon>，会来问它）。
    # 团长传过图标就用那张：一图流页面的链接写死在这里，不然换了图标只有首页变。
    if p in ('/favicon.svg','/favicon.ico'):
      f=str((config.C.site.get('brand') or {}).get('favicon') or '')
      fp=os.path.join(config.C.UPLOADS,'brand',f) if re.fullmatch(r'[\w.-]+',f) else ''
      if fp and os.path.isfile(fp):
        ct={'png':'image/png','jpg':'image/jpeg','jpeg':'image/jpeg','webp':'image/webp','gif':'image/gif','svg':'image/svg+xml'}
        with open(fp,'rb') as fh:raw=fh.read()
        return s.send(200,raw,ct.get(fp.rsplit('.',1)[-1].lower(),'application/octet-stream'))
      return s.send(200,favicon_svg(),'image/svg+xml')
    if p=='/api/guestbook':
      if not config.C.site['guestbook']['enabled']:return s.js(404,{'error':'留言区没开'})
      try:return s.js(200,{'items':review.public_notes()})
      except Exception as e:log('guestbook read err',repr(e));return s.js(500,{'error':'暂时读不到留言'})
    if p=='/api/data':return s.js(200,roster.load())
    if p=='/api/me':return s.js(200,{'auth':bool(s.tok())})
    if p=='/api/health':return s.js(200,health_payload())
    if p.startswith('/api/admin/'):return s.admin_get(p)
    if p in ('/poster','/poster/'):return s.send(200,poster_chooser(),'text/html; charset=utf-8')
    for n in ('master','portrait','wide'):
      if p in (f'/poster/{n}',f'/poster/{n}.html'):
        b=poster_page(n+'.html')
        if b is None:return s.js(404,{'error':'一图流还没生成，到后台点「生成一图流」'})
        return s.send(200,b,'text/html; charset=utf-8')
    if p.startswith('/api/'):return s.js(404,{'error':'not found'})
    return super().do_HEAD() if s.command=='HEAD' else super().do_GET()
  # ── first-run wizard (only while the instance has no roster / password) ──
  def setup_get(s,p):
    """True when handled. Static files stay reachable (the wizard uses cbase.css / icons.js); everything else goes to /setup."""
    if p in ('/setup','/setup/'):
      s.send(200,readf(os.path.join(WEB,'setup.html')).encode(),'text/html; charset=utf-8');return True
    if p=='/api/setup/examples':s.js(200,{'items':setup.examples()});return True
    if p=='/api/setup/prefill':
      t=(urllib.parse.parse_qs(urllib.parse.urlparse(s.path).query).get('t') or [''])[0]
      if not SETUP['token'] or not hmac.compare_digest(t,SETUP['token']):
        # 六位数字只有一百万种，验证码页每输错一次都记一笔：不然可以直接枚举出预填的名单。
        hits,cap,now=s.limited('setup')
        if len(hits)>=cap:s.js(429,{'error':'试错太多次了，等 10 分钟再试（或重启服务器换一个验证码）'});return True
        hits.append(now);s.js(403,{'error':'验证码不对：看服务器终端里那六位数字'});return True
      s.js(200,SETUP['prefill'] or {});return True
    if p=='/api/setup/fields':s.js(200,{'presets':[dict(v,key=k) for k,v in fields.PRESETS.items()]});return True
    if p=='/api/health':s.js(200,health_payload(True));return True
    if p in ('/','/index.html') or p in GEN or p.startswith('/api/') or p.startswith('/poster'):
      s.send_response(302);s.send_header('Location','/setup');s.send_header('Content-Length','0');s.end_headers();return True
    return False
  def setup_post(s,p):
    if p not in ('/api/setup','/api/setup/preview','/api/setup/names'):s.close_connection=True;return s.js(409,{'error':'还没初始化，先打开 /setup'})   # 没读请求体：不能复用连接，否则剩下的 body 会被当成下一个请求
    hits,cap,now=s.limited('setup')
    if len(hits)>=cap:return s.js(429,{'error':'试错太多次了，等 10 分钟再试（或重启服务器换一个验证码）'})
    try:b=s.body(400_000)
    except Exception:return s.js(400,{'error':'提交格式不对'})
    if not isinstance(b,dict) or not hmac.compare_digest(str(b.get('token') or ''),SETUP['token']):
      hits.append(now);return s.js(403,{'error':'验证码不对：看服务器终端里那六位数字'})
    import importer
    # 给了名单却没说是哪来的，按「粘贴」算：向导的「核对名字」只发 names + title，
    # 少一个 source 就被当成「先空着」，于是每次都回「名单是空的」——按钮一直是废的。
    text=str(b.get('names') or '');src=str(b.get('source') or ('paste' if text.strip() else 'blank'))
    # 向导的表格编辑器把「团 / 角色 / CN」拼成同一份名单文本再提交（source=table）：
    # 对服务端来说它和粘贴进来的一模一样，别因为多了个取值就把整份名单丢掉、建成默认的空名册。
    parse_src='paste' if src in ('paste','table') else src
    try:
      parsed=importer.parse(text,str(b.get('title') or '我们的团').strip()[:59] or '我们的团') if parse_src=='paste' else None
    except ValueError as e:return s.js(400,{'error':str(e)})
    if p=='/api/setup/preview':
      # rows 给向导的表格编辑器用：把粘贴的名单原样摊成「团 / 角色 / CN」，团长可以接着一格一格改。
      return s.js(200,{'summary':importer.summary(parsed),
        'groups':[{'name':g['name'],'n':len(g['members']),'open':sum(1 for m in g['members'] if not m['member'])} for g in parsed['groups']],
        'rows':[{'name':g['name'],'note':g.get('note') or '','kind':g.get('kind') or 'cast',
                 'members':[{'character':m['character'],'member':m['member'] or ''} for m in g['members']]} for g in parsed['groups']]} if parsed else {'summary':''})
    if p=='/api/setup/names':
      # 名单预检：每个名字能不能配上图。结果落在 uploads/art_bind.json，建站后的自动配图直接按它取图。
      if not parsed:return s.js(400,{'error':'名单是空的'})
      import artsearch
      config.use(SETUP['instance'])
      rep=artsearch.bind(parsed)
      return s.js(200,{'line':artsearch.bind_line(rep),'net':rep['net'],'ok':rep['ok'],'total':rep['total'],
        'near':rep['near'],'missing':rep['missing'],
        'groups':[{'name':g['name'],'work':g.get('work') or {},'items':g['items']} for g in rep['groups']]})
    try:
      with LOCK:
        setup.create(SETUP['instance'],title=str(b.get('title') or ''),password=str(b.get('password') or ''),date=str(b.get('date') or ''),
          start=str(b.get('start') or ''),location=str(b.get('location') or ''),contact=str(b.get('contact') or ''),contact_label=str(b.get('contactLabel') or '微信'),
          roster=parsed,example=str(b.get('example') or '') or None if src=='example' else None,seed=src=='example',
          fields=b.get('fields') if isinstance(b.get('fields'),list) else None)
        if b.get('mode') in ('single','multi') and src!='example':
          j=jload(config.C.SITE,{});j['mode']=b['mode'];tmp=config.C.SITE+'.tmp'
          with open(tmp,'w',encoding='utf-8') as f:json.dump(j,f,ensure_ascii=False,indent=1)
          os.replace(tmp,config.C.SITE)
        SETUP['token']=None
        try:os.remove(os.path.join(config.C.INSTANCE,'.setup-token'))
        except OSError:pass
      # 首次收尾：粘贴的名单先自动配图，再生成一图流（样例 / 空名册没什么可配的，只生成一图流）
      import firstrun;firstrun.run_bg(LOCK,do_art=parse_src=='paste')
    except ValueError as e:return s.js(400,{'error':str(e)})
    except Exception as e:log('setup err',repr(e));return s.js(500,{'error':'初始化失败：'+str(e)[:120]})
    log('setup done',config.C.INSTANCE)
    t=secrets.token_urlsafe(32);ttl=int(float(config.C.site['server'].get('sessionDays') or 7)*86400);SESS[t]=time.time()+ttl
    return s.js(200,{'ok':True},f'cc_s={t}; Path=/; HttpOnly; SameSite=Strict; Max-Age={ttl}')
  def admin_get(s,p):
    if not s.tok():return s.js(401,{'error':'需要登录'})
    if p=='/api/admin/signups':return s.js(200,{'items':store.signups(),'state':review.window_state(),'fields':fields.normalize(config.C.site['signup'].get('fields'))})
    if p=='/api/admin/signup-fields':return s.js(200,{'fields':fields.normalize(config.C.site['signup'].get('fields')),'presets':[dict(v,key=k) for k,v in fields.PRESETS.items()]})
    if p=='/api/admin/notice':return s.js(200,{'notice':config.C.site['notice']})
    if p=='/api/admin/shots':return s.js(200,{'shots':{**config.C.site['shots'],'items':shots.normalize(config.C.site['shots'].get('items'),config.C.UPLOADS)},'groups':[{'name':g['name'],'crew':(g.get('kind') or 'cast')=='crew','members':[{'id':m.get('id'),'character':m.get('character',''),'member':m.get('member','')} for m in g['members']]} for g in roster.load()['groups']]})
    if p=='/api/admin/mshots':return s.js(200,{'items':store.mshots(),'config':config.C.site['photos']})
    if p=='/api/admin/guestbook':return s.js(200,{'items':store.notes(limit=1000)})
    if p=='/api/admin/counts':return s.js(200,store.counts())
    if p=='/api/admin/poster':return s.js(200,poster_status())
    if p=='/api/admin/whoami':
      # 托管后自检：服务器看到的来源 IP 是不是代理的；平台用哪个请求头传真实 IP（填进 CASTCALL_TRUST_PROXY）
      H=('X-Forwarded-For','X-Real-IP','CF-Connecting-IP','True-Client-IP','Forwarded')
      return s.js(200,{'peer':s.client_address[0],'ip':s.ip(),'trustProxyHeader':config.C.proxy_header() or '','headers':{k:s.headers.get(k) for k in H if s.headers.get(k)}})
    if p=='/api/admin/firstrun':
      import firstrun;t=firstrun.STATE['thread']
      return s.js(200,{'started':bool(t),'stage':firstrun.STATE['stage'],'lines':firstrun.STATE['lines'],'poster':poster_status()})
    if p=='/api/admin/photos':return s.js(200,{'items':store.photos(),'config':config.C.site['photos']})
    if p=='/api/admin/brand':return s.js(200,{'slots':brand_state(),'poster':bool(config.C.site['poster']['enabled'])})
    if p=='/api/admin/art/search':
      import artsearch
      q=urllib.parse.parse_qs(urllib.parse.urlparse(s.path).query);Q=lambda k:(q.get(k) or [''])[0]
      res,err=artsearch.search('cover' if Q('kind')=='cover' else 'portrait',Q('q'),Q('group'))
      return s.js(200 if res or not err else 502,{'items':res[:12],'error':err})
    if p=='/api/admin/art/thumb':
      # 缩略图由服务器代取：国内线路对 lain.bgm.tv 常见 DNS 污染 / TLS 被中间设备打断，浏览器直连就是
      # ERR_SSL_PROTOCOL_ERROR 加一排破图，而服务器（另一条线路 / 国外机器）往往还取得到。
      # 按 URL 缓存在 instance/cache/thumbs/，面板反复开不重复下载；取不到就回 502，前端显示占位块。
      import artsearch
      u=(urllib.parse.parse_qs(urllib.parse.urlparse(s.path).query).get('u') or [''])[0]
      if not artsearch.allowed(u):return s.js(400,{'error':'只能取 Bangumi / AniList 的图'})
      CT={'jpg':'image/jpeg','png':'image/png','webp':'image/webp','gif':'image/gif'}
      d=os.path.join(config.C.INSTANCE,'cache','thumbs');h=hashlib.sha1(u.encode()).hexdigest()[:20]
      hit=next((e for e in CT if os.path.exists(os.path.join(d,h+'.'+e))),None)
      if hit:
        with open(os.path.join(d,h+'.'+hit),'rb') as f:raw=f.read()
        return s.send(200,raw,CT[hit],[('Cache-Control','public, max-age=86400')])
      try:raw=artsearch.fetch(u,limit=3_000_000,timeout=15)
      except ValueError as e:return s.js(502,{'error':str(e)})
      ext=sniff(raw)
      if not ext:return s.js(502,{'error':'取回来的不是图片'})
      try:
        os.makedirs(d,exist_ok=True);fp=os.path.join(d,h+'.'+ext)
        with open(fp+'.tmp','wb') as f:f.write(raw)
        os.replace(fp+'.tmp',fp)
      except OSError:pass          # 缓存写不进去不影响这次显示
      return s.send(200,raw,CT[ext],[('Cache-Control','public, max-age=86400')])
    if p=='/api/admin/art/auto':
      import artsearch
      return s.js(200,artsearch.auto_status())
    return s.js(404,{'error':'not found'})
  def do_POST(s):
    p=s.path.split('?')[0]
    if SETUP['token']:return s.setup_post(p)
    if p=='/api/login':
      hits,cap,now=s.limited('login')
      if len(hits)>=cap:return s.js(429,{'error':'尝试次数过多，请 10 分钟后再试'})
      try:pw=str(s.body(4096).get('password',''))
      except Exception:return s.js(400,{'error':'bad request'})
      if not check_pw(pw):
        hits.append(now);log('login fail',s.ip());time.sleep(.6);return s.js(401,{'error':'密码不对','left':cap-len(hits)})
      ttl=int(float(config.C.site['server'].get('sessionDays') or 7)*86400)
      t=secrets.token_urlsafe(32);SESS[t]=now+ttl;log('login ok',s.ip())
      sec='; Secure' if config.C.proxy_header() and s.headers.get('X-Forwarded-Proto')=='https' else ''
      return s.js(200,{'ok':True},f'cc_s={t}; Path=/; HttpOnly; SameSite=Strict; Max-Age={ttl}{sec}')
    if p=='/api/logout':
      SESS.pop(s.tok(),None);return s.js(200,{'ok':True},'cc_s=; Path=/; Max-Age=0')
    if p=='/api/cast-signup':return s.cast_signup()
    if p=='/api/photo':return s.photo_post()
    if p=='/api/member-shot':return s.mshot_post()
    if p=='/api/signup-sample':return s.sample_post()
    if p=='/api/guestbook':return s.guestbook_post()
    if p.startswith('/api/admin/'):
      if not s.tok():return s.js(401,{'error':'需要登录'})
      return s.admin_post(p)
    s.js(404,{'error':'not found'})
  def cast_signup(s):
    """Public vacant-seat signup → local pending row (+ Notion row when configured). Never touches the roster."""
    hits,cap,now=s.limited('signup')
    if len(hits)>=cap:s.close_connection=True;return s.js(429,{'error':'提交太频繁，请稍后再试'})
    body=s.small(2,4096)
    if body is None:return
    hits.append(now)
    try:
      rec=review.prepare(body,roster.load())
      row,dup=store.add_signup(rec['seat'],rec['grp'],rec['character'],rec['name'],rec['contact'],extra=rec['extra'])
    except ValueError as e:
      msg=str(e);return s.js(409 if msg in ('这个席位已经有人了','席位信息已变，请刷新后再试') else 400,{'error':msg})
    except Exception as e:log('signup err',repr(e));return s.js(500,{'error':'提交失败，请稍后再试'})
    log('signup',row['id'],'dup' if dup else 'new',rec['grp'],rec['seat'])
    if not dup and config.C.notion_on('signup'):bg(lambda:notion().push_signup(row))
    return s.js(200,{'ok':True,'duplicate':dup})
  def photo_post(s):
    """Public: a seated member uploads their own photo. ?seat=<id>&name=<CN on that seat>, body = the image."""
    P=config.C.site['photos'];n=int(s.headers.get('Content-Length',0) or 0)
    if not P['enabled']:s.close_connection=True;return s.js(404,{'error':'照片上传没开'})
    hits,cap,now=s.limited('photo')
    if len(hits)>=cap:s.close_connection=True;return s.js(429,{'error':'上传太频繁，请稍后再试'})
    if n<16 or n>6_000_000:s.close_connection=True;return s.js(400,{'error':'照片要小于 6 MB'})
    q=urllib.parse.parse_qs(urllib.parse.urlparse(s.path).query);seat=(q.get('seat') or [''])[0];name=(q.get('name') or [''])[0].strip()
    g,m=roster.seat(roster.load(),seat)
    member=(m or {}).get('member','').strip()
    if not m or not member:s.close_connection=True;return s.js(400,{'error':'这个席位还没人，不能传照片'})
    # 不是身份验证（成员名本来就公开），只挡住手滑传错席位；真正的把关是审核
    if name!=member:s.close_connection=True;return s.js(403,{'error':'CN 和这个席位上的不一样'})
    hits.append(now)
    try:f=save_upload('photos',s.rfile.read(n))
    except ValueError as e:return s.js(400,{'error':str(e)})
    st='approved' if P.get('moderation')=='post' else 'pending'
    r=store.add_photo(seat,g['name'],m.get('character') or '',member,f,st)
    log('photo',r['id'],st,g['name'],seat)
    return s.js(200,{'ok':True,'pending':st=='pending'})
  def mshot_post(s):
    """Public: a seated member uploads a shot they want to take. ?seat=<id>&name=<CN on that seat>&caption=, body = the image.
    Same switch / moderation / rate limit as the member photo; at most shots.MEMBER_MAX per person."""
    P=config.C.site['photos'];n=int(s.headers.get('Content-Length',0) or 0)
    if not P['enabled']:s.close_connection=True;return s.js(404,{'error':'例图上传没开'})
    hits,cap,now=s.limited('photo')
    if len(hits)>=cap:s.close_connection=True;return s.js(429,{'error':'上传太频繁，请稍后再试'})
    if n<16 or n>6_000_000:s.close_connection=True;return s.js(400,{'error':'图片要小于 6 MB'})
    q=urllib.parse.parse_qs(urllib.parse.urlparse(s.path).query);Q=lambda k:(q.get(k) or [''])[0]
    seat,name,caption=Q('seat'),Q('name').strip(),Q('caption').strip()[:shots.MEMBER_CAPTION_LEN]
    g,m=roster.seat(roster.load(),seat)
    member=(m or {}).get('member','').strip()
    if not m or not member:s.close_connection=True;return s.js(400,{'error':'这个席位还没人，不能传例图'})
    if name!=member:s.close_connection=True;return s.js(403,{'error':'CN 和这个席位上的不一样'})
    hits.append(now)
    try:f=save_upload('mshots',s.rfile.read(n))
    except ValueError as e:return s.js(400,{'error':str(e)})
    st='approved' if P.get('moderation')=='post' else 'pending'
    r=store.add_mshot(seat,g['name'],m.get('character') or '',member,f,caption,st,shots.MEMBER_MAX)
    if not r:return s.js(409,{'error':f'每人最多 {shots.MEMBER_MAX} 张，先让团长撤下几张旧的'})
    log('mshot',r['id'],r['status'],g['name'],seat)
    return s.js(200,{'ok':True,'pending':r['status']=='pending'})
  def sample_post(s):
    """Public: 报名表里的样片，先单独传，拿到文件名再随报名提交。只有登录后台才看得到（/samples/）。"""
    n=int(s.headers.get('Content-Length',0) or 0)
    if not fields.has_image(config.C.site['signup'].get('fields')) or review.window_state()!='open':s.close_connection=True;return s.js(404,{'error':'这次报名不收样片'})
    hits,cap,now=s.limited('sample')
    if len(hits)>=cap:s.close_connection=True;return s.js(429,{'error':'上传太频繁，请稍后再试'})
    if n<16 or n>6_000_000:s.close_connection=True;return s.js(400,{'error':'样片要小于 6 MB'})
    hits.append(now)
    try:f=save_upload('samples',s.rfile.read(n))
    except ValueError as e:return s.js(400,{'error':str(e)})
    return s.js(200,{'ok':True,'file':f})
  def guestbook_post(s):
    G=config.C.site['guestbook']
    if not G['enabled']:return s.js(404,{'error':'留言区没开'})
    hits,cap,now=s.limited('guestbook')
    if len(hits)>=cap:s.close_connection=True;return s.js(429,{'error':'提交太频繁，请稍后再试'})
    body=s.small(2,8192)
    if body is None:return
    hits.append(now)
    # Honeypot: humans never see the website field; pretend success, store nothing.
    if isinstance(body,dict) and str(body.get('website') or '').strip():return s.js(200,{'ok':True})
    try:name,text=review.prepare_note(body);n=store.add_note(name,text,'pending' if G.get('moderation')=='pre' else 'approved')
    except ValueError as e:return s.js(400,{'error':str(e)})
    except Exception as e:log('guestbook err',repr(e));return s.js(500,{'error':'提交失败，请稍后再试'})
    if config.C.notion_on('guestbook'):bg(lambda:notion().push_note(n))
    return s.js(200,{'ok':True,'pending':n['status']=='pending'})
  def admin_post(s,p):
    q=urllib.parse.parse_qs(urllib.parse.urlparse(s.path).query);Q=lambda k:(q.get(k) or [''])[0]
    m=re.fullmatch(r'/api/admin/signups/(\d+)',p)
    if m:
      try:act=str(s.body(4096).get('action',''))
      except Exception:return s.js(400,{'error':'bad request'})
      i=int(m.group(1))
      with LOCK:
        if act=='approve':ok,msg=review.approve(i)
        elif act=='reject':ok,msg=review.revoke(i,'rejected')
        elif act=='reopen':ok,msg=review.revoke(i,'pending')
        else:return s.js(400,{'error':'action 只能是 approve / reject / reopen'})
      r=store.signup(i)
      if r and config.C.notion_on('signup'):bg(lambda:notion().push_signup(r))
      return s.js(200 if ok else 409,{'ok':ok,'message':msg,'item':r,'data':roster.load()})
    m=re.fullmatch(r'/api/admin/guestbook/(\d+)',p)
    if m:
      try:act=str(s.body(4096).get('action',''))
      except Exception:return s.js(400,{'error':'bad request'})
      st={'hide':'hidden','show':'approved','approve':'approved'}.get(act)
      if not st:return s.js(400,{'error':'action 只能是 hide / show'})
      store.set_note(int(m.group(1)),st)
      n=next((x for x in store.notes(limit=100000) if x['id']==int(m.group(1))),None)
      if n and config.C.notion_on('guestbook'):bg(lambda:notion().push_note(n))
      return s.js(200,{'ok':True,'item':n})
    if p=='/api/admin/upload':
      kind=Q('kind')
      if kind not in ('cover','portrait','logo'):return s.js(400,{'error':'kind 只能是 cover / portrait / logo'})
      n=int(s.headers.get('Content-Length',0) or 0)
      if n<16 or n>8_000_000:s.close_connection=True;return s.js(400,{'error':'图片要小于 8 MB'})
      try:name=save_upload({'cover':'covers','portrait':'portraits','logo':'brand'}[kind],s.rfile.read(n))
      except ValueError as e:return s.js(400,{'error':str(e)})
      if kind=='portrait':
        g,c=Q('group'),Q('character')
        if not g or not c:return s.js(400,{'error':'立绘要带 group 和 character'})
        with LOCK:set_portrait(g,c,'portraits/'+name)
      log('upload',kind,name);return s.js(200,{'ok':True,'file':name})
    m=re.fullmatch(r'/api/admin/photos/(\d+)',p)
    if m:
      try:act=str(s.body(4096).get('action',''))
      except Exception:return s.js(400,{'error':'bad request'})
      st={'approve':'approved','reject':'rejected','reopen':'pending'}.get(act)
      if not st:return s.js(400,{'error':'action 只能是 approve / reject / reopen'})
      r=store.set_photo(int(m.group(1)),st)
      if not r:return s.js(404,{'error':'没有这张照片'})
      return s.js(200,{'ok':True,'item':r})
    m=re.fullmatch(r'/api/admin/mshots/(\d+)',p)
    if m:
      try:act=str(s.body(4096).get('action',''))
      except Exception:return s.js(400,{'error':'bad request'})
      st={'approve':'approved','reject':'rejected','reopen':'pending'}.get(act)
      if not st:return s.js(400,{'error':'action 只能是 approve / reject / reopen'})
      r=store.set_mshot(int(m.group(1)),st)
      if not r:return s.js(404,{'error':'没有这张例图'})
      return s.js(200,{'ok':True,'item':r})
    if p=='/api/admin/signup-fields':
      try:b=s.body(16384);fs=fields.compact(b.get('fields'))
      except Exception:return s.js(400,{'error':'提交格式不对'})
      if sum(1 for f in fs if f['key'] not in fields.PRESETS)>fields.MAX_CUSTOM:return s.js(400,{'error':f'自定义题最多 {fields.MAX_CUSTOM} 个'})
      with LOCK:site_set('signup','fields',fs)
      log('signup fields',fields.summary(fs));return s.js(200,{'ok':True,'fields':fields.normalize(fs)})
    if p=='/api/admin/notice':
      try:b=s.body(16384);nt=notice.compact(b)
      except Exception:return s.js(400,{'error':'提交格式不对'})
      with LOCK:
        site_set('notice','enabled',nt['enabled']);site_set('notice','lead',nt['lead']);site_set('notice','items',nt['items'])
      log('notice updated');return s.js(200,{'ok':True,'notice':nt})
    if p=='/api/admin/shots/upload':
      n=int(s.headers.get('Content-Length',0) or 0)
      if n<16 or n>8_000_000:s.close_connection=True;return s.js(400,{'error':'图片要小于 8 MB'})
      try:name=save_upload('shots',s.rfile.read(n))
      except ValueError as e:return s.js(400,{'error':str(e)})
      log('upload shot',name);return s.js(200,{'ok':True,'file':name})
    if p=='/api/admin/shots':
      try:b=s.body(65536);sh=shots.compact(b,config.C.UPLOADS,{m.get('id') for g in roster.load()['groups'] for m in g['members']})
      except ValueError as e:return s.js(400,{'error':str(e)})
      except Exception:return s.js(400,{'error':'提交格式不对'})
      with LOCK:
        for k in ('title','lead','items'):site_set('shots',k,sh[k])
      log('shots updated',len(sh['items']));return s.js(200,{'ok':True,'shots':sh})
    if p=='/api/admin/photos/config':
      try:b=s.body(4096)
      except Exception:return s.js(400,{'error':'bad request'})
      with LOCK:
        if 'enabled' in b:site_set('photos','enabled',bool(b['enabled']))
        if b.get('moderation') in ('pre','post'):site_set('photos','moderation',b['moderation'])
      return s.js(200,{'ok':True,'config':config.C.site['photos']})
    if p=='/api/admin/brand':
      slot=Q('slot')
      if slot not in BRAND_SLOTS:return s.js(400,{'error':'slot 只能是 logo / favicon / hero'})
      n=int(s.headers.get('Content-Length',0) or 0)
      if Q('clear')=='1':
        if n:s.rfile.read(min(n,65536))
        with LOCK:set_brand(slot,'')
        log('brand clear',slot);return s.js(200,{'ok':True,'slots':brand_state()})
      if n<16 or n>8_000_000:s.close_connection=True;return s.js(400,{'error':'图片要小于 8 MB'})
      try:name=save_upload('brand',s.rfile.read(n))
      except ValueError as e:return s.js(400,{'error':str(e)})
      with LOCK:set_brand(slot,name)
      log('brand',slot,name);return s.js(200,{'ok':True,'file':name,'slots':brand_state()})
    if p=='/api/admin/portrait':
      try:b=s.body(4096)
      except Exception:return s.js(400,{'error':'bad request'})
      # {group, character} removes the portrait; with path (an existing portraits/ file) it points that seat at it
      path=str(b.get('path') or '')
      if path and not (re.fullmatch(r'portraits/[\w.-]+',path) and os.path.isfile(os.path.join(config.C.UPLOADS,path))):return s.js(400,{'error':'没有这张图'})
      g,c=str(b.get('group','')),str(b.get('character',''))
      if not g or not c:return s.js(400,{'error':'要带 group 和 character'})
      with LOCK:set_portrait(g,c,path or None)
      return s.js(200,{'ok':True})
    if p=='/api/admin/art/pick':
      import artsearch
      try:b=s.body(8192)
      except Exception:return s.js(400,{'error':'bad request'})
      kind,url,g,c=str(b.get('kind') or ''),str(b.get('url') or ''),str(b.get('group') or ''),str(b.get('character') or '')
      try:
        if kind=='cover':name=artsearch.save_cover(g,url,LOCK)
        else:
          if not g or not c:return s.js(400,{'error':'立绘要带 group 和 character'})
          with LOCK:name=artsearch.save_portrait(g,c,url)
          # 手选的也算「绑」：存下角色 id，名单核对就不会再对同一个名字报「找不到」
          artsearch.bind_manual(g,c,b.get('id'),str(b.get('name') or c),url)
      except ValueError as e:return s.js(400,{'error':str(e)})
      log('art pick',kind,g,c,name);return s.js(200,{'ok':True,'file':name})
    if p=='/api/admin/art/auto':
      import artsearch
      return s.js(202,{'ok':True,'started':artsearch.auto_bg(LOCK),**artsearch.auto_status()})
    if p=='/api/admin/poster':
      if not config.C.site['poster']['enabled']:return s.js(404,{'error':'一图流没开（site.json poster.enabled）'})
      if not poster_available():return s.js(501,{'error':'一图流是可选功能，服务器上还没装：pip install -r requirements-poster.txt && playwright install chromium'})
      started=poster_build();return s.js(202,{'ok':True,'started':started,**poster_status()})
    return s.js(404,{'error':'not found'})
  def do_PUT(s):
    if s.path.split('?')[0]!='/api/data':return s.js(404,{'error':'not found'})
    if not s.tok():return s.js(401,{'error':'需要登录'})
    try:
      d=s.body();roster.validate(d)
      with LOCK:roster.save(d)
      log('save ok groups',len(d['groups']));return s.js(200,{'ok':True,'data':roster.load()})
    except AssertionError as e:return s.js(400,{'error':'数据不合法 '+str(e)})
    except Exception as e:log('save err',repr(e));return s.js(500,{'error':'保存失败'})
def bg(fn):
  def run():
    try:fn()
    except Exception as e:log('background err',repr(e))
  threading.Thread(target=run,daemon=True).start()
def notion():
  import notion as N
  return N
def preflight():
  """True when the instance is ready. Otherwise the server starts in wizard mode (no default password, no implicit
  roster): /setup, guarded by a one-time token that only the person who started the server sees in the console."""
  C=config.C
  if not setup.initialized(C):
    SETUP.update(token=setup_token(C),instance=C.INSTANCE);return False
  roster.validate(roster.load());config.C.site;store.db().close()
  return True
def setup_token(C):
  """向导口令：6 位数字验证码，存在实例目录里（.setup-token，只有本机用户能读）：服务器中途被杀、重启后验证码不变，已经打开的向导页还能接着提交。
  老实例里可能还留着 0.1.0-beta 之前的长串口令，继续认——否则正填到一半的人会被踢出去。建站成功后删掉。"""
  p=os.path.join(C.INSTANCE,'.setup-token')
  try:
    with open(p,encoding='utf-8') as f:t=f.read().strip()
    if re.fullmatch(r'\d{6}',t) or re.fullmatch(r'[\w-]{12,64}',t):return t
  except OSError:pass
  t=f'{secrets.randbelow(1000000):06d}';os.makedirs(C.INSTANCE,exist_ok=True)
  with open(p,'w',encoding='utf-8') as f:f.write(t)
  try:os.chmod(p,0o600)
  except OSError:pass
  return t
def make_server(host=None,port=None):
  return ThreadingHTTPServer((host or config.C.host(),config.C.port() if port is None else port),H)
def prefill(path,title=''):
  """--prefill 名单.txt → 向导预填的内容。名单格式不对就在启动时报出来，别等团长在网页上才发现。"""
  import importer
  if path=='-':text=sys.stdin.read()
  else:
    with open(path,encoding='utf-8-sig') as f:text=f.read()
  d=importer.parse(text,title or '我们的团')
  casts=sum(1 for g in d['groups'] if (g.get('kind') or 'cast')!='crew')
  return {'names':text,'title':title,'mode':'single' if casts<=1 else 'multi','summary':importer.summary(d),'file':os.path.basename(path)}
def main(argv=None):
  import argparse
  ap=argparse.ArgumentParser(description='castcall 服务器。还没初始化时进入网页开团向导。')
  ap.add_argument('--prefill',metavar='名单.txt',help='向导里预先填好这份名单（格式见 docs/quickstart.md），团长打开链接核对、选项、设密码就能建站')
  ap.add_argument('--title',default='',help='和 --prefill 一起用：预填活动名称')
  ap.add_argument('--exit-after-setup',action='store_true',help='向导完成、自动配图和一图流都跑完后自己退出（给 AI 助手 / 脚本用：前台跑它就能等到建站结束）')
  a=ap.parse_args(sys.argv[1:] if argv is None else argv)
  ready=preflight()
  if a.prefill:
    if ready:print('已经初始化过了，--prefill 不生效。改名单用：python3 tools/import.py 名单.txt --dry',file=sys.stderr)
    else:
      try:SETUP['prefill']=prefill(a.prefill,a.title.strip())
      except (OSError,ValueError) as e:print(f'名单读不了：{e}',file=sys.stderr);return 1
  try:srv=make_server()
  except OSError as e:
    if e.errno in (48,98,10048):   # EADDRINUSE on macOS / Linux / Windows
      print(f'端口 {config.C.port()} 已被占用：可能另一个 castcall 还开着。先停掉它，或者换个端口：CASTCALL_PORT=5512 python3 server/server.py',file=sys.stderr);return 1
    raise
  host,port=srv.server_address[:2]
  import firstrun
  if ready and firstrun.pending():
    pd=firstrun.pending();print('上次建站后的自动配图 / 一图流没跑完，现在补上…',flush=True);firstrun.run_bg(LOCK,do_art=pd['art'],do_poster=pd['poster'])
  if a.exit_after_setup:
    if ready and not firstrun.STATE['thread']:print('已经建好了，没有要等的。正式运行：python3 server/server.py');srv.server_close();return 0
    threading.Thread(target=lambda:exit_when_built(srv),daemon=True).start()
  threading.Thread(target=lambda:notion().loop(LOCK),daemon=True).start()
  log('start',host,port,'notion' if config.C.notion_on() else 'local-only')
  if config.C.hosted() and not config.C.proxy_header():
    # 平台前面的代理让所有请求都从同一个 IP 来：频率限制会变成全站共用一份（10 分钟全站只能报名 8 次）
    print('提示：看起来跑在托管平台上（有 PORT），但没设 CASTCALL_TRUST_PROXY。所有访客会共用一份频率限制。'
          '登录后台后打开 /api/admin/whoami 看平台用哪个请求头传真实 IP，填进 .env，见 docs/hosting.md',file=sys.stderr,flush=True)
  shown='127.0.0.1' if host in ('0.0.0.0','::','') else host
  if ready:print(f'castcall: http://{shown}:{port}/  （实例目录 {config.C.INSTANCE}，Notion {"已启用" if config.C.notion_on() else "未启用"}）',flush=True)
  else:
    pf=SETUP['prefill'];pre=f'名单已预填：{pf["file"]}（{pf["summary"]}）\n' if pf else ''
    tok=SETUP['token'];code=bool(re.fullmatch(r'\d{6}',tok or ''))
    head=f'  验证码  {tok}' if code else f'  口令  {tok}'
    hint='页面会要你输这 6 位数字；直接打开上面的链接就不用输。' if code else '打开上面的链接（末尾带着口令）。'
    print(f'castcall 还没初始化。{pre}\n{head}\n\n  打开  http://{shown}:{port}/setup?t={tok}\n\n'
          '（验证码只在这里出现一次，别发给别人。\n'
          f'  {hint}\n'
          '  也可以停掉服务器，用 python3 init.py 在命令行里初始化）',flush=True)
  try:srv.serve_forever()
  except KeyboardInterrupt:pass
  if a.exit_after_setup and firstrun.STATE.get('finished'):
    print('\n建好了：'+config.C.INSTANCE+'\n'+'\n'.join('  '+x for x in firstrun.STATE['lines'])+'\n正式运行：python3 server/server.py',flush=True)
  return 0
def exit_when_built(srv):
  """--exit-after-setup：等向导提交 → 首次收尾（配图 + 一图流子进程）跑完，留几秒让完成页拿到最后的进度，然后关服务器。"""
  import firstrun
  while not firstrun.STATE.get('finished'):time.sleep(1)
  time.sleep(5);srv.shutdown()
if __name__=='__main__':sys.exit(main())
