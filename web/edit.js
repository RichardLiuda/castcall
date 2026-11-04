(()=>{
const api=(m,u,b)=>fetch(u,{method:m,headers:{'Content-Type':'application/json'},credentials:'same-origin',body:b?JSON.stringify(b):undefined}).then(async r=>{const j=await r.json().catch(()=>({}));if(!r.ok)throw Object.assign(new Error(j.error||r.status),{status:r.status,j});return j});
const clone=o=>JSON.parse(JSON.stringify(o));let D=clone(R);const SS=sessionStorage;
const h=(t,a={},...c)=>{const e=document.createElement(t);for(const k in a)k.startsWith('on')?e.addEventListener(k.slice(2),a[k]):e.setAttribute(k,a[k]);c.flat().forEach(x=>e.append(x));return e};
document.body.append(h('button',{class:'fab',id:'fab',title:'编辑','aria-label':'进入编辑'},iconEl('lock',22)),h('div',{class:'etb',id:'etb'}),h('div',{id:'modal'},h('div',{class:'mc'})),h('div',{id:'toast'}),h('div',{id:'lv'}));
const toast=(t,ms=1800)=>{const e=$('#toast');e.textContent=t;e.classList.add('on');clearTimeout(e._t);e._t=setTimeout(()=>e.classList.remove('on'),ms)};
function modal(title,body,color){const mc=$('#modal .mc');mc.innerHTML='';mc.style.setProperty('--c',color||'#e6b35a');$('#modal').style.setProperty('--c',color||'#e6b35a');mc.append(h('h3',{},title),...body);$('#modal').classList.add('open');setTimeout(()=>{const i=mc.querySelector('input');i&&i.focus()},250)}
const close=()=>{$('#modal').classList.remove('open');const f=close.after;close.after=null;f&&f()};
$('#modal').addEventListener('click',e=>{if(e.target.id=='modal')close()});
const fld=(label,inp)=>h('div',{class:'fld'},inp,h('label',{},label));
const inp=(v,ph='',type='text')=>{const i=h('input',{type,placeholder:ph});i.value=v||'';return i};
async function persist(msg){try{await api('PUT','/api/data',D);SS.setItem('kr_edit','1');toast(msg||'已保存');setTimeout(()=>location.reload(),500);return true}
 catch(e){if(e.status==401){toast('登录过期，请重新登录');setEdit(false);login()}else toast('保存失败：'+e.message,3000);return false}}
function login(){const pw=inp('','','password'),er=h('div',{class:'err'});const go=async()=>{try{await api('POST','/api/login',{password:pw.value});SS.setItem('kr_edit','1');close();setEdit(true);toast('已进入编辑模式')}catch(e){er.textContent=e.message+(e.j&&e.j.left!=null?`（还可试 ${e.j.left} 次）`:'');const mc=$('#modal .mc');mc.classList.remove('shake');mc.offsetWidth;mc.classList.add('shake');pw.select()}};
 pw.addEventListener('keydown',e=>e.key=='Enter'&&go());modal('编辑需要密码',[fld('密码',pw),er,h('div',{class:'mrow'},h('button',{class:'btn',onclick:close},'取消'),h('button',{class:'btn pri',onclick:go},'进入编辑'))])}
let editing=false;
function setEdit(on){editing=on;document.body.classList.toggle('editing',on);$('#fab').replaceChildren(iconEl(on?'unlock':'lock',22));$('#fab').setAttribute('aria-label',on?'编辑中':'进入编辑');
 const tb=$('#etb');tb.innerHTML='';if(on){tb.append(h('button',{class:'btn pri',id:'newrole',onclick:()=>{const c=$('.cv.open');const gi=c?+c.id.slice(1):+(SS.getItem('kr_open_last')||0);entryForm(Math.min(gi,D.groups.length-1),-1,1)}},iconEl('plus'),'新角色'),h('button',{class:'btn',onclick:()=>review('signups')},iconEl('users'),'审核',h('b',{id:'rvn',hidden:''})),h('button',{class:'btn',onclick:()=>links('all')},iconEl('links'),'连线视图'),h('button',{class:'btn',onclick:()=>groupForm(-1)},iconEl('plus'),SITE.mode==='single'?'加一个团':'新团'),h('button',{class:'btn',onclick:artAuto},iconEl('palette'),'一键配图'),h('button',{class:'btn',onclick:brandPanel},iconEl('camera'),'站点素材'),h('button',{class:'btn',onclick:fieldsPanel},iconEl('pencil'),'报名表'),...(SITE.poster.enabled?[h('button',{class:'btn',onclick:posterBuild},iconEl('palette'),'生成一图流')]:[]),h('button',{class:'btn',onclick:async()=>{await api('POST','/api/logout');SS.removeItem('kr_edit');setEdit(false);toast('已退出编辑')}},iconEl('logout'),'退出'))}
 soloTools();
 $$('.cv').forEach((c,gi)=>{let t=c.querySelector('.gtools');if(!t){t=h('div',{class:'gtools'},h('button',{class:'btn',onclick:()=>entryForm(gi,-1)},iconEl('plus'),'添加'),h('button',{class:'btn',onclick:()=>groupForm(gi)},iconEl('pencil'),SITE.mode==='single'?'活动 / 团信息':'团信息'),h('button',{class:'btn',onclick:()=>links(gi)},iconEl('links'),'连线'));c.querySelector('.body').prepend(t)}});
 if(on)reviewCount()}
/* still signed in (cookie alive) → straight back into edit mode, no password prompt */
/* 单团页没有卡片，团级工具条放在 #solo 的信息区上方 */
function soloTools(){const so=$('#solo .solo-tools');if(so&&!so.firstChild)so.append(h('div',{class:'gtools'},h('button',{class:'btn',onclick:()=>entryForm(0,-1)},iconEl('plus'),'添加角色'),h('button',{class:'btn',onclick:()=>groupForm(0)},iconEl('pencil'),'活动 / 团信息'),h('button',{class:'btn',onclick:()=>links(0)},iconEl('links'),'连线')))}
$('#fab').onclick=async()=>{if(editing)return setEdit(false);try{if((await api('GET','/api/me')).auth){SS.setItem('kr_edit','1');return setEdit(true)}}catch(e){}login()};
/* inline edit in detail card */
const toastAct=(t,label,fn,ms=5000)=>{const e=$('#toast');e.innerHTML='';e.append(h('span',{},t),h('button',{class:'tact',onclick:()=>{e.classList.remove('on');fn()}},label));e.classList.add('on');clearTimeout(e._t);e._t=setTimeout(()=>e.classList.remove('on'),ms)};
async function saveField(gi,i,key,val,old,undoing){D=clone(R);const m=D.groups[gi]&&D.groups[gi].members[i];if(!m)return;m[key]=val;if(key==='character')movePortrait(D.groups[gi].name,old,D.groups[gi].name,val);
 try{const r=await api('PUT','/api/data',D);R.groups=r.data.groups;D=clone(R);
  if(document.getElementById('solo')){renderSolo();soloTools()}
  const p=document.querySelector(`.cv .pill[data-g="${gi}"][data-i="${i}"]`);if(p){const t=document.createElement('div');t.innerHTML=pill(gi,i,'');const np=t.firstChild;p.replaceWith(np);if(np.closest('.cv.open,#res'))ciLoad(np);window.fitAll&&fitAll(document.querySelector('#c'+gi))}
  if(cur&&cur[0]===gi&&cur[1]===i){const el=$(key==='member'?'#sm':'#sc');if(el&&document.activeElement!==el)el.textContent=val}
  const lbl=key==='member'?'成员':'角色';
  if(undoing)toast('已撤销');else toastAct(`${lbl}已改为「${val||'（空）'}」`,'撤销',()=>saveField(gi,i,key,old,val,true));
 }catch(err){toast('保存失败：'+err.message);const el=$(key==='member'?'#sm':'#sc');if(el)el.textContent=old}}
function decorateSheet(){if(!editing||!cur)return;const [gi,i]=cur;const card=$('#sheet .card');card.classList.add('editable');
 [['#sm','member'],['#sc','character']].forEach(([sel,key])=>{const el=card.querySelector(sel);if(!el)return;const orig=R.groups[gi].members[i][key]||'';el.contentEditable='plaintext-only';if(el.contentEditable!=='plaintext-only')el.contentEditable='true';el.spellcheck=false;el.classList.add('ie');el.title='点击编辑 · Enter 保存 · Esc 还原';el.dataset.ph=key==='member'?'（待定）':'（无角色）';
  el.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();el.blur()}else if(e.key==='Escape'){e.preventDefault();e.stopPropagation();el.textContent=orig;el._esc=1;el.blur()}});
  el.addEventListener('blur',()=>{const v=el.textContent.replace(/\s+/g,' ').trim();if(el._esc){el._esc=0;return}if(v===orig)return;if(key==='character'&&!v&&!R.groups[gi].members[i].member){el.textContent=orig;return toast('角色和成员至少保留一个')}saveField(gi,i,key,v,orig)})});
 const nav=card.querySelector('.nav');if(nav&&!nav.querySelector('.more'))nav.append(h('button',{class:'btn more',title:'更多：移动 / 删除 / 排序',onclick:()=>{$('#sheet').classList.remove('open');entryForm(gi,i)},'aria-label':'更多操作'},iconEl('more')))}
