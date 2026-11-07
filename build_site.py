"""Generate the public static site from reviewed records only. Python standard library."""
from pathlib import Path
import csv, json, html, re, shutil, collections
from urllib.parse import urlparse

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'docs'
DOMAIN='https://meitidangan.com'
payload=json.loads((ROOT/'data/public-records.json').read_text(encoding='utf-8'))
records=payload['records']
coverage=json.loads((ROOT/'data/coverage.json').read_text(encoding='utf-8'))
articles=json.loads((ROOT/'data/articles.json').read_text(encoding='utf-8'))
assert len({r['record_id'] for r in records})==len(records),'记录编号重复'
def kind(r):return r.get('record_kind','website')
SITES=[r for r in records if kind(r)=='website']
ENTITIES=[r for r in records if kind(r)=='entity']
FORMS=[r for r in records if kind(r)=='service']
assert all(r['review_status']=='verified_dated_official_record' for r in records),'存在未审核记录'
assert all(r['registered_domains'] for r in SITES),'存在缺少域名的网站记录'
assert all(not r['registered_domains'] for r in ENTITIES+FORMS),'主体与服务形式记录不应带域名'
assert all(r.get('service_form') for r in FORMS),'服务形式记录缺少 service_form'
assert all(re.fullmatch(r'\d{11}',r['license_number']) for r in records),'许可证号格式异常'
assert all(urlparse(r['source_url']).scheme in ('http','https') for r in records),'来源地址异常'
# 统计口径全部由数据推导，避免改条数时漏改文案
N=len(records)
N_SITE=len(SITES)
N_ENTITY=len(ENTITIES)
N_FORM=len(FORMS)
CENTRAL=[r for r in records if r['region']=='中央']
N_CENTRAL=len(CENTRAL)
N_LOCAL=N-N_CENTRAL
DATE=max(r['verified_at'] for r in records)
PROV=len([c for c in coverage if c['省份']!='中央' and int(c['本轮来源名单已提取行数'] or 0)>0])
MISSING=len([c for c in coverage if '原件缺口' in c['覆盖状态']])
counts=collections.Counter(r['region'] for r in records)
if OUT.exists(): shutil.rmtree(OUT)
OUT.mkdir()
(OUT/'.nojekyll').write_text('')
(OUT/'CNAME').write_text('meitidangan.com\n')
(OUT/'assets').mkdir()
for file in ['site.css','site.js']: shutil.copyfile(ROOT/'site'/file,OUT/'assets'/file)
(OUT/'data').mkdir()
shutil.copyfile(ROOT/'data/public-records.json',OUT/'data/records.json')
shutil.copyfile(ROOT/'data/coverage.json',OUT/'data/coverage.json')
REGIONS=[r['省份'] for r in coverage]
pages=[]
def esc(s):return html.escape(str(s or ''),quote=True)
def slug(r):return r['record_id'].lower()
def rec_route(r):return {'entity':'units/','service':'services/'}.get(kind(r),'media/')+slug(r)+'/'
def root_prefix(route):return '../'*len([p for p in route.strip('/').split('/') if p])
def link(prefix,path):return prefix+path
def head(title,desc,route,schema=None,active=''):
 p=root_prefix(route);nav=[('directory/','媒体查询','directory'),('sources/','来源与覆盖','sources'),('research/','媒体研究','research'),('methods/','核验方法','methods'),('about/','关于我们','about')]
 ld='';
 if schema:ld='<script type="application/ld+json">'+json.dumps(schema,ensure_ascii=False).replace('<','\\u003c')+'</script>'
 return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)} | 中国媒体身份资料库</title><meta name="description" content="{esc(desc)}"><meta name="robots" content="index,follow"><link rel="canonical" href="{DOMAIN}/{route}"><meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(desc)}"><meta property="og:type" content="website"><meta property="og:url" content="{DOMAIN}/{route}"><link rel="stylesheet" href="{p}assets/site.css">{ld}</head><body><div class="strip"><div class="wrap"><span>CHINA MEDIA REGISTRY</span><span>公开名单版本记录 · 核验日期 {DATE}</span></div></div><header class="header"><div class="wrap head"><a class="brand" href="{p or './'}"><span class="mark" aria-hidden="true">档</span><span><strong>中国媒体身份资料库</strong><small>CHINA MEDIA REGISTRY</small></span></a><nav class="nav" aria-label="主导航">{''.join(f'<a href="{p}{path}"'+(' aria-current="page"' if key==active else '')+f'>{label}</a>' for path,label,key in nav)}</nav></div></header><main class="wrap">'''
