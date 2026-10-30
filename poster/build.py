#!/usr/bin/env python3
"""一图流：把名册排成一张大海报（网页版 + JPG）。可选功能，需要 Pillow 和 Playwright：

  pip install -r requirements-poster.txt && playwright install chromium

  python3 poster/build.py                      # 按团数自动：多团 master + wide，单团 master + social
  python3 poster/build.py master wide social   # 指定版式
  python3 poster/build.py --instance /path/to/instance --chrome /usr/bin/google-chrome

版式
  master  竖版长图，2400 宽（手机上看、发群）
  wide    宽版，3840 宽，8 列瀑布（电脑 / 投屏）
  social  单团卡片 1080×1350（社交平台配图；--group 指定团，默认第一个）

产物写进 <instance>/poster/：master.html wide.html（网站 /poster/ 直接用）、master.jpg wide.jpg social.jpg、cache/（立绘裁切）。
后台的「生成一图流」按钮就是在跑这个脚本。

只读 instance 里的 roster.json、site.json、uploads/；成员是「待定 / TBD / 空」的席位不上海报。
封面在团标题条里怎么裁：组里写 "cover_focus":[x0,y0,x1,y1]（封面上必须完整露出的区域，0–1 的比例，
通常框住人物的眉毛到下巴），没写就用 [0.1,0.1,0.9,0.5]。"""
import argparse,glob,hashlib,html,io,json,math,os,re,sys
R=os.path.dirname(os.path.abspath(__file__));ROOT=os.path.dirname(R)
E=html.escape
CAM='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M4 8h3l1.6-2.2h6.8L17 8h3a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1z"/><circle cx="12" cy="13.2" r="3.6"/></svg>'
CAM_H2="<i class='hc'>"+CAM+"</i>"
FEATHER='<svg class="fe" viewBox="0 0 100 300"><path d="M50 290 C48 200 40 120 50 10 C70 80 80 160 52 250 M50 60 C30 90 22 140 30 190 M50 60 C70 95 76 140 70 185" fill="none" stroke="#fff" stroke-width="2" opacity=".55"/></svg>'
DEFAULT_FOCUS=(.1,.1,.9,.5)
# Frames every .bg[data-face] from the band's real size. The focus box is fitted into the free zone
# of the header (right of the title, left of the 「N 人」chip, its full height). A cover that can
# fill the band centres the box in that zone; a fitted one hugs the zone's right edge. Open edges
# fade (mask) instead of ending on a hard line: left/right into the group colour of the title band,
# the bottom into the cards when the art stops short of .bg (portrait covers run on under the cards).
# A side fade never reaches into the focus box.
# Portrait covers (.tall) are drawn at least band-wide so the art runs on down behind the cards; the
# faces may then cross the header's bottom edge (top kept at 12% of the header), capped at 1.6× its height.
# The zone is at least half the band wide: in narrow columns a long title left a thumbnail's worth of room,
# so the box may slide under the end of the title (never left of 30%).
FRAME_JS=("<script id=\"kr-frame\">(function(){"
 "document.querySelectorAll('section>.bg[data-face]').forEach(function(bg){"
 "var im=bg.firstElementChild,sec=bg.parentNode,hd=sec.querySelector('header'),h2=sec.querySelector('.hd h2'),ct=sec.querySelector('.hd .ct');"
 "var W=bg.offsetWidth,Hb=bg.offsetHeight,Hv=hd.offsetHeight,ar=+bg.dataset.ar,f=bg.dataset.face.split(',').map(Number);"
 "if(!W||!Hv||!ar)return;"
 "var L=Math.max(W*.3,h2?h2.offsetLeft+h2.offsetWidth+W*.03:0),R=ct?ct.offsetLeft-W*.02:W*.97,V=Hv;"
 "if(R-L<W*.5)L=Math.max(W*.3,R-W*.5);"
 "var fw=f[2]-f[0],fh=f[3]-f[1],sCov=Math.max(W,Hb*ar),sFit=Math.min(V*ar/fh,(R-L)/fw);"
 "var cov=sFit>=sCov,s=cov?sCov:sFit,ih=s/ar;"
 "var x=cov?(L+R)/2-(f[0]+f[2])/2*s:Math.min(W-s,R-f[2]*s),y=V*.5-(f[1]+f[3])/2*ih;"
 "if(cov){x=Math.min(0,Math.max(W-s,x));y=Math.min(0,Math.max(Hb-ih,y))}else{y=Math.min(0,y)}"
 "if(!cov&&sec.classList.contains('tall')){var sT=Math.max(s,Math.min(W,Hv*1.6*ar/fh));if(sT>s){s=sT;ih=s/ar;"
 "x=s>=W?Math.min(0,Math.max(W-s,W/2-(f[0]+f[2])/2*s)):Math.min(W-s,R-f[2]*s);"
 "y=Math.min(0,Math.max(Hv*.5-(f[1]+f[3])/2*ih,Hv*.12-f[1]*ih))}}"
 "var fl=Math.max(2,Math.min(30,f[0]*100-1)),fr=Math.max(2,Math.min(18,(1-f[2])*100-1));"
 "var a=x>0?'transparent 0,#000 '+fl.toFixed(1)+'%':'#000 0',b=x+s<W-1?'#000 '+(100-fr).toFixed(1)+'%,transparent 100%':'#000 100%';"
 "var v=y+ih<Hb-1?'linear-gradient(180deg,#000 '+Math.max(0,(Hv-y)/ih*100).toFixed(1)+'%,transparent 100%)':'';"
 "var m=cov&&!v?'none':[cov?'':'linear-gradient(90deg,'+a+','+b+')',v].filter(Boolean).join(',');"
 "var k=m.indexOf('),linear')>0?'intersect':'add';"
 "im.style.cssText+=';inset:auto;left:'+x.toFixed(1)+'px;top:'+y.toFixed(1)+'px;width:'+s.toFixed(1)+'px;height:'+ih.toFixed(1)+'px;background-size:100% 100%;background-position:0 0;-webkit-mask-image:'+m+';mask-image:'+m+';mask-composite:'+k+';-webkit-mask-composite:'+(k=='intersect'?'source-in':'source-over');"
 "});})();</script>")  # once, at the end of body: band sizes are fixed print px; the web fit zooms afterwards