if(typeof openSheet==='function'){const _os=openSheet;openSheet=function(...a){_os(...a);decorateSheet()}}
function entryForm(gi,i,nr){const g=D.groups[gi],m=i>=0?g.members[i]:{character:'',member:''};
 const ch=inp(m.character,'例：角色名'),mb=inp(m.member,'例：CN'),pf=h('input',{type:'file',accept:'image/jpeg,image/png,image/webp,image/gif'}),sel=h('select',{},...D.groups.map((x,k)=>{const o=h('option',{value:k},x.name);if(k==gi)o.selected=true;return o})),er=h('div',{class:'err'});
 const pos=inp(i>=0?i+1:g.members.length+1,'','number');pos.min=1;
 const save=async()=>{const c=ch.value.trim(),n=mb.value.trim();if(nr&&!c){er.textContent='请填写角色名';return}if(!c&&!n){er.textContent='角色和成员至少填一个';return}
  const to=+sel.value,obj=Object.assign({},m,{character:c,member:n}),gn=D.groups[to].name;
  try{if(pf.files[0]){if(!c){er.textContent='上传立绘要先填角色名';return}await upload('portrait',pf.files[0],{group:gn,character:c})}
   else if(i>=0&&(gn!==g.name||c!==m.character))await movePortrait(g.name,m.character,gn,c)}catch(e){er.textContent='立绘上传失败：'+e.message;return}
  if(i>=0)g.members.splice(i,1);const T=D.groups[to].members;let p=Math.max(0,Math.min(T.length,(+pos.value||T.length+1)-1));if(to!==gi&&i>=0)p=T.length;T.splice(p,0,obj);persist(i>=0?'已更新':'已添加')};
 if(nr)mb.placeholder='可留空 = 空缺';const find=h('button',{class:'btn ghost',type:'button',onclick:()=>{const c=ch.value.trim();if(!c){er.textContent='先填角色名';return}artPick('portrait',c,D.groups[+sel.value].name,c)}},iconEl('palette'),'找立绘');
 const body=[fld(crew(g)?'岗位':'角色',ch),fld('成员（coser）',mb),fld('所属团',sel),fld('顺序位置',pos),...(crew(g)?[]:[fld('立绘（可选，jpg / png / webp）',pf),h('div',{class:'mrow'},find)]),er,h('div',{class:'mrow'},h('button',{class:'btn',onclick:close},'取消'),...(i>=0?[h('button',{class:'btn dan',onclick:()=>{if(confirm(`删除「${m.character||m.member}」？`)){g.members.splice(i,1);persist('已删除')}}},'删除')]:[]),h('button',{class:'btn pri',onclick:save},i>=0?'保存':'添加'))];
 [ch,mb].forEach(x=>x.addEventListener('keydown',e=>e.key=='Enter'&&save()));if(nr)body.splice(0,4,fld('所属团',sel),fld('角色名',ch),fld('成员（coser，可选）',mb));modal(nr?'新角色':i>=0?'编辑':'添加到 '+g.name,body,g.color)}