def footer(route):
 p=root_prefix(route)
 return f'''</main><footer class="footer"><div class="wrap"><div>中国媒体身份资料库 · 荆门暗猫网络科技有限公司运营<br>独立资料整理项目，记录以所列来源及统计日期为依据。</div><div><a href="{p}about/">关于与运营主体</a>　<a href="{p}feedback/">纠错说明</a>　<a href="{p}privacy/">隐私说明</a></div></div></footer><script src="{p}assets/site.js" defer></script></body></html>'''
def write(route,title,desc,body,active='',schema=None):
 f=OUT/route/'index.html';f.parent.mkdir(parents=True,exist_ok=True)
 f.write_text(head(title,desc,route,schema,active)+body+footer(route),encoding='utf-8');pages.append(route)
def ev_meta(r):
 """证据级别与说明文案：必须按记录实际采集方式区分，不得混用。"""
 m=r.get('evidence_method')
 if m=='pdf_text_extraction_sequential_check':
  return ('PDF原件文本提取已校验','本记录来自国家网信办公布的PDF名单，已用程序校验条数与名单标注一致、序号连续、许可证号格式与登记地址完整，并保留原PDF的SHA256。PDF版面的逐行目视复核尚未完成。')
 if m=='ocr_image_recognition_domain_http_checked':
  return ('图片名单OCR提取+域名核验','本记录来自省级网信办公布的图片版名单，经本地OCR识别与表格重建，并用网站首页标题核验域名归属。图片分辨率有限，个别用字可能存在误差；如发现错误，请通过纠错渠道反馈。')
 if m=='ocr_image_recognition_address_print_confirmed':
  return ('图片名单OCR提取+地址复读','本记录来自省级网信办公布的图片版名单，登记地址经原图放大复读确认与原名单一致；该网站当前改版或暂不可访问，未能做首页标题核验。如发现错误，请通过纠错渠道反馈。')
 if m=='ocr_image_recognition_table_rebuild':
  return ('图片名单OCR提取+表格重建','本记录来自省级网信办公布的图片版名单，经本地OCR识别与表格重建，条数与名单标注核对一致；该类名单只列服务名称与标注单位，不含可核验的服务地址，因此无法做域名或链接层面的核验。如发现错误，请通过纠错渠道反馈。')
 if m=='official_attachment_text_extraction':
  return ('官方附件表格文本提取','本记录来自省级网信办公告附件中的电子表格（xls/xlsx），以文本方式直接提取、未经OCR，登记信息与原件零转写差异；已用程序校验条数与名单标注一致。个别登记域名当前可能已改版或暂停解析，不代表登记信息有误。如发现错误，请通过纠错渠道反馈。')
 return ('对应版本原件已核对','本记录的网站名称、登记地址及许可证号已与对应版本原件核对，保留原记录编号。')
def ev_short(r):
 return ev_meta(r)[0]
def ev_method_text(r):
 m=r.get('evidence_method')
 if m=='pdf_text_extraction_sequential_check':
  return 'PDF原件文本提取，条数与序号连续性已程序校验'
 if m=='ocr_image_recognition_domain_http_checked':
  return '图片名单OCR识别与表格重建，域名经网站首页标题核验'
 if m=='ocr_image_recognition_address_print_confirmed':
  return '图片名单OCR识别与表格重建，登记地址经原图放大复读确认'
 if m=='ocr_image_recognition_table_rebuild':
  return '图片名单OCR识别与表格重建，条数与名单标注核对'
 if m=='official_attachment_text_extraction':
  return '官方公告附件电子表格文本直接提取，条数已程序校验'
 return '原表页面逐条核对'
def pagehead(title,desc,kicker='PUBLIC RECORDS',route=''):
 p=root_prefix(route)
 return f'<section class="pagehead"><div class="crumb"><a href="{p or "./"}">首页</a> / {esc(title)}</div><div class="kicker">{esc(kicker)}</div><h1>{esc(title)}</h1><p>{esc(desc)}</p></section>'
def row(r,p=''):
 route=rec_route(r)
 if kind(r)=='entity':
  mid=f"<code>{esc('、'.join(r.get('service_categories') or []) or '未列服务类别')}</code><small>{esc(r.get('entity_nature') or '单位性质未列')}</small>"
  search=' '.join([r['name'],r['region'],r['license_number'],' '.join(r.get('service_categories') or []),r.get('entity_nature') or '','许可主体'])
 elif kind(r)=='service':
  form=r.get('service_form') or r.get('service_type') or '其他服务形式'
  mid=f"<code>{esc(form)}</code><small>{esc(r['operator_name'] or '该表未列单位名称')}</small>"
  search=' '.join([r['name'],r['region'],r['license_number'],form,r['operator_name'] or '','其他服务形式'])
 else:
  mid=f"<code>{esc(r['registered_addresses_raw']).replace(chr(10),'<br>')}</code>"
  search=' '.join([r['name'],r['region'],r['license_number'],r['registered_addresses_raw'],r['operator_name'] or '','网站服务'])
 return f'''<tr data-region="{esc(r['region'])}" data-kind="{kind(r)}" data-search="{esc(search)}"><td><a href="{p}{route}">{esc(r['name'])}</a><small>{esc(r['region'])} · {esc(ev_short(r))}</small></td><td>{mid}</td><td><code>{r['license_number']}</code></td><td>{esc(r['list_as_of'])}</td><td><a class="text-link" href="{p}{route}">查看记录</a></td></tr>'''
