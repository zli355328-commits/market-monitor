# -*- coding: utf-8 -*-
"""承接指纹：尾盘 30 分钟成交量占全天 ≥45% 的日期，与当日份额变动、后续走势对照。

尾盘集中度是"大额资金在收盘前集中成交"的可观测指纹；份额变动（T 日原始份额）是次日才可见的结果。
只做并置，不做主体归属。
"""
import csv, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
A = os.path.join(ROOT, "专题_宽基五分钟线", "每日量能与承接_2026-05-06至今.csv")
B = os.path.join(ROOT, "专题_宽基份额净值", "每日份额与净值_2026-05-06至11-05.csv")

vol = {}
for r in csv.DictReader(open(A, encoding="utf-8-sig")):
    vol[(r["代码"], r["日期"])] = r
sh = {}
for r in csv.DictReader(open(B, encoding="utf-8-sig")):
    sh[(r["代码"], r["日期"])] = r

out = []
for (code, d), r in sorted(vol.items(), key=lambda x: (x[0][1], x[0][0])):
    if not r["尾盘30分占比%"] or float(r["尾盘30分占比%"]) < 45:
        continue
    s = sh.get((code, d), {})
    out.append([d, code, r["名称"], r["涨跌%"], r["成交量(万手)"], r["量/前20日均量"],
                r["尾盘30分占比%"], r["首小时占比%"],
                s.get("份额日变动(亿份,已剔除分拆)", ""), s.get("估算净流入(亿元=Δ份额×当日单位净值)", ""),
                r["后续1日%"], r["后续5日%"]])

p = os.path.join(ROOT, "专题_宽基五分钟线", "承接指纹_尾盘集中度≥45%.csv")
with open(p, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["日期", "代码", "名称", "当日涨跌%", "成交量(万手)", "量/前20日均量", "尾盘30分占比%",
                "首小时占比%", "当日份额变动(亿份)", "估算净流入(亿元)", "后续1日%", "后续5日%"])
    w.writerows(out)
print("WROTE", os.path.basename(p), len(out))
for r in out:
    print(r)

# 放量样本统计
rows = list(csv.DictReader(open(A, encoding="utf-8-sig")))
big = [r for r in rows if r["量/前20日均量"] and float(r["量/前20日均量"]) >= 1.8 and r["后续5日%"]]
neg = [r for r in big if float(r["后续5日%"]) < 0]
print("\n放量日(≥1.8x) 含完整5日后续样本 %d，其中后续5日为负 %d（%.0f%%）" % (len(big), len(neg), len(neg) / len(big) * 100))
h = [r for r in rows if r["尾盘30分占比%"] and float(r["尾盘30分占比%"]) >= 45]
print("尾盘≥45%% 的日数 %d（全样本 %d 个日-标的）" % (len(h), len(rows)))