function groupForm(gi){const g=gi>=0?D.groups[gi]:{name:'',color:'#e07a5f',members:[]};const nm=inp(g.name,'通常是作品名'),col=inp(g.color,'','color'),pos=inp(gi>=0?gi+1:D.groups.length+1,'','number'),er=h('div',{class:'err'});
 const cf=h('input',{type:'file',accept:'image/jpeg,image/png,image/webp,image/gif'}),drop=h('input',{type:'checkbox'}),kind=h('select',{},h('option',{value:'cast'},'角色团（每个席位是一个角色）'),h('option',{value:'crew'},'工作组（摄影 / 后勤 / 妆娘…）'));kind.value=g.kind||'cast';
 const lead=inp(g.lead,'可选'),ct=inp(g.contact,'可选，例：微信 abc123'),note=h('textarea',{rows:3,placeholder:'可选：拍摄风格、妆造要求、集合时间…',maxlength:480});note.value=g.note||'';
 const so=h('select',{},h('option',{value:'open'},'开放报名'),h('option',{value:'closed'},'暂停报名'));so.value=g.signup||'open';
 const save=async()=>{const n=nm.value.trim();if(!n){er.textContent='团名不能为空';return}if(D.groups.some((x,k)=>k!==gi&&x.name===n)){er.textContent='已有同名的团';return}
  let cover=drop.checked?undefined:g.cover;try{if(cf.files[0])cover=(await upload('cover',cf.files[0])).file}catch(e){er.textContent='封面上传失败：'+e.message;return}
  if(gi>=0&&n!==g.name)for(const m of g.members)if(m.character)await movePortrait(g.name,m.character,n,m.character).catch(()=>{});
  const opt=(k,v)=>v?v:undefined;
  const ng=Object.assign({},g,{name:n,color:col.value,cover,kind:kind.value==='crew'?'crew':undefined,lead:opt(0,lead.value.trim()),contact:opt(0,ct.value.trim()),note:opt(0,note.value.trim()),signup:so.value==='closed'?'closed':undefined});
  Object.keys(ng).forEach(k=>ng[k]===undefined&&delete ng[k]);
  if(gi>=0)D.groups.splice(gi,1);D.groups.splice(Math.max(0,Math.min(D.groups.length,(+pos.value||1)-1)),0,ng);persist()};
 const many=D.groups.length>1||gi<0;
 const fc=h('button',{class:'btn ghost',type:'button',onclick:()=>{const n=nm.value.trim()||g.name;if(gi<0){er.textContent='先保存这个团，再找封面';return}artPick('cover',n,g.name)}},iconEl('palette'),'在线找封面');
 modal(gi>=0?'编辑团信息':'新团',[fld('团名',nm),fld('主题色',col),fld(g.cover?'换封面（不选就保留）':'封面图（可选）',cf),h('div',{class:'mrow'},fc),...(g.cover?[h('label',{class:'chk'},drop,'去掉封面')]:[]),fld('类型',kind),fld('团长',lead),fld('咨询方式',ct),fld('说明',note),fld('报名',so),...(many?[fld('排序位置',pos)]:[]),er,h('div',{class:'mrow'},h('button',{class:'btn',onclick:close},'取消'),...(gi>=0?[h('button',{class:'btn dan',onclick:()=>{if(confirm(`删除「${g.name}」及其 ${g.members.length} 个席位？`)){D.groups.splice(gi,1);persist('已删除')}}},'删除')]:[]),h('button',{class:'btn pri',onclick:save},'保存'))],g.color)}
async function upload(kind,file,q){const u=new URLSearchParams(Object.assign({kind},q||{}));if(file.size>8e6)throw new Error('图片要小于 8 MB');
 const r=await fetch('/api/admin/upload?'+u,{method:'POST',credentials:'same-origin',body:file});const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||r.status);return j}
/* 立绘按「团名|角色名」存：改名或换团时把这张图带过去 */
async function movePortrait(g0,c0,g1,c1){const p=(window.CHARS||{})[g0+'|'+c0];if(!p||(g0===g1&&c0===c1))return;
 await api('POST','/api/admin/portrait',{group:g1,character:c1,path:p.split('?')[0]});await api('POST','/api/admin/portrait',{group:g0,character:c0})}
/* ---------- review: signups + guestbook ---------- */
/* 报名的额外字段 → 审核列表里的几行：文字一行，样片是缩略图（/samples/ 只有登录后能打开）。
   题目按 key 对：后台删掉的题，旧答案用 key 本身当题目名，照样显示 */
let FIELDS=[];
function extraOf(it){let x={};try{x=JSON.parse(it.extra||'{}')}catch(e){}const keys=Object.keys(x);if(!keys.length)return [];
 const lab=k=>(FIELDS.find(f=>f.key===k)||{label:k}),txt=[],img=[];
 for(const k of keys){const f=lab(k);if(f.type==='image')img.push(h('a',{class:'rv-sample',href:'/samples/'+x[k],target:'_blank',rel:'noopener',title:f.label},h('img',{src:'/samples/'+x[k],alt:f.label,loading:'lazy'})));
  else txt.push(`${f.label} ${x[k]}${f.unit||''}`)}
 return [...(txt.length?[h('small',{class:'rv-extra'},txt.join(' · '))]:[]),...(img.length?[h('div',{class:'rv-samples'},...img)]:[])]}