THEAD='<thead><tr><th scope="col">服务名称</th><th scope="col">登记地址 / 服务类别 / 服务形式</th><th scope="col">许可证编号</th><th scope="col">名单统计截至</th><th scope="col">证据与详情</th></tr></thead>'
def table(rs,p=''):
 return '<div class="tablebox"><table>'+THEAD+'<tbody>'+''.join(row(r,p) for r in rs)+'</tbody></table></div>'
dataset={'@context':'https://schema.org','@type':'Dataset','name':'中国媒体身份资料库 已核对版本许可记录','description':f'{N}条经对应版本官方原件核对的记录（网站服务{N_SITE}条、其他服务形式{N_FORM}条、许可主体{N_ENTITY}条；省级{N_LOCAL}条、中央新闻单位{N_CENTRAL}条），当前许可有效性未单独确认；原件缺口保留。','url':DOMAIN+'/','dateModified':DATE,'creator':{'@type':'Organization','name':'荆门暗猫网络科技有限公司'},'distribution':{'@type':'DataDownload','contentUrl':DOMAIN+'/data/records.json','encodingFormat':'application/json'}}
featured=[]
featured_regions=set()
for record in records:
 if record['region'] not in featured_regions:
  featured.append(record);featured_regions.add(record['region'])
 if len(featured)==6:break
