# -*- coding: utf-8 -*-
"""宽基 ETF 每日份额（上交所官方按日公示）+ 每日净值（东方财富）+ 分红拆分。

份额：SSE COMMON_SSE_ZQPZ_ETFZL_XXPL_ETFGM_SEARCH_L，STAT_DATE=YYYYMMDD，TOT_VOL 单位=万份
      —— 上交所"ETF规模"公示，T 日盘后发布，为原始份额（非估算净流入）。
净值：EM api.fund.eastmoney.com/f10/lsjz，字段 FSRQ/DWJZ/LJJZ，T 日晚间披露。
159915 在深交所，深交所无按日份额报表（仅最新日），单列。
"""
import csv, json, os, subprocess, time
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "专题_宽基份额净值")
RAW = os.path.join(OUT, "_raw")
os.makedirs(RAW, exist_ok=True)

SSE = {"510300": "沪深300ETF华泰柏瑞", "588000": "科创50ETF华夏",
       "510050": "上证50ETF华夏", "588170": "科创半导体ETF华夏"}
ALL5 = dict(SSE); ALL5["159915"] = "创业板ETF易方达"


def curl(url, timeout=25, ref=None):
    cmd = ["curl", "-s", "--max-time", str(timeout), "-H", "User-Agent: Mozilla/5.0"]
    if ref:
        cmd += ["-H", "Referer: " + ref]
    cmd.append(url)
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore").stdout


# 交易日历：取五分钟线里出现过的日期（125 日）
cal = sorted({r["日期"] for r in csv.DictReader(
    open(os.path.join(ROOT, "专题_宽基五分钟线", "宽基五分钟线_连续_2026-05-06至今.csv"), encoding="utf-8-sig"))})
print("交易日 %d：%s .. %s" % (len(cal), cal[0], cal[-1]))

rows, fail = [], []
for d in cal:
    p = os.path.join(RAW, "sse_%s.json" % d)
    if os.path.exists(p) and os.path.getsize(p) > 500:
        txt = open(p, encoding="utf-8").read()
    else:
        txt = curl("http://query.sse.com.cn/commonQuery.do?sqlId=COMMON_SSE_ZQPZ_ETFZL_XXPL_ETFGM_SEARCH_L&STAT_DATE=%s" % d,
                   ref="http://www.sse.com.cn/")
        open(p, "w", encoding="utf-8").write(txt)
        time.sleep(0.12)
    try:
        res = json.loads(txt).get("result") or []
    except Exception:
        res = []
    hit = 0
    for r in res:
        if r.get("SEC_CODE") in SSE:
            rows.append([d, r["SEC_CODE"], SSE[r["SEC_CODE"]], r.get("TOT_VOL"), "万份",
                         r.get("STAT_DATE"), "上交所ETF规模公示(原始份额)"])
            hit += 1
    if hit < len(SSE):
        fail.append((d, hit))
print("份额行数 %d；取数不足的日期 %s" % (len(rows), fail[:20] if fail else "无"))

rows.sort(key=lambda x: (x[1], x[0]))
p = os.path.join(OUT, "每日份额_上交所示例ETF.csv")
with open(p, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["日期", "代码", "名称", "总份额", "单位", "公示日期", "来源"])
    w.writerows(rows)
print("WROTE", os.path.basename(p), len(rows))

# ---------- 净值 ----------
nav = {}
for code in ALL5:
    txt = curl("https://api.fund.eastmoney.com/f10/lsjz?fundCode=%s&pageIndex=1&pageSize=260" % code,
               ref="https://fundf10.eastmoney.com/")
    try:
        lst = json.loads(txt)["Data"]["LSJZList"]
    except Exception:
        print("NAV FAIL", code, txt[:80]); lst = []
    for it in lst:
        nav[(code, it["FSRQ"].replace("-", ""))] = (it["DWJZ"], it.get("LJJZ"), it.get("FHSP", ""))
    print("NAV", code, len(lst), lst[-1]["FSRQ"] if lst else "-", "..", lst[0]["FSRQ"] if lst else "-")
    json.dump(lst, open(os.path.join(RAW, "nav_%s.json" % code), "w", encoding="utf-8"), ensure_ascii=False)

# ---------- 分红/拆分 ----------
fh = {}
for code in ALL5:
    txt = curl("https://fundf10.eastmoney.com/fhsp_%s.html" % code, ref="https://fundf10.eastmoney.com/")
    open(os.path.join(RAW, "fhsp_%s.html" % code), "w", encoding="utf-8").write(txt)
    import re
    txt2 = re.sub(r"<[^>]+>", "|", txt)
    dates = sorted(set(re.findall(r"2026-\d{2}-\d{2}", txt2)))
    fh[code] = dates
    print("FHSP", code, dates[:8])

json.dump({"fhsp": fh, "nav_codes": list(ALL5)}, open(os.path.join(OUT, "_raw", "meta.json"), "w"), ensure_ascii=False)

# 合并：份额 + 净值（净值按 T 日；T 日净值若未披露则记空）
merged = []
for d, code, name, vol, unit, stat, src in rows:
    dz, lj, sp = nav.get((code, d), ("", "", ""))
    merged.append([d, code, name, vol, unit, dz, lj, sp, "上交所ETF规模公示", "东方财富基金净值"])
p2 = os.path.join(OUT, "每日份额与净值_合并.csv")
with open(p2, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["日期", "代码", "名称", "总份额", "份额单位", "单位净值", "累计净值", "分红送配", "份额来源", "净值来源"])
    w.writerows(merged)
print("WROTE", os.path.basename(p2), len(merged))

# 关键日份额变动
print("\n=== 关键日份额（亿份）与日变动 ===")
by = defaultdict(dict)
for d, code, name, vol, unit, stat, src in rows:
    by[code][d] = float(vol) / 1e4  # 万份 -> 亿份
for code in sorted(by):
    ds = sorted(by[code])
    for d in ["20260717", "20260720", "20260721", "20260722", "20261102", "20261103", "20261104", "20261105"]:
        if d in by[code]:
            i = ds.index(d)
            chg = by[code][d] - by[code][ds[i - 1]] if i else None
            print("%s %s 份额%.2f亿 %s" % (code, d, by[code][d], ("变动%+.2f亿" % chg) if chg is not None else ""))
    print("-")

print("\n=== 最早/最晚净值日期（验证披露可见时点）===")
for code in ALL5:
    ds = sorted(d for (c, d) in nav if c == code)
    print(code, "最新净值日", ds[-1] if ds else "-", "是否有11-05", ("20261105" in ds))