const RV_ST={pending:'待审',approved:'已通过',rejected:'已拒绝',hidden:'已隐藏',replaced:'已换新'};
async function reviewCount(){try{const c=await api('GET','/api/admin/counts');const n=(c.signups.pending||0)+(c.guestbook.pending||0)+((c.photos||{}).pending||0),b=$('#rvn');if(b){b.textContent=n;b.hidden=!n}}catch(e){}}
function review(tab){let dirty=false;const box=h('div',{class:'rv'}),tabs=h('div',{class:'chips rv-tabs'});
 const when=t=>{const d=new Date(t);return isNaN(d)?'':`${d.getMonth()+1}/${d.getDate()} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`};
 const act=async(url,action,okMsg)=>{try{const r=await api('POST',url,{action});if(r.data){R.groups=r.data.groups;dirty=true}toast(r.message||okMsg);draw()}catch(e){toast((e.j&&(e.j.message||e.j.error))||e.message,3200);draw()}};
 const draw=async()=>{tabs.replaceChildren(...[['signups','报名'],['guestbook','留言'],...(SITE.photos&&SITE.photos.enabled||tab==='photos'?[['photos','照片']]:[])].map(([k,t])=>h('button',{class:'chip'+(tab===k?' on':''),style:'--c:#333',onclick:()=>{tab=k;draw()}},t)));
  box.replaceChildren(h('p',{class:'rv-empty'},'加载中…'));let items;
  try{const j=await api('GET','/api/admin/'+tab);items=j.items;if(j.fields)FIELDS=j.fields}catch(e){box.replaceChildren(h('p',{class:'rv-empty'},'读不到：'+e.message));return}
  if(!items.length){box.replaceChildren(h('p',{class:'rv-empty'},({signups:'还没有人报名',guestbook:'还没有留言',photos:'还没有人传照片'})[tab]));return}
  const order={pending:0,approved:1,hidden:2,replaced:3,rejected:4};items.sort((a,b)=>(order[a.status]-order[b.status])||b.id-a.id);
  box.replaceChildren(...items.map(it=>{const st=h('span',{class:'rv-st '+it.status},RV_ST[it.status]||it.status);
   if(tab==='signups'){const U='/api/admin/signups/'+it.id,B=[];
    if(it.status!=='approved')B.push(h('button',{class:'btn pri',onclick:()=>act(U,'approve','已落座')},'通过'));
    if(it.status==='pending'||it.status==='approved')B.push(h('button',{class:'btn dan',onclick:()=>{if(it.status!=='approved'||confirm(`撤回 ${it.name}？名册上这个席位会空出来。`))act(U,'reject','已拒绝')}},it.status==='approved'?'撤回':'拒绝'));
    if(it.status==='rejected')B.push(h('button',{class:'btn',onclick:()=>act(U,'reopen','已退回待审')},'退回待审'));
    const ex=extraOf(it);
    return h('div',{class:'rv-it'},h('div',{class:'rv-tx'},h('b',{},it.name),h('span',{},`${SITE.signup.contactLabel||'联系方式'} ${it.contact}`),...ex,h('small',{},`${it.grp} · ${it.character||'（无角色）'} · ${when(it.created)}${it.source&&it.status!=='pending'?' · '+it.source:''}`),...(it.note?[h('small',{class:'rv-note'},it.note)]:[])),st,h('div',{class:'rv-b'},...B))}
   if(tab==='photos'){const U='/api/admin/photos/'+it.id,B=[];
    if(it.status!=='approved')B.push(h('button',{class:'btn pri',onclick:()=>{dirty=true;act(U,'approve','已通过，旧照片退下')}},'通过'));
    if(it.status==='pending'||it.status==='approved')B.push(h('button',{class:'btn dan',onclick:()=>{dirty=dirty||it.status==='approved';act(U,'reject',it.status==='approved'?'已撤下':'已拒绝')}},it.status==='approved'?'撤下':'拒绝'));
    return h('div',{class:'rv-it rv-ph'},h('a',{class:'rv-img',href:'/photos/'+it.file,target:'_blank',rel:'noopener'},h('img',{src:'/photos/'+it.file,alt:'',loading:'lazy'})),h('div',{class:'rv-tx'},h('b',{},it.member),h('small',{},`${it.grp} · ${it.character||'（无角色）'} · ${when(it.created)}`)),st,h('div',{class:'rv-b'},...B))}
   const U='/api/admin/guestbook/'+it.id;
   return h('div',{class:'rv-it'},h('div',{class:'rv-tx'},h('b',{},it.name),h('p',{},it.body),h('small',{},when(it.created))),st,h('div',{class:'rv-b'},it.status==='approved'?h('button',{class:'btn dan',onclick:()=>act(U,'hide','已隐藏')},'隐藏'):h('button',{class:'btn pri',onclick:()=>act(U,'show','已显示')},it.status==='pending'?'通过':'显示')))}))};
 modal('审核',[tabs,box,h('div',{class:'mrow'},h('button',{class:'btn',onclick:close},'关闭'))]);
 $('#modal .mc').classList.add('wide');close.after=()=>{$('#modal .mc').classList.remove('wide');reviewCount();if(dirty){SS.setItem('kr_edit','1');location.reload()}};draw()}
/* ---------- art: Bangumi / AniList ---------- */
function artPick(kind,q,group,character){const box=h('div',{class:'ap'}),qi=inp(q,kind==='cover'?'作品名':'角色名（中文、日文都行）'),er=h('div',{class:'err'});
 const run=async()=>{box.replaceChildren(h('p',{class:'rv-empty'},'正在找…'));er.textContent='';
  try{const r=await api('GET','/api/admin/art/search?'+new URLSearchParams({kind,q:qi.value.trim(),group}));
   if(!r.items.length){box.replaceChildren(h('p',{class:'rv-empty'},r.error||'没找到，换个名字试试（日文名 / 罗马字也行）'));return}
   box.replaceChildren(...r.items.map(it=>{const b=h('button',{class:'ap-it'+(kind==='cover'?' wide':''),type:'button',title:it.url},h('img',{src:it.thumb,alt:'',loading:'lazy',referrerpolicy:'no-referrer'}),h('b',{},it.title||''),h('small',{},[it.source,it.sub].filter(Boolean).join(' · ')+(it.inwork?' · ✓ 这部作品':'')));
    b.onclick=async()=>{b.disabled=true;try{await api('POST','/api/admin/art/pick',{kind,url:it.url,group,character});SS.setItem('kr_edit','1');toast(kind==='cover'?'封面已换':'立绘已换');setTimeout(()=>location.reload(),500)}catch(e){er.textContent=e.message;b.disabled=false}};return b}))}
  catch(e){box.replaceChildren();er.textContent=e.message}};
 qi.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();run()}});
 modal(kind==='cover'?`给「${group}」找封面`:`给「${character}」找立绘`,[h('div',{class:'ap-q'},qi,h('button',{class:'btn pri',type:'button',onclick:run},'搜')),box,er,h('p',{class:'ap-note'},'图片来自 Bangumi 和 AniList，点一张就用它。'),h('div',{class:'mrow'},h('button',{class:'btn',onclick:close},'关闭'))]);
 $('#modal .mc').classList.add('wide');close.after=()=>$('#modal .mc').classList.remove('wide');run()}
async function artAuto(){if(!confirm('给缺封面的团找封面、缺立绘的角色找立绘？\n只配有把握的，找不到的会跳过；已有的图不动。大概要一两分钟。'))return;
 try{await api('POST','/api/admin/art/auto')}catch(e){return toast(e.message,4000)}toast('正在配图…',3000);
 const t=setInterval(async()=>{try{const s=await api('GET','/api/admin/art/auto');if(s.running)return;clearInterval(t);const r=s.report||{};
  const msg=`配好 ${r.covers||0} 张封面、${r.portraits||0} 张立绘`+((r.skipped||[]).length?`，${r.skipped.length} 个没把握跳过`:'')+((r.errors||[]).length?`，${r.errors.length} 个出错`:'');
  if((r.covers||0)+(r.portraits||0)){SS.setItem('kr_edit','1');toastAct(msg,'刷新',()=>location.reload(),10000)}else toast(msg+((r.errors||[])[0]?'：'+r.errors[0]:''),8000)}catch(e){clearInterval(t)}},2500)}
