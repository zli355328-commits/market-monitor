# -*- coding: utf-8 -*-
"""补：四只宽基 ETF 逐 5 分钟成交额（东财 push2his klt=5，仅回溯到 2026-09-15）+ 日总量校验。

东财字段顺序：f51时间,f52开,f53收,f54高,f55低,f56量(手),f57额(元)
"""
import csv, json, os, subprocess, time
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "专题_宽基五分钟线")
RAW = os.path.join(OUT, "_raw")

SEC = {"510300": "1.510300", "588000": "1.588000", "510050": "1.510050", "159915": "0.159915"}
NAMES = {"510300": "沪深300ETF华泰柏瑞", "588000": "科创50ETF华夏", "510050": "上证50ETF华夏",
         "159915": "创业板ETF易方达"}


def curl(url, timeout=30):
    return subprocess.run(["curl", "-s", "--max-time", str(timeout), "-H", "User-Agent: Mozilla/5.0", url],
                          capture_output=True, text=True, encoding="utf-8", errors="ignore").stdout


rows = []
for code, secid in SEC.items():
    txt = curl("https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=%s"
               "&fields1=f1,f2,f3&fields2=f51,f52,f53,f54,f55,f56,f57&klt=5&fqt=0&beg=0&end=20500101&lmt=1000000" % secid)
    try:
        k = json.loads(txt)["data"]["klines"]
    except Exception:
        print("FAIL", code, txt[:100]); k = []
    json.dump(k, open(os.path.join(RAW, "em_m5_%s.json" % code), "w", encoding="utf-8"), ensure_ascii=False)
    for line in k:
        p = line.split(",")
        d, hm = p[0][:10], p[0][11:16]
        if d < "2026-09-15":
            continue
        rows.append([code, NAMES[code], d.replace("-", ""), hm.replace(":", ""), p[1], p[3], p[4], p[2],
                     p[5], "手", p[6], "元", "东方财富push2his", "区间结束时刻", "不复权"])
    print("%s bars=%d %s..%s" % (code, len(k), k[0][:16] if k else "-", k[-1][:16] if k else "-"))
    time.sleep(0.4)

p = os.path.join(OUT, "宽基五分钟线_成交额补充_2026-09-15至今.csv")
with open(p, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["代码", "名称", "日期", "时间HHMM", "开盘", "最高", "最低", "收盘",
                "成交量", "成交量单位", "成交额", "成交额单位", "来源", "K线时间含义", "复权方式"])
    w.writerows(rows)
print("WROTE", os.path.basename(p), len(rows))

# ---------- 校验：东财5分钟日聚合 vs 腾讯5分钟日聚合（量、额推算均价）----------
print("\n=== 交叉校验：东财 vs 腾讯（成交量手、OHLC）===")
tx = defaultdict(lambda: [0, None, None, None, None])
for r in csv.DictReader(open(os.path.join(OUT, "宽基五分钟线_连续_2026-05-06至今.csv"), encoding="utf-8-sig")):
    k = (r["代码"], r["日期"])
    a = tx[k]
    a[0] += int(float(r["成交量"]))
    o, h, l, c = float(r["开盘"]), float(r["最高"]), float(r["最低"]), float(r["收盘"])
    a[1] = o if a[1] is None else a[1]
    a[2] = h if a[2] is None else max(a[2], h)
    a[3] = l if a[3] is None else min(a[3], l)
    a[4] = c

em = defaultdict(lambda: [0, None, None, None, None, 0.0])
for r in rows:
    k = (r[0], r[2])
    a = em[k]
    a[0] += int(float(r[8]))
    a[5] += float(r[10])
    o, h, l, c = float(r[4]), float(r[5]), float(r[6]), float(r[7])
    a[1] = o if a[1] is None else a[1]
    a[2] = h if a[2] is None else max(a[2], h)
    a[3] = l if a[3] is None else min(a[3], l)
    a[4] = c

for code in SEC:
    ds = sorted(d for (c, d) in em if c == code)
    bad = 0
    vmax = 0.0
    for d in ds:
        t, e = tx.get((code, d)), em[(code, d)]
        if not t:
            continue
        vdiff = abs(e[0] - t[0]) / max(t[0], 1) * 100
        vmax = max(vmax, vdiff)
        # 东财均价 vs 腾讯收盘区间
        if abs(e[4] - t[4]) > 1e-9:
            bad += 1
    print("%s 日数%d 量差最大%.3f%% 收盘不一致%d天 最后日额%.2f亿(均价%.4f)"
          % (code, len(ds), vmax, bad, em[(code, ds[-1])][5] / 1e8,
             em[(code, ds[-1])][5] / (em[(code, ds[-1])][0] * 100) if em[(code, ds[-1])][0] else 0))
