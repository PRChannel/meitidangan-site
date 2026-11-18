#!/usr/bin/env python3
"""行业媒体质量分级：给 industry-media.csv 写入 quality 列（core/platform/watch）。

判据（2026-11-18 实测爱站数据）：
  - core     行业垂直重点媒体：百度预估日均 IP ≥ 300，或属公认行业品牌（白名单人工核）
  - platform 平台型社区：UGC/开发者/资料社区，有流量但非编辑型行业媒体，单列不混入
  - watch    待核：无实测流量且非公认品牌，移出对外索引（保留在 CSV 供复核）
L1（中国行业报协会 115 家）全部 core——名单口径即权威，不受流量影响。
"""
import csv
import json
import re
import sys

CSV = '/Users/yangqie/Documents/GitHub/meitidangan-site/data/industry-media.csv'
MET = '/tmp/az_metrics.json'
BR_MIN = 300

# 平台型社区：UGC/开发者/工具资料站，有认知但不是编辑型行业媒体
PLATFORM = {
    'IM-L2-002',  # CSDN
    'IM-L2-006',  # 虎扑
    'IM-L2-077',  # 雪球
    'IM-L2-219',  # 懂球帝
    'IM-L2-232',  # 17173
    'IM-L2-233',  # 游民星空
    'IM-L2-234',  # 3DM游戏网
    'IM-L2-152',  # 掘金
    'IM-L2-154',  # 博客园
    'IM-L2-153',  # SegmentFault
    'IM-L2-004',  # 开源中国
    'IM-L2-055',  # 站长之家
    'IM-L2-259',  # ABBS 建筑论坛
    'IM-L2-258',  # 土木在线
    'IM-L2-132',  # 通信人家园
    'IM-L2-156',  # 极术社区
    'IM-L2-140',  # 崔牛会
    'IM-L2-127',  # 集智俱乐部
    'IM-L2-264',  # 无讼阅读
    'IM-L2-230',  # GameRes 游资网
    'IM-L2-155',  # 图灵社区
}

