"""样例填充（init.py --example 用）：每个团一张占位封面、几条留言、几条待审报名。

封面是程序画的斜条纹渐变 PNG（只用标准库），颜色取团的主题色，不涉及任何版权图；
PNG 而不是 SVG，是因为一图流的 Pillow 也要读它。留言和报名直接写进本地数据库，
效果和网页上真的有人提交一样：留言立刻显示，报名在后台「审核」里等你点。"""
import random,struct,zlib
import roster,server,store
NOTES=[('阿光','期待这次活动！第一次参加团建，有点紧张哈哈'),
  ('','妆造群已经建好了吗？想问一下假发要不要统一订'),
  ('糯米','后勤这边准备了饮料和充电宝，有需要的找我～'),
  ('橘丸','上次的返图太好看了，这次也要拍好多张！'),
  ('','请问雨天备用场地是哪里呀'),
  ('白花枝','道具剑已经做好了，周末带去现场')]
NAMES=['小满','阿柚','栗子糕','青团','月见','柠檬汽水','米粒','星野']
def png(w,h,rows):
  """rows: iterable of h byte strings, each w*3 RGB bytes."""
  def chunk(t,b):return struct.pack('>I',len(b))+t+b+struct.pack('>I',zlib.crc32(t+b)&0xffffffff)
  raw=b''.join(b'\x00'+r for r in rows)
  return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(raw,9))+chunk(b'IEND',b'')
def cover(color,i,w=960,h=600):
  """Diagonal stripes over a light-to-deep gradient of the group colour. Stripe width and direction vary with i."""
  r0,g0,b0=(int(color[k:k+2],16) for k in (1,3,5))
  mix=lambda c,t,a:round(c+(t-c)*a)
  p=48+(i%4)*16;half=p//2;sign=1 if i%2==0 else -1;rows=[]
  for y in range(h):
    t=y/(h-1)
    a=tuple(mix(c,255,.45*(1-2*t)) if t<.5 else mix(c,0,.7*(t-.5)) for c in (r0,g0,b0))   # top lighter, bottom deeper
    b=tuple(mix(c,255,.18) for c in a)
    unit=bytes(a)*half+bytes(b)*(p-half);tile=unit*(w//p+2)
    off=(y*sign)%p
    rows.append(tile[off*3:(off+w)*3])
  return png(w,h,rows)
def seed(d,rng=None):
  """d: freshly written roster. Writes covers into it (caller saves), notes + signups into the db. Returns a summary."""
  rng=rng or random.Random(7)
  for i,g in enumerate(d['groups']):
    if not g.get('cover'):g['cover']=server.save_upload('covers',cover(g['color'],i))
  for name,text in NOTES:store.add_note(name or '匿名',text,'approved','样例')
  vac=[(g,m) for g in d['groups'] if (g.get('signup') or 'open')=='open' for m in g['members'] if not (m.get('member') or '').strip() and m.get('character')]
  rng.shuffle(vac);made=0
  for k,(g,m) in enumerate(vac[:3]):
    store.add_signup(m['id'],g['name'],m['character'],NAMES[k],f'wx_demo{k+1:02d}','样例');made+=1
  if len(vac)>=2:   # two people asking for the same seat: shows the 「席位已被占用」 case in review
    g,m=vac[0];store.add_signup(m['id'],g['name'],m['character'],NAMES[3],'wx_demo04','样例');made+=1
  return {'covers':len(d['groups']),'notes':len(NOTES),'signups':made}
