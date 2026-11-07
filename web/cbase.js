const R=window.ROSTER,$=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const hl=(s,q)=>{s=esc(s);if(!q)return s;const i=s.toLowerCase().indexOf(q);return i<0?s:s.slice(0,i)+'<mark>'+s.slice(i,i+q.length)+'</mark>'+s.slice(i+q.length)};
const hasCN=m=>!!(m&&String(m.member||'').trim());
const total=R.groups.reduce((a,g)=>a+g.members.filter(hasCN).length,0);
let memberFirst=false;
const SITE=window.SITE||{event:{},signup:{},guestbook:{},poster:{}};
/* crew 团（摄影 / 后勤 / 妆娘…）：席位不是角色，不配立绘，文案写「负责」 */
const crew=g=>!!g&&(g.kind||'cast')==='crew',crewOf=name=>crew(R.groups.find(x=>x.name===name));
const signupOn=g=>SITE.signup.enabled!==false&&SITE.signupState==='open'&&(g.signup||'open')==='open';
/* 团的负责人 / 咨询方式 / 说明，显示在展开后的席位上方；单团时就是活动说明 */
function gmeta(g){const r=[];if(g.lead)r.push(`<span><b>团长</b>${esc(g.lead)}</span>`);if(g.contact)r.push(`<span><b>咨询</b>${esc(g.contact)}</span>`);
 return r.length||g.note?`<div class=gmeta>${r.length?`<p class=gm-row>${r.join('')}</p>`:''}${g.note?`<p class=gm-note>${esc(g.note)}</p>`:''}</div>`:''}
/* 招募须知（site.json notice，全站一份，不分团）：单团页 / 报名表 / 缺人看板三处复用同一份数据。
   单团页折叠时优先 must、其次 warn（同 kind 内保持原顺序）取前 3 条；展开后按原顺序铺开。
   报名表只要 must/deny，must 优先占位凑 4 条。看板一行各取 2 条。 */
const NOTICE_RANK={must:0,warn:1,deny:2,info:3};
function noticeHTML(where){const nt=SITE.notice||{},items=nt.items||[];
 if(!nt.enabled||!items.length)return '';
 if(where==='solo'){
  const open=sessionStorage.getItem('kr_notice_open')==='1';
  const show=open?items:items.map((it,idx)=>({it,idx})).sort((a,b)=>(NOTICE_RANK[a.it.kind]-NOTICE_RANK[b.it.kind])||(a.idx-b.idx)).slice(0,3).map(x=>x.it);
  const row=it=>`<p class="notice-item" data-kind="${it.kind}">${esc(it.text)}</p>`;
  const toggle=items.length>3?`<button type="button" class="notice-more" data-notice-toggle>${open?'收起 ▴':'查看全部 '+items.length+' 条 ▾'}</button>`:'';
  return `<div class="notice-block notice-solo${open?' open':''}">${nt.lead?`<p class="notice-lead">${esc(nt.lead)}</p>`:''}<div class="notice-items">${show.map(row).join('')}</div>${toggle}</div>`}
 if(where==='signup'){
  const pool=[...items.filter(it=>it.kind==='must'),...items.filter(it=>it.kind==='deny')],shown=pool.slice(0,4),rest=pool.length-shown.length;
  if(!shown.length)return '';
  const row=it=>`<p class="notice-item" data-kind="${it.kind}">${it.kind==='deny'?'✕ ':'· '}${esc(it.text)}</p>`;
  return `<div class="notice-block notice-signup">${shown.map(row).join('')}${rest>0?`<p class="notice-more">还有 ${rest} 条，见页面须知</p>`:''}</div>`}
 if(where==='board'){
  const musts=items.filter(it=>it.kind==='must'),denies=items.filter(it=>it.kind==='deny'),shown=musts.slice(0,2).concat(denies.slice(0,2));
  if(!shown.length)return '';
  const parts=musts.slice(0,2).map(it=>esc(it.text)).concat(denies.slice(0,2).map(it=>'✕ '+esc(it.text)));
  return `<p class="notice-board">${parts.join(' · ')}${musts.length+denies.length>shown.length?'…':''}</p>`}
 return ''}
const RM=matchMedia('(prefers-reduced-motion: reduce)').matches;
// img('covers/x.jpg') -> CSS image value: versioned url, as image-set(avif, jpeg) when a fresh .avif exists (window.IMGV from chars.js)
const AV=!!(window.CSS&&CSS.supports('background-image',"image-set(url('x.avif') type('image/avif'))"));
function img(p){p=String(p).split('?')[0];const v=(window.IMGV||{})[p];if(!v)return `url('${p}')`;const j=`url('${p}?v=${v[0]}')`;return AV&&v[1]?`image-set(url('${p.slice(0,-4)}.avif?v=${v[1]}') type('image/avif'),${j} type('image/jpeg'))`:j}
function artSrc(p){p=String(p).split('?')[0];const v=(window.IMGV||{})[p];if(!v)return p;return AV&&v[1]?(p.slice(0,-4)+'.avif?v='+v[1]):(p+'?v='+v[0])}
function artWarm(p){if(!p)return;const thumb=p.startsWith('chars/')?p.replace('chars/','chars/thumb/'):p;
 [thumb,p].forEach(x=>{if(artWarm._m[x])return;artWarm._m[x]=1;const im=new Image();im.decoding='async';im.src=artSrc(x)})}
artWarm._m=Object.create(null);
function sheetArt(card,gi,i,u,from){if(!u){card.style.setProperty('--ci','none');card.classList.add('noimg');card.classList.remove('art-in','art-fade');return}
 // Detail hero = full chars/ portrait only (list thumbs are square cutouts — wrong crop on the banner).
 card.classList.remove('noimg','art-in','art-fade');card.style.setProperty('--ci','none');
 if(from)ciLoad(from);
 const still=()=>cur&&cur[0]===gi&&cur[1]===i;
 const paint=fade=>{if(!still())return;card.style.setProperty('--ci',img(u));if(fade)card.classList.add('art-fade');card.classList.add('art-in')};
 const im=new Image();im.decoding='async';
 const morph=!!from;let painted=0;
 im.src=artSrc(u);const cached=im.complete;
 const go=()=>{if(!still()||painted)return;
  // Cached at open: full crop present for whole morph. Late load: wait settle, then fade in (no mid-flight swap/jump).
  if(morph&&!cached){
   const done=e=>{if(e&&e.propertyName&&e.propertyName!=='transform')return;card.removeEventListener('transitionend',done);clearTimeout(t);if(!painted&&still()){painted=1;paint(1)}};
   card.addEventListener('transitionend',done);const t=setTimeout(done,480);return}
  painted=1;paint(0)};
 im.onload=go;if(cached)go()}
// thumbs are attached lazily (card open / press / search) so a closed roster does not download all of them
function ciLoad(r){if(!r)return;const sel='.pill[data-ci],.seat-open[data-ci]';(r.matches&&r.matches(sel)?[r]:r.querySelectorAll(sel)).forEach(p=>{p.style.setProperty('--ci',img(p.dataset.ci));p.removeAttribute('data-ci');
  const v=p.querySelector('.pv[data-pv]');if(v){v.style.setProperty('--pv',img(v.dataset.pv));v.removeAttribute('data-pv')}})}
function ci(gi,i){const g=R.groups[gi],m=g.members[i],c=(window.CHARS||{})[g.name+'|'+m.character];return c||''}
/* 成员本人照片（site.json photos.enabled，审核通过的）：按席位 id 存，服务器已经筛掉换了人的 */
function photoOf(gi,i){const m=R.groups[gi].members[i];return (m&&m.id&&(window.PHOTOS||{})[m.id])||''}
function pill(gi,i,q){const g=R.groups[gi],m=g.members[i];const P=v=>v||'（待定）';const[x,y]=memberFirst?[P(m.member),P(m.character)]:[P(m.character),P(m.member)];
 const u0=ci(gi,i),ua=u0.startsWith('chars/')?u0.replace('chars/','chars/thumb/'):u0,ph=photoOf(gi,i),u=ph||ua;
 /* 有本人照片时它是卡片主图；角色立绘缩成右下角的小圆徽（只有单团的大卡显示，多团胶囊太小） */
 const pv=ph&&ua?`<i class="pv" data-pv="${esc(ua)}"></i>`:'';
 return `<button class="pill${ph?' ph':''}" style="--c:${g.color};--k:${Math.min(i,24)}"${u?` data-ci="${esc(u)}"`:''} data-g="${gi}" data-i="${i}">${u?'<i class="ci">'+pv+'</i>'+(crew(g)?'<i class="ni cam">'+icon('camera',13)+'</i>':''):`<i class="ni">${crew(g)?icon('camera',16):esc([...(m.character||m.member||'?')][0])}</i>`}<span class="a">${hl(x,q)}</span><span class="b">${hl(y,q)}</span></button>`}
/* 单团页：一个团就是整个活动，不需要「点开/收起」。顶部是团的封面和人数，然后是团长、咨询、说明，
   招募中的角色排在最前、直接点「报名」；已定的阵容放后面。多个团时 index.html 走封面卡墙，不用这里。 */
