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
import config,fields,notice,roster,review,setup,store
from config import ROOT,WEB
LOCK=threading.Lock();SESS={};HITS={}
SETUP={'token':None,'instance':None,'prefill':None}   # set while the instance is not initialized: the first-run wizard needs this token
# prefill：server.py --prefill 名单.txt 带进来的名单 / 活动名，向导打开时预填（同样要口令才读得到）
log=roster.log

# ── auth ──────────────────────────────────────────────────────────────────
def check_pw(p):
  a=jload(config.C.AUTH,None)
  if not a:return False
  h=hashlib.pbkdf2_hmac('sha256',p.encode(),bytes.fromhex(a['salt']),int(a.get('iter',200000))).hex()
  return hmac.compare_digest(h,a['hash'])
from setup import set_password   # re-exported: tests and older scripts call server.set_password

# ── uploads (covers, portraits, logo) ─────────────────────────────────────
UP_DIRS=('covers','portraits','brand','photos')
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
  return 'window.CHARS='+json.dumps(m2,ensure_ascii=False)+';window.CHARPOS={};window.IMGV='+json.dumps(I,ensure_ascii=False,separators=(',',':'))+';window.PHOTOS='+json.dumps(photos_shown(I),ensure_ascii=False)+';'
def photos_shown(I=None):
  """{seat id: 'photos/x.jpg?v=..'}：开关开着、照片已通过、而且席位上还是上传的那个人（换人后旧照片不挂到新人头上）。"""
  if not config.C.site['photos']['enabled']:return {}
  I=I or imgv();cur={m.get('id'):(m.get('member') or '').strip() for g in roster.load()['groups'] for m in g['members']}
  out={}
  for seat,(member,f) in store.shown_photos().items():
    p='photos/'+f
    if cur.get(seat)==member and p in I:out[seat]=p+'?v='+str(I[p][0])
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
  rep={'{{title}}':E(e.get('title')),'{{subtitle}}':E(e.get('subtitle')),'{{logo}}':logo_tag,'{{date}}':date,'{{loc}}':loc,
       '{{location}}':E(e.get('location')),'{{poster}}':poster,'{{mode}}':mode(d),'{{head}}':style,
       '{{favicon}}':'/brand/'+E(s['brand'].get('favicon')) if s['brand'].get('favicon') else '/favicon.svg'}
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
  args+=['master','social'] if mode()=='single' else ['master','wide']
  env=dict(os.environ,CASTCALL_INSTANCE=config.C.INSTANCE)
  if config.C.getenv('CASTCALL_CHROME'):env['CASTCALL_CHROME']=config.C.getenv('CASTCALL_CHROME')   # .env values are not in os.environ
  return args,env
def poster_status():
  p=POSTER['proc'];run=bool(p and p.poll() is None)
  if p and not run:POSTER['rc']=p.returncode
  try:tail=readf(os.path.join(config.C.LOGS,'poster.log'))[-1500:]
  except OSError:tail=''
  return {'available':poster_available(),'running':run,'rc':POSTER['rc'],'startedAt':POSTER['at'],'ready':poster_ready(),'log':tail}
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
'var ex=document.getElementById("kr-poster-export"),wide=/\\/poster\\/wide/i.test(location.pathname);'
'var slug=document.documentElement.dataset.slug||"poster",n=wide?"wide.jpg":"master.jpg",fname=slug+"-"+n;'
'if(ex){ex.href="/poster/"+n+"?v="+Date.now();ex.setAttribute("download",fname);'
'ex.addEventListener("click",function(e){e.preventDefault();fetch(ex.href,{cache:"no-store"}).then(function(r){if(!r.ok)throw 0;return r.blob()})'
'.then(function(blob){var a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download=fname;document.body.appendChild(a);a.click();a.remove();'
'setTimeout(function(){URL.revokeObjectURL(a.href)},1500)}).catch(function(){location.href=ex.href})});}'
'place();if(window.visualViewport){visualViewport.addEventListener("resize",place);visualViewport.addEventListener("scroll",place)}'
'addEventListener("resize",place);addEventListener("scroll",place,{passive:true});addEventListener("load",place);'
'})();</script>'
)
def poster_page(name):
  f=os.path.join(config.C.POSTER,name)
  if not os.path.isfile(f):return None
  h=readf(f)
  slug=re.sub(r'[^\w-]','',config.C.site['poster'].get('slug') or 'poster') or 'poster'
  h=re.sub(r'<html([^>]*)>',lambda m:f'<html{m.group(1)} data-slug="{slug}">',h,count=1)
  m=re.search(r'<body[^>]*>',h,re.I)
  h=h[:m.end()]+POSTER_BACK+h[m.end():] if m else h+POSTER_BACK
  return h.encode()
