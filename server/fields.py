"""报名表的额外字段：团长在部署时（init.py --fields / 网页向导）或后台「报名表」里选，存在 site.json 的 signup.fields。

site.json 里只记 key 和是否必填，自定义题再带 label：
  "fields":[{"key":"height"},{"key":"sample","required":true},{"key":"q1","label":"想出的妆面","type":"text"}]
normalize() 把它补全成前后端都用的完整定义（label / type / 单位 / 选项）；没写 required 就是选填。
CN 和联系方式是固定的两项，不在这里。"""
import os,re
PRESETS={
  'height':{'label':'身高','type':'number','unit':'cm','min':100,'max':230},
  'age':{'label':'年龄','type':'number','unit':'岁','min':10,'max':80},
  'gender':{'label':'性别','type':'select','options':['女','男','其他']},
  'sample':{'label':'样片','type':'image','hint':'过往的 cos 照片，一张就行'},
  'city':{'label':'所在城市','type':'text'},
  'experience':{'label':'出过的角色','type':'text'},
  'note':{'label':'想说的话','type':'textarea'},
}
ORDER=list(PRESETS)
TYPES=('text','textarea','number','select','image')
MAX_CUSTOM=6
def normalize(raw):
  """site.json 里的列表 → 完整定义。未知预设、坏条目直接丢掉（配置手改坏了也不让报名表挂掉）。"""
  out,seen=[],set()
  for f in raw or []:
    if isinstance(f,str):f={'key':f}
    if not isinstance(f,dict):continue
    k=str(f.get('key') or '').strip()
    if not re.fullmatch(r'[a-z][a-z0-9_]{0,23}',k) or k in seen:continue
    if k in PRESETS:d=dict(PRESETS[k],key=k)
    else:
      lab=str(f.get('label') or '').strip()[:20];t=f.get('type') if f.get('type') in ('text','textarea') else 'text'
      if not lab:continue
      d={'key':k,'label':lab,'type':t}
    d['required']=bool(f.get('required'));seen.add(k);out.append(d)
  return out
def compact(fs):
  """完整定义 → 写回 site.json 的精简形式。"""
  return [{'key':f['key'],**({'required':True} if f.get('required') else {}),**({} if f['key'] in PRESETS else {'label':f['label'],'type':f['type']})} for f in normalize(fs)]
ALIAS={v['label']:k for k,v in PRESETS.items()}|{'照片':'sample','样图':'sample','作品':'sample','备注':'note','城市':'city'}
def parse_spec(spec):
  """init.py --fields "身高,样片*,年龄,性别,想出的妆面"：逗号分隔，* 结尾 = 必填，其余选填；
  预设可以写中文名或 key，认不出的当作自定义文字题。"""
  out,n=[],0
  for part in re.split(r'[,，、]',spec or ''):
    p=part.strip()
    if not p:continue
    req=p.endswith('*');p=p.rstrip('*').strip()
    k=p if p in PRESETS else ALIAS.get(p)
    if k:out.append({'key':k,'required':req})
    else:
      n+=1
      if n>MAX_CUSTOM:raise ValueError(f'自定义题最多 {MAX_CUSTOM} 个')
      out.append({'key':f'q{n}','label':p[:20],'type':'text','required':req})
  return compact(out)
def summary(fs):
  fs=normalize(fs)
  return '、'.join(f['label']+('（必填）' if f['required'] else '') for f in fs) or '只填 CN 和联系方式'
def validate(fs,extra,sample_ok):
  """公开报名提交的 extra（dict）→ 清洗后的 {key: 值}。sample_ok(name) 判断样片文件是否真的传上来了。"""
  if extra is None:extra={}
  if not isinstance(extra,dict):raise ValueError('提交格式不对')
  out={}
  for f in normalize(fs):
    v=extra.get(f['key']);lab=f['label']
    if isinstance(v,(int,float)) and not isinstance(v,bool):v=str(v)
    if v is None:v=''
    if not isinstance(v,str):raise ValueError(lab+'格式不对')
    v=v.strip()
    if not v:
      if f['required']:raise ValueError(('请上传' if f['type']=='image' else '请填写')+lab)
      continue
    t=f['type']
    if t=='number':
      if not re.fullmatch(r'\d{1,3}(\.\d)?',v):raise ValueError(lab+'要填数字')
      if not f['min']<=float(v)<=f['max']:raise ValueError(f"{lab}不太对（{f['min']}–{f['max']}{f['unit']}）")
    elif t=='select':
      if v not in f['options']:raise ValueError(lab+'选项不对')
    elif t=='image':
      if not re.fullmatch(r'[0-9a-f]{12}\.(jpg|png|webp|gif)',v) or not sample_ok(v):raise ValueError(lab+'没传上来，请重新选一张')
    else:
      n=400 if t=='textarea' else 60
      if len(v)>n:raise ValueError(lab+'太长')
      if t=='text' and any(ord(c)<32 for c in v):raise ValueError(lab+'里不能有换行')
      if any(ord(c)<32 and c not in '\n' for c in v):raise ValueError(lab+'里有不能用的字符')
    out[f['key']]=v
  return out
def text(fs,extra):
  """{key: 值} → 一行给人看的文字（审核列表、Notion）。"""
  parts=[]
  for f in normalize(fs):
    v=(extra or {}).get(f['key'])
    if not v:continue
    parts.append(f"{f['label']} {'已上传' if f['type']=='image' else v+f.get('unit','') if f['type']=='number' else v}")
  return ' · '.join(parts)
def has_image(fs):return any(f['type']=='image' for f in normalize(fs))