function soloHTML(gi){const g=R.groups[gi],seats=g.members.map((m,i)=>[m,i]);
 const set=seats.filter(([m])=>hasCN(m)),open=seats.filter(([m])=>!hasCN(m)&&(m.character||'').trim()),on=signupOn(g);
 const stat=(n,t,k)=>`<span class="solo-st${k?' '+k:''}"><b>${n}</b>${t}</span>`;
 const seat=(m,i,gj,can)=>{const u0=ci(gj,i),u=u0.startsWith('chars/')?u0.replace('chars/','chars/thumb/'):u0;
  return `<button type="button" class="seat-open" data-g="${gj}" data-i="${i}"${u?` data-ci="${esc(u)}"`:''}>${u?'<i class="ci"></i>':`<i class="ni">${esc([...(m.character||'?')][0])}</i>`}<span class="a">${esc(m.character)}</span><span class="go">${can?'报名 →':'暂停报名'}</span></button>`};
 /* 工作组（摄影 / 后勤 / 妆娘…）不是「另一个团」，但人得在页面上：已定的进胶囊，缺的留报名入口。
    放在已定阵容之后，一个 crew 组一段。 */
 const crewBlock=R.groups.map((c,j)=>[c,j]).filter(([c,j])=>j!==gi&&crew(c)).map(([c,j])=>{
  const cs=c.members.map((m,i)=>[m,i]),cset=cs.filter(([m])=>hasCN(m)),
   copen=cs.filter(([m])=>!hasCN(m)&&(m.character||'').trim()),con=signupOn(c);
  if(!cset.length&&!copen.length)return '';
  return `<h3 class="solo-h">${esc(c.name)}<b>${cset.length}</b></h3>`+
   (cset.length?`<div class="pills">${cset.map(([m,i])=>pill(j,i,'')).join('')}</div>`:'')+
   (copen.length?`<div class="solo-open">${copen.map(([m,i])=>seat(m,i,j,con)).join('')}</div>`:'');
 }).join('');
 return `<section id="solo" style="--c:${g.color}"><header class="solo-hero"><div class="solo-tx">`+
  `<p class="solo-k">CAST CALL${crew(g)?'':' · '+g.members.length+' 个角色'}</p><h2>${esc(g.name)}</h2>`+
  `<p class="solo-sts">${stat(set.length,'已定')}${open.length?stat(open.length,'招募中','hot'):stat('✓','全员已定')}</p></div></header>`+
  `<div class="solo-body"><div class="solo-tools"></div>${gmeta(g)}${noticeHTML('solo')}`+
  (open.length?`<h3 class="solo-h">招募中<b>${open.length}</b>${on?'':'<small>暂停报名</small>'}</h3><div class="solo-open">${open.map(([m,i])=>seat(m,i,gi,on)).join('')}</div>`:'')+
  `<h3 class="solo-h">${crew(g)?'成员':'已定阵容'}<b>${set.length}</b></h3>`+
  (set.length?`<div class="pills">${set.map(([m,i])=>pill(gi,i,'')).join('')}</div>`:`<p class="empty">还没有人，等你来。</p>`)+
  crewBlock+`</div></section>`}
function renderSolo(){const cv=$('#cv');if(!cv)return;
 // 主团 = 第一个非 crew 组；全是 crew 时就退回第一个
 const gi=Math.max(0,R.groups.findIndex(x=>!crew(x)));cv.innerHTML=soloHTML(gi);
 /* 封面不再放在卡片里：整页背景用它（cast.css body.single::before），没封面就用团的主题色渐变 */
 const g=R.groups[gi],bs=document.body.style;bs.setProperty('--solo-c',g.color);bs.setProperty('--solo-img',g.cover?img('covers/'+g.cover):'none');
 /* 宽横幅不能 cover 撑满整屏（cast.css body.single.wide-cover）：量一下图片比例和原图高 */
 document.body.classList.remove('wide-cover');renderSolo._w=null;
 if(g.cover){const im=new Image();im.onload=()=>{const r=im.naturalWidth/im.naturalHeight;if(R.groups[gi]!==g||!(r>2))return;
  renderSolo._w={r,nh:im.naturalHeight};document.body.classList.add('wide-cover');fit()};im.src='covers/'+g.cover}
  /* 横幅从页顶铺到留言区，但最多到团名下 620px（--solo-h；手机页面很长，再高封面会被放大得只剩局部）；--solo-e 是团名徽章下沿，深色压层到这里为止，之后慢慢淡出 */
 const fit=()=>{const h=$('.solo-hero'),gb=$('#guestbook');if(!h)return;const e=Math.ceil(h.getBoundingClientRect().bottom+scrollY+24);bs.setProperty('--solo-e',e+'px');const g=gb&&gb.offsetParent?Math.ceil(gb.getBoundingClientRect().top+scrollY):e+600;bs.setProperty('--solo-h',Math.max(e+240,Math.min(g,e+620))+'px');
  /* 宽横幅的清晰带：铺到团名下沿，但不超过原图高；屏幕比原图还宽时只能按页宽来 */
  const w=renderSolo._w;if(w)bs.setProperty('--solo-bh',Math.round(Math.max(innerWidth/w.r,Math.min(e,w.nh)))+'px')};
 fit();if(!renderSolo._on){renderSolo._on=1;addEventListener('resize',fit);addEventListener('load',fit);document.fonts&&document.fonts.ready.then(fit)}const s=$('#solo');ciLoad(s);fitAll(s)}
const match=(m,q)=>!q||(m.character+'\u0001'+m.member).toLowerCase().includes(q);
let cur=null;
function openSheet(gi,i,dir,from){const g=R.groups[gi],n=g.members.length;if(!n)return;
 if(dir){let guard=n;while(guard--){if(i<0)i=n-1;if(i>=n)i=0;if(hasCN(g.members[i]))break;i+=dir>0?1:-1}}
 else{if(i<0)i=n-1;if(i>=n)i=0}
 cur=[gi,i];const m=g.members[i];
 const seats=g.members.map((_,j)=>j).filter(j=>hasCN(g.members[j]));const at=seats.indexOf(i);
 const tag=at>=0?`${at+1}/${seats.length}`:'空缺';
 const sh=$('#sheet'),card=$('#sheet .card');sh.style.setProperty('--c',g.color);const ua=ci(gi,i),ph=photoOf(gi,i),u=ph||ua;card.style.setProperty('--cp',(window.CHARPOS||{})[g.name+'|'+m.character]||'50% 20%');card.style.setProperty('--dir',dir||0);
 const join=castKind(g.name,m)==='vacant'&&signupOn(g)?`<button type="button" class="cast-join" data-signup>${icon('users',16)}报名</button>`:'';
 const sw=ph&&ua?`<div class="ph-sw" role="group" aria-label="大图"><button type="button" class="on" data-ph="${esc(ph)}">本人</button><button type="button" data-ph="${esc(ua)}">角色</button></div>`:'';
 const up=SITE.photos&&SITE.photos.enabled&&hasCN(m)?`<button type="button" class="ph-up" data-photo>${icon('camera',15)}${ph?'换一张我的照片':'上传我的照片'}</button>`:'';
 card.innerHTML=`<div class="hero${dir?' sl':''}">${sw}</div><div class="in${dir?' sl':''}"><span class="tag">${esc(g.name)} · ${tag}</span><h2 id="sm" data-ph="（待定）">${esc(m.member)}</h2><p class="as">${crew(g)?'负责':'出演角色'}</p><h3 id="sc" data-ph="（无角色）">${esc(m.character)}</h3>${join}${up}<div class="nav"><button class="btn" data-d="-1">${icon('left',18)}上一位</button><button class="btn x" style="--c:#ffe08a;background:#ffe08a">关闭</button><button class="btn" data-d="1">下一位${icon('right',18)}</button></div></div>`;
 // Morph offsets after final card layout (hero+body), not previous empty/old card
 if(from&&!sh.classList.contains('open')){const r=from.getBoundingClientRect();card.style.transition='none';sh.classList.remove('open');const c=card.getBoundingClientRect();card.style.setProperty('--fx',(r.left+r.width/2-(c.left+c.width/2))+'px');card.style.setProperty('--fy',(r.top+r.height/2-(c.top+c.height/2))+'px');card.offsetWidth;card.style.transition=''}
 sheetArt(card,gi,i,u,from);
 $('#sheet').classList.add('open')}
document.addEventListener('pointerenter',e=>{const p=e.target.closest&&e.target.closest('.pill');if(!p)return;artWarm(ci(+p.dataset.g,+p.dataset.i))},true);
document.addEventListener('pointerdown',e=>{const p=e.target.closest('.pill');if(p){ciLoad(p);artWarm(ci(+p.dataset.g,+p.dataset.i))}if(!p||RM)return;const r=p.getBoundingClientRect(),s=Math.max(r.width,r.height)*2.2,d=document.createElement('span');d.className='rp';d.style.cssText=`width:${s}px;height:${s}px;left:${e.clientX-r.left-s/2}px;top:${e.clientY-r.top-s/2}px`;p.appendChild(d);setTimeout(()=>d.remove(),500)});
document.addEventListener('click',e=>{const nt=e.target.closest('[data-notice-toggle]');if(nt){const open=sessionStorage.getItem('kr_notice_open')==='1';try{sessionStorage.setItem('kr_notice_open',open?'0':'1')}catch(err){}if(document.getElementById('solo'))renderSolo();return}
 const p=e.target.closest('.pill');if(p)return openSheet(+p.dataset.g,+p.dataset.i,0,p);
 const so=e.target.closest('.seat-open');if(so){const g=R.groups[+so.dataset.g];if(g&&signupOn(g)&&!document.body.classList.contains('editing'))return openSignup(+so.dataset.g,+so.dataset.i);return openSheet(+so.dataset.g,+so.dataset.i,0,so)}
 if(e.target.closest('#sheet [data-signup]')){if(cur)openSignup(cur[0],cur[1]);return}
 if(e.target.closest('#sheet [data-photo]')){if(cur)openPhoto(cur[0],cur[1]);return}
 const sw=e.target.closest('#sheet .ph-sw button');if(sw){if(sw.classList.contains('on')||!cur)return;sw.parentNode.querySelectorAll('button').forEach(b=>b.classList.toggle('on',b===sw));sheetArt($('#sheet .card'),cur[0],cur[1],sw.dataset.ph);return}
 if(e.target.id=='sheet'||e.target.closest('#sheet .x'))return $('#sheet').classList.remove('open');
 const d=e.target.closest('#sheet [data-d]');if(d)openSheet(cur[0],cur[1]+ +d.dataset.d,+d.dataset.d)});
