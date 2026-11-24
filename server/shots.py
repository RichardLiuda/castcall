"""例图（site.json shots）：团长想拍的参考图——机位、构图、氛围、动作，放在名册下面给报名的人看。

site.json 里：
  "shots":{"title":"想拍的例图","lead":"大概是这种感觉","items":[{"file":"ab12cd34ef56.jpg","caption":"逆光侧脸","group":"团名","seats":["r1a2b3c4d"]}]}
图片文件放 uploads/shots/（后台「例图」面板上传，文件名 = 内容 hash）。
items 为空 = 页面上没有这一块。group 可选：多团时这张图放进那个团的卡片，留空就是全活动通用，放在名册下面。
seats 可选：这张图涉及的席位 id（多人照标角色），这些成员的个人页里也会出现这张图。

成员自己想拍的例图不在这里：存在 sqlite 的 mshots 表（store.py），开关和审核方式跟成员本人照片（site.json photos）共用。
caption 截 60 字，title 截 20 字，lead 截 80 字，最多 MAX_ITEMS 张。不做富文本，渲染端一律过 esc()。"""
import os,re
MAX_ITEMS=30
MAX_SEATS=20
MEMBER_MAX=6       # 每个成员最多几张（待审 + 已通过）
MEMBER_CAPTION_LEN=40
TITLE_LEN=20
LEAD_LEN=80
CAPTION_LEN=60
FILE_RE=re.compile(r'[0-9a-f]{12}\.(?:jpg|png|webp|gif)')
def normalize(items,uploads=None):
  """site.json 里的列表 → 清洗后的只读视图。给了 uploads 目录时，文件不在的那条丢掉（手删了图片不留破图）。"""
  out=[];seen=set()
  for it in items or []:
    if not isinstance(it,dict):continue
    f=str(it.get('file') or '')
    if not FILE_RE.fullmatch(f) or f in seen:continue
    if uploads and not os.path.isfile(os.path.join(uploads,'shots',f)):continue
    seen.add(f)
    seats=[];raw=it.get('seats') if isinstance(it.get('seats'),list) else []
    for x in raw:
      x=str(x)
      if re.fullmatch(r'[\w-]{1,40}',x) and x not in seats:seats.append(x)
    out.append({'file':f,'caption':str(it.get('caption') or '').strip()[:CAPTION_LEN],'group':str(it.get('group') or '').strip()[:60],'seats':seats[:MAX_SEATS]})
    if len(out)>=MAX_ITEMS:break
  return out
def compact(body,uploads,seat_ids=None):
  """后台提交的 {title, lead, items} → 校验/清洗后可直接 site_set 的结构。给了 seat_ids 时，名册里没有的席位标记丢掉。"""
  if not isinstance(body,dict):raise ValueError('提交格式不对')
  if not isinstance(body.get('items',[]),list):raise ValueError('提交格式不对')
  if len(body.get('items') or [])>MAX_ITEMS:raise ValueError(f'例图最多 {MAX_ITEMS} 张')
  items=normalize(body.get('items'),uploads)
  if seat_ids is not None:
    for it in items:it['seats']=[x for x in it['seats'] if x in seat_ids]
  return {'title':str(body.get('title') or '').strip()[:TITLE_LEN],'lead':str(body.get('lead') or '').strip()[:LEAD_LEN],'items':items}