/* ---------- poster ---------- */
/* 站点素材：logo / 标签页图标 / 一图流大图，选了就上传并写进 site.json，关掉面板后刷新页面生效 */
const BRAND=[['logo','标题前的 logo','透明底 PNG 最好，方形或横向都行'],['favicon','浏览器标签页图标','方形 PNG，64×64 以上；留空用内置图标'],['hero','一图流大图','铺在海报标题和底部；换完要重新生成一图流']];
/* 报名表要填什么（site.json signup.fields）：和开团向导同一个选择器（fields.js）。改了立刻对新报名生效，旧报名的答案不动 */
async function fieldsPanel(){let st;try{st=await api('GET','/api/admin/signup-fields')}catch(e){return toast('读不到报名表设置：'+e.message,3000)}
 const box=h('div'),er=h('div',{class:'err'}),fp=fieldPicker(box,st.presets,st.fields);
 const save=async()=>{er.textContent='';try{await api('POST','/api/admin/signup-fields',{fields:fp.value()});SS.setItem('kr_edit','1');toast('报名表已更新');setTimeout(()=>location.reload(),500)}catch(e){er.textContent=e.message}};
 modal('报名表要填什么',[box,h('p',{class:'ap-note'},'去掉某一项不会删掉已经收到的答案，审核里照样能看到。'),er,h('div',{class:'mrow'},h('button',{class:'btn',onclick:close},'取消'),h('button',{class:'btn pri',onclick:save},'保存'))])}
async function brandPanel(){let st;try{st=await api('GET','/api/admin/brand')}catch(e){return toast('读不到站点素材：'+e.message,3000)}
 let dirty=false;const er=h('div',{class:'err'}),list=h('div',{class:'brand'});
 const send=async(slot,file)=>{er.textContent='';if(file&&file.size>8e6){er.textContent='图片要小于 8 MB';return}
  try{const r=await fetch('/api/admin/brand?'+new URLSearchParams(file?{slot}:{slot,clear:'1'}),{method:'POST',credentials:'same-origin',body:file||''});const j=await r.json().catch(()=>({}));
   if(!r.ok)throw new Error(j.error||r.status);st.slots=j.slots;dirty=true;draw();toast(file?'已换上':'已恢复默认')}catch(e){er.textContent=e.message}};
 const draw=()=>{list.innerHTML='';for(const [k,t,hint] of BRAND){if(k==='hero'&&!st.poster)continue;const v=st.slots[k];
  const f=h('input',{type:'file',accept:'image/png,image/jpeg,image/webp,image/gif',hidden:''});f.addEventListener('change',()=>f.files[0]&&send(k,f.files[0]));
  list.append(h('div',{class:'brand-row'+(k==='hero'?' wide':'')},h('div',{class:'brand-th'},v.url?h('img',{src:v.url,alt:''}):h('span',{},k==='favicon'?'内置':'未设置')),
   h('div',{class:'brand-tx'},h('b',{},t),h('small',{},hint),h('div',{class:'brand-act'},h('button',{class:'btn',type:'button',onclick:()=>f.click()},v.url?'换一张':'上传'),
    ...(v.url?[h('button',{class:'btn ghost',type:'button',onclick:()=>confirm('恢复默认？图片文件会留在服务器上。')&&send(k)},'恢复默认')]:[]),f))))}};
 /* 成员照片开关：开了以后已定成员能在自己的角色卡里传本人照片 */
 let pc;try{pc=(await api('GET','/api/admin/photos')).config}catch(e){pc={enabled:false,moderation:'pre'}}
 const on=h('input',{type:'checkbox'}),mo=h('select',{},h('option',{value:'pre'},'先审后显示'),h('option',{value:'post'},'先显示，可撤下'));on.checked=!!pc.enabled;mo.value=pc.moderation||'pre';mo.disabled=!on.checked;
 const setPc=async()=>{er.textContent='';try{pc=(await api('POST','/api/admin/photos/config',{enabled:on.checked,moderation:mo.value})).config;mo.disabled=!pc.enabled;dirty=true;toast(pc.enabled?'成员照片已开启':'成员照片已关闭')}catch(e){er.textContent=e.message;on.checked=!!pc.enabled}};
 on.addEventListener('change',setPc);mo.addEventListener('change',setPc);
 const photos=h('div',{class:'brand-row brand-sw'},h('div',{class:'brand-tx'},h('label',{class:'chk'},on,h('b',{},'成员本人照片')),h('small',{},'开了以后，已定的成员能在自己的角色卡里上传照片，显示在卡片和详情里；在「审核 → 照片」里管理。'),h('div',{class:'fld'},mo,h('label',{},'审核方式'))));
 draw();close.after=()=>{if(dirty){SS.setItem('kr_edit','1');location.reload()}};
 modal('站点素材',[list,photos,er,h('div',{class:'mrow'},h('button',{class:'btn pri',onclick:close},'完成'))])}
async function posterBuild(){try{await api('POST','/api/admin/poster');toast('一图流生成中，大概要一两分钟…',4000)}catch(e){return toast((e.j&&e.j.error)||e.message,6000)}
 const t=setInterval(async()=>{try{const s=await api('GET','/api/admin/poster');if(s.running)return;clearInterval(t);
  if(s.rc===0)toastAct('一图流已更新','打开',()=>open('/poster/','_blank'),8000);else toast('一图流生成失败，日志在 instance/logs/poster.log',6000)}catch(e){clearInterval(t)}},2500)}