document.addEventListener('keydown',e=>{if(e.key!=='Escape')return;if(gbOpen()){e.preventDefault();closeGuestbook();return}if(signupOpen()){e.preventDefault();closeSignup();return}if($('#sheet').classList.contains('open'))return $('#sheet').classList.remove('open');if(document.body.classList.contains('casting'))setCast(false)});
// shrink/wrap pill labels that overflow. All pills are processed in lock-step rounds (read every pill, then write every pill)
// so a call costs a handful of layouts instead of one per measurement. Default scope: what is visible (open cards, search, sheet).
function fitAll(root){const P=[];(root?root.querySelectorAll('.pill'):document.querySelectorAll('.cv.open .pill,#res .pill')).forEach(p=>{const a=p.querySelector('.a'),b=p.querySelector('.b');if(a&&b)P.push({p,a,b})});
 const V=P.filter(x=>x.p.offsetParent);// hidden pills keep their (pre)fit
 V.forEach(x=>{x.p.classList.remove('tight');[x.a,x.b].forEach(s=>{s.classList.remove('wrap');s.style.fontSize=''})});
 const ov=s=>s.scrollWidth>s.clientWidth+1;V.forEach(x=>x.f=x.base=parseFloat(getComputedStyle(x.a).fontSize));let L=V;
 for(;;){L=L.filter(x=>x.f>x.base*.75&&((x.oa=ov(x.a))|(x.ob=ov(x.b))));if(!L.length)break;
  L.forEach(x=>{x.f-=.5;if(x.oa||x.a.style.fontSize)x.a.style.fontSize=x.f+'px';if(x.ob||x.b.style.fontSize)x.b.style.fontSize=x.f+'px'})}
 V.filter(x=>ov(x.b)).forEach(x=>x.p.classList.add('tight'));
 for(let k=0;k<3;k++){const W=[];V.forEach(x=>[x.a,x.b].forEach(s=>{if(!s.classList.contains('wrap')&&ov(s))W.push(s)}));if(!W.length)break;W.forEach(s=>s.classList.add('wrap'))}}
let _rz;addEventListener('resize',()=>{clearTimeout(_rz);_rz=setTimeout(()=>fitAll($('#res')),120)});
document.fonts&&document.fonts.ready.then(()=>fitAll());

/* 缺人看板。状态只在这张表上派生，不写回名册，也不改 Notion 同步。
   空缺：有角色（或空行）、成员为空。与 roster_sync.status_of、连线视图「空缺」一致。剧组页药丸不展示空缺；缺人看板里空成员写成「还缺 coser」。
   待定：有成员、角色为空。连线里的「变待定」。status_of 因成员非空会落到「已定」。
   待配图：有角色、不是 crew 团、还没有立绘。与 roster.status_of 一致。默认先收着。
   已定：其余，不进这张表。 */
const CAST_ON={vacant:true,loose:true,art:false};
try{const s=JSON.parse(sessionStorage.getItem('kr_cast_on')||'');if(s&&typeof s==='object'){CAST_ON.vacant=!!s.vacant;CAST_ON.loose=!!s.loose;CAST_ON.art=!!s.art}}catch(e){}
function castKind(work,m){const member=(m.member||'').trim(),character=(m.character||'').trim();
 const hasArt=!!(character&&(window.CHARS||{})[work+'|'+character]);
 const artGap=!!character&&!crewOf(work)&&!hasArt;
 if(!member)return 'vacant';
 if(!character)return 'loose';
 if(artGap)return 'art';
 return 'set'}
