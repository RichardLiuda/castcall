"""初始化一个实例：init.py（命令行）和网页向导（/setup）共用。

create() 写出 site.json、roster.json、auth.json 和 uploads/ 等目录。名册三选一：
  roster=…    已经解析好的名册（向导里粘贴的名单，见 importer.parse）
  example=…   examples/roster.<名字>.json（可顺带生成占位封面、留言、待审报名）
  都不给      空名册：一个只有一个空缺角色的团，等你在后台改"""
import hashlib,json,os,secrets
import config
ROOT=config.ROOT
def example_path(name):
  p=os.path.join(ROOT,'examples',f'roster.{name}.json');return p if os.path.isfile(p) else None
def examples():
  out=[]
  for f in sorted(os.listdir(os.path.join(ROOT,'examples'))):
    if f.startswith('roster.') and f.endswith('.json'):
      with open(os.path.join(ROOT,'examples',f),encoding='utf-8') as fh:d=json.load(fh)
      out.append({'name':f[len('roster.'):-len('.json')],'groups':len(d['groups']),'seats':sum(len(g['members']) for g in d['groups'])})
  return out
def set_password(pw,path=None):
  """Write auth.json (PBKDF2-SHA256). There is no built-in default password."""
  s=secrets.token_hex(16);path=path or config.C.AUTH
  os.makedirs(os.path.dirname(path),exist_ok=True)
  with open(path,'w',encoding='utf-8') as f:json.dump({'salt':s,'iter':200000,'hash':hashlib.pbkdf2_hmac('sha256',pw.encode(),bytes.fromhex(s),200000).hex()},f)
  try:os.chmod(path,0o600)
  except OSError:pass
def initialized(C=None):
  C=C or config.C;return os.path.isfile(C.ROSTER) and os.path.isfile(C.AUTH)
def create(instance,*,title,password,date='',start='',end='',location='',contact='',contact_label='微信',
           roster=None,example=None,seed=True,force=False,fields=None):
  """Returns (Config, seeded summary or None). Never overwrites an existing roster."""
  if not password or len(password)<8:raise ValueError('管理密码至少 8 位')
  if not (title or '').strip():raise ValueError('请填写活动名称')
  C=config.use(instance)
  if os.path.exists(C.ROSTER) and not force:raise ValueError(f'{C.INSTANCE} 已经初始化过了')
  with open(os.path.join(ROOT,'examples','site.example.json'),encoding='utf-8') as f:site=json.load(f)
  contact=(contact or '').strip()
  cl,_,cv=contact.partition(' ') if ' ' in contact else ('',None,contact)
  site['mode']='auto'
  site['event'].update(title=title.strip(),date=(date or '').strip(),startAt=(start or '').strip(),endAt=(end or '').strip(),
                       location=(location or '').strip(),organizer='',contact={'label':cl,'value':cv})
  site['signup']['contactLabel']=(contact_label or '微信').strip()
  if fields is not None:
    import fields as F
    site['signup']['fields']=F.compact(fields)   # 报名额外要填的（身高 / 样片…），见 server/fields.py
  for d in (C.INSTANCE,C.UPLOADS,C.POSTER,C.BACKUPS,C.LOGS):os.makedirs(d,exist_ok=True)
  with open(C.SITE,'w',encoding='utf-8') as f:json.dump(site,f,ensure_ascii=False,indent=1)
  seeded=None
  if not os.path.exists(C.ROSTER):
    import roster as R
    if roster is not None:d=json.loads(json.dumps(roster))
    elif example:
      p=example_path(example)
      if not p:raise ValueError('没有这个样例：'+example)
      with open(p,encoding='utf-8') as f:d=json.load(f)
    else:d={'groups':[{'name':title.strip()[:59],'color':'#e07a5f','members':[{'character':'第一个角色','member':''}]}]}
    R.validate(d);R.ensure_ids(d)
    for g in d['groups']:g['count']=len(g['members'])
    if example and seed:
      import demo;seeded=demo.seed(d)
    with open(C.ROSTER,'w',encoding='utf-8') as f:json.dump(d,f,ensure_ascii=False,indent=1)
  set_password(password,C.AUTH)
  return C,seeded
