# -*- coding: utf-8 -*-
"""宽基 ETF 每日量能与市场承接（承接研究用）。

每日：收盘、涨跌%、成交量(万手)、成交额(亿元，仅 09-15 起有)、量/20日均量、尾盘30分占比、首小时占比、后续1/5日涨跌
"""
import csv, os
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "专题_宽基五分钟线")
NAMES = {"510300": "沪深300ETF华泰柏瑞", "588000": "科创50ETF华夏",
         "510050": "上证50ETF华夏", "159915": "创业板ETF易方达"}

bars = defaultdict(list)
for r in csv.DictReader(open(os.path.join(OUT, "宽基五分钟线_连续_2026-05-06至今.csv"), encoding="utf-8-sig")):
    bars[r["代码"]].append(r)

amt = {}
p = os.path.join(OUT, "宽基五分钟线_成交额补充_2026-09-15至今.csv")
if os.path.exists(p):
    for r in csv.DictReader(open(p, encoding="utf-8-sig")):
        k = (r["代码"], r["日期"])
        amt[k] = amt.get(k, 0.0) + float(r["成交额"])

out = []
for code in NAMES:
    rs = bars[code]
    days = sorted({r["日期"] for r in rs})
    agg = {}
    for d in days:
        b = [r for r in rs if r["日期"] == d]
        b.sort(key=lambda x: x["时间HHMM"])
        vol = sum(float(x["成交量"]) for x in b)
        last30 = sum(float(x["成交量"]) for x in b if x["时间HHMM"] >= "1430")
        first60 = sum(float(x["成交量"]) for x in b if x["时间HHMM"] <= "1030")
        agg[d] = dict(o=float(b[0]["开盘"]), h=max(float(x["最高"]) for x in b),
                      l=min(float(x["最低"]) for x in b), c=float(b[-1]["收盘"]),
                      vol=vol, last30=last30 / vol * 100 if vol else 0,
                      first60=first60 / vol * 100 if vol else 0)
    for i, d in enumerate(days):
        a = agg[d]
        prev = agg[days[i - 1]]["c"] if i else None
        chg = (a["c"] / prev - 1) * 100 if prev else None
        base = [agg[x]["vol"] for x in days[max(0, i - 20):i]]
        ratio = a["vol"] / (sum(base) / len(base)) if base else None
        f1 = (agg[days[i + 1]]["c"] / a["c"] - 1) * 100 if i + 1 < len(days) else None
        f5 = (agg[days[min(i + 5, len(days) - 1)]]["c"] / a["c"] - 1) * 100 if i + 5 < len(days) else None
        out.append([d[:4] + "-" + d[4:6] + "-" + d[6:], code, NAMES[code],
                    "%.3f" % a["o"], "%.3f" % a["h"], "%.3f" % a["l"], "%.3f" % a["c"],
                    ("%+.2f" % chg) if chg is not None else "",
                    "%.0f" % (a["vol"] / 1e4),
                    ("%.2f" % (amt[(code, d)] / 1e8)) if (code, d) in amt else "未取得",
                    ("%.2f" % ratio) if ratio else "",
                    "%.1f" % a["last30"], "%.1f" % a["first60"],
                    ("%+.2f" % f1) if f1 is not None else "",
                    ("%+.2f" % f5) if f5 is not None else ""])

p2 = os.path.join(OUT, "每日量能与承接_2026-05-06至今.csv")
with open(p2, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["日期", "代码", "名称", "开盘", "最高", "最低", "收盘", "涨跌%",
                "成交量(万手)", "成交额(亿元)", "量/前20日均量", "尾盘30分占比%", "首小时占比%",
                "后续1日%", "后续5日%"])
    w.writerows(out)
print("WROTE", os.path.basename(p2), len(out))

# 放量日清单（量≥1.8倍20日均量），并标后续走势
print("\n=== 放量日（量≥1.8×20日均量）及后续5日 ===")
print("日期 代码 涨跌% 量(万手) 倍数 尾盘占比 后续5日%")
for r in out:
    if r[10] and float(r[10]) >= 1.8:
        print(r[0], r[1], r[7], r[8], r[10], r[11], r[14] or "(不足5日)")

# 关键日
print("\n=== 关键日（7/17-7/22、10/29-11/05）===")
for r in out:
    if r[0] in ("2026-07-17", "2026-07-20", "2026-07-21", "2026-07-22",
                "2026-10-29", "2026-10-30", "2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05"):
        print(r[0], r[1], "涨跌", r[7], "量", r[8], "倍", r[10], "尾盘", r[11], "首小时", r[12], "额", r[9])
