#!/usr/bin/env python3
"""China media source monitoring proof of concept. No writes to production systems."""
import argparse,csv,hashlib,json,re,time,sys
from pathlib import Path
from datetime import datetime,timezone
from urllib.request import Request,urlopen
from urllib.parse import urlparse
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parent
HEADERS=['region','url','http_status','downloaded','sha256','bytes','tables','candidate_rows','warning','snapshot_path']
URL_RE=re.compile(r'(?:https?://)?(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)+',re.I)
LIC_RE=re.compile(r'(?<![0-9])\d{11}(?![0-9])')

def read_sources():
    """Read the complete official-source index; preserve order for 4x8 matrix."""
    index=json.loads((ROOT/'official_sources_nationwide_32.json').read_text(encoding='utf-8'))
    for row in index:
        yield str(row['region']).strip(), str(row.get('source_url') or '').strip()

def inspect_html(content):
    """Read only website service tables. Other service types are never candidates."""
    soup=BeautifulSoup(content,'html.parser')
    tables=soup.select('table')
    candidates=[];table_report=[]
    for k,table in enumerate(tables):
        title=table.get_text(' ',strip=True)[:180]
        # Published tables usually include their numbered service-type heading in the first row.
        website=bool(re.search(r'(互联网站|网站名单|网站服务)',title[:110]))
        excluded=bool(re.search(r'(应用程序|公众账号|论坛|博客|微博客|直播)',title[:110]))
        # Do not guess when source omitted a category header.
        kind='website' if website and not excluded else ('other' if excluded else 'unknown')
        rows=table.find_all('tr');count=0
        if kind=='website':
            for i,tr in enumerate(rows):
                cells=[' '.join(c.stripped_strings).strip() for c in tr.find_all(['th','td'],recursive=False)]
                if len(cells)<3:continue
                text=' '.join(cells)
                ids=re.findall(r'(?<!\d)\d{11}(?!\d)',text)
                domains=re.findall(r'(?<![\w.-])(?:https?://)?(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/[^\s；，,]*)?',text,re.I)
                if ids and domains:
                    candidates.append({'table_index':k,'row_index':i,'raw_cells':cells,'license_candidates':ids,'domain_candidates':domains,'service_type':'website','verified':False});count+=1
        table_report.append({'table_index':k,'service_type':kind,'title_excerpt':title[:110],'rows':len(rows),'website_candidates':count})
    attachments=[]
    for a in soup.find_all('a',href=True):
        href=a['href'].strip();label=a.get_text(' ',strip=True)
        if re.search(r'\.(docx?|xlsx?|pdf|csv)(?:[?#]|$)',href,re.I):
            attachments.append({'title':label,'href':href,'status':'discovered_only_not_downloaded'})
    return len(tables),candidates,table_report,attachments

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--online',action='store_true',help='Explicitly access official sites; defaults to no network')
    p.add_argument('--limit',type=int,default=8,help='Number of source entries per batch, max 32')
    p.add_argument('--offset',type=int,default=0,help='Zero-based start entry in the 32-source list')
    p.add_argument('--from-file',help='Parse an existing local HTML file (fixture or user-provided snapshot)')
    p.add_argument('--regions',default='',help='Comma-separated regions; only test these official sources')
    a=p.parse_args()
    selected = list(read_sources())
    if a.regions.strip():
        wanted=[v.strip() for v in a.regions.split(',') if v.strip()]
        unknown=[r for r in wanted if r not in {n for n,_ in selected}]
        if unknown: p.error('Unknown region(s): '+','.join(unknown))
        selected=[(n,u) for n,u in selected if n in wanted]
    if not 0 <= a.offset < 32: p.error('--offset must be in 0..31')
    if not 1 <= a.limit <= 32: p.error('--limit must be in 1..32')
    selected=selected[a.offset:a.offset+a.limit]
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=ROOT/'runs'/stamp
    out.mkdir(parents=True,exist_ok=True)
    manifest=[]; candidates=[]; inspections=[]; discovered_attachments=[]
    if a.from_file:
        file=Path(a.from_file)
        content=file.read_bytes()
        n,rows,table_info,attachments=inspect_html(content)
        manifest.append({'region':'LOCAL_TEST','url':'file://'+str(file),'http_status':'local','downloaded':True,'sha256':hashlib.sha256(content).hexdigest(),'bytes':len(content),'tables':n,'candidate_rows':len(rows),'warning':'Local parsing validation only, not official-source acquisition','snapshot_path':str(file)})
        candidates=[dict(r,region='LOCAL_TEST',verified=False) for r in rows];inspections.extend(dict(x,region='LOCAL_TEST') for x in table_info);discovered_attachments.extend(dict(x,region='LOCAL_TEST') for x in attachments)
    elif a.online:
        for region,url in selected:
            row=dict(region=region,url=url,http_status='',downloaded=False,sha256='',bytes=0,tables=0,candidate_rows=0,warning='',snapshot_path='')
            if not url:
                row['warning']='MISSING_OFFICIAL_SOURCE_URL: manual source discovery required'
                manifest.append(row)
                continue
            if urlparse(url).scheme != 'https':
                row['warning']='INVALID_SOURCE_URL: https required'
                manifest.append(row)
                continue
            try:
                req=Request(url,headers={'User-Agent':'ChinaMediaRegistryResearch/0.2 (low-frequency source monitor)'})
                # One retry only for transient timeouts; no bypass of access controls.
                try:
                    response=urlopen(req,timeout=18)
                except (TimeoutError, OSError) as first_error:
                    time.sleep(2)
                    response=urlopen(req,timeout=22)
                with response:
                    final_url=response.geturl()
                    raw=response.read(5_000_001)
                    row['http_status']=response.status
                    ct=response.headers.get('Content-Type','')
                if urlparse(final_url).scheme != 'https':raise ValueError('Non-HTTPS redirect; manual review')
                if len(raw)>5_000_000:raise ValueError('Over 5MB; needs manual fetch')
                if 'text/html' not in ct and not raw.lstrip().startswith((b'<!DOCTYPE',b'<html')):raise ValueError('Not HTML; requires adapter: '+ct)
                snap=out/(hashlib.sha256(url.encode()).hexdigest()[:12]+'.html')
                snap.write_bytes(raw)
                row.update(downloaded=True,sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),snapshot_path=str(snap.relative_to(ROOT)))
                n,rows,table_info,attachments=inspect_html(raw)
                row.update(tables=n,candidate_rows=len(rows))
                if not rows:row['warning']='No strict candidates; check images, PDFs, iframe, or table format'
                candidates.extend(dict(r,region=region,verified=False) for r in rows)
                inspections.extend(dict(x,region=region) for x in table_info)
                discovered_attachments.extend(dict(x,region=region) for x in attachments)
            except Exception as ex:
                row['warning']=type(ex).__name__+': '+str(ex)[:150]
            manifest.append(row)
            time.sleep(1.0)
    else:
        for region,url in selected:
            manifest.append(dict(region=region,url=url,http_status='',downloaded=False,sha256='',bytes=0,tables=0,candidate_rows=0,warning='Offline mode: no network attempted',snapshot_path=''))
    with (out/'source_run.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=HEADERS);w.writeheader();w.writerows(manifest)
    (out/'table_types.json').write_text(json.dumps(inspections,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'attachments_discovered.json').write_text(json.dumps(discovered_attachments,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'candidate_rows.json').write_text(json.dumps(candidates,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'SUMMARY.json').write_text(json.dumps({'run':stamp,'sources':len(manifest),'downloaded':sum(bool(x['downloaded']) for x in manifest),'candidate_rows':len(candidates),'attachments_found':len(discovered_attachments),'missing_urls':sum(not x['url'] for x in manifest),'failed_access':sum(bool(x['url']) and not x['downloaded'] for x in manifest),'successful_html_without_candidates':sum(bool(x['downloaded']) and x['candidate_rows']==0 for x in manifest),'all_unverified':True,'publish_allowed':False},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'run':str(out),'sources':len(manifest),'downloaded':sum(bool(x['downloaded']) for x in manifest),'missing_urls':sum(not x['url'] for x in manifest),'candidate_rows':len(candidates),'publish_allowed':False},ensure_ascii=False))
if __name__=='__main__':main()