def poster_chooser():
  only=mode()=='single' or not os.path.isfile(os.path.join(config.C.POSTER,'wide.html'))
  js="location.replace('/poster/master.html'+location.search+location.hash)" if only else "location.replace((matchMedia('(min-width:900px)').matches?'/poster/wide.html':'/poster/master.html')+location.search+location.hash)"
  return f'<!doctype html><html lang=zh><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>一图流</title><script>{js}</script><p style="font:600 14px/1.5 system-ui,sans-serif;margin:24px"><a href="/poster/master.html">一图流</a> · <a href="/">返回名单</a></p>'.encode()

# ── HTTP ──────────────────────────────────────────────────────────────────
FAVICON=b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="8" fill="#e6b35a"/><path d="M9 22V10h5a4 4 0 0 1 0 8h-5m7 0 6 4" fill="none" stroke="#333" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>'
class H(SimpleHTTPRequestHandler):
  protocol_version='HTTP/1.1';timeout=60
  def __init__(s,*a,**k):super().__init__(*a,directory=WEB,**k)
  def log_message(s,f,*a):pass
  def translate_path(s,path):
    """/covers/ /portraits/ /brand/ come from instance/uploads, /poster/ from instance/poster, the rest from web/."""
    p=urllib.parse.unquote(path.split('?',1)[0].split('#',1)[0])
    for pre,base in (('/covers/',os.path.join(config.C.UPLOADS,'covers')),('/portraits/',os.path.join(config.C.UPLOADS,'portraits')),
                     ('/brand/',os.path.join(config.C.UPLOADS,'brand')),('/photos/',os.path.join(config.C.UPLOADS,'photos')),('/samples/',os.path.join(config.C.UPLOADS,'samples')),('/poster/',config.C.POSTER)):
      if p.startswith(pre):
        # 成员照片只公开正在显示的那张；待审 / 被拒的只有登录后（审核时）能看
        if pre=='/samples/' and not s.tok():return os.path.join(base,'__nope__')   # 报名样片：只给后台看
        if pre=='/photos/' and not s.tok() and 'photos/'+p[len(pre):] not in {v.split('?')[0] for v in photos_shown().values()}:return os.path.join(base,'__nope__')
        rel=os.path.normpath(p[len(pre):]).lstrip(os.sep)
        if rel.startswith('..'):return os.path.join(base,'__nope__')
        return os.path.join(base,rel)
    return super().translate_path(path)
  def end_headers(s):
    p,_,q=s.path.partition('?')
    if s.path.startswith('/api') or p.endswith(('.html','/')) or (p.startswith('/poster/') and p.endswith('.jpg') and '/cache/' not in p):
      s.send_header('Cache-Control','no-store')
    elif p in GEN:s.send_header('Cache-Control',getattr(s,'_cc','no-cache'))
    elif p.endswith(('.css','.js','.jpg','.jpeg','.png','.svg','.webp','.gif')):
      # ?v= that matches the file's mtime -> safe to cache forever (a new file gets a new v); otherwise revalidate
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
    if p in ('/favicon.svg','/favicon.ico'):return s.send(200,FAVICON,'image/svg+xml')   # .ico: pages without a <link rel=icon> (the poster)
    if p=='/api/guestbook':
      if not config.C.site['guestbook']['enabled']:return s.js(404,{'error':'留言区没开'})
      try:return s.js(200,{'items':review.public_notes()})
      except Exception as e:log('guestbook read err',repr(e));return s.js(500,{'error':'暂时读不到留言'})
    if p=='/api/data':return s.js(200,roster.load())
    if p=='/api/me':return s.js(200,{'auth':bool(s.tok())})
    if p=='/api/health':return s.js(200,{'ok':True})
    if p.startswith('/api/admin/'):return s.admin_get(p)
    if p in ('/poster','/poster/'):return s.send(200,poster_chooser(),'text/html; charset=utf-8')
    for n in ('master','wide'):
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
      if not SETUP['token'] or not hmac.compare_digest(t,SETUP['token']):s.js(403,{'error':'口令不对'});return True
      s.js(200,SETUP['prefill'] or {});return True
    if p=='/api/setup/fields':s.js(200,{'presets':[dict(v,key=k) for k,v in fields.PRESETS.items()]});return True
    if p=='/api/health':s.js(200,{'ok':True,'setup':True});return True
    if p in ('/','/index.html') or p in GEN or p.startswith('/api/') or p.startswith('/poster'):
      s.send_response(302);s.send_header('Location','/setup');s.send_header('Content-Length','0');s.end_headers();return True
    return False
  def setup_post(s,p):
    if p not in ('/api/setup','/api/setup/preview'):s.close_connection=True;return s.js(409,{'error':'还没初始化，先打开 /setup'})   # 没读请求体：不能复用连接，否则剩下的 body 会被当成下一个请求
    hits,cap,now=s.limited('login')
    if len(hits)>=cap:return s.js(429,{'error':'尝试次数过多，请 10 分钟后再试'})
    try:b=s.body(400_000)
    except Exception:return s.js(400,{'error':'提交格式不对'})
    if not isinstance(b,dict) or not hmac.compare_digest(str(b.get('token') or ''),SETUP['token']):
      hits.append(now);return s.js(403,{'error':'口令不对：用服务器启动时终端里打印的那个链接打开'})
    import importer
    text=str(b.get('names') or '');src=b.get('source') or 'blank'
    try:
      parsed=importer.parse(text,str(b.get('title') or '我们的团').strip()[:59] or '我们的团') if src=='paste' else None
    except ValueError as e:return s.js(400,{'error':str(e)})
    if p=='/api/setup/preview':
      return s.js(200,{'summary':importer.summary(parsed),'groups':[{'name':g['name'],'n':len(g['members']),'open':sum(1 for m in g['members'] if not m['member'])} for g in parsed['groups']]} if parsed else {'summary':''})
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
      import firstrun;firstrun.run_bg(LOCK,do_art=src=='paste')
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
    if p=='/api/admin/guestbook':return s.js(200,{'items':store.notes(limit=1000)})
    if p=='/api/admin/counts':return s.js(200,store.counts())
    if p=='/api/admin/poster':return s.js(200,poster_status())
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
  """向导口令存在实例目录里（.setup-token，只有本机用户能读）：服务器中途被杀、重启后链接不变，已经打开的向导页还能接着提交。
  建站成功后删掉。"""
  p=os.path.join(C.INSTANCE,'.setup-token')
  try:
    with open(p,encoding='utf-8') as f:t=f.read().strip()
    if re.fullmatch(r'[\w-]{12,64}',t):return t
  except OSError:pass
  t=secrets.token_urlsafe(9);os.makedirs(C.INSTANCE,exist_ok=True)
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
  shown='127.0.0.1' if host in ('0.0.0.0','::','') else host
  if ready:print(f'castcall: http://{shown}:{port}/  （实例目录 {config.C.INSTANCE}，Notion {"已启用" if config.C.notion_on() else "未启用"}）',flush=True)
  else:
    pf=SETUP['prefill'];pre=f'名单已预填：{pf["file"]}（{pf["summary"]}）\n' if pf else ''
    print(f'castcall 还没初始化。{pre}在浏览器里打开下面这个链接完成设置（链接里的口令只在这里出现，别发给别人）：\n\n  http://{shown}:{port}/setup?t={SETUP["token"]}\n\n（也可以停掉服务器，用 python3 init.py 在命令行里初始化）',flush=True)
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
