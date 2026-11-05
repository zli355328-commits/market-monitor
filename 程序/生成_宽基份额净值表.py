# -*- coding: utf-8 -*-
"""重建：每日份额(T日) + 每日净值(T日) + 拆分记录 + 原始份额变动/估算净流入 区分。

份额来源：上交所 ETF 规模公示（原始份额，T 日盘后）
净值来源：东方财富基金净值（T 日晚间披露，T+1 早间媒体引用）
"""
import csv, json, os, re, subprocess, time
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "专题_宽基份额净值")
RAW = os.path.join(OUT, "_raw")

NAMES = {"510300": "沪深300ETF华泰柏瑞", "588000": "科创50ETF华夏", "510050": "上证50ETF华夏",
         "588170": "科创半导体ETF华夏", "159915": "创业板ETF易方达"}


def curl(url, ref=None, timeout=25):
    cmd = ["curl", "-s", "--max-time", str(timeout), "-H", "User-Agent: Mozilla/5.0"]
    if ref:
        cmd += ["-H", "Referer: " + ref]
    cmd.append(url)
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore").stdout


# ---------- 净值（带重试） ----------
nav = {}
for code in NAMES:
    lst, page = [], 1
    while page <= 9:
        got = []
        for attempt in range(4):
            txt = curl("https://api.fund.eastmoney.com/f10/lsjz?fundCode=%s&pageIndex=%d&pageSize=20" % (code, page),
                       ref="https://fundf10.eastmoney.com/")
            try:
                got = json.loads(txt)["Data"]["LSJZList"] or []
            except Exception:
                got = []
            if got:
                break
            time.sleep(1.2)
        if not got:
            break
        lst += got
        if got[-1]["FSRQ"] < "2026-05-06":
            break
        page += 1
        time.sleep(0.35)
    for it in lst:
        nav[(code, it["FSRQ"].replace("-", ""))] = (it["DWJZ"], it.get("LJJZ", ""))
    if lst:
        print("NAV %s n=%d %s..%s 最新DWJZ=%s" % (code, len(lst), lst[-1]["FSRQ"], lst[0]["FSRQ"], lst[0]["DWJZ"]))
        json.dump(lst, open(os.path.join(RAW, "nav_%s.json" % code), "w", encoding="utf-8"), ensure_ascii=False)
    else:
        print("NAV %s FAIL" % code)
    time.sleep(0.8)

# ---------- 份额 ----------
sh = defaultdict(dict)
for fn in os.listdir(RAW):
    if not (fn.startswith("sse_") and fn.endswith(".json")):
        continue
    d = fn[4:12]
    try:
        res = json.loads(open(os.path.join(RAW, fn), encoding="utf-8").read()).get("result") or []
    except Exception:
        continue
    for r in res:
        if r.get("SEC_CODE") in ("510300", "588000", "510050", "588170"):
            sh[r["SEC_CODE"]][d] = float(r["TOT_VOL"]) / 1e4  # 万份 -> 亿份

dates = sorted({d for c in sh for d in sh[c]})
print("\n份额日期 %d：%s .. %s" % (len(dates), dates[0], dates[-1]))
for c in sh:
    print("  %s %d 日，缺 %s" % (c, len(sh[c]), [d for d in dates if d not in sh[c]] or "无"))

# ---------- 合并 ----------
rows, flags = [], []
SPLIT = {("588170", "20260703"): ("1:3", 3.0)}
for c in ["510300", "588000", "510050", "588170"]:
    ds = sorted(sh[c])
    prev = None
    for d in ds:
        vol = sh[c][d]
        chg = vol - prev if prev is not None else None
        dz, lj = nav.get((c, d), ("", ""))
        note = ""
        if (c, d) in SPLIT and prev:
            ratio = SPLIT[(c, d)][1]
            split_part = prev * (ratio - 1)
            real = chg - split_part
            note = "含 %s 分拆：分拆贡献约 %+.2f 亿份，真实净申购约 %+.2f 亿份" % (
                SPLIT[(c, d)][0], split_part, real)
            chg = real
        est = (chg * float(dz)) if (chg is not None and dz) else ""
        rows.append([d[:4] + "-" + d[4:6] + "-" + d[6:], c, NAMES[c], "%.2f" % vol,
                     ("%+.2f" % chg) if chg is not None else "", ("%.2f" % est) if est != "" else "",
                     dz, lj, "上交所ETF规模公示", "东方财富", note])
        if d == "20261105":
            flags.append((c, "11-05 份额已公示"))
        prev = vol

p = os.path.join(OUT, "每日份额与净值_2026-05-06至11-05.csv")
with open(p, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["日期", "代码", "名称", "总份额(亿份)", "份额日变动(亿份,已剔除分拆)",
                "估算净流入(亿元=Δ份额×当日单位净值)",
                "单位净值", "累计净值", "份额来源", "净值来源", "备注"])
    w.writerows(rows)
print("WROTE", os.path.basename(p), len(rows))

# ---------- 拆分 / 分红 ----------
fork = []
for code in NAMES:
    t = open(os.path.join(RAW, "fhsp_%s.html" % code), encoding="utf-8", errors="ignore").read()
    s = re.sub(r"<script.*?</script>", "", t, flags=re.S)
    s = re.sub(r"<[^>]+>", "|", s)
    s = re.sub(r"\|{2,}", "|", s)
    for m in re.finditer(r"\|(\d{4}-\d{2}-\d{2})\|(份额分拆|份额折算|拆分)\|([\d.]+:[\d.]+)", s):
        fork.append([code, NAMES[code], m.group(1), m.group(2), m.group(3)])
p2 = os.path.join(OUT, "拆分与分红记录.csv")
with open(p2, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["代码", "名称", "拆分/折算日", "类型", "比例", "来源", "窗口内是否有分红"])
    for r in fork:
        w.writerow(r + ["东方财富基金档案 fhsp", "窗口内无分红记录"])
print("WROTE", os.path.basename(p2), len(fork))
for r in fork:
    print("  ", r)

# ---------- 关键日 ----------
print("\n=== 关键日：份额、变动、净流入估算 ===")
for d in ["20260717", "20260720", "20260721", "20260722", "20261102", "20261103", "20261104", "20261105"]:
    line = [d]
    for c in ["510300", "588000", "510050", "588170"]:
        ds = sorted(sh[c])
        if d in sh[c] and ds.index(d) > 0:
            chg = sh[c][d] - sh[c][ds[ds.index(d) - 1]]
            line.append("%s %+.2f亿份" % (c, chg))
        else:
            line.append("%s 无" % c)
    print(" | ".join(line))

# 区间累计
print("\n=== 区间累计（2026-05-06 → 最新）===")
for c in ["510300", "588000", "510050", "588170"]:
    ds = sorted(sh[c])
    print("%s %s %.2f -> %s %.2f 亿份，累计 %+.2f 亿份" %
          (c, ds[0], sh[c][ds[0]], ds[-1], sh[c][ds[-1]], sh[c][ds[-1]] - sh[c][ds[0]]))