function castRows(){const out=[];R.groups.forEach((g,gi)=>g.members.forEach((m,i)=>{const k=castKind(g.name,m);if(k!=='set')out.push({gi,i,g,m,k,order:i+1})}));return out}
function castHex(c){return /^#[0-9a-fA-F]{6}$/.test(c||'')?c:'#888888'}
function castFolio(n){return String(n).padStart(2,'0')}
function castFace(row){const character=(row.m.character||'').trim(),member=(row.m.member||'').trim(),o=castFolio(row.order);
 if(row.k==='vacant')return {title:character||'空席',role:character||'空席',who:'还缺 coser',meta:o+' · 还缺 coser',gap:true};
 if(row.k==='loose')return {title:member||'待定',role:'角色未定',who:member||'待定',meta:o+' · 角色未定',gap:true};
 return {title:character||member||'待配图',role:character||'—',who:member||'—',meta:o+' · '+(member||'立绘未齐'),gap:false}}
function castAv(g,m){const u0=(window.CHARS||{})[g.name+'|'+(m.character||'')]||'',u=u0.startsWith('chars/')?u0.replace('chars/','chars/thumb/'):u0;
 if(u)return `<i class="cast-av" style="--ci:${img(u)}"></i>`;
 if(crew(g))return `<i class="cast-av cast-cam">${icon('camera',18)}</i>`;
 const ch=((m.character||m.member||'席').trim());return `<i class="cast-av cast-mono">${esc([...ch][0]||'席')}</i>`}
function castCover(g){const c=g.cover&&/^[\w.-]+$/.test(g.cover)?img('covers/'+g.cover):'';return c?` style="--img:${c}"`:''}
const CAST_LABEL={vacant:'空缺',loose:'待定',art:'待配图'};
function castEmpty(all){const gaps=all.some(r=>r.k==='vacant'||r.k==='loose'),arts=all.filter(r=>r.k==='art').length;
 if(!CAST_ON.vacant&&!CAST_ON.loose&&!CAST_ON.art)return {h:'先选一种状态',p:'点上面的空缺、待定或待配图。'};
 if(!CAST_ON.vacant&&!CAST_ON.loose&&CAST_ON.art)return {h:'配图已齐',p:'没有还在等立绘的角色。',hero:true};
 if(!gaps)return {h:'全员已定',p:'这一期没有待定或空缺的席位。',hero:true,census:true,artBtn:arts&&!CAST_ON.art?arts:0};
 return {h:'没有这类席位',p:'换一个状态看看。',artBtn:arts&&!CAST_ON.art?arts:0}}
function castHero(){return `<div class="cast-spine" aria-hidden="true">${R.groups.map(g=>`<i style="background:${castHex(g.color)}" title="${esc(g.name)}"></i>`).join('')}</div><svg class="cast-illu" viewBox="0 0 220 140" aria-hidden="true"><rect class="pg" x="18" y="16" width="132" height="104" rx="12"/><path class="rules" d="M36 48h80M36 64h64M36 80h74"/><g transform="rotate(-8 156 86)"><circle class="seal" cx="156" cy="86" r="26"/><path class="tick" d="M144 86l8 8 16-18"/></g></svg>`}
function renderCast(){closeSignup();closeGuestbook();const root=$('#cast');if(!root)return;const all=castRows(),vis=all.filter(r=>CAST_ON[r.k]);
 const counts={vacant:0,loose:0,art:0};all.forEach(r=>counts[r.k]++);
 const chips=[['vacant','空缺'],['loose','待定'],['art','待配图']].map(([k,t])=>`<button type="button" class="cast-chip" data-k="${k}" aria-pressed="${CAST_ON[k]?'true':'false'}">${t}<b>${counts[k]}</b></button>`).join('');
 const when=(SITE.event.date||'').trim();
 let body;
 if(!vis.length){const em=castEmpty(all);
  body=`<section class="cast-empty${em.hero?' hero':''}">${em.hero?castHero():''}<div class="cast-copy"><h3>${esc(em.h)}</h3><p class="lede">${esc(em.p)}</p>${em.census?`<p class="cast-census"><strong>${total}</strong><span>位伙伴都已落在角色上</span></p>`:''}${em.artBtn?`<button type="button" class="cast-aside" data-cast-art="1">还有 ${em.artBtn} 位待配图</button>`:''}</div></section>`}
 else{const groups=[];vis.forEach(r=>{let g=groups.find(x=>x.gi===r.gi);if(!g){g={gi:r.gi,g:r.g,rows:[]};groups.push(g)}g.rows.push(r)});
  body='<div class="cast-board">'+groups.map(gr=>{const col=castHex(gr.g.color),face=r=>{const f=castFace(r);return `<button type="button" class="cast-line cast-row" data-k="${r.k}" data-g="${r.gi}" data-i="${r.i}" title="${esc(f.title)}"><span class="cast-ord">${castFolio(r.order)}</span>${castAv(gr.g,r.m)}<span class="cast-role"><b class="cast-d${f.gap&&r.k==='loose'?' miss':''}">${esc(f.role)}</b><b class="cast-p">${esc(f.title)}</b></span><span class="cast-mem${r.k==='vacant'?' miss':''}">${esc(f.who)}</span><span class="cast-meta">${esc(f.meta)}</span><span class="cast-st">${CAST_LABEL[r.k]}</span></button>`};
   return `<section class="cast-work" style="--c:${col}"><header class="cast-wh"><i class="cast-cover"${castCover(gr.g)}></i><div class="cast-wt"><p class="cast-no">No. ${castFolio(gr.gi+1)}</p><h3 title="${esc(gr.g.name)}">${esc(gr.g.name)}</h3></div><p class="cast-count">${gr.rows.length} 席</p></header><div class="cast-cols cast-line" aria-hidden="true"><span>排序</span><span>配图</span><span>角色</span><span>成员</span><span>状态</span></div>${gr.rows.map(face).join('')}</section>`}).join('')+'</div>'}
 const ct=SITE.event.contact||{},note=ct.value?`<footer class="cast-note"><b>联系方式</b><p>${esc((ct.label?ct.label+' ':'')+ct.value)}</p></footer>`:'';
 root.innerHTML=`<div class="cast-top"><div class="cast-mast"><p class="cast-kicker"><span>CALL SHEET</span>${when?`<span class="cast-when">${esc(when)}</span>`:''}</p><h2>缺人看板</h2></div><div class="cast-chips" role="group" aria-label="筛选状态">${chips}</div></div>${body}${noticeHTML('board')}${note}`}
function setCast(on){on=!!on;document.body.classList.toggle('casting',on);const m=$('#m');if(m)m.classList.toggle('casting',on);
 const root=$('#cast');if(root)root.setAttribute('aria-hidden',on?'false':'true');
 const b=$('#castbtn');if(b){b.setAttribute('aria-pressed',on?'true':'false');const n=castRows().filter(r=>r.k==='vacant'||r.k==='loose').length;
  b.innerHTML=icon(on?'left':'users',18)+'<span>'+(on?'名册':'缺人')+'</span>'+(!on&&n?`<b>${n}</b>`:'');
  b.setAttribute('aria-label',on?'返回名册':'缺人看板')}
 if(on){$$('.cv').forEach(c=>{c.getAnimations().forEach(a=>a.cancel());c.style.removeProperty('transform')});
  const q=$('#q');if(q&&q.value.trim()){q.value='';const box=$('#m');if(box)box.classList.remove('searching');const res=$('#res');if(res)res.innerHTML=''}const sh=$('#sheet');if(sh)sh.classList.remove('open');renderCast();scrollTo({top:0,behavior:'instant'})}
 else{closeSignup();closeGuestbook();
  /* covers were display:none — wait two frames so layout is real, then clear FLIP leftovers and relayout */
  const back=()=>{if(document.body.classList.contains('casting'))return;(window.KRcastBack||window.KRlay||(()=>{}))()};
  requestAnimationFrame(()=>requestAnimationFrame(back))}}
function bootCast(){const b=$('#castbtn'),root=$('#cast');if(!b||!root)return;setCast(false);
 b.addEventListener('click',()=>setCast(!document.body.classList.contains('casting')));
 root.addEventListener('click',e=>{const chip=e.target.closest('.cast-chip');if(chip){const k=chip.dataset.k;if(!(k in CAST_ON))return;CAST_ON[k]=chip.getAttribute('aria-pressed')!=='true';try{sessionStorage.setItem('kr_cast_on',JSON.stringify(CAST_ON))}catch(err){}renderCast();return}
  if(e.target.closest('[data-cast-art]')){CAST_ON.art=true;try{sessionStorage.setItem('kr_cast_on',JSON.stringify(CAST_ON))}catch(err){}renderCast();return}
  const row=e.target.closest('.cast-row');if(!row)return;openSheet(+row.dataset.g,+row.dataset.i,0,row)})}
bootCast();
/* 空缺报名。空缺行先开角色卡，卡上的「报名」再打开这张表。不写名册，提交进 /api/cast-signup → 本地待审，后台通过才落座。
   取消、遮罩、Escape 只关报名，角色卡留在下面。报名层铺满键盘上方的可见区域。CN 和联系方式都不压缩，装不下时卡片内部滚。 */
let signupY=null,signupKickOn=false,signupBaseH=0,signupVp=null,signupFrameH=0;
function signupRoot(){let root=$('#signup');if(root)return root;root=document.createElement('div');root.id='signup';root.setAttribute('role','dialog');root.setAttribute('aria-modal','true');root.setAttribute('aria-labelledby','signup-title');root.setAttribute('aria-hidden','true');root.hidden=true;root.innerHTML='<div class="signup-card"></div>';document.body.append(root);return root}
function signupOpen(){const root=$('#signup');return !!(root&&!root.hidden)}
function closeSignup(){const root=$('#signup');if(!root||root.hidden)return;const ae=document.activeElement;if(ae&&root.contains(ae))ae.blur();
 root.classList.remove('open','signup-short');root.hidden=true;root.setAttribute('aria-hidden','true');
 root.style.top=root.style.left=root.style.width=root.style.height=root.style.bottom=root.style.right='';
 root.style.removeProperty('--vv-pad');
 signupMeta(false);signupBaseH=0;signupFrameH=0;
 const y=signupY;signupY=null;if(y==null)return;
 const back=()=>{if(Math.abs((window.scrollY||0)-y)>1)scrollTo({top:y,behavior:'instant'})};back();setTimeout(back,350)}
function castToast(t){let e=$('#toast');if(!e){e=document.createElement('div');e.id='toast';document.body.append(e)}e.textContent=t;e.classList.add('on');clearTimeout(e._t);e._t=setTimeout(()=>e.classList.remove('on'),2400)}
function signupMeta(on){const meta=document.querySelector('meta[name=viewport]');if(!meta)return;
 if(on){if(signupVp==null)signupVp=meta.getAttribute('content')||'';
  if(!/interactive-widget\s*=/.test(signupVp))meta.setAttribute('content',signupVp+',interactive-widget=resizes-content')}
 else if(signupVp!=null){meta.setAttribute('content',signupVp);signupVp=null}}
function vvBox(baseH){const vv=window.visualViewport,ih=window.innerHeight,iw=window.innerWidth,base=baseH||ih;
 const vvH=vv?vv.height:ih,vvW=vv?vv.width:iw;
 /* 布局视口已经跟着键盘变矮时，fixed 的原点就是用户看见的顶，不要再加 offsetTop。
    没变矮时才用 visualViewport 的偏移。不用 getBoundingClientRect 回改 top：安卓上那一步会把层拽回布局视口，顶上露灰缝、底下露出角色卡。 */
 const shrunk=base-ih>80;
 let top=shrunk?0:(vv?vv.offsetTop||0:0),left=shrunk?0:(vv?vv.offsetLeft||0:0),width=vvW,height=shrunk?Math.min(ih,vvH):vvH;
 const vk=navigator.virtualKeyboard,kb=vk&&vk.boundingRect?vk.boundingRect.height:0;
 if(!shrunk&&kb>40&&base-vvH<80&&Math.abs((vv?vv.offsetTop||0:0)+vvH-ih)<=2){const next=ih-kb-top;if(next>=200)height=next}
 if(top<0)top=0;if(left<0)left=0;if(width>iw)width=iw;if(left+width>iw)width=Math.max(120,iw-left);
 return {top,left,width,height}}
function signupBox(){return vvBox(signupBaseH)}
function signupFrame(){const card=$('#signup .signup-card');if(!card)return;const cn=card.querySelector('.signup-cn'),wx=card.querySelector('.signup-wx'),foot=card.querySelector('.signup-foot');
 card.scrollTop=0;if(!cn||!wx)return;
 const room=card.clientHeight,bot=el=>el.offsetTop+el.offsetHeight+4;
 const goal=foot?bot(foot):bot(wx);
 let top=goal>room?goal-room:0;
 const keep=Math.min(cn.offsetTop,wx.offsetTop);
 if(top>keep)top=keep;
 const wxNeed=bot(wx)-room;
 if(wxNeed>top)top=Math.max(0,Math.min(wx.offsetTop,wxNeed));
 card.scrollTop=top}
function signupPin(){const root=$('#signup');if(!root||root.hidden)return;const b=signupBox();
 if(b.height<120||b.width<120)return;
 root.style.top=b.top+'px';root.style.left=b.left+'px';root.style.width=b.width+'px';root.style.height=b.height+'px';root.style.bottom=root.style.right='auto';
 const h=b.height;root.classList.toggle('signup-short',h<560);
 const base=signupBaseH||innerHeight,kb=navigator.virtualKeyboard&&navigator.virtualKeyboard.boundingRect?navigator.virtualKeyboard.boundingRect.height:0;
 root.style.setProperty('--vv-pad',(kb>40||h<base-80)?'16px':'min(48px, max(16px, env(safe-area-inset-bottom)))');
 if(Math.abs(h-signupFrameH)>1){signupFrameH=h;signupFrame()}}
function signupKick(){if(signupKickOn)return;signupKickOn=true;const t0=performance.now();
 const step=()=>{if(!signupOpen()){signupKickOn=false;return}signupPin();if(performance.now()-t0<1200)requestAnimationFrame(step);else signupKickOn=false};step()}
function openSignup(gi,i){const g=R.groups[gi],m=g&&g.members[i];if(!m||castKind(g.name,m)!=='vacant'||!signupOn(g))return;const CL=esc(SITE.signup.contactLabel||'联系方式');const root=signupRoot();root.style.setProperty('--c',castHex(g.color));
 const role=(m.character||'').trim()||'空席',card=root.querySelector('.signup-card');
 card.innerHTML=`<form novalidate><div class="signup-ctx"><p class="signup-kicker">${icon('users',14)}<span>空缺报名</span></p><h2 id="signup-title">${esc(role)}</h2><p class="signup-work">${esc(g.name)}</p></div><label class="signup-fld signup-cn"><span>${icon('user',14)}CN</span><input name="name" maxlength="40" autocomplete="name" enterkeyhint="next" required></label><label class="signup-fld signup-wx"><span>${icon('message',14)}${CL}</span><input name="contact" maxlength="60" autocomplete="off" enterkeyhint="done" required></label>${signupExtraHTML()}<div class="signup-foot"><p class="signup-err" role="alert"></p><div class="signup-actions"><button type="button" class="signup-btn" data-signup-close>取消</button><button type="submit" class="signup-btn go">${icon('arrow',16)}提交报名</button></div>${noticeHTML('signup')}${SITE.signup.note?`<p class="signup-fine">${esc(SITE.signup.note)}</p>`:''}</div></form>`;
 card.dataset.id=m.id||'';card.dataset.work=g.name;card.dataset.character=(m.character||'').trim();
 card.querySelectorAll('.ph-pick input[type=file]').forEach(f=>{const pv=f.parentNode.querySelector('.ph-prev');f.addEventListener('change',()=>{const x=f.files[0];if(pv._u)URL.revokeObjectURL(pv._u);pv.hidden=!x;if(x){pv._u=URL.createObjectURL(x);pv.style.backgroundImage=`url(${pv._u})`}})});
 signupShow(root,card)}
/* 团长选的额外字段（site.json signup.fields，server/fields.py 定义）：身高 / 年龄 / 性别 / 样片 / 自定义题 */
function signupExtraHTML(){return (SITE.signup.fields||[]).map(f=>{const lab=`<span>${esc(f.label)}${f.required?'':'<i class="signup-opt">选填</i>'}</span>`,n=`name="x-${esc(f.key)}"`;
 if(f.type==='number')return `<label class="signup-fld signup-x">${lab}<span class="signup-num"><input ${n} type="number" inputmode="decimal" min="${f.min}" max="${f.max}" step="0.1">${f.unit?`<b>${esc(f.unit)}</b>`:''}</span></label>`;
 if(f.type==='select')return `<fieldset class="signup-fld signup-x signup-seg"><legend>${lab}</legend><div>${f.options.map(o=>`<label><input type="radio" ${n} value="${esc(o)}"><span>${esc(o)}</span></label>`).join('')}</div></fieldset>`;
 if(f.type==='image')return `<label class="signup-fld signup-x ph-pick">${lab}<input ${n} type="file" accept="image/jpeg,image/png,image/webp"><i class="ph-prev" hidden></i>${f.hint?`<small class="signup-hint">${esc(f.hint)}，只有团长看得到</small>`:''}</label>`;
 if(f.type==='textarea')return `<label class="signup-fld signup-x">${lab}<textarea ${n} rows="3" maxlength="400"></textarea></label>`;
 return `<label class="signup-fld signup-x">${lab}<input ${n} maxlength="60" autocomplete="off"></label>`}).join('')}
/* 收集额外字段；样片先传到 /api/signup-sample 换文件名。→ {extra} 或抛出给用户看的错误 */
async function signupExtra(form){const extra={};
 for(const f of SITE.signup.fields||[]){const els=form.querySelectorAll(`[name="x-${f.key}"]`);let v='';
  if(f.type==='select')v=([...els].find(e=>e.checked)||{}).value||'';
  else if(f.type==='image'){const x=els[0]&&els[0].files[0];if(x){const body=await shrinkPhoto(x);if(body.size>6e6)throw new Error(f.label+'要小于 6 MB');
    const r=await fetch('/api/signup-sample',{method:'POST',body});const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||f.label+'上传失败');v=j.file}}
  else v=((els[0]||{}).value||'').trim();
  if(!v&&f.required)throw new Error((f.type==='image'?'请上传':f.type==='select'?'请选择':'请填写')+f.label);
  if(v)extra[f.key]=v}
 return extra}
