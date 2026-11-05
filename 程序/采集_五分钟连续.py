# -*- coding: utf-8 -*-
"""连续五分钟线（腾讯 ifzq mkline，同源）：2026-05-06 ~ 2026-11-05。

- 单页 320 根，按结束时间向前翻页直至早于 2026-05-06 09:35。
- 字段 [时间,开,收,高,低,量]；量=手（已与新浪 ×100 及日线总量双向校验）；第8字段非成交额，不采用。
- 时间戳=区间结束时刻；不复权。
- 588170 于 2026-07-06 1拆3 → 不复权序列在该日出现 -66.7% 假跳空，单独标注。
输出：
  专题_五分钟线/五分钟线_连续_2026-05-06至11-05.csv
  专题_五分钟线/五分钟线_2026-07-20至08-04.csv
  专题_五分钟线/_raw/tx_cont_<code>.json
  控制台：每日根数异常、日线校验、事件清单
"""
import csv, json, os, subprocess, time
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "专题_五分钟线")
RAW = os.path.join(OUT, "_raw")
os.makedirs(RAW, exist_ok=True)

SYMS = {"588170": "sh588170", "000688": "sh000688", "000001": "sh000001"}
NAMES = {"588170": "科创半导体ETF", "000688": "科创50指数", "000001": "上证指数"}
FIRST = "202605060935"


def curl(url, timeout=20):
    r = subprocess.run(["curl", "-s", "--max-time", str(timeout), "-H", "User-Agent: Mozilla/5.0", url],
                       capture_output=True, text=True, encoding="utf-8", errors="ignore")
    return r.stdout


def fetch_all(sym):
    bars, end, pages = [], "202611052000", 0
    while pages < 40:
        t = curl("https://ifzq.gtimg.cn/appstock/app/kline/mkline?param=%s,m5,%s,320" % (sym, end))
        try:
            data = json.loads(t)["data"][sym]["m5"]
        except Exception as e:
            print("  FAIL", sym, end, repr(e)[:60]); time.sleep(1.2); pages += 1; continue
        if not data:
            break
        bars = data + bars
        pages += 1
        if data[0][0] <= FIRST:
            break
        end = data[0][0]
        time.sleep(0.25)
    # 去重 + 排序
    seen, uniq = set(), []
    for b in bars:
        if b[0] not in seen:
            seen.add(b[0]); uniq.append(b)
    uniq.sort(key=lambda x: x[0])
    print("  %s pages=%d bars=%d %s..%s" % (sym, pages, len(uniq), uniq[0][0], uniq[-1][0]))
    return uniq


all_rows = []
for code, sym in SYMS.items():
    print("fetch", code)
    bars = fetch_all(sym)
    json.dump(bars, open(os.path.join(RAW, "tx_cont_%s.json" % code), "w", encoding="utf-8"))
    for b in bars:
        if b[0] < FIRST:
            continue
        all_rows.append([code, NAMES[code], b[0][:8], b[0][8:], b[1], b[3], b[4], b[2],
                         b[5], "手", "", "未取得", "腾讯ifzq.mkline", "区间结束时刻", "不复权"])

HDR = ["代码", "名称", "日期", "时间HHMM", "开盘", "最高", "最低", "收盘",
       "成交量", "成交量单位", "成交额", "成交额单位", "来源", "K线时间含义", "复权方式"]