# Fit the print-width layout into the viewport (pinch/scroll still ok). Zoom only #kr-poster-scale so the server's
# .kr-poster-chrome can float on the real viewport. Never set overflow-x on html/body — Chromium then treats
# position:fixed like absolute. Clip h-scroll on #kr-poster-clip around the scale wrapper instead.
FIT_JS=('<script id="kr-poster-fit">(function(){'
 'function ensureWrap(){var scale=document.getElementById("kr-poster-scale"),clip=document.getElementById("kr-poster-clip");'
 'if(scale){if(!clip){clip=document.createElement("div");clip.id="kr-poster-clip";if(scale.parentNode)scale.parentNode.insertBefore(clip,scale);clip.appendChild(scale);}return scale;}'
 'scale=document.createElement("div");scale.id="kr-poster-scale";clip=document.createElement("div");clip.id="kr-poster-clip";'
 'var keep=new Set(),chrome=document.querySelector(".kr-poster-chrome");'
 'if(chrome){keep.add(chrome);var sib=chrome.nextElementSibling,taken=0;while(sib&&taken<2&&(sib.tagName==="STYLE"||(sib.tagName==="SCRIPT"&&sib.id!=="kr-poster-fit"))){keep.add(sib);taken++;sib=sib.nextElementSibling;}}'
 'var fitEl=document.getElementById("kr-poster-fit");if(fitEl)keep.add(fitEl);keep.add(clip);'
 'var nodes=[].slice.call(document.body.childNodes),placed=0;'
 'nodes.forEach(function(n){if(n.nodeType===1&&(keep.has(n)||n.id==="kr-poster-scale"||n.id==="kr-poster-clip"))return;'
 'if(!placed){document.body.insertBefore(clip,n);clip.appendChild(scale);placed=1;}scale.appendChild(n);});'
 'if(!placed){document.body.insertBefore(clip,document.body.firstChild);clip.appendChild(scale);}return scale;}'
 'function printW(scale,b){var w=parseInt(scale.dataset.printW,10);if(w)return w;w=parseInt(b.style.width,10)||parseInt(getComputedStyle(b).width,10)||2400;scale.dataset.printW=String(w);return w;}'
 'function fit(){var scale=ensureWrap(),clip=document.getElementById("kr-poster-clip"),r=document.documentElement,b=document.body,W=printW(scale,b),s=Math.min(1,r.clientWidth/W);'
 'r.style.width="100%";r.style.maxWidth="100%";b.style.width="100%";b.style.maxWidth="100%";'
 'if(clip){clip.style.width="100%";clip.style.maxWidth="100%";clip.style.overflowX="hidden";clip.style.boxSizing="border-box";}'
 'scale.style.width=W+"px";scale.style.maxWidth=W+"px";scale.style.boxSizing="border-box";'
 'if("zoom" in scale.style){scale.style.zoom=s;scale.style.transform="";scale.style.marginBottom="";}'
 'else{scale.style.transform="scale("+s+")";scale.style.transformOrigin="top left";var h=scale.offsetHeight||scale.scrollHeight||0;scale.style.marginBottom=(h?(s-1)*h:0)+"px";}}'
 'function boot(){fit();addEventListener("resize",fit);}'
 'if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",boot);else boot();'
 '})();</script>')