function signupShow(root,card){card.scrollTop=0;
 if(signupY==null)signupY=window.scrollY||0;
 if(!signupBaseH)signupBaseH=window.innerHeight;
 signupMeta(true);
 root.hidden=false;root.classList.add('open');root.setAttribute('aria-hidden','false');
 signupPin();
 const input=card.querySelector('[name=name]');if(input)input.focus({preventScroll:true});
 signupKick()}
/* 本人照片：已定席位的成员自己传。借用报名表的弹层（手机键盘那套定位都现成）。
   CN 要和席位上的一致——不是身份验证，只防传错席位；真正的把关是后台审核（photos.moderation） */
function openPhoto(gi,i){const g=R.groups[gi],m=g&&g.members[i];if(!m||!hasCN(m)||!(SITE.photos&&SITE.photos.enabled))return;const root=signupRoot();root.style.setProperty('--c',castHex(g.color));
 const card=root.querySelector('.signup-card'),pre=SITE.photos.moderation!=='post';
 card.innerHTML=`<form novalidate data-kind="photo"><div class="signup-ctx"><p class="signup-kicker">${icon('camera',14)}<span>本人照片</span></p><h2 id="signup-title">${esc((m.character||'').trim()||g.name)}</h2><p class="signup-work">${esc(g.name)}</p></div><label class="signup-fld signup-cn"><span>${icon('user',14)}你的 CN</span><input name="name" maxlength="40" autocomplete="name" enterkeyhint="done" required></label><label class="signup-fld signup-wx ph-pick"><span>${icon('camera',14)}照片</span><input name="file" type="file" accept="image/jpeg,image/png,image/webp" required><i class="ph-prev" hidden></i></label><div class="signup-foot"><p class="signup-err" role="alert"></p><div class="signup-actions"><button type="button" class="signup-btn" data-signup-close>取消</button><button type="submit" class="signup-btn go">${icon('arrow',16)}上传</button></div><p class="signup-fine">${pre?'提交后等审核，通过后显示在你的角色卡上。':'提交后直接显示在你的角色卡上；不合适的会被撤下。'}</p></div></form>`;
 card.dataset.id=m.id||'';const f=card.querySelector('[name=file]'),pv=card.querySelector('.ph-prev');
 f.addEventListener('change',()=>{const x=f.files[0];if(pv._u)URL.revokeObjectURL(pv._u);pv.hidden=!x;if(x){pv._u=URL.createObjectURL(x);pv.style.backgroundImage=`url(${pv._u})`}});
 signupShow(root,card)}
/* 手机原图动辄 5～10 MB 还带定位：浏览器里先缩到长边 1600、转 JPEG（顺带去掉 EXIF）；做不到就原样传 */
async function shrinkPhoto(file){try{const b=await createImageBitmap(file),k=Math.min(1,1600/Math.max(b.width,b.height)),c=document.createElement('canvas');
 c.width=Math.round(b.width*k);c.height=Math.round(b.height*k);c.getContext('2d').drawImage(b,0,0,c.width,c.height);b.close&&b.close();
 const out=await new Promise(r=>c.toBlob(r,'image/jpeg',.86));return out&&out.size<file.size*1.2?out:file}catch(_){return file}}
async function onPhotoSubmit(e){e.preventDefault();const form=e.target,card=form.closest('.signup-card'),err=form.querySelector('.signup-err'),btn=form.querySelector('[type=submit]');
 const nameEl=form.querySelector('[name=name]'),name=(nameEl.value||'').trim(),file=form.querySelector('[name=file]').files[0];
 if(!name){err.textContent='请填写你的 CN';nameEl.focus();return}
 if(!file){err.textContent='先选一张照片';return}
 if(form.dataset.busy==='1')return;form.dataset.busy='1';btn.disabled=true;err.textContent='上传中…';
 try{const body=await shrinkPhoto(file);if(body.size>6e6)throw new Error('照片要小于 6 MB');
  const r=await fetch('/api/photo?'+new URLSearchParams({seat:card.dataset.id,name}),{method:'POST',body});
  const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||'上传失败，请稍后再试');
  closeSignup();if(j.pending)castToast('已提交，等审核');else{castToast('照片已换上');setTimeout(()=>location.reload(),900)}}
 catch(ex){err.textContent=ex.message||'上传失败，请稍后再试';form.dataset.busy='';btn.disabled=false}}