def wcsv(path, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(HDR)
        w.writerows(rows)
    print("WROTE", os.path.basename(path), len(rows))


wcsv(os.path.join(OUT, "五分钟线_连续_2026-05-06至11-05.csv"), all_rows)
wcsv(os.path.join(OUT, "五分钟线_2026-07-20至08-04.csv"),
     [r for r in all_rows if "20260720" <= r[2] <= "20260804"])

# ---------- 完整性 ----------
print("\n=== 每日根数（48=完整，非48列出）===")
cnt = defaultdict(lambda: defaultdict(int))
for r in all_rows:
    cnt[r[0]][r[2]] += 1
cal = sorted(cnt["000001"])
print("交易日数(000001为基准) %d：%s .. %s" % (len(cal), cal[0], cal[-1]))
for code in SYMS:
    bad = {d: n for d, n in cnt[code].items() if n != 48}
    miss = [d for d in cal if d not in cnt[code]]
    print("%s 有数据日 %d，非48根日 %s，缺日 %s" % (code, len(cnt[code]), bad or "无", miss or "无"))

# ---------- 日线校验 ----------
daily = defaultdict(dict)
with open(os.path.join(ROOT, "2026-11-04", "日线.csv"), encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        daily[r["代码"]][r["日期"]] = r
agg = defaultdict(lambda: [0, None, None, None, None])
for r in all_rows:
    a = agg[(r[0], r[2])]
    a[0] += int(float(r[8]))
    o, h, l, c = float(r[4]), float(r[5]), float(r[6]), float(r[7])
    a[1] = o if a[1] is None else a[1]
    a[2] = h if a[2] is None else max(a[2], h)
    a[3] = l if a[3] is None else min(a[3], l)
    a[4] = c

print("\n=== 日线校验（量/OHLC，抽 6 天：05-06、06-30、07-06、07-21、07-27、11-04）===")
for d0 in ["2026-05-06", "2026-06-30", "2026-07-06", "2026-07-21", "2026-07-27", "2026-11-04"]:
    d = d0.replace("-", "")
    for code in ["588170", "000001"]:
        dr = daily.get(code, {}).get(d0)
        a = agg.get((code, d))
        if not dr or not a:
            continue
        print("%s %s 量 %d vs 日线 %s | 分时O%.3f H%.3f L%.3f C%.3f vs 日线 O%s H%s L%s C%s"
              % (code, d0, a[0], dr["成交量"], a[1], a[2], a[3], a[4],
                 dr["开盘"], dr["最高"], dr["最低"], dr["收盘"]))

# ---------- 7/20-8/4 每日摘要（观察反弹衰退）----------
print("\n=== 2026-07-20 ~ 08-04 每日摘要（腾讯5分钟聚合）===")
print("日期 代码 开 高 低 收 涨跌% 量(万手) 相对07-21量%")
base = {}
for code in ["588170", "000688", "000001"]:
    days = sorted(d for (c, d) in agg if c == code and "20260720" <= d <= "20260804")
    prev = None
    for d in days:
        a = agg[(code, d)]
        if d == "20260721":
            base[code] = a[0]
        chg = (a[4] / prev - 1) * 100 if prev else 0
        print("%s-%s-%s %s %.3f %.3f %.3f %.3f %+.2f %10.1f %6.1f%%"
              % (d[:4], d[4:6], d[6:], code, a[1], a[2], a[3], a[4], chg,
                 a[0] / 1e4, a[0] / base.get(code, a[0]) * 100))
        prev = a[4]
    print("-")

# ---------- 事件清单：单日≥5% 与后续 5 日回吐 ----------
print("\n=== 588170 单日涨幅≥5% 事件及后续（不复权，07-06 分拆日单独标注）===")
days = sorted(d for (c, d) in agg if c == "588170")
closes = {d: agg[("588170", d)][4] for d in days}
for i, d in enumerate(days):
    if i == 0:
        continue
    chg = (closes[d] / closes[days[i - 1]] - 1) * 100
    if chg >= 5:
        fwd = []
        for k in range(1, 6):
            if i + k < len(days):
                fwd.append(round((closes[days[i + k]] / closes[d] - 1) * 100, 2))
        tag = " [分拆日, 涨幅失真]" if d == "20260706" else ""
        print("%s-%s-%s %+.2f%% 后续1..5日 %s%s" % (d[:4], d[4:6], d[6:], chg, fwd, tag))
