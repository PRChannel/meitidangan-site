#!/usr/bin/env python3
"""Nationwide official-source discovery and conservative candidate extraction.
No changes to website, no auto-approval. Use only official, explicitly configured URLs.
"""
import argparse, csv, datetime, hashlib, io, json, re, time, zipfile
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parent
LIC=re.compile(r'(?<!\d)\d{11}(?!\d)')
DOMAIN=re.compile(r'(?<![\w.-])(?:https?://)?(?:[a-z0-9-]+\.)+[a-z]{2,}(?![a-z0-9-])',re.I)
WEBSITE=re.compile('互联网站|网站服务|网站名单|网站类|网站名称|网站地址|域名|网址')
EXCLUDE=re.compile('应用程序|移动应用|公众号|公众账号|论坛|博客|微博|直播|单位名单|服务单位|许可单位|账号名称')
EXT=re.compile(r'\.(?:docx?|xlsx?|pdf|csv)(?:$|[?#])',re.I)


def norm(s):return re.sub(r'[\s；;，,、|/]+','',str(s or '')).strip().lower()
def domains(s):return sorted(set(d.lower().removeprefix('https://').removeprefix('http://').removeprefix('www.') for d in DOMAIN.findall(s or '')))
def read_csv(p):return list(csv.DictReader(open(p,encoding='utf-8-sig',newline='')))
def write_csv(p,rows,fields):
    p.parent.mkdir(parents=True,exist_ok=True)
    with open(p,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)

def extract_table(rows,context,origin):
    """Only accept tables with explicit website cues; cannot prove rows valid."""
    candidates=[]
    ctx=' '.join(context)
    # Header with 服务地址 is useful, but is NOT enough when section is explicitly forum/other service.
    headings=' '.join(context[1:])
    if EXCLUDE.search(headings) and not re.search('互联网站|网站服务|网站名单',headings):return candidates
    if not WEBSITE.search(ctx):return candidates
    if EXCLUDE.search(context[0]) and not re.search('互联网站|网站服务|网站名单',context[0]):return candidates
    for i,cells in enumerate(rows):
        if len(cells)<2:continue
        joined=' '.join(cells)
        ids=LIC.findall(joined)
        if not ids:continue
        if EXCLUDE.search(' '.join(cells[:2])) and not WEBSITE.search(' '.join(cells[:2])):continue
        # Service name is typically adjacent to license; preserve raw cells instead of guessing silently.
        idpos=next((j for j,c in enumerate(cells) if LIC.search(c)),None)
        if idpos is None:continue
        name=''
        # Ordinary official website columns: sequence, service name, website address/operator, license.
        for j in [1, idpos-2, idpos-1, idpos+1,0]:
            if 0<=j<len(cells):
                v=cells[j].strip()
                if v and not LIC.search(v) and not re.fullmatch(r'\d+',v) and len(v)<100 and not WEBSITE.fullmatch(v):
                    name=v;break
        if not name:continue
        candidates.append(dict(record_name=name,license_number=ids[0],domains_raw=';'.join(domains(joined)),raw_cells=json.dumps(cells,ensure_ascii=False),row_number=i+1,origin=origin,review_status='candidate_unverified'))
    return candidates

def parse_html(raw,url):
    soup=BeautifulSoup(raw,'html.parser'); candidate=[];attachments=[]; reports=[]
    for a in soup.find_all('a',href=True):
        link=urljoin(url,a['href'].strip());label=a.get_text(' ',strip=True)
        if EXT.search(link) or (re.search(r'附件|下载|名单|许可',label) and any(s in link.lower() for s in ['download','attachment','upload'])):
            if urlparse(link).scheme=='https':attachments.append({'url':link,'label':label[:140]})
    for idx,t in enumerate(soup.select('table')):
        # title can be preceding siblings; table header may be separate from first row
        nearest=[]
        x=t
        for _ in range(4):
            x=x.find_previous(['h1','h2','h3','h4','p','div','strong','b'])
            if x:nearest.append(x.get_text(' ',strip=True)[:95])
        rows=[]
        for tr in t.find_all('tr'):
            cells=[c.get_text(' ',strip=True) for c in tr.find_all(['td','th'],recursive=False)]
            if cells:rows.append(cells)
        top=[' '.join(r) for r in rows[:2]]
        context=top+nearest[:2]
        entries=extract_table(rows,context,f'html_table_{idx}')
        candidate+=entries
        reports.append({'index':idx,'rows':len(rows),'context':' | '.join(context)[:240],'candidates':len(entries)})
    return candidate,attachments,reports