/* ---------- links view ---------- */
let L=null;
function links(scope){L={scope,ops:[],sel:null,pop:null,showDiff:false};D=clone(R);drawLV();$('#lv').classList.add('open');document.body.style.overflow='hidden'}
function closeLV(force){if(!force&&L&&L.ops.length&&!confirm(`有 ${L.ops.length} 处连线修改未保存，放弃？`))return false;$('#lv').classList.remove('open');document.body.style.overflow='';closePop();D=clone(R);L=null;return true}
function freeEnsure(E,x){if(x&&!E.some(e=>e.member===x))E.push({character:'',member:x})}
function tidy(E){for(let k=E.length-1;k>=0;k--){const e=E[k];if(!e.character&&!e.member)E.splice(k,1);else if(!e.character&&E.some((o,j)=>j!==k&&o.member===e.member&&o.character))E.splice(k,1)}}
const roleBy=(E,c)=>E.find(e=>e.character===c);
/* op kinds: assign (empty target, source->空缺), swap, replace (X->待定, source->空缺), multi (keep source, X->待定), unlink */
function applyOp(G,o){const E=G[o.gi].members,t=roleBy(E,o.tc);if(!t)return false;
 if(o.k==='unlink'){if(t.member!==o.m)return false;t.member='';freeEnsure(E,o.m);tidy(E);return true}
 const X=t.member,src=o.fc?roleBy(E,o.fc):null;if(src&&src.member!==o.m)return false;if((X||'')!==(o.X||''))return false;if(X===o.m)return false;
 t.member=o.m;
 if(o.k==='swap'){if(src)src.member=X||'';else freeEnsure(E,X)}
 else if(o.k==='multi'){freeEnsure(E,X)}
 else{if(src)src.member='';freeEnsure(E,X)}
 tidy(E);return true}
function rebuild(){const G=clone(R).groups;L.ops=L.ops.filter(o=>applyOp(G,o));D.groups=G}
function opHTML(o){const e=x=>String(x).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));return e(opText(o)).replace(/ ⇄ /g,' '+icon('swap',15)+' ').replace(/ → /g,' '+icon('arrow',15)+' ').replace(/ ✕ /g,' '+icon('unlink',15)+' ')}
function opText(o){const k={assign:'分配',swap:'互换',replace:'替换',multi:'兼任',unlink:'断开'}[o.k];const g=R.groups[o.gi].name;
 return o.k==='unlink'?`${g}：断开 ${o.m} ✕ ${o.tc}`:o.k==='swap'?`${g}：${o.m} ⇄ ${o.X||'空缺'}（${o.tc}${o.fc?' / '+o.fc:''}）`:`${g}：${o.m} → ${o.tc}（${k}${o.X?`，${o.X} 变待定`:''}${o.fc&&o.k!=='multi'?`，${o.fc} 空缺`:''}）`}
function doOp(o){const G=clone(D.groups);if(!applyOp(G,o))return toast('无法执行');L.ops.push(o);D.groups=G;L.sel=null;closePop();drawLV();toast(opText(o)+' · 未保存')}
function undoOp(i){L.ops.splice(i,1);rebuild();drawLV();toast('已撤销该项')}
function closePop(){const p=$('#lvpop');p&&p.remove();if(L)L.pop=null;$$('#lv path.ln.pick').forEach(x=>x.classList.remove('pick'))}
function popAt(anchor,title,btns){closePop();const r=anchor.getBoundingClientRect();const p=h('div',{id:'lvpop',role:'dialog'},h('div',{class:'pt'},...[].concat(title)),h('div',{class:'pb'},...btns.map(([t,fn,cls])=>h('button',{class:'btn '+(cls||''),onclick:fn},t))));
 document.body.append(p);const pw=p.offsetWidth,ph=p.offsetHeight;let x=Math.min(innerWidth-pw-8,Math.max(8,r.left+r.width/2-pw/2)),y=r.bottom+8;if(y+ph>innerHeight-8)y=Math.max(8,r.top-ph-8);p.style.left=x+'px';p.style.top=y+'px';
 const c=[...p.querySelectorAll('button')].find(b=>b.textContent==='取消');(c||p.querySelector('button')).focus();L.pop=p}
function srcOf(E,m,from){if(from!=null)return from;const rs=E.filter(e=>e.member===m&&e.character);return rs.length===1?rs[0].character:null}
function propose(gi,m,ci,from,anchor){const E=D.groups[gi].members,t=E[ci];if(!t||!t.character)return;if(t.member===m){L.sel=null;drawLV();return toast(`${m} 已经是 ${t.character}`)}
 const fc=srcOf(E,m,from),X=t.member,base={gi,m,tc:t.character,fc,X};
 if(!X)return popAt(anchor,[m,iconEl('arrow',16),t.character],[[`分配${fc?`（${fc} 变空缺）`:''}`,()=>doOp({...base,k:'assign'}),'pri'],...(fc?[['兼任（保留 '+fc+'）',()=>doOp({...base,k:'multi'})]]:[]),['取消',()=>{closePop()}]]);
 popAt(anchor,`「${t.character}」已由 ${X} 扮演`,[['互换',()=>doOp({...base,k:'swap'}),'pri'],['替换（'+X+' 变待定）',()=>doOp({...base,k:'replace'})],['兼任（多角色）',()=>doOp({...base,k:'multi'})],['取消',()=>closePop()]])}
function linePop(gi,ci,el){const E=D.groups[gi].members,e=E[ci];$$('#lv path.ln').forEach(p=>p.classList.toggle('pick',+p.dataset.c===ci&&p.closest('.cols').dataset.g==gi));
 popAt(el,`${e.member} — ${e.character}`,[['断开',()=>{if(confirm(`确认断开 ${e.member} 与 ${e.character}？`))doOp({k:'unlink',gi,m:e.member,tc:e.character})},'dan'],['取消',()=>closePop()]])}
