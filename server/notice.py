"""招募须知（site.json notice）：团长在一处写下「要求 / 不接受 / 补充 / 风险」，单团页 / 报名表 / 缺人看板三处自动复用。

site.json 里：
  "notice":{"enabled":true,"lead":"自然感团片，不修厚涂","items":[{"kind":"must","text":"挡脸出图"}]}
kind 只有 must / deny / warn / info 四种，见不到的值整条丢掉；lead 截 40 字，text 截 80 字，items 最多 12 条。
不做富文本，渲染端一律过 esc()。"""
KINDS=('must','deny','warn','info')
MAX_ITEMS=12
LEAD_LEN=40
TEXT_LEN=80
def normalize(items):
  """site.json 里的列表 → 清洗后的只读视图：非法 kind 丢掉，text 截断，整体截到 MAX_ITEMS 条。"""
  out=[]
  for it in items or []:
    if not isinstance(it,dict):continue
    k=it.get('kind')
    if k not in KINDS:continue
    t=str(it.get('text') or '').strip()[:TEXT_LEN]
    if not t:continue
    out.append({'kind':k,'text':t})
    if len(out)>=MAX_ITEMS:break
  return out
def compact(body):
  """后台提交的 {enabled, lead, items} → 校验/清洗后可直接 site_set 的结构。"""
  if not isinstance(body,dict):raise ValueError('提交格式不对')
  lead=str(body.get('lead') or '').strip()[:LEAD_LEN]
  return {'enabled':bool(body.get('enabled')),'lead':lead,'items':normalize(body.get('items'))}
