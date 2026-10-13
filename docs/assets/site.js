(()=>{'use strict';
const form=document.querySelector('#directory-form');if(!form)return;
const rows=Array.from(document.querySelectorAll('#directory-body tr'));
const q=document.querySelector('#query'),region=document.querySelector('#region');
const result=document.querySelector('#result-count'),empty=document.querySelector('#empty-result');
const prev=document.querySelector('#prev-page'),next=document.querySelector('#next-page'),pageLabel=document.querySelector('#page-label');
const pagination=document.querySelector('#pagination');let page=1;const size=25;
const normal=s=>String(s).normalize('NFKC').toLowerCase().trim();
const params=new URLSearchParams(location.search);q.value=params.get('q')||'';
if([...region.options].some(o=>o.value===params.get('region')))region.value=params.get('region');
function render(){const query=normal(q.value),reg=region.value;const matched=rows.filter(r=>(!reg||r.dataset.region===reg)&&(!query||normal(r.dataset.search).includes(query)));const pages=Math.max(1,Math.ceil(matched.length/size));page=Math.max(1,Math.min(page,pages));rows.forEach(r=>r.hidden=true);matched.slice((page-1)*size,page*size).forEach(r=>r.hidden=false);result.textContent=`找到 ${matched.length} 条已核对版本记录`;pageLabel.textContent=`第 ${page} / ${pages} 页`;prev.disabled=page===1;next.disabled=page===pages;empty.hidden=matched.length!==0;pagination.hidden=matched.length===0;const p=new URLSearchParams();if(q.value.trim())p.set('q',q.value.trim());if(reg)p.set('region',reg);history.replaceState(null,'',location.pathname+(p.size?'?'+p.toString():''));}
form.addEventListener('submit',e=>{e.preventDefault();page=1;render();});region.addEventListener('change',()=>{page=1;render();});document.querySelector('#reset-filter').addEventListener('click',()=>{q.value='';region.value='';page=1;render();q.focus();});prev.addEventListener('click',()=>{page--;render();document.querySelector('#directory-table').scrollIntoView({block:'start'});});next.addEventListener('click',()=>{page++;render();document.querySelector('#directory-table').scrollIntoView({block:'start'});});pagination.hidden=false;render();
})();
