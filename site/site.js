(()=>{'use strict';
/* 通用列表筛选：许可记录表与行业媒体表共用一套逻辑，字段与文案由 cfg 指定。 */
const normal=s=>String(s).normalize('NFKC').toLowerCase().trim();
function bind(cfg){
const form=document.querySelector(cfg.form);if(!form)return;
const body=document.querySelector(cfg.body);if(!body)return;
const rows=Array.from(body.querySelectorAll('tr'));
const q=document.querySelector(cfg.q);
const selects=(cfg.selects||[]).map(s=>{const el=document.querySelector(s.el);return el?{el,key:s.key,param:s.param}:null}).filter(Boolean);
const result=document.querySelector(cfg.result),empty=document.querySelector(cfg.empty);
const prev=document.querySelector(cfg.prev),next=document.querySelector(cfg.next),pageLabel=document.querySelector(cfg.label);
const pagination=document.querySelector(cfg.pagination);
const reset=document.querySelector(cfg.reset);
let page=1;const size=cfg.size||25;
const params=new URLSearchParams(location.search);
if(q&&params.get('q'))q.value=params.get('q');
selects.forEach(s=>{const v=params.get(s.param);if(v&&[...s.el.options].some(o=>o.value===v))s.el.value=v;});
function render(){
 const query=normal(q?q.value:'');
 const matched=rows.filter(r=>selects.every(s=>!s.el.value||r.dataset[s.key]===s.el.value)&&(!query||normal(r.dataset.search).includes(query)));
 const pages=Math.max(1,Math.ceil(matched.length/size));page=Math.max(1,Math.min(page,pages));
 rows.forEach(r=>r.hidden=true);
 matched.slice((page-1)*size,page*size).forEach(r=>r.hidden=false);
 result.textContent=cfg.text(matched.length);
 pageLabel.textContent=`第 ${page} / ${pages} 页`;
 prev.disabled=page===1;next.disabled=page===pages;
 empty.hidden=matched.length!==0;pagination.hidden=matched.length===0;
 const p=new URLSearchParams();
 if(q&&q.value.trim())p.set('q',q.value.trim());
 selects.forEach(s=>{if(s.el.value)p.set(s.param,s.el.value)});
 history.replaceState(null,'',location.pathname+(p.size?'?'+p.toString():''));
}
form.addEventListener('submit',e=>{e.preventDefault();page=1;render();});
selects.forEach(s=>s.el.addEventListener('change',()=>{page=1;render();}));
if(reset)reset.addEventListener('click',()=>{if(q)q.value='';selects.forEach(s=>s.el.value='');page=1;render();if(q)q.focus();});
prev.addEventListener('click',()=>{page--;render();document.querySelector(cfg.table).scrollIntoView({block:'start'});});
next.addEventListener('click',()=>{page++;render();document.querySelector(cfg.table).scrollIntoView({block:'start'});});
pagination.hidden=false;render();
}
bind({form:'#directory-form',body:'#directory-body',q:'#query',selects:[{el:'#region',key:'region',param:'region'},{el:'#kind',key:'kind',param:'kind'}],result:'#result-count',empty:'#empty-result',prev:'#prev-page',next:'#next-page',label:'#page-label',pagination:'#pagination',reset:'#reset-filter',table:'#directory-table',size:25,text:n=>`找到 ${n} 条已核对版本记录`});
bind({form:'#industry-form',body:'#ind-body',q:'#ind-query',selects:[{el:'#ind-industry',key:'industry',param:'industry'},{el:'#ind-quality',key:'quality',param:'quality'},{el:'#ind-tier',key:'tier',param:'tier'},{el:'#ind-lic',key:'lic',param:'lic'}],result:'#ind-count',empty:'#ind-empty',prev:'#ind-prev',next:'#ind-next',label:'#ind-page-label',pagination:'#ind-pagination',reset:'#ind-reset',table:'#ind-table',size:30,text:n=>`找到 ${n} 家行业媒体`});
})();
