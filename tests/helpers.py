"""Shared test plumbing: a throw-away instance and an in-process HTTP client.

Requests go through a socketpair straight into the real handler (server.H), so the tests need no free port and run
where binding a socket is not allowed (sandboxes, some CI)."""
import json,os,shutil,socket,sys,tempfile,threading,unittest
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)));sys.path.insert(0,os.path.join(ROOT,'server'))
import config
# 首次收尾（init.py / 网页向导建完站后的自动配图 + 一图流）在测试里不联网、不开 Chrome：只记下被调用过
import firstrun
FIRSTRUN=[]
REAL_POSTER=firstrun.poster
firstrun.art=lambda lock=None,log=print:(FIRSTRUN.append('art'),{'covers':0,'portraits':0,'skipped':[],'errors':[]})[1]
firstrun.poster=lambda wait=True,log=print:(FIRSTRUN.append(('poster',wait)),(False,'stub'))[1]
PW='test-password-1'
def rj(p):
  with open(p,encoding='utf-8') as f:return json.load(f)
def wj(p,o):
  with open(p,'w',encoding='utf-8') as f:json.dump(o,f,ensure_ascii=False)
def edit_site(fn):
  j=rj(config.C.SITE);fn(j);wj(config.C.SITE,j)
def make_instance(mode='multi',site=None):
  d=tempfile.mkdtemp(prefix='castcall-test-')
  C=config.use(d)
  C.env={}   # 开发机根目录 .env（上线的 CASTCALL_TRUST_PROXY 等）不该渗进单测：用例自己设的头才算数
  for k in ('UPLOADS','POSTER','BACKUPS','LOGS'):os.makedirs(getattr(C,k),exist_ok=True)
  s=rj(os.path.join(ROOT,'examples','site.example.json'))
  config.merge(s,site or {})
  wj(C.SITE,s)
  shutil.copy(os.path.join(ROOT,'examples',f'roster.{mode}.example.json'),C.ROSTER)
  import roster,server
  r=roster.load();roster.ensure_ids(r);wj(C.ROSTER,r)
  server.set_password(PW,C.AUTH);server.HITS.clear();server.SESS.clear()
  # Background pushes run inline in tests: a thread that outlives its test would talk to the next test's fake (or
  # to the real api.notion.com once the fake is gone).
  server.bg=lambda fn:fn()
  return d
class Resp:
  def __init__(s,raw):
    head,_,body=raw.partition(b'\r\n\r\n');lines=head.decode('latin-1').split('\r\n')
    s.status=int(lines[0].split()[1]);s.headers={}
    for ln in lines[1:]:
      k,_,v=ln.partition(':');s.headers.setdefault(k.strip().lower(),[]).append(v.strip())
    s.body=body
  def json(s):return json.loads(s.body.decode('utf-8'))
  @property
  def text(s):return s.body.decode('utf-8')
  def header(s,k):return (s.headers.get(k.lower()) or [''])[0]
class Client:
  def __init__(s,ip='127.0.0.1'):s.cookie='';s.ip=ip
  def req(s,method,path,body=None,headers=None,raw=None):
    import server
    a,b=socket.socketpair()
    data=raw if raw is not None else (json.dumps(body,ensure_ascii=False).encode() if body is not None else b'')
    h={'Host':'test','Connection':'close','Content-Length':str(len(data))}
    if s.cookie:h['Cookie']=s.cookie
    h.update(headers or {})
    a.sendall(f'{method} {path} HTTP/1.1\r\n'.encode()+''.join(f'{k}: {v}\r\n' for k,v in h.items()).encode('utf-8')+b'\r\n'+data)
    out=[]
    def read():
      while True:
        x=a.recv(65536)
        if not x:break
        out.append(x)
    rt=threading.Thread(target=read);rt.start()
    class Srv:pass
    ht=threading.Thread(target=lambda:server.H(b,(s.ip,40000),Srv()));ht.start();ht.join(30)
    b.close();rt.join(30);a.close()
    r=Resp(b''.join(out))
    c=r.header('set-cookie')
    if c.startswith('cc_s='):s.cookie=c.split(';')[0]
    return r
  def get(s,p,**k):return s.req('GET',p,**k)
  def post(s,p,body=None,**k):return s.req('POST',p,body,**k)
  def put(s,p,body=None,**k):return s.req('PUT',p,body,**k)
  def login(s,pw=PW):return s.post('/api/login',{'password':pw})
class Base(unittest.TestCase):
  mode='multi';site=None
  def setUp(s):
    s.dir=make_instance(s.mode,s.site);s.c=Client()
  def tearDown(s):shutil.rmtree(s.dir,ignore_errors=True)
  def roster(s):
    import roster
    return roster.load()
  def vacant(s,group=None):
    for g in s.roster()['groups']:
      if group and g['name']!=group:continue
      if g.get('signup')=='closed':continue
      for m in g['members']:
        if not m.get('member'):return g,m