async function onSignupSubmit(e){if(e.target.dataset.kind==='photo')return onPhotoSubmit(e);e.preventDefault();const form=e.target,card=form.closest('.signup-card'),err=form.querySelector('.signup-err'),btn=form.querySelector('[type=submit]');
 const nameEl=form.querySelector('[name=name]'),wxEl=form.querySelector('[name=contact]'),CL=SITE.signup.contactLabel||'联系方式';
 const name=(nameEl.value||'').trim(),contact=(wxEl.value||'').trim();
 if(!name){err.textContent='请填写CN';nameEl.focus();return}
 if(!contact){err.textContent='请填写'+CL;wxEl.focus();return}
 if(SITE.signup.contactPattern){let ok=true;try{ok=new RegExp('^(?:'+SITE.signup.contactPattern+')$').test(contact)}catch(_){}if(!ok){err.textContent=CL+'格式不对';wxEl.focus();return}}
 if(!card.dataset.id){err.textContent='这条席位暂时不能报名';return}
 if(form.dataset.busy==='1')return;form.dataset.busy='1';btn.disabled=true;err.textContent='';
 try{const extra=await signupExtra(form);
  const r=await fetch('/api/cast-signup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,contact,work:card.dataset.work||'',character:card.dataset.character||'',id:card.dataset.id,extra})});
  const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||'提交失败，请稍后再试');
  closeSignup();castToast('已提交，等审核')}
 catch(ex){err.textContent=ex.message||'提交失败，请稍后再试';form.dataset.busy='';btn.disabled=false}}
function bootSignup(){const root=signupRoot();root.addEventListener('click',e=>{if(e.target===root||e.target.closest('[data-signup-close]'))closeSignup()});root.addEventListener('submit',onSignupSubmit);
 root.addEventListener('focusin',e=>{if(e.target.matches&&e.target.matches('input'))signupKick()});
 root.addEventListener('touchmove',e=>{if(e.target===root)e.preventDefault()},{passive:false});
 const vv=window.visualViewport;if(vv){vv.addEventListener('resize',signupPin);vv.addEventListener('scroll',signupPin)}
 addEventListener('resize',signupPin);addEventListener('scroll',signupPin,{passive:true});
 const vk=navigator.virtualKeyboard;if(vk&&vk.addEventListener)vk.addEventListener('geometrychange',signupPin)}
bootSignup();

/* 一图流：抬头文字链 → 全页海报 HTML（宽屏 wide，竖屏 master）。 */
const POSTER_MQ='(min-width:900px)';
function posterHref(){return SITE.mode!=='single'&&matchMedia(POSTER_MQ).matches?'/poster/wide.html':'/poster/master.html'}
function bootPoster(){const sync=()=>{const href=posterHref();document.querySelectorAll('#posterlink-hdr,a.poster-mini').forEach(a=>{a.href=href})};
 sync();try{const mq=matchMedia(POSTER_MQ);if(mq.addEventListener)mq.addEventListener('change',sync);else if(mq.addListener)mq.addListener(sync)}catch(_){}}
bootPoster();
/* 留言区。CN 可空，空则服务端存「匿名」。默认先发后审（site.json guestbook.moderation=post），后台可隐藏；
   pre 时提交后要等后台通过才出现。页面只渲染 GET /api/guestbook 读到的已通过条目，不写名册。
   表单仍是固定浮层（visualViewport，避免手机键盘把输入框顶出屏幕）。
   补间源是「写一条」按钮，不是列表里的纸条：打开从按钮长成表单，取消缩回按钮。
   只有写下成功且列表里已经有这条新留言时，才落到那一张新纸条上。
   关上时要取消 fill 动画。否则下一回打开时，表单还停在上一张纸条的终点，目标矩形会被顶到视口下面。
   打开期间锁住页面滚动，列表第一条的位置和文字保持不动。
   prefers-reduced-motion 时不补间，直接切换。 */
const GB_MS=460,GB_EASE='cubic-bezier(.2,.8,.2,1)';
let gbY=null,gbKickOn=false,gbBaseH=0,gbFrameH=0,gbGen=0,gbScrim=null,gbFormChrome=null;
function gbOpen(){const root=$('#gb');return !!(root&&!root.hidden)}
function gbStill(){return RM||matchMedia('(prefers-reduced-motion: reduce)').matches||typeof HTMLElement==='undefined'||!HTMLElement.prototype.animate}
function gbBox(el){const r=el.getBoundingClientRect();return {top:r.top,left:r.left,width:r.width,height:r.height}}
function gbRel(vp){const o=$('#gb').getBoundingClientRect();return {top:vp.top-o.top,left:vp.left-o.left,width:vp.width,height:vp.height}}
function gbPlace(el,p){el.style.top=p.top+'px';el.style.left=p.left+'px';el.style.width=p.width+'px';el.style.height=p.height+'px'}
function gbNear(a,b){return Math.abs(a.top-b.top)<1.5&&Math.abs(a.left-b.left)<1.5&&Math.abs(a.width-b.width)<1.5&&Math.abs(a.height-b.height)<1.5}
function gbOp(v,fallback){const x=parseFloat(v);return Number.isFinite(x)?x:fallback}
function gbShadow(el){const s=getComputedStyle(el).boxShadow;if(s&&s!=='none')return s;
 const gold=getComputedStyle(document.documentElement).getPropertyValue('--gold-2').trim()||'#e6b35a';
 return '3px 3px 0 '+gold}
function gbScrimColor(){if(gbScrim)return gbScrim;const d=document.createElement('div');d.style.cssText='position:absolute;left:-999px;background:var(--scrim-sheet)';document.body.appendChild(d);gbScrim=getComputedStyle(d).backgroundColor||'rgba(51,51,51,.53)';d.remove();return gbScrim}
function gbFormLook(card){if(!gbFormChrome){const cs=getComputedStyle(card);gbFormChrome={shadow:gbShadow(card),radius:cs.borderRadius||'20px',bg:cs.backgroundColor||'#fff'}}return gbFormChrome}
function gbNoteFor(text){if(!text)return null;const list=$('#gb-list');if(!list)return null;
 return [...list.querySelectorAll('.gb-note')].find(n=>((n.querySelector('p')||{}).textContent||'')===text)||null}
function gbAnchor(){return $('#gb-open')}
function gbLock(){const b=document.body;if(b.classList.contains('gb-lock'))return;const y=window.scrollY||0;gbY=y;
 /* position:fixed collapses scrollY→0; syncChrome would drop .sm2 and .bar gap jumps (0↔10px). Freeze chrome first. */
 const hdr=document.querySelector('.hdr');if(hdr)hdr.classList.toggle('sm',y>40);
 b.classList.toggle('sm2',y>90);document.documentElement.classList.add('chrome-lock');
 const gap=Math.max(0,window.innerWidth-document.documentElement.clientWidth);
 b.classList.add('gb-lock');b.style.position='fixed';b.style.top=(-y)+'px';b.style.left='0';b.style.right='0';b.style.width='100%';
 if(gap)b.style.paddingRight=gap+'px'}
function gbUnlock(){const b=document.body;if(!b.classList.contains('gb-lock')){gbY=null;return}const y=gbY;
 b.classList.remove('gb-lock');b.style.position=b.style.top=b.style.left=b.style.right=b.style.width=b.style.paddingRight='';
 document.documentElement.classList.remove('chrome-lock');
 gbY=null;if(y==null){if(typeof syncChrome==='function')syncChrome();return}
 const back=()=>{if(Math.abs((window.scrollY||0)-y)>1)scrollTo({top:y,behavior:'instant'})};back();setTimeout(back,350);
 if(typeof syncChrome==='function')syncChrome()}
function gbFormHTML(){return `<form novalidate><div class="gb-ctx"><p class="gb-kicker">${icon('message',14)}<span>留言</span></p><h2 id="gb-form-title">写一条</h2></div><label class="gb-fld gb-cn"><span>${icon('user',14)}CN</span><input name="CN" maxlength="40" autocomplete="nickname" enterkeyhint="next" placeholder="不填就是匿名"></label><label class="gb-fld gb-body"><span>${icon('pencil',14)}内容</span><textarea name="body" maxlength="500" required rows="4" placeholder="想说的话"></textarea></label><input name="website" class="hp" tabindex="-1" autocomplete="off" aria-hidden="true"><div class="gb-foot"><p class="gb-err" role="alert"></p><div class="gb-actions"><button type="button" class="gb-btn" data-gb-close>取消</button><button type="submit" class="gb-btn go">${icon('arrow',16)}写下</button></div></div></form>`}
function gbGhost(src,vp){const g=document.createElement('div');g.className='gb-flight';g.setAttribute('aria-hidden','true');
 if(src){const c=src.cloneNode(true);c.removeAttribute('id');c.style.width=vp.width+'px';c.style.height=vp.height+'px';c.style.maxWidth='none';c.style.visibility='visible';g.appendChild(c)}
 return g}
function gbFlush(){const list=$('#gb-list');if(!list)return;delete list.dataset.fly;const p=list._pend;list._pend=null;if(p)renderGuestbook(p,true)}
function gbShowPapers(){document.querySelectorAll('#gb-list .gb-note,#gb-list .gb-empty,#gb-open').forEach(n=>{n.style.visibility=''})}
function gbClear(root){if(!root)return;[root,...root.querySelectorAll('.gb-card,.gb-flight,form')].forEach(el=>el.getAnimations().forEach(a=>a.cancel()))}
function gbShut(root){gbClear(root);root.classList.remove('open','gb-short','gb-morph');delete root.dataset.morph;root.hidden=true;root.setAttribute('aria-hidden','true');
 root.style.top=root.style.left=root.style.width=root.style.height=root.style.bottom=root.style.right='';root.style.backgroundColor='';root.style.removeProperty('--vv-pad');
 root.querySelectorAll('.gb-flight').forEach(n=>n.remove());
 const card=root.querySelector('.gb-card');if(card)card.style.cssText='';
 gbShowPapers();gbFlush();
 if(!signupOpen())signupMeta(false);gbBaseH=0;gbFrameH=0;
 gbUnlock()}
