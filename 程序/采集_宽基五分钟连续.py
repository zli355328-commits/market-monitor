# -*- coding: utf-8 -*-
"""宽基 ETF 连续五分钟线（腾讯 ifzq mkline，同一来源，2026-05-06 ~ 当日）。

标的：510300 沪深300ETF(华泰柏瑞)、588000 科创50ETF(华夏)、159915 创业板ETF(易方达)、510050 上证50ETF(华夏)
- 单页 320 根，按结束时间向前翻页至早于 2026-05-06 09:35
- 字段 [时间,开,收,高,低,量]，量=手；第8字段非成交额（已逐根证伪），不采用
- 时间戳=区间结束时刻；不复权
输出：专题_宽基五分钟线/
"""
import csv, json, os, subprocess, time
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "专题_宽基五分钟线")
RAW = os.path.join(OUT, "_raw")
os.makedirs(RAW, exist_ok=True)

SYMS = {
    "510300": ("sh510300", "沪深300ETF华泰柏瑞"),
    "588000": ("sh588000", "科创50ETF华夏"),
    "159915": ("sz159915", "创业板ETF易方达"),
    "510050": ("sh510050", "上证50ETF华夏"),
}
FIRST = "202605060935"


def curl(url, timeout=25):
    r = subprocess.run(["curl", "-s", "--max-time", str(timeout), "-H", "User-Agent: Mozilla/5.0", url],
                       capture_output=True, text=True, encoding="utf-8", errors="ignore")
    return r.stdout


def fetch_all(sym):
    bars, end, pages = [], "202611052000", 0
    while pages < 45:
        t = curl("https://ifzq.gtimg.cn/appstock/app/kline/mkline?param=%s,m5,%s,320" % (sym, end))
        try:
            data = json.loads(t)["data"][sym]["m5"]
        except Exception as e:
            print("  FAIL", sym, end, repr(e)[:60], flush=True)
            time.sleep(1.5); pages += 1; continue
        if not data:
            break
        bars = data + bars
        pages += 1
        if data[0][0] <= FIRST:
            break
        end = data[0][0]
        time.sleep(0.2)
    seen, uniq = set(), []
    for b in bars:
        if b[0] not in seen:
            seen.add(b[0]); uniq.append(b)
    uniq.sort(key=lambda x: x[0])
    if uniq:
        print("  %s pages=%d bars=%d %s..%s" % (sym, pages, len(uniq), uniq[0][0], uniq[-1][0]), flush=True)
    return uniq


ALL = []
for code, (sym, name) in SYMS.items():
    print("fetch", code, name, flush=True)
    bars = fetch_all(sym)
    json.dump(bars, open(os.path.join(RAW, "tx_m5_%s.json" % code), "w", encoding="utf-8"))
    for b in bars:
        if b[0] < FIRST:
            continue
        ALL.append([code, name, b[0][:8], b[0][8:], b[1], b[3], b[4], b[2], b[5],
                    "手", "未取得", "未取得", "腾讯 ifzq.mkline", "区间结束时刻", "不复权"])

HDR = ["代码", "名称", "日期", "时间HHMM", "开盘", "最高", "最低", "收盘",
       "成交量", "成交量单位", "成交额", "成交额单位", "来源", "K线时间含义", "复权方式"]
p = os.path.join(OUT, "宽基五分钟线_连续_2026-05-06至今.csv")
with open(p, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f); w.writerow(HDR); w.writerows(ALL)
print("WROTE", os.path.basename(p), len(ALL))

# 完整性
cnt = defaultdict(lambda: defaultdict(int))
for r in ALL:
    cnt[r[0]][r[2]] += 1
cal = sorted(cnt["510300"])
print("\n交易日 %d：%s .. %s" % (len(cal), cal[0], cal[-1]))
for code in SYMS:
    bad = {d: n for d, n in cnt[code].items() if n != 48}
    miss = [d for d in cal if d not in cnt[code]]
    print("%s 有数据 %d 日；非48根 %s；缺日 %s" % (code, len(cnt[code]), bad or "无", miss or "无"))

# 日聚合，供校验与摘要
agg = {}
for r in ALL:
    k = (r[0], r[2])
    a = agg.setdefault(k, [0, None, None, None, None])
    a[0] += int(float(r[8]))
    o, h, l, c = float(r[4]), float(r[5]), float(r[6]), float(r[7])
    a[1] = o if a[1] is None else a[1]
    a[2] = h if a[2] is None else max(a[2], h)
    a[3] = l if a[3] is None else min(a[3], l)
    a[4] = c
json.dump({"%s|%s" % k: v for k, v in agg.items()},
          open(os.path.join(OUT, "_raw", "daily_agg.json"), "w"), ensure_ascii=False)

print("\n=== 日聚合抽样（最近5日）===")
for code in SYMS:
    ds = sorted(d for (c, d) in agg if c == code)[-5:]
    for d in ds:
        a = agg[(code, d)]
        print(code, d, "O%.3f H%.3f L%.3f C%.3f 量%d手" % (a[1], a[2], a[3], a[4], a[0]))
    print("-")
