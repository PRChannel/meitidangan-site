#!/usr/bin/env python3
"""Offline-first, read-only CMR attachment preflight. Standard library only.
DO NOT merge output into any public registry without source and row review.
"""
import argparse,csv,hashlib,io,json,re,zipfile,xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urljoin,urlparse
from urllib.request import Request,urlopen
from datetime import datetime,timezone

MAX_BYTES=8_000_000
APPROVED_HOSTS={'jcdn.xhby.net','www.gscn.com.cn'}
XMLNS={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
LICENSE_RE=re.compile(r'(?<!\d)\d{11}(?!\d)')
DOMAIN_RE=re.compile(r'(?<![\w.-])(?:[a-z0-9-]+\.)+[a-z]{2,}(?![\w.-])',re.I)
ATTACHMENTS=[
 {'region':'江苏','kind':'website_source_attachment','title':'江苏许可情况统计表（待识别服务类型）','url':'https://jcdn.xhby.net/dams-res/editing/file/202607/02/6a461cfae4b084d2d0a56554.docx','source_page':'https://jsnews.jschina.com.cn/jsyw/202607/t20260702_s6a45c01fe4b0b98c2df2bfb1.shtml','file':'jiangsu.docx'},
 {'region':'甘肃','kind':'website_source_attachment','title':'获得互联网新闻信息服务许可的互联网站名单（页面标注共34个）','url':'https://www.gscn.com.cn/doc/003/021/728/00302172896_46731fee.xlsx','source_page':'https://gansu.gscn.com.cn/system/2026/04/13/013484231.shtml','file':'gansu-websites.xlsx'}]

def word_rows(file):
 with zipfile.ZipFile(file) as z:
  root=ET.fromstring(z.read('word/document.xml'))
  tbls=[]
  for tbl in root.findall('.//w:tbl',XMLNS):
   data=[]
   for tr in tbl.findall('./w:tr',XMLNS):
    cells=[]
    for tc in tr.findall('./w:tc',XMLNS):
     cells.append(' '.join(''.join((t.text or '') for t in p.findall('.//w:t',XMLNS)).strip() for p in tc.findall('.//w:p',XMLNS)).strip())
    data.append(cells)
   tbls.append(data)
  return tbls

def xlsx_rows(file):
 with zipfile.ZipFile(file) as z:
  shared=[]
  if 'xl/sharedStrings.xml' in z.namelist():
   ss=ET.fromstring(z.read('xl/sharedStrings.xml'))
   shared=[''.join(t.text or '' for t in si.findall('.//s:t',XMLNS)) for si in ss.findall('s:si',XMLNS)]
  names=sorted(n for n in z.namelist() if re.fullmatch(r'xl/worksheets/sheet\d+\.xml',n))
  sheets=[]
  for name in names:
   root=ET.fromstring(z.read(name)); rows=[]
   for r in root.findall('.//s:sheetData/s:row',XMLNS):
    cellmap={}; maxidx=0
    for c in r.findall('s:c',XMLNS):
     ref=c.attrib.get('r','A1'); col=re.match(r'[A-Z]+',ref)
     if not col:continue
     idx=0
     for ch in col.group():idx=idx*26+(ord(ch)-64)
     maxidx=max(maxidx,idx)
     v=c.find('s:v',XMLNS); inline=c.find('s:is',XMLNS)
     raw=v.text if v is not None and v.text else ''
     if c.get('t')=='s' and raw.isdigit(): raw=shared[int(raw)] if int(raw)<len(shared) else ''
     elif c.get('t')=='inlineStr' and inline is not None:raw=''.join(t.text or '' for t in inline.findall('.//s:t',XMLNS))
     cellmap[idx]=raw
    rows.append([cellmap.get(i,'') for i in range(1,min(maxidx,80)+1)])
   sheets.append({'sheet_path':name,'rows':rows})
  return sheets

def parse_attachment(path,meta):
 content=path.read_bytes()
 if len(content)>MAX_BYTES:raise ValueError('File exceeds size limit')
 if not zipfile.is_zipfile(io.BytesIO(content)):raise ValueError('Not a valid DOCX/XLSX ZIP container')
 tabs=[{'section':f'docx_table_{i+1}','rows':r} for i,r in enumerate(word_rows(path))] if path.suffix=='.docx' else [{'section':x['sheet_path'],'rows':x['rows']} for x in xlsx_rows(path)]
 out=[]; sections=[]
 for t in tabs:
  sections.append({'section':t['section'],'rows_total':len(t['rows'])})
  for i,cells in enumerate(t['rows'],start=1):
   joined=' '.join(cells)
   if not joined.strip():continue
   # No silent interpretation of column positions. Candidate only if license-like ID is present.
   licenses=LICENSE_RE.findall(joined)
   out.append({'region':meta['region'],'attachment':meta['file'],'section':t['section'],'row_index':i,'raw_cells':json.dumps(cells,ensure_ascii=False),'license_candidates':';'.join(licenses),'domain_candidates':';'.join(dict.fromkeys(DOMAIN_RE.findall(joined))),'has_license':bool(licenses),'review_status':'needs_review','publish_allowed':'false','source_page':meta['source_page'],'source_attachment':meta['url'],'attachment_sha256':hashlib.sha256(content).hexdigest()})
 return sections,out

def download_exact(meta,destination):
 uri=meta['url'];p=urlparse(uri)
 if p.scheme!='https' or p.hostname not in APPROVED_HOSTS:raise ValueError('Unapproved source host')
 req=Request(uri,headers={'User-Agent':'ChinaMediaRegistryResearch/0.3 (low-frequency public attachment audit)'})
 with urlopen(req,timeout=25) as resp:
  end=urlparse(resp.geturl()); ct=resp.headers.get('Content-Type','')
  if end.scheme!='https' or end.hostname not in APPROVED_HOSTS:raise ValueError('Unexpected redirect host')
  raw=resp.read(MAX_BYTES+1)
 if len(raw)>MAX_BYTES:raise ValueError('Attachment exceeds 8MB')
 if not zipfile.is_zipfile(io.BytesIO(raw)):raise ValueError('Received HTML/error page instead of DOCX/XLSX; content-type '+ct)
 destination.write_bytes(raw)

def main():
 p=argparse.ArgumentParser(description='Offline-first DOCX/XLSX website attachment audit; never publishes records')
 p.add_argument('--download',action='store_true',help='Explicitly download two selected official-page attachments (no other URLs)')
 p.add_argument('--input',default='attachments',help='Directory for locally obtained attachments')
 p.add_argument('--output',default='review_report')
 a=p.parse_args(); base=Path(a.input);base.mkdir(parents=True,exist_ok=True)
 dest=Path(a.output);dest.mkdir(parents=True,exist_ok=True)
 reviews=[]; status=[]; all_rows=[]
 for m in ATTACHMENTS:
  path=base/m['file']; row={**m,'download_status':'not_requested','parsed':False,'sections':0,'candidate_rows_with_license':0,'error':''}
  try:
   if not path.exists() and a.download:
    download_exact(m,path);row['download_status']='downloaded'
   if path.exists():
    row['download_status']='local_file_present' if row['download_status']!='downloaded' else 'downloaded'
    sections,rows=parse_attachment(path,m)
    row.update(parsed=True,sections=len(sections),candidate_rows_with_license=sum(x['has_license'] for x in rows),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    all_rows.extend(rows);reviews.extend([{'region':m['region'],**s} for s in sections])
   else:row['error']='附件尚未下载，不能确认其中数据量'
  except Exception as e:row['error']=type(e).__name__+': '+str(e)[:250]
  status.append(row)
 fields=['region','attachment','section','row_index','raw_cells','license_candidates','domain_candidates','has_license','review_status','publish_allowed','source_page','source_attachment','attachment_sha256']
 with (dest/'attachment_candidate_rows.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(all_rows)
 (dest/'attachment_status.json').write_text(json.dumps({'generated_at':datetime.now(timezone.utc).isoformat(),'records':status,'sections':reviews,'total_candidate_rows_with_license':sum(r['has_license'] for r in all_rows),'publish_allowed':False},ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'status':[{'region':x['region'],'parsed':x['parsed'],'candidate_rows_with_license':x['candidate_rows_with_license'],'error':x['error']} for x in status],'publish_allowed':False},ensure_ascii=False))
if __name__=='__main__':main()