function gbPlay(anims,gen,done){let settled=false;const finish=()=>{if(settled||gbGen!==gen)return;settled=true;clearTimeout(tid);done()};
 const tid=setTimeout(finish,GB_MS+520);
 Promise.all(anims.map(a=>a.finished.catch(()=>{}))).then(finish)}
function gbFrame(){const root=$('#gb');if(root&&root.dataset.morph)return;const card=$('#gb .gb-card');if(!card)return;const cn=card.querySelector('.gb-cn'),body=card.querySelector('.gb-body'),foot=card.querySelector('.gb-foot');
 card.scrollTop=0;if(!body)return;
 const room=card.clientHeight,bot=el=>el.offsetTop+el.offsetHeight+4;
 const goal=foot?bot(foot):bot(body);
 let top=goal>room?goal-room:0;
 const keep=cn?Math.min(cn.offsetTop,body.offsetTop):body.offsetTop;
 if(top>keep)top=keep;
 const need=bot(body)-room;
 if(need>top)top=Math.max(0,Math.min(body.offsetTop,need));
 card.scrollTop=top}
function gbPin(){const root=$('#gb');if(!root||root.hidden||root.dataset.morph)return;const b=vvBox(gbBaseH);
 if(b.height<120||b.width<120)return;
 root.style.top=b.top+'px';root.style.left=b.left+'px';root.style.width=b.width+'px';root.style.height=b.height+'px';root.style.bottom=root.style.right='auto';
 const h=b.height;root.classList.toggle('gb-short',h<640);
 const base=gbBaseH||innerHeight,kb=navigator.virtualKeyboard&&navigator.virtualKeyboard.boundingRect?navigator.virtualKeyboard.boundingRect.height:0;
 root.style.setProperty('--vv-pad',(kb>40||h<base-80)?'16px':'min(48px, max(16px, env(safe-area-inset-bottom)))');
 if(Math.abs(h-gbFrameH)>1){gbFrameH=h;gbFrame()}}
function gbKick(){if(gbKickOn)return;gbKickOn=true;const t0=performance.now();
 const step=()=>{if(!gbOpen()){gbKickOn=false;return}gbPin();if(performance.now()-t0<1200)requestAnimationFrame(step);else gbKickOn=false};step()}
function gbWhen(s){const d=new Date(s||'');if(!s||Number.isNaN(d.getTime()))return '';const p=n=>String(n).padStart(2,'0');
 return d.getFullYear()+'-'+p(d.getMonth()+1)+'-'+p(d.getDate())+' '+p(d.getHours())+':'+p(d.getMinutes())+':'+p(d.getSeconds())}
function gbPageSize(){try{return matchMedia('(min-width:720px)').matches?17:8}catch(_){return 8}}
function gbPager(){let p=$('#gb-pager');if(p)return p;const sec=$('#guestbook');if(!sec)return null;
 p=document.createElement('nav');p.id='gb-pager';p.className='gb-pager';p.setAttribute('aria-label','留言翻页');
 sec.appendChild(p);return p}
function gbKey(it){return String(it&&it.提交时间||'')+'\0'+String(it&&it.CN||'')+'\0'+String(it&&it.内容||'')}
function gbPaintPage(list,enterKeys){const items=list._items||[];const pager=gbPager();const sz=gbPageSize();
 if(!items.length){list.innerHTML='<p class="gb-empty"><b>还没有留言</b></p>';if(pager){pager.hidden=true;pager.innerHTML=''}return}
 const pages=Math.max(1,Math.ceil(items.length/sz));
 let page=Math.max(1,Math.min(pages,list._page|0||1));list._page=page;
 const slice=items.slice((page-1)*sz,page*sz);
 const enter=enterKeys instanceof Set?enterKeys:null;
 list.innerHTML=slice.map(it=>{const when=gbWhen(it.提交时间);const neu=enter&&enter.has(gbKey(it))?' gb-in':'';
  return `<article class="gb-note${neu}"><header><b>${esc(it.CN||'匿名')}</b>${when?`<time datetime="${esc(it.提交时间)}">${esc(when)}</time>`:''}</header><p>${esc(it.内容||'')}</p></article>`}).join('');
 if(enter&&enter.size){const drop=n=>n.classList.remove('gb-in');
  requestAnimationFrame(()=>list.querySelectorAll('.gb-note.gb-in').forEach(n=>{n.addEventListener('animationend',()=>drop(n),{once:true});setTimeout(()=>drop(n),700)}))}
 if(!pager)return;
 if(pages<=1){pager.hidden=true;pager.innerHTML='';return}
 pager.hidden=false;
 pager.innerHTML=`<button type="button" class="gb-page" data-gb-page="prev" ${page<=1?'disabled':''}>上一页</button><span class="gb-page-meta">${page} / ${pages}</span><button type="button" class="gb-page" data-gb-page="next" ${page>=pages?'disabled':''}>下一页</button>`}
function renderGuestbook(items,force){const list=$('#gb-list');if(!list)return;
 if(!force&&(list.dataset.fly||gbOpen())){list._pend=items;return}list._pend=null;
 const next=Array.isArray(items)?items:[];
 const keys=next.map(gbKey);const sig=keys.join('\n');
 if(!force&&list._sig===sig){list._items=next;return}
 const prev=list._seen instanceof Set?list._seen:null;
 let enter=null;
 if(!force&&prev&&prev.size){enter=new Set(keys.filter(k=>!prev.has(k)));if(!enter.size)enter=null}
 if(enter&&(list._page|0||1)!==1)enter=null;
 list._items=next;list._seen=new Set(keys);list._sig=sig;
 if(force)list._page=1;
 else{
  const pages=Math.max(1,Math.ceil((list._items.length||0)/gbPageSize()));
  list._page=Math.max(1,Math.min(pages,list._page|0||1));
 }
 gbPaintPage(list,enter)}
function gbEndOpen(root,card,src,input){[root,card,...root.querySelectorAll('.gb-flight,form')].forEach(el=>el.getAnimations().forEach(a=>a.cancel()));
 root.querySelectorAll('.gb-flight').forEach(n=>n.remove());
 root.classList.remove('gb-morph');delete root.dataset.morph;root.style.backgroundColor='';card.style.cssText='';
 const form=card.querySelector('form');if(form){form.style.opacity='';form.style.pointerEvents=''}
 if(src&&src.isConnected)src.style.visibility=gbOpen()?'hidden':'';
 if(!gbOpen())return;
 if(input)input.focus({preventScroll:true});
 gbKick()}
function openGuestbook(){const root=$('#gb');if(!root||gbOpen())return;const card=root.querySelector('.gb-card');if(!card)return;
 const src=gbAnchor();if(!src)return;
 gbClear(root);root.querySelectorAll('.gb-flight').forEach(n=>n.remove());card.style.cssText='';
 gbLock();
 card.innerHTML=gbFormHTML();card.scrollTop=0;
 if(!gbBaseH)gbBaseH=window.innerHeight;
 signupMeta(true);
 // measure while visible, hide real #gb-open before the open layer paints
 src.style.visibility='';
 const fromVP=gbBox(src);
 const cs=getComputedStyle(src);
 const srcR=cs.borderRadius||'12px',srcS=gbShadow(src),srcBg=cs.backgroundColor;
 src.style.visibility='hidden';
 root.hidden=false;root.classList.add('open');root.setAttribute('aria-hidden','false');
 gbPin();
 const input=card.querySelector('[name=CN]'),form=card.querySelector('form');
 if(gbStill()||fromVP.width<8||fromVP.height<8){if(input)input.focus({preventScroll:true});gbKick();return}
 const toVP=gbBox(card),look=gbFormLook(card),scrim=gbScrimColor();
 const gen=++gbGen;root.dataset.morph='open';root.classList.add('gb-morph');
 const from=gbRel(fromVP),to=gbRel(toVP);
 gbPlace(card,from);if(form){form.style.opacity='0';form.style.pointerEvents='none'}
 const flight=gbGhost(src,fromVP);gbPlace(flight,from);flight.style.opacity='1';flight.style.borderRadius=srcR;root.appendChild(flight);
 const list=$('#gb-list');if(list)list.dataset.fly='1';
 root.style.backgroundColor='transparent';
 card.offsetWidth;
 const opt={duration:GB_MS,easing:GB_EASE,fill:'both'};
 const geo=(a,b,extraA,extraB)=>[Object.assign({top:a.top+'px',left:a.left+'px',width:a.width+'px',height:a.height+'px',borderRadius:srcR},extraA||{}),Object.assign({top:b.top+'px',left:b.left+'px',width:b.width+'px',height:b.height+'px',borderRadius:look.radius},extraB||{})];
 let anims=[];
 try{anims=[
  card.animate(geo(from,to,{boxShadow:srcS,backgroundColor:srcBg},{boxShadow:look.shadow,backgroundColor:look.bg}),opt),
  flight.animate(geo(from,to),opt),
  flight.animate([{opacity:1},{opacity:0,offset:.16},{opacity:0}],{duration:GB_MS,easing:'linear',fill:'both'}),
  root.animate([{backgroundColor:'transparent'},{backgroundColor:scrim}],opt)];
 if(form)anims.push(form.animate([{opacity:0},{opacity:0,offset:.08},{opacity:1,offset:.42},{opacity:1}],{duration:GB_MS,easing:'linear',fill:'both'}))}
 catch(e){gbEndOpen(root,card,src,input);return}
 gbPlay(anims,gen,()=>gbEndOpen(root,card,src,input))}
