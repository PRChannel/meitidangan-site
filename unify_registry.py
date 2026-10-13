#!/usr/bin/env python3
"""Merge audited baselines with source-derived candidates. Never silently publish candidates."""
import argparse, csv, json, re
from pathlib import Path
from collections import Counter, defaultdict

ROOT=Path(__file__).resolve().parent

def read(path):
    with open(path, newline='', encoding='utf-8-sig') as f:return list(csv.DictReader(f))

def write(path,rows,cols):
    with open(path,'w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=cols,extrasaction='ignore');w.writeheader();w.writerows(rows)

def region(s):
    return str(s or '').replace('西藏自治区','西藏').replace('河北省','河北').replace('重庆市','重庆').replace('江苏省','江苏').strip()

def domains(s):
    return set(x.lower().removeprefix('www.') for x in re.split(r'[;,；，\s]+',str(s or '')) if x.strip())

def key(r,area,lic,name):return (region(r.get(area)),r.get(lic,'').strip(),r.get(name,'').strip())

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--baseline',default=str(ROOT/'data/baseline_400.csv'));ap.add_argument('--candidates',default=str(ROOT/'data/latest_candidates_179.csv'));ap.add_argument('--status',default=str(ROOT/'data/source_status_32.csv'));ap.add_argument('--out',default=str(ROOT/'out'));a=ap.parse_args()
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    base=read(a.baseline);cand=read(a.candidates);status=read(a.status)
    idx=defaultdict(list)
    for b in base: idx[key(b,'source_region','license_number','service_name')].append(b)
    compare=[]; additions=[]; conflicts=[]; matched_ids=set()
    for c in cand:
        k=key(c,'region','license_number','service_name');matches=idx.get(k,[])
        row={'region':region(c['region']),'service_name':c['service_name'],'license_number':c['license_number'],'candidate_domains':c.get('domains',''),'evidence_file':c.get('evidence_file',''),'source_type':c.get('source_type',''),'baseline_ids':'','baseline_domains':'','finding':'','review_required':'是'}
        if len(matches)==1:
            b=matches[0];matched_ids.add(b['record_id']);row['baseline_ids']=b['record_id'];row['baseline_domains']=b.get('domains_raw','')
            bd=domains(b.get('domains_raw',''));cd=domains(c.get('domains',''))
            # Both missing = match on available fields; only one missing = unknown, not a difference.
            if bd and cd and bd!=cd:row['finding']='域名字段冲突';conflicts.append(dict(row))
            elif not bd or not cd:row['finding']='名称证号匹配_域名无法比较'
            else:row['finding']='名称证号域名一致'
        elif len(matches)>1:
            row['finding']='基线存在同名同证多条';row['baseline_ids']=';'.join(x['record_id'] for x in matches);conflicts.append(dict(row))
        else:
            potential=[b for b in base if region(b['source_region'])==region(c['region']) and b.get('license_number')==c['license_number']]
            if potential:
                row['finding']='证号相同但名称不同_人工判断';row['baseline_ids']=';'.join(x['record_id'] for x in potential);conflicts.append(dict(row))
            else:
                row['finding']='基线未匹配_待审核新增';additions.append(dict(row))
        compare.append(row)
    cols=list(compare[0]) if compare else ['region','service_name','license_number','finding']
    write(out/'候选比对明细.csv',compare,cols)
    write(out/'待审新增.csv',additions,cols)
    write(out/'冲突复核.csv',conflicts,cols)
    write(out/'全国基线400条.csv',base,list(base[0]))
    write(out/'来源覆盖状态.csv',status,list(status[0]))
    stats=Counter(x['finding'] for x in compare)
    summary={'baseline_records':len(base),'candidate_rows':len(cand),'source_index_entries':len(status),'match_status':dict(stats),'pending_additions':len(additions),'conflicts':len(conflicts),'records_added_to_public_site':0,'notes':['这是候选与现有基线的字段对比，不是独立人工核验','基线来源版本不同，不能据此推断许可当前有效','任何新增或变更都必须经人工确认后才可发布']}
    (out/'SUMMARY.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