async function saveLV(){if(!L.ops.length)return toast('没有修改');if(!confirm(`保存以下 ${L.ops.length} 处修改？\n\n`+L.ops.map((o,i)=>`${i+1}. ${opText(o)}`).join('\n')))return;const ops=L.ops;L.ops=[];if(!await persist('连线已保存'))L.ops=ops}
function drawLV(){const lv=$('#lv'),st0=lv.querySelector('.stage'),sc=st0?st0.scrollTop:0;const gis=L.scope==='all'?D.groups.map((g,i)=>i):[L.scope];
 lv.innerHTML='';lv.append(h('div',{class:'lh'},h('h3',{},iconEl('links',22),'Coser · 角色'),h('button',{class:'btn',onclick:()=>{if(!L.ops.length)return toast('没有可撤销的');L.ops.pop();rebuild();drawLV()}},iconEl('undo'),'撤销'),h('button',{class:'btn',onclick:()=>closeLV(),'aria-label':'关闭'},iconEl('x'))));
 lv.append(h('div',{class:'chips'},h('button',{class:'chip'+(L.scope==='all'?' on':''),style:'--c:#333',onclick:()=>{L.scope='all';L.sel=null;drawLV()}},'全部'),...D.groups.map((g,i)=>h('button',{class:'chip'+(L.scope===i?' on':''),style:`--c:${g.color}`,onclick:()=>{L.scope=i;L.sel=null;drawLV()}},g.name))));
 lv.append(h('div',{class:'hint'},'点成员，再点角色，选择操作 · 长按（触屏）或拖动成员到角色 · 点连线可断开 · 修改需保存'));
 const st=h('div',{class:'stage'}),grid=h('div',{class:'panels'+(gis.length===1?' one':'')});st.append(grid);lv.append(st);
 const wide=innerWidth>=980;
 gis.forEach(gi=>{const g=D.groups[gi],E=g.members;const roles=E.map((e,ci)=>[e,ci]).filter(([e])=>e.character);
  const names=[...new Set(E.map(e=>e.member).filter(Boolean))];
  const split=wide&&roles.length>=11;const half=Math.ceil(roles.length/2);
  const firstIdx=n=>{const k=roles.findIndex(([e])=>e.member===n);return k<0?1e9:k};
  const parts=split?[[0,half],[half,roles.length]]:[[0,roles.length]];
  const pn=h('section',{class:'pn'+(split?' big':''),style:`--c:${g.color}${g.cover?`;--img:${img('covers/'+g.cover)}`:''}`});
  pn.append(h('header',{class:'ph'},h('b',{},g.name),h('span',{},`${names.length} 人 · ${roles.length} 角色`)));
  const cols=h('div',{class:'cols'+(split?' two':''),'data-g':gi});
  parts.forEach(([s0,s1],pi)=>{const lc=h('div',{class:'col m'}),rc=h('div',{class:'col c'});
   names.filter(n=>{const k=firstIdx(n);return split?(pi===0?k<half:k>=half):true}).forEach(n=>{const has=E.some(e=>e.member===n&&e.character);
    lc.append(h('div',{class:'nd m'+(has?'':' free')+(L.sel&&L.sel.t==='m'&&L.sel.g==gi&&L.sel.v===n?' sel':''),'data-m':n,'data-g':gi},h('i',{class:'ini'},[...n][0]),h('span',{class:'tx'},n),h('i',{class:'dot'})))});
   roles.slice(s0,s1).forEach(([e,ci])=>{const a=(window.CHARS||{})[g.name+'|'+e.character];
    rc.append(h('div',{class:'nd c'+(e.member?'':' free')+(L.sel&&L.sel.t==='c'&&L.sel.g==gi&&L.sel.v===ci?' sel':''),'data-c':ci,'data-g':gi},h('i',{class:'dot'}),a?h('i',{class:'av',style:`--ci:${img(a.replace('chars/','chars/thumb/'))}`}):h('i',{class:'av ini'},[...e.character][0]),h('span',{class:'tx'},e.character),...(e.member?[]:[h('em',{},'空缺')])))});
   cols.append(lc,rc)});
  const NS='http://www.w3.org/2000/svg',svg=document.createElementNS(NS,'svg');svg.innerHTML=`<defs><linearGradient id="lg${gi}" x1="0" x2="1"><stop offset="0" stop-color="${g.color}" stop-opacity=".55"/><stop offset="1" stop-color="${g.color}"/></linearGradient></defs>`;cols.append(svg);
  pn.append(cols);grid.append(pn)});
 const n=L.ops.length;const lf=h('div',{class:'lf'},h('button',{class:'chip pend'+(n?' on':''),style:'--c:#e07a5f',onclick:()=>{L.showDiff=!L.showDiff;drawLV()}},...(n?[`${n} 处修改`,iconEl(L.showDiff?'up':'down',16)]:['无修改'])),h('span',{class:'sp'}),h('button',{class:'btn pri',style:'--c:#2a9d8f',onclick:saveLV},iconEl('save'),'保存'));
 if(n&&L.showDiff)lv.append(h('div',{class:'diff'},...L.ops.map((o,i)=>h('div',{class:'di'},(()=>{const sp=h('span',{});sp.innerHTML=`${i+1}. `+opHTML(o);return sp})(),h('button',{class:'btn',onclick:()=>undoOp(i),'aria-label':'撤销此项'},iconEl('undo',18))))));
 lv.append(lf);
 st.scrollTop=sc;requestAnimationFrame(lines)}
function pt(el,cols,side){const d=el.querySelector('.dot').getBoundingClientRect(),c=cols.getBoundingClientRect();return[d.left+d.width/2-c.left,d.top+d.height/2-c.top]}
const curve=(a,b)=>{if(Math.abs(b[1]-a[1])<1)b=[b[0],a[1]+1];const dx=Math.max(24,Math.abs(b[0]-a[0])*.45)*(b[0]>=a[0]?1:-1);return `M${a[0]},${a[1]} C${a[0]+dx},${a[1]} ${b[0]-dx},${b[1]} ${b[0]},${b[1]}`};
function lines(){$$('#lv .cols').forEach(cols=>{const gi=+cols.dataset.g,g=D.groups[gi],svg=cols.querySelector('svg');svg.querySelectorAll('path').forEach(p=>p.remove());
 g.members.forEach((e,ci)=>{if(!e.character||!e.member)return;const m=[...cols.querySelectorAll('.nd.m')].find(x=>x.dataset.m===e.member),c=cols.querySelector(`.nd.c[data-c="${ci}"]`);if(!m||!c)return;
  const d=curve(pt(m,cols),pt(c,cols));const NS='http://www.w3.org/2000/svg';const p=document.createElementNS(NS,'path');p.setAttribute('d',d);p.setAttribute('class','ln');p.style.stroke=`url(#lg${gi})`;p.dataset.c=ci;p.dataset.m=e.member;svg.append(p);const len=p.getTotalLength();p.style.setProperty('--len',len);p.style.animationDelay=Math.min(ci,20)*14+'ms';
  const hp=document.createElementNS(NS,'path');hp.setAttribute('d',d);hp.setAttribute('class','hit');hp.dataset.c=ci;hp.dataset.g=gi;hp.dataset.m=e.member;svg.append(hp)})})}