home=f'''<section class="hero"><div><div class="kicker">PUBLIC MEDIA RECORDS / CHINA</div><h1>以公开来源<br>核对媒体身份信息。</h1><p>按网站服务名称、登记域名、应用或账号名称、许可证编号检索已核对的名单记录，查看原始来源和统计日期，理解不同版本的资料范围。</p><form action="directory/" class="search"><label for="hero-query" class="screenreader">媒体名称、域名或许可证编号</label><input id="hero-query" name="q" placeholder="媒体名称、域名或许可证编号" autocomplete="off"><button type="submit">查询资料</button></form><div class="hint">例如：红网、www.rednet.cn、黄河Plus</div></div><aside class="heroaside"><h2>收录的是名单版本记录</h2><p>每条公开记录关联来源公告和原件核对信息。统计日期、来源发布日期和核验日期分别记录，许可当前有效性未单独确认。</p><p>当前资料仍存在覆盖缺口。搜索未找到结果时，请结合来源范围判断。</p><a class="text-link" href="sources/">查看来源与覆盖情况</a></aside></section><div class="stats"><div class="stat"><span>已核对公开版本记录</span><strong>{N}</strong><span>网站、其他服务形式与主体合计</span></div><div class="stat"><span>其中网站服务记录</span><strong>{N_SITE}</strong><span>按名单服务项计</span></div><div class="stat"><span>其中其他服务形式</span><strong>{N_FORM}</strong><span>应用、账号等，无域名</span></div><div class="stat"><span>其中许可主体记录</span><strong>{N_ENTITY}</strong><span>按持证单位计</span></div><div class="stat"><span>其中中央新闻单位</span><strong>{N_CENTRAL}</strong><span>国家网信办名单</span></div><div class="stat"><span>公开记录涉及省份</span><strong>{len([k for k in counts if k!='中央'])}</strong><span>与采集覆盖数分开列示</span></div><div class="stat"><span>原件缺口省份</span><strong>{MISSING}</strong><span>在来源页明确保留</span></div></div><section class="section"><div class="section-head"><div><div class="kicker">DIRECTORY</div><h2>查询公开记录</h2></div><a class="text-link" href="directory/">查看全部{N}条</a></div>{table(featured)}</section><section class="section"><div class="section-head"><div><div class="kicker">REGIONAL COVERAGE</div><h2>按地区检索</h2></div></div><div class="region-grid">{''.join(f'<a href="regions/{REGIONS.index(region)+1:02d}/">{esc(region)}<small>{counts[region]}条公开版本记录</small></a>' for region in REGIONS)}</div></section><section class="section"><div class="section-head"><div><div class="kicker">RESEARCH & METHODS</div><h2>媒体研究与实务观察</h2></div><a class="text-link" href="research/">查看文章</a></div><div class="cards">{''.join(f'<a class="card" href="research/{esc(a["id"])}/"><span class="category">{esc(a["category"])}</span><h3>{esc(a["title"])}</h3><p>{esc(a["summary"])}</p></a>' for a in articles)}</div></section>'''
write('','首页',f'依据公开名单版本查询中国新闻网站、应用程序与公众账号的服务名称、登记域名、许可证号与来源。{N}条已核对记录（含中央新闻单位{N_CENTRAL}条），覆盖缺口明确保留。',home,schema=dataset)
directory=pagehead('媒体查询',f'仅检索{N}条已经过对应版本原件核对的公开记录（网站服务{N_SITE}条、其他服务形式{N_FORM}条、许可主体{N_ENTITY}条）。名称相同、编号相同或同域名的服务项不据此自动合并。',route='directory/')+f'''<form id="directory-form" class="filters" action="./"><label>媒体、域名或许可证编号<input id="query" name="q" aria-label="媒体、域名或许可证编号" autocomplete="off"></label><label>地区<select id="region" name="region"><option value="">全部地区</option>{''.join(f'<option value="{esc(r)}">{esc(r)}</option>' for r in REGIONS)}</select></label><label>记录类型<select id="kind" name="kind"><option value="">全部类型</option><option value="website">网站服务</option><option value="service">其他服务形式</option><option value="entity">许可主体</option></select></label><button class="btn" type="submit">查询</button><button class="btn-light" type="button" id="reset-filter">重置</button></form><div class="resultmeta"><span id="result-count">共{N}条已核对版本记录</span><span>核验日期：{DATE}</span></div><div class="tablebox" id="directory-table"><table>{THEAD}<tbody id="directory-body">{''.join(row(r,'../') for r in records)}</tbody></table></div><div id="empty-result" class="empty" hidden>未找到符合条件的公开版本记录。未查到不等同于网站没有许可，请查看<a class="text-link" href="../sources/">来源与覆盖范围</a>。</div><div id="pagination" class="pagination" hidden><button id="prev-page" class="btn-light" type="button">上一页</button><span id="page-label" class="meta"></span><button id="next-page" class="btn-light" type="button">下一页</button></div><noscript><p class="note">当前浏览器未运行筛选脚本，下面保留完整记录表，可使用浏览器查找功能检索。</p></noscript>'''
write('directory/','媒体查询',f'检索{N}条对应版本原件已核对的公开记录（网站服务、其他服务形式与许可主体），支持名称、域名、许可证号、类型和地区查询。',directory,'directory')
name_counts=collections.Counter(r['name'] for r in records)
dup_key=collections.Counter((r['name'],r['license_number']) for r in records)
def list_seq(r):
 d=r['record_id'].rsplit('-',1)[-1].lstrip('0')
 return d if d.isdigit() else ''