# 行业品牌白名单：实测搜索流量低/无数据，但业内公认、发稿有采购价值
BRAND = {
    'IM-L2-005',  # 懒熊体育
    'IM-L2-007',  # 农博网
    'IM-L2-011',  # 动脉网
    'IM-L2-023',  # 多知网
    'IM-L2-025',  # 品橙旅游
    'IM-L2-026',  # 新旅界
    'IM-L2-027',  # 环球旅讯
    'IM-L2-040',  # 游戏葡萄
    'IM-L2-052',  # 机器之心
    'IM-L2-057',  # 量子位
    'IM-L2-064',  # FT中文网
    'IM-L2-070',  # 环球老虎财经
    'IM-L2-072',  # 蓝鲸财经
    'IM-L2-079',  # 零壹财经
    'IM-L2-087',  # C2CC传媒
    'IM-L2-089',  # 聚美丽
    'IM-L2-090',  # 青眼
    'IM-L2-091',  # 化妆品报
    'IM-L2-095',  # 华丽志
    'IM-L2-097',  # WWD CHINA
    'IM-L2-098',  # FashionNetwork 中国
    'IM-L2-100',  # 母婴行业观察
    'IM-L2-101',  # 中童传媒
    'IM-L2-104',  # 宠业家
    'IM-L2-109',  # 现代家电网（《现代家电》杂志社）
    'IM-L2-116',  # 餐饮老板内参
    'IM-L2-121',  # 国际电子商情
    'IM-L2-123',  # 芯智讯
    'IM-L2-124',  # 芯东西
    'IM-L2-126',  # 数据猿
    'IM-L2-133',  # 安全牛
    'IM-L2-135',  # 嘶吼
    'IM-L2-136',  # 安全内参
    'IM-L2-138',  # 安全客
    'IM-L2-139',  # 牛透社
    'IM-L2-141',  # 中国软件网
    'IM-L2-144',  # CIO时代
    'IM-L2-169',  # 中国企业家
    'IM-L2-170',  # 商界
    'IM-L2-171',  # 销售与市场
    'IM-L2-172',  # 证券市场周刊
    'IM-L2-173',  # 新财富
    'IM-L2-174',  # 哈佛商业评论
    'IM-L2-175',  # 第一财经YiMagazine
    'IM-L2-181',  # 清科
    'IM-L2-184',  # 猎云网
    'IM-L2-186',  # 甲子光年
    'IM-L2-187',  # IT桔子
    'IM-L2-188',  # 市值风云
    'IM-L2-189',  # 面包财经
    'IM-L2-193',  # 南风窗
    'IM-L2-194',  # 南方人物周刊
    'IM-L2-195',  # 瞭望
    'IM-L2-197',  # 医药魔方
    'IM-L2-198',  # 米内网
    'IM-L2-199',  # 药渡
    'IM-L2-200',  # 看医界
    'IM-L2-202',  # E药经理人
    'IM-L2-203',  # 赛柏蓝
    'IM-L2-204',  # 鲸媒体
    'IM-L2-205',  # 顶思
    'IM-L2-207',  # 蓝鲸教育
    'IM-L2-209',  # 新学说
    'IM-L2-210',  # 执惠
    'IM-L2-211',  # 劲旅网
    'IM-L2-215',  # 禹唐体育
    'IM-L2-216',  # ECO氪体
    'IM-L2-218',  # 新体育网（中国体育报业总社）
    'IM-L2-220',  # 娱乐资本论
    'IM-L2-221',  # 骨朵传媒
    'IM-L2-222',  # 艺恩
    'IM-L2-225',  # Vlinkage
    'IM-L2-226',  # 中国文化传媒网
    'IM-L2-229',  # 竞核
    'IM-L2-237',  # 隆众资讯
    'IM-L2-239',  # 中国煤炭网
    'IM-L2-243',  # 新材料在线
    'IM-L2-248',  # 35斗
    'IM-L2-253',  # 物流指闻
    'IM-L2-254',  # 罗戈网
    'IM-L2-255',  # 万联网
    'IM-L2-260',  # ArchDaily 中文版
    'IM-L2-262',  # 智合
    'IM-L2-263',  # 律新社
}


def br_ip(v):
    if not v or v == '-':
        return 0
    nums = [int(x.replace(',', '')) for x in re.findall(r'[\d,]+', v) if x.replace(',', '').isdigit()]
    return max(nums) // 2 if nums else 0


def main():
    met = json.load(open(MET))
    rows = list(csv.DictReader(open(CSV, encoding='utf-8-sig')))
    for r in rows:
        if r['tier'] == 'L1':
            r['quality'] = 'core'
            continue
        ip = br_ip(met.get(r['domain'], {}).get('br_ip'))
        r['_ip'] = ip
        if r['id'] in PLATFORM:
            r['quality'] = 'platform'
        elif ip >= BR_MIN or r['id'] in BRAND:
            r['quality'] = 'core'
        else:
            r['quality'] = 'watch'

    import collections
    c = collections.Counter((r['tier'], r['quality']) for r in rows)
    for k in sorted(c):
        print(k, c[k])
    watch = [r for r in rows if r['quality'] == 'watch']
    print(f'\n=== watch 待核 {len(watch)} 家（移出对外索引）===')
    for r in sorted(watch, key=lambda x: x['_ip']):
        print(f"{r['id']:10} ip={r['_ip']:>4} {r['name'][:22]:24} {r['domain']:24} {r['sector']}")

    with open(CSV, 'w', encoding='utf-8-sig', newline='') as f:
        fields = ['id', 'tier', 'name', 'sector', 'industry', 'domain',
                  'http_status', 'licensed', 'quality', 'note', 'source']
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)
    print('\n已写回', CSV)


if __name__ == '__main__':
    main()