def parse_docx(raw):
    from docx import Document
    d=Document(io.BytesIO(raw));all=[];table_report=[]
    for j,t in enumerate(d.tables):
        rows=[[c.text.strip() for c in row.cells] for row in t.rows]
        context=[' '.join(rows[0]) if rows else '']
        # DOCX official annexes commonly use numbered tables in this order:
        # unit, websites, applications, forums, public accounts, others.
        # Without category header, require website address column AND exclude ambiguous sheets.
        if j != 1: context.append('应用程序')
        else: context.append('互联网站名单')
        hits=extract_table(rows,context,f'docx_table_{j}')
        all+=hits;table_report.append({'table':j,'rows':len(rows),'candidates':len(hits),'heading':' | '.join(context)[:180]})
    return all,table_report

def parse_xlsx(raw):
    from openpyxl import load_workbook
    wb=load_workbook(io.BytesIO(raw),read_only=True,data_only=True)
    all=[];report=[]
    for ws in wb:
        rows=[[str(c).strip() if c is not None else '' for c in r] for r in ws.iter_rows(values_only=True)]
        context=[' '.join(rows[0]) if rows else '',ws.title]
        hits=extract_table(rows,context,'xlsx_sheet_'+ws.title)
        all+=hits;report.append({'sheet':ws.title,'rows':len(rows),'candidates':len(hits)})
    return all,report

def fetch(url,limit=8_000_000):
    req=Request(url,headers={'User-Agent':'ChinaMediaRegistryResearch/0.4 (+manual public-record survey)','Accept':'text/html,application/pdf,application/octet-stream,*/*'})
    with urlopen(req,timeout=24) as resp:
        end=resp.geturl()
        if urlparse(end).scheme!='https':raise ValueError('HTTPS redirect required')
        data=resp.read(limit+1)
        if len(data)>limit:raise ValueError('File exceeds size limit')
        return data,resp.headers.get('Content-Type',''),end

