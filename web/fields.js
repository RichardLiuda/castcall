/* 报名表字段选择器：网页向导（setup.html）和后台「报名表」面板（edit.js）共用。
   fieldPicker(root, presets, current) → {value()}：value() 是写进 site.json signup.fields 的列表。
   预设（身高 / 年龄 / 性别 / 样片…）勾选 + 选填 / 必填；另外最多 6 道自定义文字题。 */
(()=>{
const css=`.fp{display:grid;gap:8px}.fp-row{display:flex;align-items:center;gap:10px;border:2px solid var(--ink);border-radius:12px;padding:8px 10px;background:var(--paper)}
.fp-row.off{opacity:.55}.fp-row label{display:flex;align-items:center;gap:8px;flex:1;min-width:0;cursor:pointer;font-weight:700}.fp-row label b{white-space:nowrap;flex:none}.fp-row label small{min-width:0;font-weight:500;color:var(--ink-soft);font-size:12px}
.fp-row select,.fp-row input[type=text]{border:2px solid var(--ink);border-radius:9px;padding:5px 8px;font:inherit;font-size:13px;background:var(--paper);color:var(--ink)}
.fp-row input[type=text]{flex:1;min-width:0}.fp-x{border:0;background:none;color:var(--ink-soft);font-size:18px;cursor:pointer;padding:0 4px}
.fp-add{justify-self:start;border:2px dashed var(--ink);border-radius:10px;background:none;color:var(--ink);font:inherit;font-weight:700;font-size:13px;padding:6px 12px;cursor:pointer}
.fp-fixed{font-size:12.5px;color:var(--ink-soft);margin:0}`;
if(!document.getElementById('fp-css')){const s=document.createElement('style');s.id='fp-css';s.textContent=css;document.head.append(s)}
const el=(t,a={},...c)=>{const e=document.createElement(t);for(const k in a)k.startsWith('on')?e.addEventListener(k.slice(2),a[k]):a[k]!==false&&e.setAttribute(k,a[k]===true?'':a[k]);e.append(...c.flat());return e};
const HINT={number:f=>'数字'+(f.unit?'（'+f.unit+'）':''),select:f=>(f.options||[]).join(' / '),image:()=>'图片，只有后台看得到',text:()=>'一行文字',textarea:()=>'一段文字'};
const req=on=>{const s=el('select',{},el('option',{value:''},'选填'),el('option',{value:'1'},'必填'));s.value=on?'1':'';return s};
window.fieldPicker=function(root,presets,current){
 const cur=Object.fromEntries((current||[]).map(f=>[f.key,f]));
 const rows=presets.map(p=>{const on=el('input',{type:'checkbox'}),r=req(cur[p.key]&&cur[p.key].required);on.checked=!!cur[p.key];
  const row=el('div',{class:'fp-row'},el('label',{},on,el('b',{},p.label),el('small',{},(p.hint||HINT[p.type](p)))),r);
  const sync=()=>{row.classList.toggle('off',!on.checked);r.disabled=!on.checked};on.addEventListener('change',sync);sync();
  return {get:()=>on.checked?{key:p.key,...(r.value?{required:true}:{})}:null,row}});
 const box=el('div',{class:'fp'});const customs=[];
 const addCustom=(f)=>{if(customs.length>=6)return;const t=el('input',{type:'text',maxlength:20,placeholder:'自定义题目，比如「想出的妆面」'});t.value=f?f.label:'';const r=req(f&&f.required);
  const c={row:null,key:f&&f.key,get:()=>t.value.trim()?{label:t.value.trim(),type:'text',...(r.value?{required:true}:{})}:null};
  c.row=el('div',{class:'fp-row'},t,r,el('button',{type:'button',class:'fp-x','aria-label':'删除',onclick:()=>{customs.splice(customs.indexOf(c),1);c.row.remove();add.hidden=false}},'×'));
  customs.push(c);box.insertBefore(c.row,add);add.hidden=customs.length>=6;if(!f)t.focus()};
 const add=el('button',{type:'button',class:'fp-add',onclick:()=>addCustom()},'+ 自定义一题');
 box.append(el('p',{class:'fp-fixed'},'CN 和联系方式是固定要填的。下面勾选的会加在后面：'),...rows.map(x=>x.row),add);
 (current||[]).filter(f=>!presets.some(p=>p.key===f.key)).forEach(addCustom);
 root.replaceChildren(box);
 /* 已有的自定义题保留原来的 key（旧报名的答案按 key 对题目），新加的取没用过的 q 编号 */
 return {value(){const used=new Set(customs.map(c=>c.key).filter(Boolean));let n=0;const next=()=>{do n++;while(used.has('q'+n));used.add('q'+n);return 'q'+n};
  return [...rows.map(x=>x.get()),...customs.map(c=>{const v=c.get();return v&&{key:c.key||(c.key=next()),...v}})].filter(Boolean)}}};
})();
