# -*- coding: utf-8 -*-
"""专题五分钟线：生成最终 CSV + 校验。

窗口A 2026-07-20~07-24：腾讯 ifzq mkline（唯一可回溯源）。字段 [时间,开,收,高,低,量(手),{},?]
  - 第8字段经与新浪逐根比对：与成交量成严格比例、与成交额不成固定比例 → 判为非成交额，不采用。
窗口B 2026-10-26~11-05：东财 push2his（量手/额元，与日线口径一致）为主，新浪（量份/额元）交叉。
所有源 K 线时间戳 = 区间结束时刻（首根 09:35=09:30-09:35，末根 15:00=14:55-15:00 含收盘集合竞价）。
均不复权。588170 于 2026-07-06 1拆3，早于两窗口，窗口内价格无分拆失真。
"""
import csv, json, os, subprocess
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "专题_五分钟线")
RAW = os.path.join(OUT, "_raw")


def curl(url, timeout=25):
    r = subprocess.run(["curl", "-s", "--max-time", str(timeout), "-H", "User-Agent: Mozilla/5.0", url],
                       capture_output=True, text=True, encoding="utf-8", errors="ignore")
    return r.stdout


def em_daily(code, beg, end):
    t = curl("https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=1.%s&fields1=f1,f2,f3"
             "&fields2=f51,f52,f53,f54,f55,f56,f57&klt=101&fqt=0&beg=%s&end=%s" % (code, beg, end))
    return {x.split(",")[0]: x.split(",") for x in json.loads(t)["data"]["klines"]}


NAMES = {"588170": "科创半导体ETF", "000688": "科创50指数", "000001": "上证指数"}

# ---------- 窗口A：腾讯 ----------
rows_a = []
for code in ["588170", "000688", "000001"]:
    bars = json.load(open(os.path.join(RAW, "tx_%s_m5_0720-0724.json" % code), encoding="utf-8"))
    for b in bars:
        d, hm = b[0][:8], b[0][8:]
        if "20260720" <= d <= "20260724":
            rows_a.append([code, NAMES[code], d, hm, b[1], b[3], b[4], b[2], b[5], "手",
                           "", "未取得", "腾讯ifzq.mkline", "区间结束时刻", "不复权"])

# ---------- 窗口B：东财为主 ----------
rows_b = []
for code in ["588170", "000688", "000001"]:
    k = json.load(open(os.path.join(RAW, "em_%s_full.json" % code), encoding="utf-8"))["data"]["klines"]
    for line in k:
        p = line.split(",")
        d, hm = p[0][:10].replace("-", ""), p[0][11:16].replace(":", "")
        if "20261026" <= d <= "20261105":
            rows_b.append([code, NAMES[code], d, hm, p[1], p[3], p[4], p[2], p[5], "手",
                           p[6], "元", "东财push2his.kline(klt=5)", "区间结束时刻", "不复权"])

HDR = ["代码", "名称", "日期", "时间HHMM", "开盘", "最高", "最低", "收盘",
       "成交量", "成交量单位", "成交额", "成交额单位", "来源", "K线时间含义", "复权方式"]