def main():
    p=argparse.ArgumentParser();p.add_argument('--online',action='store_true');p.add_argument('--offline-zip',action='append',default=[],help='Prior GitHub source artifact zip, repeatable');p.add_argument('--output',default='nationwide_output');p.add_argument('--max-attachments',type=int,default=75);a=p.parse_args()
    output=ROOT/a.output;output.mkdir(exist_ok=True,parents=True)
    index=json.loads((ROOT/'data/sources_32.json').read_text());baseline=read_csv(ROOT/'data/baseline_400.csv')
    existing={(norm(r['service_name']),norm(r['license_number'])):r for r in baseline}
    allrows=[];state=[];evidence=[];errors=[];used=set();queue=[]
    # Reuse existing downloadable snapshots if provided; do not mistake prior artifacts for new official fetching.
    for zpath in a.offline_zip:
        with zipfile.ZipFile(zpath) as z:
            for name in z.namelist():
                if not name.endswith('.html'):continue
                raw=z.read(name)
                if len(raw)>8_000_000:continue
                # Without source manifest linkage, this is only an unassigned diagnostic snapshot.
                evidence.append({'region':'unassigned','origin':name,'sha256':hashlib.sha256(raw).hexdigest(),'status':'offline_snapshot_not_source_matched'})
    for i,src in enumerate(index):
        region=src.get('region','');url=src.get('source_url','')
        entry=dict(region=region,url=url,status='not_run',website_candidates=0,attachments_found=0,notes='')
        if not url:entry.update(status='missing_url');state.append(entry);continue
        if not a.online:entry.update(status='offline_not_fetched');state.append(entry);continue
        try:
            raw,ct,end=fetch(url)
            if b'<html' not in raw[:4000].lower() and 'text/html' not in ct:raise ValueError('Non-HTML source, manual adapter needed')
            sha=hashlib.sha256(raw).hexdigest();fn=f'{i+1:02d}_{sha[:12]}.html';(output/'evidence').mkdir(exist_ok=True);(output/'evidence'/fn).write_bytes(raw)
            rows,attachments,tables=parse_html(raw,end)
            for r in rows:r.update(region=region,source_url=end,evidence_sha256=sha,evidence_path='evidence/'+fn)
            allrows+=rows
            for att in attachments:queue.append(dict(att,region=region,source_url=end))
            entry.update(status='downloaded',website_candidates=len(rows),attachments_found=len(attachments),notes='Check table classifications, attachments and missing records')
            evidence.append({'region':region,'origin':end,'sha256':sha,'status':'html_saved'})
        except Exception as e:entry.update(status='failed',notes=f'{type(e).__name__}: {str(e)[:180]}')
        state.append(entry);time.sleep(0.5)
    # Official-site attachments discovered by the complete official index. Dedup and keep isolated.
    seen=set();attachment_log=[]
    for att in queue:
        url=att['url'];key=(att['region'],url)
        if key in seen:continue
        seen.add(key)
        if len(attachment_log)>=a.max_attachments:break
        row=dict(region=att['region'],url=url,label=att['label'],status='skipped',candidates=0,note='')
        if not a.online:row['note']='offline';attachment_log.append(row);continue
        suffix=Path(urlparse(url).path).suffix.lower()
        if suffix not in ('.docx','.xlsx'):
            row['note']='PDF/legacy attachment requires separate conservative handling';attachment_log.append(row);continue
        try:
            raw,ct,end=fetch(url)
            sha=hashlib.sha256(raw).hexdigest();(output/'evidence').mkdir(exist_ok=True);fn=f'attachment_{sha[:12]}{suffix}';(output/'evidence'/fn).write_bytes(raw)
            hits,report=(parse_docx(raw) if suffix=='.docx' else parse_xlsx(raw))
            for r in hits:r.update(region=att['region'],source_url=att['source_url'],evidence_sha256=sha,evidence_path='evidence/'+fn)
            allrows+=hits;row.update(status='downloaded_parsed',candidates=len(hits),note=json.dumps(report[:5],ensure_ascii=False)[:500]);evidence.append({'region':att['region'],'origin':end,'sha256':sha,'status':'attachment_saved'})
        except Exception as e:row.update(status='failed',note=f'{type(e).__name__}: {str(e)[:180]}')
        attachment_log.append(row)
    # Strict key dedup only; never infer identity from license alone (may span services).
    candidates=[];dup=0
    for r in allrows:
        k=(r['region'],norm(r['record_name']),norm(r['license_number']))
        if k in used:dup+=1;continue
        used.add(k)
        base=existing.get((norm(r['record_name']),norm(r['license_number'])))
        if not base:result='待审核新增';baseid=''
        elif r['domains_raw'] and base.get('domains_raw') and set(domains(r['domains_raw']))!=set(domains(base['domains_raw'])):result='域名差异待审';baseid=base['record_id']
        else:result='匹配旧库待证据复核';baseid=base['record_id']
        r.update(match_status=result,baseline_record_id=baseid)
        candidates.append(r)
    cf=['region','record_name','license_number','domains_raw','match_status','baseline_record_id','source_url','origin','evidence_path','evidence_sha256','review_status','raw_cells']
    write_csv(output/'全国候选记录.csv',candidates,cf)
    write_csv(output/'待审核新增.csv',[r for r in candidates if r['match_status']=='待审核新增'],cf)
    write_csv(output/'域名冲突.csv',[r for r in candidates if r['match_status']=='域名差异待审'],cf)
    write_csv(output/'32地区来源状态.csv',state,['region','url','status','website_candidates','attachments_found','notes'])
    write_csv(output/'附件处理状态.csv',attachment_log,['region','url','label','status','candidates','note'])
    (output/'证据索引.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2))
    summary=dict(sources=len(index),downloaded=sum(x['status']=='downloaded' for x in state),candidates=len(candidates),pending_additions=sum(r['match_status']=='待审核新增' for r in candidates),conflicts=sum(r['match_status']=='域名差异待审' for r in candidates),duplicates_discarded=dup,attachments_processed=sum(x['status']=='downloaded_parsed' for x in attachment_log),baseline_records=len(baseline),publish_allowed=False,all_new_records_require_review=True)
    (output/'SUMMARY.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(json.dumps(summary,ensure_ascii=False))
if __name__=='__main__':main()
