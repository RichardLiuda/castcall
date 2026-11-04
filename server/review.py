"""报名和留言的校验与审核。

公开报名：空缺席位 → 本地待审 → 后台（或 Notion）通过后写进名册。

和 keyroster 的区别：审核不再只认 Notion。approve() 是唯一落座入口，后台按钮和 Notion 轮询都调它，
而且走 roster.save()，所以 count、备份、outbox 和网页保存完全一致。"""
import datetime,re
import os
import config,fields,roster,store
def _text(v,n,label,required):
  if v is None:v=''
  if not isinstance(v,str):raise ValueError(label+'格式不对')
  v=v.strip()
  if any(ord(c)<32 for c in v):raise ValueError(label+'里不能有换行或控制符')
  if len(v)>n:raise ValueError(label+'太长')
  if required and not v:raise ValueError('请填写'+label)
  return v
def _when(s):
  if not s:return None
  try:return datetime.datetime.fromisoformat(s.replace('Z','+00:00'))
  except ValueError:return None
def window_state(site=None):
  """'open' / 'closed' / 'before' / 'after' for the event-wide signup switch and time window."""
  s=(site or config.C.site)['signup']
  if not s.get('enabled',True):return 'closed'
  now=datetime.datetime.now(datetime.timezone.utc)
  a,b=_when(s.get('opensAt')),_when(s.get('closesAt'))
  if a and a.tzinfo and now<a:return 'before'
  if b and b.tzinfo and now>=b:return 'after'
  return 'open'
WHY={'closed':'报名已关闭','before':'报名还没开始','after':'报名已截止'}
def prepare(body,d):
  """Validate a public signup against the current roster. Raises ValueError with a message for the page."""
  if not isinstance(body,dict):raise ValueError('提交格式不对')
  st=window_state()
  if st!='open':raise ValueError(WHY[st])
  site=config.C.site['signup'];label=site.get('contactLabel') or '联系方式'
  name=_text(body.get('name'),40,'CN',True)
  # keyroster 的前端发 wechat；模板发 contact。两个都认，方便旧页面过渡。
  contact=_text(body.get('contact',body.get('wechat')),60,label,True)
  pat=site.get('contactPattern') or ''
  if pat:
    try:ok=re.fullmatch(pat,contact)
    except re.error:ok=True
    if not ok:raise ValueError(label+'格式不对')
  grp=_text(body.get('work',body.get('group')),60,'团',True)
  character=_text(body.get('character'),60,'角色',False)
  rid=body.get('id','')
  if not isinstance(rid,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,32}',rid.strip()):raise ValueError('找不到这个席位')
  g,m=roster.seat(d,rid.strip())
  if not m:raise ValueError('找不到这个席位')
  if g['name']!=grp or (m.get('character') or '')!=character:raise ValueError('席位信息已变，请刷新后再试')
  if (g.get('signup') or 'open')=='closed':raise ValueError('这个团暂停报名了')
  if (m.get('member') or '').strip():raise ValueError('这个席位已经有人了')
  # 团长选的额外字段（身高 / 样片…）；样片要先走 /api/signup-sample 传上来，这里只认已经在 uploads/samples/ 里的文件
  extra=fields.validate(site.get('fields'),body.get('extra'),lambda f:os.path.isfile(os.path.join(config.C.UPLOADS,'samples',f)))
  return {'seat':m['id'],'grp':grp,'character':character,'name':name,'contact':contact,'extra':extra}
def approve(i,source='后台'):
  """Seat signup #i. Caller holds the server LOCK. Returns (ok, message).
  A seat that someone else took meanwhile is never overwritten: the signup stays pending with a note."""
  r=store.signup(i)
  if not r:return False,'没有这条报名'
  if r['status']=='approved':return True,'已经通过了'
  d=roster.load();g,m=roster.seat(d,r['seat'])
  if not m:
    store.set_signup(i,r['status'],source,'名册里已经没有这个席位');return False,'名册里已经没有这个席位'
  cur=(m.get('member') or '').strip()
  if cur and cur!=r['name']:
    store.set_signup(i,r['status'],source,f'席位已被 {cur} 占用');return False,f'席位已被 {cur} 占用'
  if not cur:
    m['member']=r['name'];roster.save(d,'报名')
  store.set_signup(i,'approved',source);return True,'已落座'
def revoke(i,status='rejected',source='后台'):
  """Undo or refuse #i. Clears the seat only if it still holds the name this signup put there."""
  r=store.signup(i)
  if not r:return False,'没有这条报名'
  msg='已拒绝' if status=='rejected' else '已退回待审'
  if r['status']=='approved':
    d=roster.load();g,m=roster.seat(d,r['seat'])
    if m and (m.get('member') or '').strip()==r['name']:
      m['member']='';roster.save(d,'报名');msg+='，席位已空出'
  store.set_signup(i,status,source);return True,msg

# ── guestbook ──────────────────────────────────────────────────────────────
def prepare_note(body):
  if not isinstance(body,dict):raise ValueError('提交格式不对')
  name=_text(body.get('CN',body.get('name')),40,'CN',False) or '匿名'
  text=body.get('内容',body.get('body'))
  if text is None:text=''
  if not isinstance(text,str):raise ValueError('内容格式不对')
  text=text.replace('\r\n','\n').replace('\r','\n').strip()
  if any(ord(c)<32 and c!='\n' for c in text):raise ValueError('内容里不能有控制符')
  if len(text)>500:raise ValueError('内容太长')
  if not text:raise ValueError('请填写内容')
  return name,text
def public_notes():
  """What the page shows: approved notes, newest first, in the field names the front end already uses."""
  return [{'id':n['id'],'CN':n['name'],'内容':n['body'],'提交时间':n['created'],'状态':'已通过'} for n in store.notes('approved')]
