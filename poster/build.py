#!/usr/bin/env python3
"""一图流：把名册排成一张大海报（网页版 + JPG）。可选功能，需要 Pillow 和 Playwright：

  pip install -r requirements-poster.txt && playwright install chromium

  python3 poster/build.py                      # 按团数自动：多团 master + wide，单团 master + social
  python3 poster/build.py master wide social   # 指定版式
  python3 poster/build.py --instance /path/to/instance --chrome /usr/bin/google-chrome

版式
  master    2400 宽（多团：横条；单团：阵容长卷）
  wide      3840 宽，多列瀑布（电脑 / 投屏，只有多团）
  portrait  1200 宽的竖版（手机网页用）
  social    1080 宽（社交平台配图；--group 指定团，默认第一个）

单团不套多团那套「一个团 = 一张白卡 + 封面标题条 + 卡片网格」：一个团的时候那张白卡
就是整张海报，读起来像把多团版删到只剩一个团。单团的三个画布都走 lineup()——封面铺满
顶部当背景、标题压在画上、立绘从背景里站出来压住封面下沿、名字排在纸面上（没有卡片），
工作组在底部排成一行署名。

产物写进 <instance>/poster/：master.html portrait.html wide.html（网站 /poster/ 直接用）、
master.jpg wide.jpg social.jpg、cache/（立绘裁切）。
后台的「生成一图流」按钮就是在跑这个脚本。

只读 instance 里的 roster.json、site.json、uploads/；
还没定人的席位（空 / 待定 / TBD）也画，画成虚线 + 「招募中」——招募海报最该露的就是还在招的那几席。
封面铺满团的标题条（不是缩成一块贴上去），裁到哪儿由组里的 "cover_focus":[x0,y0,x1,y1] 决定
（0–1 的比例，通常框住人物的眉毛到下巴）：框的中心定横向，框的上沿附近定纵向。没写就用
[0.1,0.1,0.9,0.5]。竖版封面铺进横条必然要裁掉大半高度，这是取舍，不是 bug。"""
import argparse,glob,hashlib,html,io,json,math,os,re,sys
R=os.path.dirname(os.path.abspath(__file__));ROOT=os.path.dirname(R)
E=html.escape
CAM='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M4 8h3l1.6-2.2h6.8L17 8h3a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1z"/><circle cx="12" cy="13.2" r="3.6"/></svg>'
CAM_H2="<i class='hc'>"+CAM+"</i>"
FEATHER='<svg class="fe" viewBox="0 0 100 300"><path d="M50 290 C48 200 40 120 50 10 C70 80 80 160 52 250 M50 60 C30 90 22 140 30 190 M50 60 C70 95 76 140 70 185" fill="none" stroke="#fff" stroke-width="2" opacity=".55"/></svg>'
DEFAULT_FOCUS=(.1,.1,.9,.5)
# Covers the whole title band with the group's cover (every .bg[data-face]), after measuring the band's
# real size: the cover is scaled to max(band width, band height × aspect), so it always fills width and
# height and the only remaining question is where to crop. That is decided by cover_focus — horizontally
# by the box's centre, vertically by the box's upper 15% (a face sits in the upper half of a standing
# portrait, so centring on the box crops the top of the head). The bottom still fades into the cards
# when the art stops short of .bg; portrait covers run on under the cards.
# Earlier versions fitted the box instead of filling the band: the cover shrank to a thumbnail pinned to
# the right of the title with the group colour filling the rest — it read as a sticker on a colour block.
FRAME_JS=("<script id=\"kr-frame\">(function(){"
 "document.querySelectorAll('section>.bg[data-face]').forEach(function(bg){"
 "var im=bg.firstElementChild,sec=bg.parentNode,hd=sec.querySelector('header');"
 "var W=bg.offsetWidth,Hb=bg.offsetHeight,Hv=hd.offsetHeight,ar=+bg.dataset.ar,f=bg.dataset.face.split(',').map(Number);"
 "if(!W||!Hv||!ar)return;"
 # 铺满整条。以前是缩成一个刚好装下 focus 框的小方块，贴到标题右侧：460px 的封面缩到 230px 宽，
 # 左边一半靠品牌色渐变去填空，成品看着像在标题条上贴了张缩略图。封面自己就是这条的底。
 # 只剩一个问题——裁哪儿：横竖都按 focus 框的中心对位，再夹回图内，别露白。
 "var s=Math.max(W,Hb*ar),ih=s/ar;"
 "var x=Math.min(0,Math.max(W-s,W*.5-(f[0]+f[2])*.5*s));"
 # 竖版封面铺进横条，纵向要裁掉七成多：对位不能取 focus 框的正中，那样正好把头顶切掉。
 # 取 focus 框上部三分之一——人脸在上半身构图里就在那儿。
 "var cy=f[1]+(f[3]-f[1])*.15;"
 "var y=Math.min(0,Math.max(Hb-ih,Hv*.5-cy*ih));"
 "var v=y+ih<Hb-1?'linear-gradient(180deg,#000 '+Math.max(0,(Hv-y)/ih*100).toFixed(1)+'%,transparent 100%)':'none';"
 "im.style.cssText+=';inset:auto;left:'+x.toFixed(1)+'px;top:'+y.toFixed(1)+'px;width:'+s.toFixed(1)+'px;height:'+ih.toFixed(1)+'px;background-size:100% 100%;background-position:0 0;-webkit-mask-image:'+v+';mask-image:'+v+';';"
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
 # 背景两层（.sky-bg / .wash）不进缩放壳：它们要铺满视口。跟着缩放的话，海报下面会
 # 出现一条硬边 + 一片空白——「一图流没有背景」有一半是这么来的。
 'var wl=document.querySelector(".wash"),sk=document.querySelector(".sky-bg");if(wl)keep.add(wl);if(sk)keep.add(sk);'
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
 'function fitText(){'
 # 构建时的字号是拿 Chrome + 构建机字体量的，放得下但没余量。团长手机上字体一回落（iPhone 是
 # Songti SC）、再叠 zoom 的亚像素取整，那点余量就没了，nowrap + text-overflow:clip 把最后一个字切掉。
 # 所以在**用户自己的设备上**再量一遍：回到 CSS 字号，收到可用宽度的 97% 以内（下限 45%）。
 # 量的是克隆节点 max-content 的宽度，不能用 scrollWidth——放得下时它等于 clientWidth，会永远判溢出。
 'function tw(e){var c=e.cloneNode(true);'
 'c.style.cssText+="position:absolute;left:-9999px;top:0;width:max-content;max-width:none;overflow:visible;white-space:nowrap";'
 'document.body.appendChild(c);var w=c.getBoundingClientRect().width;c.parentNode.removeChild(c);return w;}'
 'var els=document.querySelectorAll(".role,.mem,.lu-name,.lu-cn");'
 'for(var i=0;i<els.length;i++){var e=els[i];'
 'if(!e.dataset.baseFs){var inl=e.style.fontSize;e.style.fontSize="";'
 'var b=parseFloat(getComputedStyle(e).fontSize)||0;'
 'if(!b){e.style.fontSize=inl;continue;}e.dataset.baseFs=String(b);}'
 'var base=parseFloat(e.dataset.baseFs),f=base,min=base*0.45,guard=0;'
 'e.style.fontSize=base+"px";'
 'while(tw(e)>e.clientWidth*0.97&&f>min&&guard++<80){f-=1;e.style.fontSize=f+"px";}'
 '}}'
 'function boot(){fit();fitText();'
 'if(document.fonts&&document.fonts.ready)document.fonts.ready.then(fitText);'
 'addEventListener("resize",function(){fit();fitText();});}'
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
    with open(os.path.join(R,'poster.css'),encoding='utf-8') as f:s.css=f.read()
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
  def portrait_file(s,g,m):
    """这个席位配的立绘文件（portrait() 版式方法的名字要留给版式本身）。"""
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
  def credit(s,g,m):
    """工作组的「名牌」：徽章 + 姓名 + 职务。

    工作组没有立绘位。以前它跟 coser 用同一套卡片，空出来的 16:10 图位里就摆一个
    满屏的相机线稿——那是占位符，不是内容；职务文字前面还有一个同样的小相机，
    一卡两图标，看着像三张没传完的图。名牌把版位还给「谁在做什么」这件事本身。"""
    p=s.portrait_file(g,m);vac=s.pending(m)
    mem='招募中' if vac else (m.get('member') or '').strip()
    bdg=f'<img src="file://{p}">' if p else CAM
    return (f'<div class="card crew{" vac" if vac else ""}">'
            f'<span class="bdg">{bdg}</span>'
            f'<div class="tx"><div class="mem">{E(mem)}</div>'
            f'<div class="role">{E(m.get("character",""))}</div></div></div>')
  def card(s,g,m,photo=False):
    """一张卡。member 是空 / 待定 的席位照样画出来，只是标成「招募中」：
    招募海报最该露的就是还在招的那几席。以前把它们整个藏掉，5 席里定 2 席时
    整张图就剩两张卡 —— 版面空掉一半，看着像没做完。

    工作组又不一样：没传工作照时走 credit()，不占立绘位；传了才用照片卡。"""
    p=s.portrait_file(g,m)
    if photo and not p:return s.credit(g,m)
    b=(p if photo else s.bust(p)) if p else None
    vac=s.pending(m)
    img=f'<img src="file://{b}">' if b else f'<div class="cam">{CAM}</div>'
    mem=(m.get('member') or '').strip()
    role=('<i>'+CAM+'</i>' if photo else '')+E(m.get('character',''))
    if vac:
      mem='招募中';cls='card vac'+(' ph' if photo else '')
    else:cls='card'+(' ph' if photo else '')
    return f'<div class="{cls}"><div class="art">{img}</div><div class="tx"><div class="role">{role}</div><div class="mem">{E(mem)}</div></div></div>'
  @staticmethod
  def seats(g):return g.get('members') or []
  @staticmethod
  def span(n):
    """（团，几张卡）→ 这个团占 8 列里的几列、里面排几列。
    卡宽永远约等于 1 列：定了 5 席就占 5 列，而不是占满 8 列、让后 3 列空着。"""
    return n if n<=8 else 8
  def focus(s,g):
    f=g.get('cover_focus')
    return tuple(float(v) for v in f) if isinstance(f,list) and len(f)==4 else DEFAULT_FOCUS
  def section(s,g,cols,span=None,cw=False):
    """cw：这一段的卡片够宽（竖版整行 / 宽版多列），工作组的名牌可以横过来摆。
    master 的 crew 段只有两列、每张 220 宽，那里必须竖着。"""
    photo=s.crew(g);cvp=s.cover(g);ms=s.seats(g);tall=False;span=span or cols
    if cvp:
      w,h=s.Image.open(cvp).size;tall=h>w;f=s.focus(g)
      fp=f"{(f[0]+f[2])*50:.1f}% {(f[1]+f[3])*50:.1f}%"     # no-JS fallback: cover, centred on the focus box
      bg=(f'<div class="bg" data-ar="{w/h:.4f}" data-face="{",".join(f"{v:.3f}" for v in f)}">'
          f'<div class="im" style="background-image:url(\'file://{cvp}\');background-position:{fp}"></div></div>')
    else:bg='<div class="bg sky"></div>'
    h2=(CAM_H2 if photo else '')+E(g['name'])
    n=len(ms);got=len([m for m in ms if not s.pending(m)])
    ct=f'{got}/{n} 人' if got<n else f'{n} 人'
    cls=' '.join(x for x in ('tall' if tall else '','cw' if cw and photo else '','cr' if photo else '') if x)
    return (f'<section class="{cls}" style="--c:{g["color"]};--cols:{cols};grid-column:span {span}">{bg}<div class="ov"></div>'
            f'<header><div class="hd"><h2>{h2}</h2><span class="ct">{ct}</span></div></header>'
            f'<div class="grid">{"".join(s.card(g,m,photo) for m in ms)}</div></section>')
  def logo(s):
    p=s.up('brand',s.B.get('logo'));return f'<img class="brandlogo" src="file://{p}">' if p else ''
  def hero(s):
    """整页底图：团长传了海报底图就用它；没传就用第一个团的封面，糊成一片颜色。
    以前没有 hero 就只剩一层蓝色渐变 —— 一图流看着"没背景"，就是这么来的。"""
    p=s.up('brand',s.P.get('hero'))
    if p:return p,False
    for g in s.D.get('groups') or []:
      c=s.cover(g)
      if c:return c,True
    return '',False
  def page(s,body,cls,w):
    h,soft=s.hero();decl='' if soft else (f"--hero:url('file://{h}');" if h else '')
    # 磨砂底放在 .sky-bg 之后：底图要在那层淡蓝渐变**上面**才看得见，否则被 .82 的白色盖掉。
    # 图走 CSS 变量而不是 background-image：直接写在 .wash 上，元素自己也会把 460px 的封面
    # 按默认 repeat 平铺一遍，糊层再半透明，底下就是一片重复的人脸。
    wash='<div class="wash" style="--img:url(\'file://%s\')"><i class="wf"></i></div>'%h if soft else ''
    return f'<!doctype html><html><head><meta charset="utf-8"><style>{s.css}</style></head><body class="{cls}" style="width:{w}px;{decl}"><div class="sky-bg">{FEATHER*3}</div>{wash}{body}{FRAME_JS}</body></html>'
  def title(s):
    h,soft=s.hero()
    tiles=f'<div class="tbg{" soft" if soft else ""}" style="background-image:url(\'file://{h}\')"></div>' if h else ''
    meta=''.join(f'<span>{E(x)}</span>' for x in (s.ev.get('date'),s.ev.get('location')) if x)
    meta=meta.replace('</span><span>','</span><b></b><span>')
    return f'<div class="title{" soft" if soft else ""}"><div class="tbgs" data-n="1">{tiles}</div><div class="tov"></div><div class="tplate"><h1>{s.logo()}{E(s.ev.get("title") or "")}</h1><div class="meta">{meta}</div></div></div>'
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
      # 量**文字本身**的宽度再和可用宽度比。以前用 scrollWidth>clientWidth+1：overflow:hidden 时
      # 放得下 scrollWidth 就等于 clientWidth，容差只剩 1px，构建机 Chrome + 本机 Noto 量着刚好够，
      # 换台设备字体一回落就切字。也不能拿 scrollWidth 乘系数——放得下时它恒等于 clientWidth，
      # 会把所有卡片判成溢出（整张图矮一截）。
      pg.evaluate('''()=>{
        const tw=e=>{const c=e.cloneNode(true);
          c.style.cssText+="position:absolute;left:-9999px;top:0;width:max-content;max-width:none;overflow:visible;white-space:nowrap";
          document.body.appendChild(c);const w=c.getBoundingClientRect().width;c.remove();return w};
        for(const e of document.querySelectorAll(".mem,.role,.lu-name,.lu-cn")){
          let f=parseFloat(getComputedStyle(e).fontSize),m=f*.45;
          while(tw(e)>e.clientWidth*.97&&f>m){f-=1;e.style.fontSize=f+"px"}
        }}''')
      bad=pg.evaluate("""[...document.querySelectorAll('.mem,.role,h2,.lu-name,.lu-cn')].filter(e=>e.scrollWidth>e.clientWidth+1).map(e=>e.textContent)""")
      # 标题条有没有被封面铺满，也要量：FRAME_JS 一旦退回「缩成方块贴到右边」，
      # 左边靠品牌色渐变填空，成品像贴纸，可上面所有断言都是绿的。
      gap=pg.evaluate("""()=>[...document.querySelectorAll('section>.bg[data-face]>.im')].filter(im=>{
        const b=im.getBoundingClientRect(),s=im.parentNode.getBoundingClientRect();
        return b.left>s.left+1.5||b.right<s.right-1.5
      }).map(im=>(im.parentNode.parentNode.querySelector('h2')||{}).textContent||'?')""")
      # 单团阵容没有 section（封面是整页的 .lu-hero），别把「没有标题条」报成「铺满了」
      nsec=pg.evaluate("()=>document.querySelectorAll('section>.bg').length")
      # 量高度时把每个 section 的底边也算进来：body 是 overflow:hidden（网页版才放开），
      # 个别版式下 scrollHeight 会比最后一个卡片矮几十像素，导出图的最后一排就被切掉。
      H=h or pg.evaluate('''()=>Math.max(document.documentElement.scrollHeight,document.body.scrollHeight,
        ...[...document.querySelectorAll('section')].map(e=>Math.ceil(e.getBoundingClientRect().bottom)+24))''')
      if h:png=Image.open(io.BytesIO(pg.screenshot(clip={'x':0,'y':0,'width':w,'height':h})))
      else:
        Image.MAX_IMAGE_PIXELS=None;pg.set_viewport_size({'width':w,'height':1600});png=Image.new('RGB',(w*2,H*2),'white')
        for y in range(0,H,1600):
          hh=min(1600,H-y);png.paste(Image.open(io.BytesIO(pg.screenshot(clip={'x':0,'y':y,'width':w,'height':hh},full_page=True))),(0,y*2))
      b.close()
    png.convert('RGB').save(os.path.join(s.OUT,name+'.jpg'),quality=88,optimize=True)
    # 收到 45% 还放不下的只有「角色名太长」这一种情况：报出来，让团长知道该改短，而不是以为图坏了
    print(name,w,'x',H,'cover band:',(' / '.join(gap)+'   ← 标题条没铺满') if gap else ('—' if not nsec else 'full'),
          '| still clipped:',(' / '.join(bad)+'   ← 名字太长，字号已经收到下限') if bad else 'none',flush=True)
    return f
  def web(s,src,dst):
    """Print HTML → the page the site serves: file:// paths to URLs, viewport meta, fit-to-screen script."""
    h=open(src,encoding='utf-8').read()
    for a,b in ((f'file://{s.U}/covers/','/covers/'),(f'file://{s.U}/portraits/','/portraits/'),(f'file://{s.U}/brand/','/brand/'),(f'file://{s.CACHE}/','/poster/cache/')):h=h.replace(a,b)
    h=h.replace('<meta charset="utf-8">','<meta charset="utf-8"><link rel="icon" href="/favicon.svg" type="image/svg+xml"><meta name="viewport" content="width=device-width, initial-scale=1">',1)
    # iOS Safari 会按列宽自动放大字号（font boosting）；放大后 nowrap 的名字就溢出被切
    # 网页版：背景铺满一屏、海报在竖直方向居中。手机上面板宽 390、海报 2400 宽，
    # 按宽适配后只有 200 出头高 —— 顶在最上面看着就是「图掉在一大片空地里」。
    # 居中用 margin:auto（不是 justify-content:center）：内容比视口高时 auto 会退成 0，不会切顶。
    # #kr-poster-clip 要抬到背景之上：它里面的 zoom 让整个海报落进一个 z-index:auto 的
    # 层里，不抬的话 z-index:0 的 .wash 会盖在海报上面（整张图像蒙了一层雾）。
    h=h.replace('</head>','<style>html{-webkit-text-size-adjust:100%;text-size-adjust:100%;background:#fbfcfe}'
                'body{min-height:100vh;display:flex;flex-direction:column}'
                '.sky-bg,.wash{position:fixed}'
                '#kr-poster-clip{position:relative;z-index:1;margin-top:auto;margin-bottom:auto}'
                # 竖版比一屏高，海报从页面顶上开始，左上角那两个悬浮按钮（返回名单 / 导出图片）
                # 正好压住标题玻璃板的左半边。给 body 留出一条和按钮同高的 header 带：
                # 内容从按钮下面开始，滚动时按钮照旧浮在上面。
                'body.portrait{padding-top:104px}'
                # 画布固定 1200 宽、靠 transform 缩放，所以版式不随窗口变——只有媒体查询能分叉。
                # 屏幕够宽（平板 / 桌面窗口）时把 5 席以上的团改排 3 列：卡片小一圈、整幅短一截。
                # 这段只加在网页版，导出的 jpg 仍是 2 列。
                '@media (min-width:640px){body.portrait .c2>.grid>.card{flex-basis:calc((100% - 40px)/3)}}'
                # 标题带自己那层底图（.tbgs）在网页上会变成一块独立的暖色矩形：上边是页面的模糊底，
                # 中间突然换了一段更艳的图，下边又切回底色——团长说的「背景一刀切」就是它。
                # 网页版直接不画这一层，整页只剩一层 .wash，从上到下连续；标题玻璃板直接浮在上面。
                # 导出的 jpg 保留这层（海报需要标题带的气口），网页版交给页面背景。
                '.title .tbgs{display:none}'
                '</style></head>',1)
    h=h.replace('position:relative;overflow:hidden}','position:relative;overflow:auto}',1)
    h=h.replace('</body>',FIT_JS+'</body>',1)
    open(os.path.join(s.OUT,dst),'w',encoding='utf-8').write(h)
  def prune(s,built=None):
    """Drop crops no published page references (re-uploaded portraits).

    顺带清掉「已经不生成的那一版」：团数从多个掉到单个之后，上一轮留下的 wide.html 还在，
    /poster/ 的挑选脚本看见 wide.html 就用它——桌面打开还是那张多团旧图，改了像没改。
    （这轮明确要了 wide 就不算遗留。）"""
    if s.single() and 'wide' not in (built or ()):
      for n in ('wide.html','wide.jpg'):
        f=os.path.join(s.OUT,n)
        if os.path.exists(f):os.remove(f)
    used=set()
    for n in ('master.html','portrait.html','wide.html'):
      f=os.path.join(s.OUT,n)
      if os.path.exists(f):used|=set(re.findall(r'/poster/cache/([0-9a-f]{12}\.jpg)',open(f,encoding='utf-8').read()))
    if used:
      for n in os.listdir(s.CACHE):
        if n.endswith('.jpg') and n not in used:os.remove(os.path.join(s.CACHE,n))
  def master(s):
    if s.single():return s.lineup('master')
    def one(g):
      n=len(s.seats(g));cols=n if n<=8 else math.ceil(n/2);span=s.span(n)
      # 工作组至少占 3 列：「摄影 / 后勤」加相机图标，2 列（220px）时标题会顶到右边
      # 的人数胶囊上，卡片也被压成 220 宽的窄条，整段挤成一团。
      if s.crew(g):span=max(span,3)
      return s.section(g,cols,span)
    body=s.title()+'<div class="wrap">'+''.join(one(g) for g in s.D['groups'])+'</div>'
    s.web(s.render('master',s.page(body,'master',2400),2400),'master.html')
  def wide(s):
    # 列数跟着团数走：写死 8 列，两个团的团片就只剩左边四分之一有东西，右边全是空的
    C=max(2,min(8,len(s.D['groups'])));cols=[[] for _ in range(C)];hs=[0]*C
    for g in s.D['groups']:
      n=len(s.seats(g));k=max(2,min(3,n))          # 1 张卡也给 2 列：一列会把卡片拉成一整条
      i=hs.index(min(hs));cols[i].append(s.section(g,k,cw=True));hs[i]+=0.8+math.ceil(n/k)*1.6
    body=s.title()+'<div class="wrap">'+''.join('<div class="col">'+''.join(c)+'</div>' for c in cols)+'</div>'
    s.web(s.render('wide',s.page(body,'wide',3840),3840),'wide.html')
  def portrait(s):
    """手机竖版：画布 1200 宽，一个团占满一行、卡片 2 列（5 席就是 2+2+1）。

    为什么单独一版：master 是 2400×1255 的横条，按宽缩到 390 的手机上只剩 204 高，
    网页再竖直居中，上下各空 320 —— 卡片看着像被挤到屏幕下面。竖版把画布收窄一半，
    字号是绝对 px，相对就放大一倍，高度占比也从 42% 拉到整屏。
    列数跟着席位数：1 席独占一行（一列会把卡拉成长条），5 席给 2 列（3 列每张只剩 117px 宽）。"""
    if s.single():return s.lineup('portrait')
    def one(g):
      n=len(s.seats(g));k=1 if n==1 else (2 if n<=6 else 3)
      # 工作组一人一行：2 列时每张卡在 390 的手机上只有 150px，徽章 + 名字 + 职务挤成
      # 一行；单列后卡宽 560（画布），名字回到和 coser 一样的字号。
      h=s.section(g,1 if s.crew(g) else k,8,cw=True)
      # 5 席以上、画布是 2 列的团，网页版在中等宽度（平板、没最大化的窗口）改排 3 列：
      # 2 列在 880 宽的窗口里每张卡 430px，像把手机页放大了两倍，还要滚两屏半。
      # 只给网页版加这个类，导出的 portrait.jpg 仍是 2 列（发群是在手机上看，列宽才对）。
      # 4 席以下不加：2 列正好排满两行，改成 3 列反而剩一个洞。
      return h.replace('<section class="','<section class="c2 ',1) if k==2 and n>=5 else h
    body=s.title()+'<div class="wrap">'+''.join(one(g) for g in s.D['groups'])+'</div>'
    s.web(s.render('portrait',s.page(body,'portrait',1200),1200),'portrait.html')
  def single(s):return sum(1 for g in s.D['groups'] if not s.crew(g))==1
  @staticmethod
  def lu_cols(n,maxc):
    """单团阵容的列数：优先让最后一行不留孤零零的一张（9 席排 5+4，不排 3+3+3）。"""
    if n<=1:return 1
    for c in range(maxc,1,-1):
      if (c-n%c)%c<=1:return c
    return maxc
  def lineup(s,cls,group=None,crew=True):
    """单团版式：一张连续的舞台，不是「一个团 = 一张白卡 + 封面标题条 + 卡片网格」。

    多团版式里 section 就是「一个团」；单团时那张白卡就是整张海报、卡片网格就是全部内容，
    读起来像把多团版删到只剩一个团。这里换掉三件事：
      · 封面铺满顶部当背景（不是缩进卡片里的标题条），标题直接压在画上；
      · 立绘从背景里站出来、压住封面的下沿，名字排在纸面上——没有卡片、没有边框；
      · 工作组在底部排成一行署名（相机徽章 + 名字 + 职务），不再是一组名牌卡。
    进度用一条细进度条 +「已定 4 / 9 席」，比标题条上那个「4/9 人」胶囊更像招募海报。
    三个画布共用这一套，尺寸变量在 poster.css 里按 .master / .portrait / .social 分。"""
    w=dict(master=2400,portrait=1200,social=1080)[cls]
    maxc=3 if cls=='portrait' else 5
    g=group or next((x for x in s.D['groups'] if not s.crew(x)),s.D['groups'][0])
    ms=s.seats(g);n=len(ms);got=len([m for m in ms if not s.pending(m)])
    cols=(1 if n==1 else (2 if n<=4 else 3)) if cls=='portrait' else s.lu_cols(n,maxc)
    # 封面：团长传了海报底图就用它，否则用这个团的封面。铺满整条，裁哪儿由 cover_focus 定。
    up=s.up('brand',s.P.get('hero'));cvp=up or s.cover(g)
    if cvp:
      if up:pos='center 26%'
      else:
        f=s.focus(g);pos=f"{(f[0]+f[2])*50:.1f}% {(f[1]+f[3])*50:.1f}%"
      st=f"background-image:url('file://{cvp}');background-position:{pos}"
      # 460px 的封面铺到 2400 是 5 倍放大，不糊一层会看到块状噪点；团长自己的高清底图不糊。
      cw=s.Image.open(cvp).size[0]
      if cw<w*.6:st+=f";filter:blur({min(3.2,(w/cw-1)*.55):.1f}px) saturate(1.06);transform:scale(1.02)"
      hero=f'<div class="im" style="{st}"></div>'
    else:hero='<div class="im sky"></div>'
    kick=[x for x in (s.ev.get('title'),s.ev.get('date')) if x]
    if kick and kick[0]==g['name']:kick=kick[1:]          # 活动名和团名一样时不重复一遍
    kicker='　'.join(E(x) for x in kick)
    pct=round(got*100/n) if n else 0
    prog=(f'<div class="lu-prog"><span class="bar"><i style="width:{pct}%"></i></span>'
          f'<span>已定 {got} / {n} 席</span></div>')
    def seat(m):
      p=s.portrait_file(g,m);vac=s.pending(m);b=s.bust(p) if p else ''
      art=f'<img src="file://{b}">' if b else ('' if vac else f'<span class="cam">{CAM}</span>')
      if vac:art+='<span class="lu-vac">招募中</span>'
      cn='待定' if vac else (m.get('member') or '').strip()
      return (f'<div class="lu-seat{" vac" if vac else ""}"><div class="lu-art">{art}</div>'
              f'<div class="lu-name">{E(m.get("character",""))}</div><div class="lu-cn">{E(cn)}</div></div>')
    crew_html=''
    if crew:
      cg=[x for x in s.D['groups'] if s.crew(x)]
      if cg:
        it=[]
        for x in cg:
          for m in s.seats(x):
            p=s.portrait_file(x,m);vac=s.pending(m)
            bdg=f'<img src="file://{p}">' if p else CAM
            nm='招募中' if vac else (m.get('member') or '').strip()
            it.append(f'<span class="lu-credit{" vac" if vac else ""}"><span class="bdg">{bdg}</span>'
                      f'<b>{E(nm)}</b><em>{E(m.get("character",""))}</em></span>')
        crew_html=(f'<div class="lu-crew"><span class="lu-crew-h">{E(" / ".join(x["name"] for x in cg))}</span>'
                   +''.join(it)+'</div>')
    foot=[x for x in (s.ev.get('date'),s.ev.get('location')) if x]
    foot_html=('<div class="lu-foot">'+'<b></b>'.join(f'<span>{E(x)}</span>' for x in foot)+'</div>') if foot else ''
    body=(f'<div class="lu" style="--c:{g["color"]};--cols:{cols}">'
          f'<div class="lu-hero">{hero}<div class="lu-head"><div class="lu-kicker">{kicker}</div>'
          f'<h1>{E(g["name"])}</h1>{prog}</div></div>'
          f'<div class="lu-cast">{"".join(seat(m) for m in ms)}</div>{crew_html}{foot_html}</div>')
    doc=(f'<!doctype html><html><head><meta charset="utf-8"><style>{s.css}</style></head>'
         f'<body class="{cls} lu-page" style="width:{w}px;--c:{g["color"]}">{body}</body></html>')
    src=s.render(cls,doc,w)
    if cls!='social':s.web(src,cls+'.html')
  def social(s,name=None):
    gs=[g for g in s.D['groups'] if not name or g['name']==name]
    if not gs:raise SystemExit('没有这个团：'+str(name))
    s.lineup('social',gs[0],crew=s.single())
def main(argv):
  ap=argparse.ArgumentParser(description='生成一图流');ap.add_argument('variants',nargs='*',help='master / portrait / wide / social')
  ap.add_argument('--instance',default=os.environ.get('CASTCALL_INSTANCE') or os.path.join(ROOT,'instance'))
  ap.add_argument('--chrome',default=os.environ.get('CASTCALL_CHROME') or None,help='Chrome/Chromium 路径；默认用 playwright install chromium 装的那个')
  ap.add_argument('--group',help='social 版式用哪个团（默认第一个）')
  a=ap.parse_args(argv)
  bad=[v for v in a.variants if v not in ('master','portrait','wide','social')]
  if bad:ap.error('版式只能是 master / portrait / wide / social：'+' '.join(bad))
  b=Build(a.instance,a.chrome)
  # 和 server.mode() 一致：工作组不算「另一个团」
  casts=sum(1 for g in b.D['groups'] if (g.get('kind') or 'cast')!='crew')
  v=a.variants or (['master','social','portrait'] if casts==1 else ['master','wide','portrait'])
  for x in v:
    if x=='social':b.social(a.group)
    else:getattr(b,x)()
  b.prune(v);print('done',' '.join(v),'→',b.OUT,flush=True)
  return 0
if __name__=='__main__':sys.exit(main(sys.argv[1:]))