def wcsv(path, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(HDR)
        w.writerows(rows)
    print("WROTE", os.path.basename(path), len(rows))


wcsv(os.path.join(OUT, "五分钟线_2026-07-20至07-24.csv"), rows_a)
wcsv(os.path.join(OUT, "五分钟线_2026-10-26至11-05.csv"), rows_b)

# ---------- 校验 ----------
daily = defaultdict(dict)
with open(os.path.join(ROOT, "2026-11-04", "日线.csv"), encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        daily[r["代码"]][r["日期"]] = r

em688 = {}
em688.update(em_daily("000688", "20260718", "20260726"))
em688.update(em_daily("000688", "20261024", "20261105"))

print("\n=== 校验A：腾讯分时 vs 日总量/日OHLC（000688用东财日线独立核对）===")
aggA = defaultdict(lambda: [0, None, None, None, None])  # vol, o,h,l,c
for r in rows_a:
    k = (r[0], r[2])
    a = aggA[k]
    a[0] += int(float(r[8]))
    o, h, l, c = float(r[4]), float(r[5]), float(r[6]), float(r[7])
    a[1] = o if a[1] is None else a[1]
    a[2] = h if a[2] is None else max(a[2], h)
    a[3] = l if a[3] is None else min(a[3], l)
    a[4] = c
for (code, d), (v, o, h, l, c) in sorted(aggA.items()):
    dd = "%s-%s-%s" % (d[:4], d[4:6], d[6:8])
    dr = daily.get(code, {}).get(dd)
    if dr:
        dv, da = int(dr["成交量"]), float(dr["成交额"])
        print("A %s %s 量 %d vs 日线 %d (%s) OHLC 分时%s vs 日线 O%s H%s L%s C%s 额 %s vs 日线 %.0f"
              % (code, dd, v, dv, "一致" if v == dv else "不一致", (o, h, l, c),
                 dr["开盘"], dr["最高"], dr["最低"], dr["收盘"], "-", da))
    else:
        e = em688.get(dd)
        if e:
            ev = int(e[5])
            print("A %s %s 量 %d vs 东财日线 %d (%s) OHLC 分时(%.2f,%.2f,%.2f,%.2f) vs 东财(%s,%s,%s,%s)"
                  % (code, dd, v, ev, "一致" if v == ev else "不一致", o, h, l, c, e[1], e[3], e[4], e[2]))

print("\n=== 校验B：东财分时 vs 日总量/日OHLC + 与新浪逐根比对 ===")
aggB = defaultdict(lambda: [0, 0.0, None, None, None, None])
for r in rows_b:
    k = (r[0], r[2])
    a = aggB[k]
    a[0] += int(float(r[8]))
    a[1] += float(r[10])
    o, h, l, c = float(r[4]), float(r[5]), float(r[6]), float(r[7])
    a[2] = o if a[2] is None else a[2]
    a[3] = h if a[3] is None else max(a[3], h)
    a[4] = l if a[4] is None else min(a[4], l)
    a[5] = c
for (code, d), (v, amt, o, h, l, c) in sorted(aggB.items()):
    dd = "%s-%s-%s" % (d[:4], d[4:6], d[6:8])
    dr = daily.get(code, {}).get(dd)
    if dr:
        dv, da = int(dr["成交量"]), float(dr["成交额"])
        print("B %s %s 量 %d vs 日线 %d (%s) 额 %.0f vs %.0f (%.4f%%) OHLC %s vs O%s H%s L%s C%s"
              % (code, dd, v, dv, "一致" if v == dv else "不一致", amt, da,
                 abs(amt - da) / da * 100, (o, h, l, c), dr["开盘"], dr["最高"], dr["最低"], dr["收盘"]))
    else:
        e = em688.get(dd)
        if e:
            print("B %s %s 量 %d vs 东财日线 %d (%s) 额 %.0f vs %s" % (code, dd, v, int(e[5]),
                  "一致" if v == int(e[5]) else "不一致", amt, e[6]))

# 新浪逐根
for code in ["588170", "000688", "000001"]:
    sina = {x["day"]: x for x in json.load(open(os.path.join(RAW, "sina_%s_m5.json" % code), encoding="utf-8"))}
    tot = same_v = same_ohlc = same_amt = 0
    for r in rows_b:
        if r[0] != code:
            continue
        key = "%s-%s-%s %s:%s:00" % (r[2][:4], r[2][4:6], r[2][6:], r[3][:2], r[3][2:])
        s = sina.get(key)
        if not s:
            continue
        tot += 1
        if int(s["volume"]) == int(float(r[8])) * 100:
            same_v += 1
        if (s["open"], s["high"], s["low"], s["close"]) == (r[4], r[5], r[6], r[7]):
            same_ohlc += 1
        if abs(float(s["amount"]) - float(r[10])) < 1:
            same_amt += 1
    print("B %s 东财vs新浪: 共%d根 量严格一致%d OHLC全等%d 额差<1元%d" % (code, tot, same_v, same_ohlc, same_amt))

# ---------- 7/21 盘中路径要点 ----------
print("\n=== 2026-07-21 盘中路径（腾讯5分钟）===")
for code in ["588170", "000688", "000001"]:
    bars = [(r[3], float(r[4]), float(r[5]), float(r[6]), float(r[7]), int(float(r[8])))
            for r in rows_a if r[0] == code and r[2] == "20260721"]
    lo = min(bars, key=lambda x: x[3]); hi = max(bars, key=lambda x: x[2])
    am = sum(b[5] for b in bars if b[0] < "1130"); pm = sum(b[5] for b in bars if b[0] >= "1300")
    biggest = max(bars, key=lambda x: x[5])
    print("%s 低 %s@%s 高 %s@%s 开%s 收%s 上午量%.0f 下午量%.0f(%.0f%%) 量最大根 %s"
          % (code, lo[3], lo[0], hi[2], hi[0], bars[0][1], bars[-1][4], am, pm, pm / (am + pm) * 100, biggest[0]))