function closeGuestbook(land){if(land&&land.nodeType!==1)land=null;const root=$('#gb');if(!root||root.hidden||root.dataset.morph==='close')return;
 const card=root.querySelector('.gb-card');
 const ae=document.activeElement;if(ae&&root.contains(ae))ae.blur();
 const dest=(land&&land.isConnected)?land:gbAnchor();
 if(gbStill()||!card||!dest){gbShut(root);return}
 const destVP=gbBox(dest);
 if(destVP.width<8||destVP.height<8){gbShut(root);return}
 const curVP=gbBox(card),scrimNow=getComputedStyle(root).backgroundColor,look=gbFormLook(card);
 const oldFlight=root.querySelector('.gb-flight');const flightVP=oldFlight?gbBox(oldFlight):curVP;
 const form=card.querySelector('form');const formOp=form?getComputedStyle(form).opacity:'1';
 const flightOp=oldFlight?getComputedStyle(oldFlight).opacity:'0';
 const shadowNow=gbShadow(card),radiusNow=getComputedStyle(card).borderRadius||look.radius,bgNow=getComputedStyle(card).backgroundColor;
 const flightR=oldFlight?(getComputedStyle(oldFlight).borderRadius||radiusNow):radiusNow;
 [root,card,form,oldFlight].filter(Boolean).forEach(el=>el.getAnimations().forEach(a=>a.cancel()));
 const gen=++gbGen;root.dataset.morph='close';root.classList.add('gb-morph');
 const from=gbRel(curVP),to=gbRel(destVP),flightFrom=gbRel(flightVP);
 gbPlace(card,from);root.style.backgroundColor=scrimNow;
 if(form)form.style.opacity=formOp;
 let flight=oldFlight,op=gbOp(flightOp,0);
 const destIsNote=dest.id!=='gb-open',flightIsNote=!!(flight&&flight.querySelector('.gb-note'));
 if(!flight||flightIsNote!==destIsNote){if(flight)flight.remove();flight=gbGhost(dest,destVP);op=0;flight.style.opacity='0';root.appendChild(flight)}
 gbPlace(flight,flightFrom);
 dest.style.visibility='hidden';
 const list=$('#gb-list');if(list)list.dataset.fly='1';
 const destCs=getComputedStyle(dest),destR=destCs.borderRadius||'12px',destS=gbShadow(dest),destBg=destCs.backgroundColor;
 card.offsetWidth;
 const opt={duration:GB_MS,easing:GB_EASE,fill:'both'};
 const geo=(a,b,radiusA,radiusB,extraA,extraB)=>[{top:a.top+'px',left:a.left+'px',width:a.width+'px',height:a.height+'px',borderRadius:radiusA,...(extraA||{})},{top:b.top+'px',left:b.left+'px',width:b.width+'px',height:b.height+'px',borderRadius:radiusB,...(extraB||{})}];
 const anims=[
  card.animate(geo(from,to,radiusNow,destR,{boxShadow:shadowNow,backgroundColor:bgNow},{boxShadow:destS,backgroundColor:destBg}),opt),
  flight.animate(geo(flightFrom,to,flightR,destR),opt),
  flight.animate([{opacity:op},{opacity:op,offset:.22},{opacity:1,offset:.68},{opacity:1}],{duration:GB_MS,easing:'linear',fill:'both'}),
  root.animate([{backgroundColor:scrimNow},{backgroundColor:'rgba(0,0,0,0)'}],opt)];
 if(form){const o=gbOp(formOp,1);anims.push(form.animate([{opacity:o},{opacity:o,offset:.28},{opacity:0,offset:.7},{opacity:0}],{duration:GB_MS,easing:'linear',fill:'both'}))}
 gbPlay(anims,gen,()=>{
  if(!dest.isConnected){gbShut(root);return}
  const now=gbBox(flight),want=gbBox(dest);
  if(gbNear(now,want)){gbShut(root);return}
  const a=gbRel(now),b=gbRel(want);
  const nudge=[flight,card].map(el=>el.animate([{top:a.top+'px',left:a.left+'px',width:a.width+'px',height:a.height+'px'},{top:b.top+'px',left:b.left+'px',width:b.width+'px',height:b.height+'px'}],{duration:160,easing:GB_EASE,fill:'both'}));
  let done=false;const end=()=>{if(done||gbGen!==gen)return;done=true;gbShut(root)};
  setTimeout(end,240);
  Promise.all(nudge.map(n=>n.finished.catch(()=>{}))).then(end)})}
async function onGuestbookSubmit(e){e.preventDefault();const form=e.target,err=form.querySelector('.gb-err'),btn=form.querySelector('[type=submit]');
 const cnEl=form.querySelector('[name=CN]'),bodyEl=form.querySelector('[name=body]');
 const CN=(cnEl.value||'').trim(),text=(bodyEl.value||'').trim(),website=(form.querySelector('[name=website]')||{}).value||'';
 if(!text){err.textContent='请填写内容';bodyEl.focus();return}
 if(form.dataset.busy==='1')return;form.dataset.busy='1';btn.disabled=true;err.textContent='';
 try{const r=await fetch('/api/guestbook',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({CN,内容:text,website})});
  const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||'提交失败，请稍后再试');
  if(j.pending){castToast('已提交，审核后显示');if(gbOpen())closeGuestbook();return}
  const want=text;let ok=false;
  for(let i=0;i<8&&!ok;i++){if(i)await new Promise(r=>setTimeout(r,200));
   try{const g=await fetch('/api/guestbook',{cache:'no-store'});const gj=await g.json();if(!g.ok)continue;
    const items=gj.items||[];renderGuestbook(items,true);ok=items.some(it=>(it.内容||'')===want)}catch(_){}}
  if(!ok)await loadGuestbook(true);
  castToast('已记下');
  if(gbOpen())closeGuestbook(ok?gbNoteFor(want):null)}
 catch(ex){err.textContent=ex.message||'提交失败，请稍后再试';form.dataset.busy='';btn.disabled=false}}
async function loadGuestbook(force){try{const r=await fetch('/api/guestbook',{cache:'no-store'});const j=await r.json();if(!r.ok)throw new Error(j.error||'');renderGuestbook(j.items||[],!!force)}
 catch(e){const list=$('#gb-list');if(!list||list.dataset.fly||(gbOpen()&&!force))return;list._items=[];list._page=1;list.innerHTML='<p class="gb-empty"><b>留言暂时读不到</b><span>过一会儿再刷新这个页面。</span></p>';const pager=$('#gb-pager');if(pager){pager.hidden=true;pager.innerHTML=''}}}
function bootGuestbook(){const openBtn=$('#gb-open'),root=$('#gb');if(!openBtn||!root)return;
 const sec=$('#guestbook');if(sec&&!sec._gbPage){sec._gbPage=1;sec.addEventListener('click',e=>{const b=e.target.closest('[data-gb-page]');if(!b||b.disabled)return;const list=$('#gb-list');if(!list||!list._items)return;
  const pages=Math.max(1,Math.ceil(list._items.length/gbPageSize()));let page=list._page|0||1;
  if(b.dataset.gbPage==='prev')page--;else if(b.dataset.gbPage==='next')page++;
  list._page=Math.max(1,Math.min(pages,page));gbPaintPage(list);list.scrollIntoView({block:'nearest',behavior:'smooth'})});
  try{const mq=matchMedia('(min-width:720px)');const onW=()=>{const list=$('#gb-list');if(list&&list._items)gbPaintPage(list)};
   if(mq.addEventListener)mq.addEventListener('change',onW);else if(mq.addListener)mq.addListener(onW)}catch(_){}}
 openBtn.innerHTML=icon('pencil',16)+'<span>写一条留言</span>';
 const kicker=$('#guestbook .gb-kicker');if(kicker)kicker.innerHTML=icon('message',14)+'<span>NOTES</span>';
 openBtn.addEventListener('click',openGuestbook);
 root.addEventListener('click',e=>{if(e.target===root||e.target.closest('[data-gb-close]'))closeGuestbook()});
 root.addEventListener('submit',onGuestbookSubmit);
 root.addEventListener('focusin',e=>{if(e.target.matches&&e.target.matches('input,textarea'))gbKick()});
 root.addEventListener('touchmove',e=>{if(e.target===root)e.preventDefault()},{passive:false});
 const vv=window.visualViewport;if(vv){vv.addEventListener('resize',gbPin);vv.addEventListener('scroll',gbPin)}
 addEventListener('resize',gbPin);addEventListener('scroll',gbPin,{passive:true});
 const vk=navigator.virtualKeyboard;if(vk&&vk.addEventListener)vk.addEventListener('geometrychange',gbPin);
 loadGuestbook();
 let gbPoll=0;const gbTick=()=>{if(document.hidden)return;loadGuestbook()};
 clearInterval(gbPoll);gbPoll=setInterval(gbTick,12000);
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)loadGuestbook()});
}
bootGuestbook();
window.KRCast={kind:castKind,set:setCast,render:renderCast,on:CAST_ON,rows:castRows,signup:openSignup};