$('#lv').addEventListener('mouseover',e=>{if(drag)return;const t=e.target.closest('.nd,path.hit');$$('#lv .cols.hl').forEach(c=>{c.classList.remove('hl');c.querySelectorAll('.on').forEach(x=>x.classList.remove('on'))});if(!t)return;
 const cols=t.closest('.cols');let ms=new Set(),cs=new Set();const E=D.groups[+cols.dataset.g].members;
 if(t.matches('path.hit')){ms.add(t.dataset.m);cs.add(+t.dataset.c)}else if(t.classList.contains('m')){ms.add(t.dataset.m);E.forEach((x,i)=>x.member===t.dataset.m&&x.character&&cs.add(i))}else{const i=+t.dataset.c;cs.add(i);E[i].member&&ms.add(E[i].member)}
 cols.classList.add('hl');cols.querySelectorAll('.nd.m').forEach(n=>ms.has(n.dataset.m)&&n.classList.add('on'));cols.querySelectorAll('.nd.c').forEach(n=>cs.has(+n.dataset.c)&&n.classList.add('on'));cols.querySelectorAll('path.ln').forEach(p=>cs.has(+p.dataset.c)&&ms.has(p.dataset.m)&&p.classList.add('on'))});
let _lr;addEventListener('resize',()=>{if(!L)return;clearTimeout(_lr);_lr=setTimeout(drawLV,150)});
let drag=null;const hitC=e=>{for(const el of document.elementsFromPoint(e.clientX,e.clientY)){const c=el.closest&&el.closest('.nd.c');if(c)return c}return null};
function dragStart(e){const d=drag;d.active=true;d.src.classList.add('lift');try{d.src.setPointerCapture(d.pid)}catch(_){}if(navigator.vibrate&&d.touch)navigator.vibrate(10)}
$('#lv').addEventListener('pointerdown',e=>{if(e.button>0)return;const n=e.target.closest('.nd'),hp=e.target.closest('path.hit');if(!n&&!hp)return;const cols=(n||hp).closest('.cols'),gi=+cols.dataset.g;
 let m=null,from=null,src=null;if(n&&n.classList.contains('m')){m=n.dataset.m;src=n}
 drag={n,hp,gi,cols,m,from,src,x:e.clientX,y:e.clientY,t:Date.now(),pid:e.pointerId,touch:e.pointerType!=='mouse',active:false,dead:false};
 if(drag.touch&&src)drag.timer=setTimeout(()=>{if(drag&&!drag.dead&&!drag.active)dragStart(e)},300)});
$('#lv').addEventListener('pointermove',e=>{if(!drag||drag.dead)return;const dist=Math.hypot(e.clientX-drag.x,e.clientY-drag.y);
 if(!drag.active){if(drag.touch){if(dist>8){drag.dead=true;clearTimeout(drag.timer)}return}if(!drag.src||dist<=12)return;dragStart(e)}
 const svg=drag.cols.querySelector('svg');let t=svg.querySelector('.tmp');if(!t){t=document.createElementNS('http://www.w3.org/2000/svg','path');t.setAttribute('class','tmp');t.style.stroke=D.groups[drag.gi].color;svg.append(t)}
 const c=drag.cols.getBoundingClientRect();t.setAttribute('d',curve(pt(drag.src,drag.cols),[e.clientX-c.left,e.clientY-c.top]));
 $$('#lv .nd.over').forEach(x=>x.classList.remove('over'));const tc=hitC(e);if(tc&&+tc.dataset.g===drag.gi)tc.classList.add('over')});
document.addEventListener('touchmove',e=>{if(drag&&drag.active)e.preventDefault()},{passive:false});
const endDrag=()=>{if(!drag)return null;const d=drag;drag=null;clearTimeout(d.timer);d.src&&d.src.classList.remove('lift');$$('#lv .nd.over').forEach(x=>x.classList.remove('over'));const t=$('#lv .tmp');t&&t.remove();return d};
$('#lv').addEventListener('pointercancel',endDrag);
$('#lv').addEventListener('pointerup',e=>{const d=endDrag();if(!d||d.dead)return;
 if(d.active){const tc=hitC(e);if(tc&&+tc.dataset.g===d.gi)return propose(d.gi,d.m,+tc.dataset.c,null,tc);return}
 if(Math.hypot(e.clientX-d.x,e.clientY-d.y)>12)return;
 if(d.hp&&!d.n)return linePop(d.gi,+d.hp.dataset.c,d.hp);
 closePop();
 if(d.n.classList.contains('c')){const ci=+d.n.dataset.c;if(L.sel&&L.sel.t==='m'&&L.sel.g===d.gi)return propose(d.gi,L.sel.v,ci,null,d.n);L.sel=(L.sel&&L.sel.t==='c'&&L.sel.v===ci&&L.sel.g===d.gi)?null:{t:'c',g:d.gi,v:ci};return drawLV()}
 if(L.sel&&L.sel.t==='c'&&L.sel.g===d.gi){const ci=L.sel.v;const el=$(`#lv .nd.c[data-g="${d.gi}"][data-c="${ci}"]`)||d.n;return propose(d.gi,d.m,ci,null,el)}
 L.sel=(L.sel&&L.sel.t==='m'&&L.sel.v===d.m&&L.sel.g===d.gi)?null:{t:'m',g:d.gi,v:d.m};drawLV()});
document.addEventListener('keydown',e=>{if(e.key!=='Escape'||!L)return;if(L.pop)return closePop();if(L.sel){L.sel=null;return drawLV()}closeLV()});
document.addEventListener('pointerdown',e=>{if(L&&L.pop&&!e.target.closest('#lvpop,#lv .nd,#lv path.hit'))closePop()},true);
addEventListener('beforeunload',e=>{if(L&&L.ops.length){e.preventDefault();e.returnValue=''}});
/* restore */
api('GET','/api/me').then(r=>{if(r.auth&&SS.getItem('kr_edit'))setEdit(true)}).catch(()=>{});
const og=SS.getItem('kr_open');if(og!=null){SS.removeItem('kr_open');const c=$('#c'+og);c&&!c.classList.contains('open')&&c.querySelector('header').click()}
document.addEventListener('click',e=>{const hd=e.target.closest('.cv header');if(hd)SS.setItem('kr_open_last',hd.closest('.cv').id.slice(1))});
const _p=persist;persist=async m=>{const c=$('.cv.open');if(c)SS.setItem('kr_open',c.id.slice(1));return _p(m)};
window.KR={links,setEdit,get L(){return L},get D(){return D}};
})();