for r in records:
 route=rec_route(r)
 if name_counts[r['name']]==1:
  dtitle=r['name']
 elif dup_key[(r['name'],r['license_number'])]==1:
  dtitle=f"{r['name']}（{r['license_number']}）"
 else:
  sq=list_seq(r)
  dtitle=f"{r['name']}（{r['license_number']}，名单第{sq}项）" if sq else f"{r['name']}（{r['license_number']}，{r['record_id']}）"
 is_ent=kind(r)=='entity'
 is_form=kind(r)=='service'
 form=r.get('service_form') or r.get('service_type') or '其他服务形式'
 if is_ent:
  detail=pagehead(dtitle,f"{r['region']}互联网新闻信息服务许可主体记录。对应名单统计截至{r['list_as_of']}，当前许可有效性未单独确认。",'LICENSE HOLDER',route)
 elif is_form:
  detail=pagehead(dtitle,f"{r['region']}{form}服务记录。对应名单统计截至{r['list_as_of']}，当前许可有效性未单独确认。",'SERVICE FORM',route)
 else:
  detail=pagehead(dtitle,f"{r['region']}网站服务记录。对应名单统计截至{r['list_as_of']}，当前许可有效性未单独确认。",'MEDIA RECORD',route)
 # 证据级别必须如实区分：省级为原件页面逐条核对，中央为PDF文本提取+程序校验
 ev_label,ev_text=ev_meta(r)
 if is_ent:
  fields=[('单位名称',r['name']),('单位性质',r.get('entity_nature') or '该表未列单位性质'),('许可服务类别','、'.join(r.get('service_categories') or []) or '该表未列服务类别'),('许可证编号',r['license_number']),('许可机关',r.get('issuing_authority') or '属地网信办名单'),('所属地区',r['region']),('名单统计截至',r['list_as_of']),('来源发布日期',r['source_published_at'] or '原来源未明确'),('最近核验日期',r['verified_at']),('证据方式',ev_method_text(r)),('记录编号',r['record_id'])]
 elif is_form:
  fields=[('服务名称',r['name']),('服务形式',form),('名单标注单位',r['operator_name'] or '该表未列单位名称'),('许可证编号',r['license_number']),('登记地址',r.get('registered_addresses_raw') or '该表未列服务地址（应用与账号类名单只列名称与单位）'),('许可机关',r.get('issuing_authority') or '属地网信办名单'),('所属地区',r['region']),('名单统计截至',r['list_as_of']),('来源发布日期',r['source_published_at'] or '原来源未明确'),('最近核验日期',r['verified_at']),('证据方式',ev_method_text(r)),('记录编号',r['record_id'])]
 else:
  fields=[('网站服务名称',r['name']),('登记地址原文',r['registered_addresses_raw']),('许可证编号',r['license_number']),('许可单位',r['operator_name'] or '该网站表未列许可单位'),('许可服务类型',r['service_type'] or '该网站表未直接列示'),('许可机关',r.get('issuing_authority') or '属地网信办名单'),('所属地区',r['region']),('名单统计截至',r['list_as_of']),('来源发布日期',r['source_published_at'] or '原来源未明确'),('最近核验日期',r['verified_at']),('证据方式',ev_method_text(r)),('记录编号',r['record_id'])]
 fields_html=''.join(f'<div class="field"><dt>{esc(k)}</dt><dd>{esc(v).replace(chr(10),"<br>")}</dd></div>' for k,v in fields)
 dup_note=''
 if dup_key[(r['name'],r['license_number'])]>1:
  dup_note=f'<p class="note">名单中该服务名称与许可证号出现{dup_key[(r["name"],r["license_number"])]}次（本页对应名单序号 {list_seq(r)}），原件如此登记，未做合并或删除。</p>'
 date_note=''
 if r['source_published_at'] and r['source_published_at'][:4]!=r['list_as_of'][:4]:date_note='<p class="note">原来源页面显示的发布日期早于名单更新年份，本页分别照录两项日期，不据旧页面日期判定名单版本。</p>'
 if is_ent:
  scope_note='本条为主体记录：只说明该单位在所列统计日期名单中的许可主体身份，不表示其名下具体网站、应用程序或公众账号均已覆盖。'
 elif is_form:
  scope_note=f'本条为{form}类服务项记录：只说明该服务名称在所列统计日期的名单中被登记，名单不提供可核验的服务地址，因此无法做域名或链接层面的核验；也不表示该服务当前仍在运营、或某个同名账号即为名单所指对象。'
 else:
  scope_note='这条记录说明其出现于所列统计日期的名单。不能据此认定当前许可仍有效、站点实时可访问或某个商业发稿渠道获得授权。'
 detail+=f'''<div class="detail-grid"><section class="panel"><h2>名单登记信息</h2><dl class="fields">{fields_html}</dl></section><aside class="panel"><span class="label">{ev_label}</span><h2>来源与核对说明</h2><p>{ev_text}</p><p>{scope_note}</p>{dup_note}{date_note}<p><a class="source-link" href="{esc(r['source_url'])}" target="_blank" rel="noopener noreferrer">打开原始来源公告</a></p><details class="evidence"><summary>原件核对信息</summary><p>证据编号：{esc(r['evidence_id'])}</p><p>原件SHA256：<code>{esc(r['evidence_sha256'])}</code></p></details><p><a class="text-link" href="../../methods/">查看核验方法</a></p></aside></div><p><a class="text-link" href="../../directory/">返回媒体查询</a></p>'''
 if is_ent:
  schema={'@context':'https://schema.org','@type':'WebPage','name':r['name']+' 许可主体名单版本记录','url':DOMAIN+'/'+route,'description':f"互联网新闻信息服务许可主体及许可证号，名单截至{r['list_as_of']}；当前许可有效性未单独确认。",'dateModified':r['verified_at'],'citation':r['source_url'],'isPartOf':{'@type':'WebSite','name':'中国媒体身份资料库','url':DOMAIN+'/'}}
  write(route,dtitle+' '+r['license_number'],f"{r['name']}，互联网新闻信息服务许可主体，许可证号{r['license_number']}，名单截至{r['list_as_of']}。",detail,'directory',schema)
 elif is_form:
  schema={'@context':'https://schema.org','@type':'WebPage','name':r['name']+' '+form+'名单版本记录','url':DOMAIN+'/'+route,'description':f"{form}类互联网新闻信息服务项，名单标注单位与许可证号，名单截至{r['list_as_of']}；当前许可有效性未单独确认。",'dateModified':r['verified_at'],'citation':r['source_url'],'isPartOf':{'@type':'WebSite','name':'中国媒体身份资料库','url':DOMAIN+'/'}}
  write(route,dtitle+' '+r['license_number'],f"{r['name']}，{form}类互联网新闻信息服务项，许可证号{r['license_number']}，名单截至{r['list_as_of']}。",detail,'directory',schema)
 else:
  schema={'@context':'https://schema.org','@type':'WebPage','name':r['name']+' 网站许可名单版本记录','url':DOMAIN+'/'+route,'description':f"网站登记地址及编号，名单截至{r['list_as_of']}；当前许可有效性未单独确认。",'dateModified':r['verified_at'],'citation':r['source_url'],'isPartOf':{'@type':'WebSite','name':'中国媒体身份资料库','url':DOMAIN+'/'}}
  write(route,dtitle+' '+r['registered_domains'][0],f"{r['name']}，登记地址{r['registered_addresses_raw']}，许可证号{r['license_number']}，名单截至{r['list_as_of']}。",detail,'directory',schema)
