#!/usr/bin/env python3
"""Discover evidence images/downloads in official source snapshots, no OCR and no auto-approval.
The input must be a previously obtained GitHub Actions artifact ZIP.
"""
import argparse,csv,hashlib,io,json,re,zipfile
from pathlib import Path
from urllib.parse import urljoin,urlsplit
from bs4 import BeautifulSoup

KEY=re.compile('许可|新闻信息|网站名单|互联网|附件|下载|统计表|公示|名录')
FILE=re.compile(r'\.(?:png|jpe?g|gif|webp|pdf|docx?|xlsx?|csv)(?:[?#]|$)',re.I)
SUSPICIOUS=re.compile(r'captcha|verify|验证码|登录|logo|icon|二维码|qrcode|wechat|share|广告|头像',re.I)
FIELDS=['region','status','source_url','kind','asset_url','text','score','snapshot','sha256','review_status']

def writecsv(path,rows,columns):
 with open(path,'w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=columns,extrasaction='ignore');w.writeheader();w.writerows(rows)

def discover(html,url,region,snapshot,sha):
 soup=BeautifulSoup(html,'html.parser');out={}
 for tag in soup.select('a[href],img[src],iframe[src],embed[src],object[data],source[src],source[srcset]'):
  attr='href' if tag.name=='a' else ('data' if tag.name=='object' else 'src')
  value=tag.get(attr) or '';value=value.split(' ')[0].strip()
  if not value or value.startswith(('javascript:','data:','blob:','#')):continue
  absolute=urljoin(url,value)
  if urlsplit(absolute).scheme not in ('http','https'):continue
  label=' '.join((tag.get_text(' ',strip=True),tag.get('alt',''),tag.get('title',''))).strip()[:160]
  isfile=bool(FILE.search(absolute));interesting=bool(KEY.search(label+' '+value))
  if not (isfile or interesting):continue
  if tag.name=='img' and SUSPICIOUS.search(label+' '+value):continue
  if tag.name in ('iframe','embed','object'):kind='embedded'
  elif re.search(r'\.(?:png|jpe?g|gif|webp)(?:[?#]|$)',absolute,re.I):kind='image'
  elif isfile:kind='document'
  else:kind='linked_page'
  score=(3 if interesting else 0)+(2 if kind in ('document','embedded') else 0)+(1 if kind=='image' else 0)
  row=dict(region=region,status='discovered_not_verified',source_url=url,kind=kind,asset_url=absolute,text=label,score=score,snapshot=snapshot,sha256=sha,review_status='pending_manual_review')
  k=(region,absolute)
  if k not in out or score>out[k]['score']:out[k]=row
 return sorted(out.values(),key=lambda x:(-x['score'],x['asset_url']))

def main():
 p=argparse.ArgumentParser();p.add_argument('--artifact',required=True);p.add_argument('--sources',default='data/sources_32.json');p.add_argument('--output',default='deep_source_report');args=p.parse_args()
 sources=json.loads(Path(args.sources).read_text(encoding='utf8'))
 byindex={i+1:rec for i,rec in enumerate(sources)}
 out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
 assets=[];summary=[]
 with zipfile.ZipFile(args.artifact) as z:
  for n in z.namelist():
   m=re.match(r'evidence/(\d\d)_.*\.html$',n)
   if not m:continue
   idx=int(m.group(1));source=byindex.get(idx,{})
   region=source.get('region','');url=source.get('source_url','')
   raw=z.read(n);sha=hashlib.sha256(raw).hexdigest()
   entries=discover(raw,url,region,n,sha)
   assets.extend(entries)
   kinds={k:sum(a['kind']==k for a in entries) for k in ['image','document','embedded','linked_page']}
   summary.append(dict(region=region,snapshot=n,assets=len(entries),**kinds))
 writecsv(out/'页面附件与图片待核验.csv',assets,FIELDS)
 writecsv(out/'页面证据资产统计.csv',summary,['region','snapshot','assets','image','document','embedded','linked_page'])
 (out/'README.txt').write_text('本报告仅从已保存HTML中发现文件和链接，不自动识别图片文字，不证明资产属于许可名单，不自动入库。所有资源需按原始来源和文件内容审核。\n',encoding='utf8')
 print(json.dumps({'snapshots_checked':len(summary),'assets_discovered':len(assets),'image_assets':sum(x['kind']=='image' for x in assets),'document_assets':sum(x['kind']=='document' for x in assets)},ensure_ascii=False))
if __name__=='__main__':main()