class Build:
  def __init__(s,instance,chrome=None):
    from PIL import Image
    s.Image=Image;s.I=os.path.abspath(instance);s.U=os.path.join(s.I,'uploads')
    s.OUT=os.path.join(s.I,'poster');s.CACHE=os.path.join(s.OUT,'cache');s.WORK=os.path.join(s.OUT,'.build')
    for d in (s.OUT,s.CACHE,s.WORK):os.makedirs(d,exist_ok=True)
    s.D=s.json(os.path.join(s.I,'roster.json'),None)
    if not s.D:raise SystemExit('没有 roster.json：'+s.I)
    s.S=s.json(os.path.join(s.I,'site.json'),{});s.ev=s.S.get('event') or {};s.P=s.S.get('poster') or {};s.B=s.S.get('brand') or {}
    s.M=s.json(os.path.join(s.U,'map.json'),{});s.chrome=chrome
    s.css=open(os.path.join(R,'poster.css'),encoding='utf-8').read()
  @staticmethod
  def json(p,d):
    try:
      with open(p,encoding='utf-8') as f:return json.load(f)
    except Exception:return d
  def up(s,kind,name):
    """Absolute path of an uploaded file, or '' (names come from the roster: never leave uploads/)."""
    if not name or not re.fullmatch(r'[\w.-]+',name):return ''
    p=os.path.join(s.U,kind,name);return p if os.path.isfile(p) else ''
  def cover(s,g):return s.up('covers',g.get('cover'))
  def portrait(s,g,m):
    p=s.M.get(f"{g['name']}|{m.get('character','')}") or ''
    p=p.split('?')[0];f=os.path.join(s.U,p)
    return f if p.startswith('portraits/') and '..' not in p and os.path.isfile(f) else ''
  def bust(s,src):
    """Crop a portrait to a 4:5 bust (440×550). Faces are assumed in the upper third; white-pads the edges."""
    key=hashlib.md5(open(src,'rb').read()+b'bust-v2').hexdigest()[:12];out=os.path.join(s.CACHE,key+'.jpg')
    if os.path.exists(out):return out
    im=s.Image.open(src).convert('RGB');W,H=im.size
    bw=min(W,H)*.92;y=bw*.42;bh=bw*1.25;l=W/2-bw/2;t=min(max(0,y-bh*.40),max(0,H-bh))
    c=s.Image.new('RGB',(int(bw),int(bh)),'white');box=(max(0,int(l)),int(t),min(W,int(l+bw)),min(H,int(t+bh)))
    c.paste(im.crop(box),(box[0]-int(l),0))
    c.resize((440,550),s.Image.LANCZOS).save(out,quality=90);return out
  @staticmethod
  def pending(m):
    mem=(m.get('member') or '').strip()
    return (not mem) or mem in ('待定','TBD','tbd','—','-','？','?')
  def settled(s,g):return [m for m in g['members'] if not s.pending(m)]
  @staticmethod
  def crew(g):return (g.get('kind') or 'cast')=='crew'
  def card(s,g,m,photo=False):
    p=s.portrait(g,m);b=(p if photo else s.bust(p)) if p else None
    img=f'<img src="file://{b}">' if b else f'<div class="cam">{CAM}</div>'
    mem=(m.get('member') or '').strip() or '待定'
    role=('<i>'+CAM+'</i>' if photo else '')+E(m.get('character',''))
    return f'<div class="card{" ph" if photo else ""}"><div class="art">{img}</div><div class="tx"><div class="role">{role}</div><div class="mem">{E(mem)}</div></div></div>'
  @staticmethod
  def span(n):return 4 if n<=4 or 9<=n<=12 else 8
  def focus(s,g):
    f=g.get('cover_focus')
    return tuple(float(v) for v in f) if isinstance(f,list) and len(f)==4 else DEFAULT_FOCUS
  def section(s,g,cols):
    photo=s.crew(g);cvp=s.cover(g);ms=s.settled(g);tall=False
    if cvp:
      w,h=s.Image.open(cvp).size;tall=h>w;f=s.focus(g)
      fp=f"{(f[0]+f[2])*50:.1f}% {(f[1]+f[3])*50:.1f}%"     # no-JS fallback: cover, centred on the focus box
      bg=(f'<div class="bg" data-ar="{w/h:.4f}" data-face="{",".join(f"{v:.3f}" for v in f)}">'
          f'<div class="im" style="background-image:url(\'file://{cvp}\');background-position:{fp}"></div></div>')
    else:bg='<div class="bg sky"></div>'
    h2=(CAM_H2 if photo else '')+E(g['name'])
    return (f'<section class="{"tall" if tall else ""}" style="--c:{g["color"]};--cols:{cols};grid-column:span {cols}">{bg}<div class="ov"></div>'
            f'<header><div class="hd"><h2>{h2}</h2><span class="ct">{len(ms)} 人</span></div></header>'
            f'<div class="grid">{"".join(s.card(g,m,photo) for m in ms)}</div></section>')
  def logo(s):
    p=s.up('brand',s.B.get('logo'));return f'<img class="brandlogo" src="file://{p}">' if p else ''
  def hero(s):return s.up('brand',s.P.get('hero'))
  def page(s,body,cls,w):
    h=s.hero();decl=f"--hero:url('file://{h}');" if h else ''
    return f'<!doctype html><html><head><meta charset="utf-8"><style>{s.css}</style></head><body class="{cls}" style="width:{w}px;{decl}"><div class="sky-bg">{FEATHER*3}</div>{body}{FRAME_JS}</body></html>'
  def title(s):
    h=s.hero();tiles=f'<div class="tbg" style="background-image:url(\'file://{h}\')"></div>' if h else ''
    meta=''.join(f'<span>{E(x)}</span>' for x in (s.ev.get('date'),s.ev.get('location')) if x)
    meta=meta.replace('</span><span>','</span><b></b><span>')
    return f'<div class="title"><div class="tbgs" data-n="1">{tiles}</div><div class="tov"></div><div class="tplate"><h1>{s.logo()}{E(s.ev.get("title") or "")}</h1><div class="meta">{meta}</div></div></div>'
  def render(s,name,doc,w,h=None):
    from playwright.sync_api import sync_playwright
    from PIL import Image
    f=os.path.join(s.WORK,name+'.html');open(f,'w',encoding='utf-8').write(doc)
    with sync_playwright() as p:
      kw={'args':['--no-sandbox','--allow-file-access-from-files']}
      if s.chrome:kw['executable_path']=s.chrome
      b=p.chromium.launch(**kw)
      pg=b.new_page(viewport={'width':w,'height':h or 1000},device_scale_factor=2);pg.goto('file://'+f)
      pg.wait_for_load_state('networkidle');pg.evaluate('document.fonts.ready');pg.wait_for_timeout(500)
      pg.evaluate('''()=>{for(const e of document.querySelectorAll('.mem,.role')){let f=parseFloat(getComputedStyle(e).fontSize),m=f*.45;while(e.scrollWidth>e.clientWidth+1&&f>m){f-=1;e.style.fontSize=f+'px'}}}''')
      bad=pg.evaluate("""[...document.querySelectorAll('.mem,.role,h2')].filter(e=>e.scrollWidth>e.clientWidth+1).map(e=>e.textContent)""")
      H=h or pg.evaluate('document.documentElement.scrollHeight')
      if h:png=Image.open(io.BytesIO(pg.screenshot(clip={'x':0,'y':0,'width':w,'height':h})))
      else:
        Image.MAX_IMAGE_PIXELS=None;pg.set_viewport_size({'width':w,'height':1600});png=Image.new('RGB',(w*2,H*2),'white')
        for y in range(0,H,1600):
          hh=min(1600,H-y);png.paste(Image.open(io.BytesIO(pg.screenshot(clip={'x':0,'y':y,'width':w,'height':hh},full_page=True))),(0,y*2))
      b.close()
    png.convert('RGB').save(os.path.join(s.OUT,name+'.jpg'),quality=88,optimize=True)
    print(name,w,'x',H,'still clipped:',bad or 'none',flush=True)
    return f
  def web(s,src,dst):
    """Print HTML → the page the site serves: file:// paths to URLs, viewport meta, fit-to-screen script."""
    h=open(src,encoding='utf-8').read()
    for a,b in ((f'file://{s.U}/covers/','/covers/'),(f'file://{s.U}/portraits/','/portraits/'),(f'file://{s.U}/brand/','/brand/'),(f'file://{s.CACHE}/','/poster/cache/')):h=h.replace(a,b)
    h=h.replace('<meta charset="utf-8">','<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">',1)
    h=h.replace('position:relative;overflow:hidden}','position:relative;overflow:auto}',1)
    h=h.replace('</body>',FIT_JS+'</body>',1)
    open(os.path.join(s.OUT,dst),'w',encoding='utf-8').write(h)
  def prune(s):
    """Drop crops no published page references (re-uploaded portraits)."""
    used=set()
    for n in ('master.html','wide.html'):
      f=os.path.join(s.OUT,n)
      if os.path.exists(f):used|=set(re.findall(r'/poster/cache/([0-9a-f]{12}\.jpg)',open(f,encoding='utf-8').read()))
    if used:
      for n in os.listdir(s.CACHE):
        if n.endswith('.jpg') and n not in used:os.remove(os.path.join(s.CACHE,n))
  def master(s):
    body=s.title()+'<div class="wrap">'+''.join(s.section(g,s.span(len(s.settled(g)))) for g in s.D['groups'])+'</div>'
    s.web(s.render('master',s.page(body,'master',2400),2400),'master.html')
  def wide(s):
    C=8;cols=[[] for _ in range(C)];hs=[0]*C
    for g in s.D['groups']:
      i=hs.index(min(hs));cols[i].append(s.section(g,3));hs[i]+=0.8+math.ceil(len(s.settled(g))/3)*1.6
    body=s.title()+'<div class="wrap">'+''.join('<div class="col">'+''.join(c)+'</div>' for c in cols)+'</div>'
    s.web(s.render('wide',s.page(body,'wide',3840),3840),'wide.html')
  def social(s,name=None):
    gs=[g for g in s.D['groups'] if not name or g['name']==name]
    if not gs:raise SystemExit('没有这个团：'+str(name))
    g=gs[0];cvp=s.cover(g)
    ban=f'<div class="ban" style="background-image:url(\'file://{cvp}\')"></div>' if cvp else '<div class="ban sky"></div>'
    eyebrow='　'.join(E(x) for x in (s.ev.get('title'),s.ev.get('date')) if x)
    body=(f'<div class="wt" style="--c:{g["color"]}">{ban}<div class="wtx"><div class="eyebrow">{eyebrow}</div><h1>{E(g["name"])}</h1></div></div>'
          f'<section class="solo" style="--c:{g["color"]};--cols:5"><div class="grid">{"".join(s.card(g,m) for m in s.settled(g))}</div></section>')
    s.render('social',s.page(body,'social',1080),1080,1350)
def main(argv):
  ap=argparse.ArgumentParser(description='生成一图流');ap.add_argument('variants',nargs='*',help='master / wide / social')
  ap.add_argument('--instance',default=os.environ.get('CASTCALL_INSTANCE') or os.path.join(ROOT,'instance'))
  ap.add_argument('--chrome',default=os.environ.get('CASTCALL_CHROME') or None,help='Chrome/Chromium 路径；默认用 playwright install chromium 装的那个')
  ap.add_argument('--group',help='social 版式用哪个团（默认第一个）')
  a=ap.parse_args(argv)
  bad=[v for v in a.variants if v not in ('master','wide','social')]
  if bad:ap.error('版式只能是 master / wide / social：'+' '.join(bad))
  b=Build(a.instance,a.chrome)
  # 和 server.mode() 一致：工作组不算「另一个团」
  casts=sum(1 for g in b.D['groups'] if (g.get('kind') or 'cast')!='crew')
  v=a.variants or (['master','social'] if casts==1 else ['master','wide'])
  for x in v:
    if x=='social':b.social(a.group)
    else:getattr(b,x)()
  b.prune();print('done',' '.join(v),'→',b.OUT,flush=True)
  return 0
if __name__=='__main__':sys.exit(main(sys.argv[1:]))