for i,x in enumerate(coverage,1):
 allrs=[r for r in records if r['region']==x['省份']]
 sites=[r for r in allrs if kind(r)=='website'];ents=[r for r in allrs if kind(r)=='entity'];forms=[r for r in allrs if kind(r)=='service']
 route=f'regions/{i:02d}/'
 parts=[f'网站服务{len(sites)}条']+([f'其他服务形式{len(forms)}条'] if forms else [])+[f'许可主体{len(ents)}条']
 body=pagehead(x['省份']+'公开记录',f"当前公开{len(allrs)}条对应版本记录（{'、'.join(parts)}）。采集状态：{x['覆盖状态']}。",'REGIONAL RECORDS',route)
 body+='<p class="note">'+esc(x['问题与后续'])+('。公开记录数不是全国现行许可总量。' if x['省份']=='中央' else '。公开记录数不是全省现行许可总量。')+'</p>'
 if sites:
  body+='<h2 class="subhead">网站服务记录</h2>'+table(sites,'../../')
 if forms:
  byform=collections.Counter((r.get('service_form') or '其他服务形式') for r in forms)
  body+='<h2 class="subhead">其他服务形式记录</h2><p class="meta">'+esc('、'.join(f'{k} {v} 条' for k,v in byform.items()))+'；该类记录名单只列服务名称与单位，不含可核验的服务地址。</p>'
  for form_name in byform:
   body+=table([r for r in forms if (r.get('service_form') or '其他服务形式')==form_name],'../../')
 if ents:
  body+='<h2 class="subhead">许可主体记录</h2>'+table(ents,'../../')
 if not allrs:
  body+='<div class="empty">本地区暂没有通过本轮公开审核的记录。请到<a class="text-link" href="../../sources/">来源与覆盖页</a>查看已取得资料和剩余缺口。</div>'
 write(route,x['省份']+'公开记录',x['省份']+'对应版本的网站服务、其他服务形式与许可主体公开记录及当前资料覆盖范围。',body,'directory')
with (ROOT/'data/official-sources.csv').open(encoding='utf-8-sig',newline='') as f:official=list(csv.DictReader(f))
source_cards=[]
for x in official:
 urls=[u for u in x['本轮可公开记录采用入口'].split('；') if u] or [x['国家总索引指定入口']]
 source_cards.append('<section class="source-card"><h2>'+esc(x['许可范围'])+'</h2><p>公开版本记录：'+esc(x['公开版本记录数'])+'条</p><p>'+esc(x['原件覆盖状态'])+'</p><p>'+esc(x['剩余问题'])+'</p>'+''.join('<p><a class="source-link" href="'+esc(u)+'" target="_blank" rel="noopener noreferrer">'+('本轮采用公告' if x['本轮可公开记录采用入口'] else '国家索引指定入口')+'</a></p>' for u in urls if u)+'</section>')
