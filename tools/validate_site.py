"""Validate the generated public site, internal links and record scope."""
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlsplit, unquote
import json, re, xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]; DOCS=ROOT/'docs'
class Page(HTMLParser):
 def __init__(self):super().__init__();self.links=[];self.h1=0;self.title=[];self.in_title=False;self.canonical='';self.description='';self.ld=[];self.in_ld=False;self.cur=[]
 def handle_starttag(self,t,a):
  d=dict(a)
  if t=='h1':self.h1+=1
  if t=='title':self.in_title=True
  if t in ('a','link','script'):
   u=d.get('href') or d.get('src')
   if u:self.links.append(u)
  if t=='link' and d.get('rel')=='canonical':self.canonical=d.get('href','')
  if t=='meta' and d.get('name')=='description':self.description=d.get('content','')
  if t=='script' and d.get('type')=='application/ld+json':self.in_ld=True;self.cur=[]
 def handle_data(self,d):
  if self.in_title:self.title.append(d)
  if self.in_ld:self.cur.append(d)
 def handle_endtag(self,t):
  if t=='title':self.in_title=False
  if t=='script' and self.in_ld:self.ld.append(json.loads(''.join(self.cur)));self.in_ld=False

records=json.loads((DOCS/'data/records.json').read_text())['records']
assert records and len({x['record_id'] for x in records})==len(records),'记录编号重复'
assert all(x['review_status']=='verified_dated_official_record' and x['current_license_validity']=='not_independently_confirmed' for x in records)
paths=list(DOCS.rglob('*.html'));titles=set();link_count=0;broken=[]
for f in paths:
 p=Page();p.feed(f.read_text());assert p.h1==1,(f,'h1 count',p.h1)
 title=''.join(p.title);assert title and title not in titles,(f,'duplicate title');titles.add(title)
 assert p.description and p.canonical.startswith('https://meitidangan.com/')
 for u in p.links:
  q=urlsplit(u)
  if q.scheme or q.netloc or not q.path:continue
  candidate=(f.parent/unquote(q.path)).resolve()
  assert candidate.is_relative_to(DOCS.resolve()),(f,u,'path escapes docs')
  if candidate.is_dir():candidate=candidate/'index.html'
  if not candidate.exists():broken.append([str(f.relative_to(DOCS)),u])
  link_count+=1
 for ld in p.ld:assert ld.get('@context')=='https://schema.org'
assert not broken,broken[:20]
record_pages=list((DOCS/'media').glob('*/index.html'))+list((DOCS/'units').glob('*/index.html'))
assert len(record_pages)==len(records),(len(record_pages),len(records))
for x in records:
 sub='units' if x.get('record_kind')=='entity' else 'media'
 f=DOCS/sub/x['record_id'].lower()/'index.html';s=f.read_text()
 assert x['license_number'] in s and x['list_as_of'] in s and x['evidence_sha256'] in s
 assert '当前许可' in s
 if x.get('record_kind')=='entity':
  assert x['name'] in s and not x['registered_domains']
sitemap=ET.parse(DOCS/'sitemap.xml');urls=[x.text for x in sitemap.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}loc')]
assert len(urls)==len(paths)-1 and len(set(urls))==len(urls)
assert '404.html' not in '\n'.join(urls)
coverage=json.loads((DOCS/'data/coverage.json').read_text());assert len(coverage)>=31
report={'html_pages_checked':len(paths),'public_record_pages':len(record_pages),'internal_links_checked':link_count,'broken_internal_links':0,'unique_titles':len(titles),'sitemap_urls':len(urls),'regions':len(coverage),'public_records':len(records),'held_records_in_public_data':0,'site_records':len([x for x in records if x.get('record_kind')!='entity']),'entity_records':len([x for x in records if x.get('record_kind')=='entity'])}
(ROOT/'VALIDATION.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False))
