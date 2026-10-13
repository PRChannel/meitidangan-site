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
assert len(records)==898 and len({x['record_id'] for x in records})==898
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
record_pages=list((DOCS/'media').glob('*/index.html'));assert len(record_pages)==898
for x in records:
 f=DOCS/'media'/x['record_id'].lower()/'index.html';s=f.read_text()
 assert x['license_number'] in s and x['list_as_of'] in s and x['evidence_sha256'] in s
 assert '当前许可' in s
sitemap=ET.parse(DOCS/'sitemap.xml');urls=[x.text for x in sitemap.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}loc')]
assert len(urls)==len(paths)-1 and len(set(urls))==len(urls)
assert '404.html' not in '\n'.join(urls)
coverage=json.loads((DOCS/'data/coverage.json').read_text());assert len(coverage)==31
report={'html_pages_checked':len(paths),'public_record_pages':len(record_pages),'internal_links_checked':link_count,'broken_internal_links':0,'unique_titles':len(titles),'sitemap_urls':len(urls),'regions':31,'public_records':898,'held_records_in_public_data':0}
(ROOT/'VALIDATION.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False))