sourcebody=pagehead('数据来源与覆盖',f'全国31省份纳入来源检查清单，{PROV}省取得网站行表，{MISSING}省原件缺口。{N}条公开记录（省级{N_LOCAL}条、中央新闻单位{N_CENTRAL}条）；采集行表、原件证据与公开审核分开列示。','SOURCE REGISTER','sources/')+'<p class="note">中央及国家网信办其他单位的PDF目前主要完成文本提取，未宣称原PDF版面核对完成。新疆生产建设兵团单列，不计入31省份完成数。各名单统计日期不一致，不能相加作为全国实时许可总量。</p><p><a class="text-link" href="https://www.cac.gov.cn/2026-07/22/c_1786465601042567.htm" target="_blank" rel="noopener noreferrer">国家网信办2026年7月22日总索引</a></p><div class="sources-list">'+''.join(source_cards)+'</div>'
write('sources/','数据来源与覆盖',f'31省来源检查、{PROV}省行表取得及{MISSING}省原件缺口，提供原始公告入口与公开审核范围。',sourcebody,'sources')
method=pagehead('核验方法','公开版本记录与实时许可状态分开处理，保留原表字段、统计日期和来源差异。','VERIFICATION METHOD','methods/')+f'''<div class="copy"><h2>核对什么</h2><p>核对网站服务名称、登记地址和许可证编号，按原表服务项边界保存。应用程序、公众账号、论坛和直播项目不混入网站表。名单没有给出的单位、服务类型或域名保持空缺，不根据名称推测补入。</p><h2>如何处理日期和版本</h2><p>来源发布日期、名单统计截止日期、实际核验日期分别记录。原表只写到月份时，保留月份。不同版本名称或证号发生变化时，保留两版证据并复核，不自动解释为注销或换主体。</p><h2>哪些记录暂不公开</h2><p>原件未取得、官方链尚未确认、登记域名缺失、统计日期不明、明确字段差异及同域不同证号线索，均进入待审资料，不写入公开数据。</p><h2>三类记录</h2><p>记录分为「网站服务」「其他服务形式」与「许可主体」三种。网站服务记录对应名单中的具体网站服务项，含登记地址（域名）；其他服务形式记录对应名单中的应用程序、公众账号、论坛、博客、微博客、即时通信工具、网络直播等非网站服务项，名单只给服务名称与标注单位，没有可核验的地址；许可主体记录对应持证单位，只有单位名称、单位性质、许可服务类别和许可证编号。同一许可证号下可能既有主体记录、也有若干网站或其他服务形式记录，三者不互相替代，也不据此推断主体名下所有服务均已收录。</p><h2>证据级别</h2><p>省级记录为逐条与对应版本原件页面核对后公开。中央新闻单位与国家网信办其他单位共{N_CENTRAL}条，采用国家网信办公布的PDF原件文本提取，并以程序校验条数与名单标注一致、序号连续、许可证号格式与登记域名完整；PDF版面逐行目视复核尚未完成，记录页已标注这一区别。</p><h2>如何理解查询结果</h2><p>同一个许可证可能对应多个网站，同名也可能对应不同服务项。查询未找到记录，可能来自覆盖缺口、来源发布时间、名称差异或暂缓审核，不能据此认定网站违法。</p><h2>公开数据范围</h2><p>当前公开数据为静态版本记录，非全国完整现行许可名录。可下载<a class="text-link" href="../data/records.json">{N}条公开记录JSON</a>。数据文件也明确保留当前许可有效性未单独确认的状态。</p></div>'''
write('methods/','核验方法','网站表原件核对、日期版本处理、暂缓标准及查询适用范围。',method,'methods')
about=pagehead('关于我们','面向公众的独立媒体资料整理与检索项目。','ABOUT THE REGISTRY','about/')+f'''<div class="copy"><h2>项目与运营主体</h2><p>中国媒体身份资料库由荆门暗猫网络科技有限公司建设与运营，围绕互联网新闻信息服务网站名单整理可追溯的公开版本记录。本项目不属于政府机关，也未宣称获得官方授权认证。</p><h2>业务关联与数据支持</h2><p>运营公司同时运营暗传播（PR Channel），两者存在明确运营关联。本资料库与商业媒体报价目录分开维护，收录与审核以公开证据为依据，不因合作关系或商业发布服务而改变。</p><p>感谢<a class="text-link" href="https://www.epr.ink/" target="_blank" rel="noopener noreferrer">暗传播</a>为资料整理提供数据支持。许可事实及名单版本以国家和地方许可机关的原始公开来源为准。</p><h2>维护与局限</h2><p>当前公开{N}条对应版本记录，其中省级{N_LOCAL}条、中央新闻单位{N_CENTRAL}条；{MISSING}省仍缺可复核原件。数据更新存在时差，不提供实时许可有效性保证、媒体权威排名或商业渠道授权结论。</p><h2>纠错与隐私</h2><p>如发现名称、域名或编号差异，应先提供可追溯的原始证据。当前公开受理渠道尚未配置，网站不设反馈收集表单，也不收集或储存访客提交信息。详见<a class="text-link" href="../feedback/">纠错说明</a>与<a class="text-link" href="../privacy/">隐私说明</a>。</p></div>'''
write('about/','关于我们','中国媒体身份资料库的运营主体、业务关联、数据支持和资料维护范围。',about,'about')
feedback=pagehead('纠错说明','原始来源与可定位字段是核对资料差异的依据。','CORRECTION POLICY','feedback/')+'''<div class="copy"><h2>准备哪些证据</h2><p>请保留记录编号、需要修正的字段、原始官方公告网址、发布时间及具体差异。提交前移除非公开个人信息。</p><h2>如何处理争议</h2><p>先核对原件、名单版本与服务项范围，再保留修订依据。待审状态不等同于认定网站违法、许可失效或名单注销。</p><h2>受理渠道状态</h2><p>公开受理渠道尚未配置，本网站不提供在线提交表单。请勿通过未经验证的邮箱或社交账号发送敏感资料。</p></div>'''
write('feedback/','纠错说明','记录编号、原始公告、字段差异和当前纠错受理渠道状态。',feedback)
privacy=pagehead('隐私说明','本网站提供静态资料查询，不提供登录、支付或访客资料提交功能。','PRIVACY','privacy/')+'''<div class="copy"><h2>网站处理的信息</h2><p>网站不设置统计追踪脚本、第三方广告代码或反馈收集表单。查询列表的筛选在浏览器当前页面执行，页面没有专门收集搜索内容的接口。搜索条件会显示在网址中；从首页打开带条件的查询网址时，请求由托管服务处理，条件可能出现在浏览器历史或托管访问日志中。网站未使用浏览器持久存储保存查询内容。</p><h2>托管服务与外部来源</h2><p>网站由GitHub Pages托管时，托管服务商可能按其政策处理访问日志等技术信息。点击原始公告链接后，将进入相应外部网站，适用该网站的规则与隐私政策。</p><h2>资料范围</h2><p>公开记录来自公开许可名单，不用于建立访客画像。数据使用边界和现有覆盖缺口见核验方法与来源页。</p></div>'''
write('privacy/','隐私说明','静态搜索、无登录及提交表单、外部公告和托管服务的信息处理范围。',privacy)
research=pagehead('媒体研究与实务观察','保留核验方法和实际渠道观察，资料解释不替代许可机关公告。','RESEARCH & ANALYSIS','research/')+'<section class="section"><div class="cards">'+''.join(f'<a class="card" href="{esc(a["id"])}/"><span class="category">{esc(a["category"])}</span><h3>{esc(a["title"])}</h3><p>{esc(a["summary"])}</p><p class="meta">{esc(a["date"])}</p></a>' for a in articles)+'</div></section>'
write('research/','媒体研究与实务观察','围绕名单范围、实际发布渠道和不同版本变化的资料解读。',research,'research')
for a in articles:
 route='research/'+a['id']+'/'
 body=pagehead(a['title'],a['summary'],'RESEARCH & METHODS',route)+f'<article class="copy article"><p class="meta">发布：{a["date"]} · {esc(a["category"])}</p><p class="lead">{esc(a["summary"])}</p>'+''.join('<section><h2>'+esc(t)+'</h2><p>'+esc(p)+'</p></section>' for t,p in a['sections'])+'<p><a class="text-link" href="../../sources/">查看原始来源与覆盖</a>　<a class="text-link" href="../../methods/">查看核验方法</a></p></article>'
 write(route,a['title'],a['summary'],body,'research')
notfound=head('页面未找到','当前地址未对应公开资料页面。','404.html')+'<section class="pagehead"><h1>页面未找到</h1><p>请返回媒体查询，按名称、域名或许可证编号查找。</p><a class="btn" href="'+DOMAIN+'/directory/">返回媒体查询</a></section>'+footer('404.html')
notfound=notfound.replace('../assets/',DOMAIN+'/assets/').replace('href="../',f'href="{DOMAIN}/')
(OUT/'404.html').write_text(notfound,encoding='utf-8')
(OUT/'robots.txt').write_text('User-agent: *\nAllow: /\nSitemap: '+DOMAIN+'/sitemap.xml\n')
(OUT/'sitemap.xml').write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+''.join(f'<url><loc>{DOMAIN}/{p}</loc><lastmod>{DATE}</lastmod></url>' for p in pages)+'</urlset>')
manifest={'built_at':DATE,'public_records':len(records),'site_records':N_SITE,'service_form_records':N_FORM,'entity_records':N_ENTITY,'record_pages':len(records),'central_records':N_CENTRAL,'local_records':N_LOCAL,'public_provinces':len([k for k in counts if k!='中央']),'source_coverage_provinces':PROV,'original_missing_provinces':MISSING,'html_pages':len(pages)+1,'search_page_size':25,'domain':DOMAIN,'current_validity':'not_independently_confirmed','original_records_modified':False}
(ROOT/'BUILD.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
print(json.dumps(manifest,ensure_ascii=False))
