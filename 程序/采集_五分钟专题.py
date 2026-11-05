# -*- coding: utf-8 -*-
"""专题：抓取 588170 / 科创50(sh000688) / 上证指数(sh000001) 五分钟线。

窗口A：2026-07-20 ~ 2026-07-24（腾讯 ifzq mkline，按结束时间翻页，单页320根）
窗口B：2026-10-26 ~ 2026-11-05（新浪 getKLineData，datalen=1970 上限回溯至 2026-09-01）

输出：专题_五分钟线/ 下两份 CSV + 原始 JSON 存档；单位用日线总量定标。
"""
import csv, json, os, subprocess, time
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "专题_五分钟线")
RAW = os.path.join(OUT, "_raw")
os.makedirs(RAW, exist_ok=True)

SYMS = {"588170": "sh588170", "000688": "sh000688", "000001": "sh000001"}
NAMES = {"588170": "科创半导体ETF", "000688": "科创50指数", "000001": "上证指数"}

WIN_A = ("20260720", "20260724")   # 含端点
WIN_B = ("20261026", "20261105")


def curl(url, timeout=25, ref=None):
    cmd = ["curl", "-s", "--max-time", str(timeout), "-H", "User-Agent: Mozilla/5.0"]
    if ref:
        cmd += ["-H", "Referer: " + ref]
    cmd.append(url)
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    return r.stdout


def fetch_tencent(sym, end_first, stop_before):
    """按结束时间向前翻页，返回该区间全部 m5 根。"""
    bars, end = [], end_first
    for page in range(30):
        url = "https://ifzq.gtimg.cn/appstock/app/kline/mkline?param=%s,m5,%s,320" % (sym, end)
        t = curl(url)
        try:
            data = json.loads(t)["data"][sym]["m5"]
        except Exception as e:
            print("TX FAIL", sym, end, repr(e)[:80]); break
        if not data:
            break
        newfirst = data[0][0]
        bars = data + bars if bars and bars[0][0] > newfirst else data + bars
        if newfirst[:8] < stop_before:
            break
        end = newfirst  # 下一页从这根之前取
        time.sleep(0.3)
    return bars


def fetch_sina(sym):
    url = ("https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData"
           "?symbol=%s&scale=5&ma=no&datalen=1970" % sym)
    t = curl(url, ref="https://finance.sina.com.cn")
    return json.loads(t)


rows_a, rows_b = [], []
for code, sym in SYMS.items():
    # ---- 窗口A：腾讯翻页（从 7/24 15:05 往前，到 7/20 之前停）----
    bars = fetch_tencent(sym, "202607241505", "202607200930")
    open(os.path.join(RAW, "tx_%s_m5_0720-0724.json" % code), "w", encoding="utf-8").write(json.dumps(bars))
    for b in bars:
        d, hm = b[0][:8], b[0][8:]
        if WIN_A[0] <= d <= WIN_A[1]:
            rows_a.append([code, d, hm, b[1], b[2], b[3], b[4], b[5], b[7] if len(b) > 7 else "", "腾讯ifzq.mkline"])
    print("A", code, "bars", sum(1 for r in rows_a if r[0] == code))
    # ---- 窗口B：新浪 ----
    arr = fetch_sina(sym)
    open(os.path.join(RAW, "sina_%s_m5.json" % code), "w", encoding="utf-8").write(json.dumps(arr))
    for x in arr:
        d, hm = x["day"][:10].replace("-", ""), x["day"][11:16].replace(":", "")
        if WIN_B[0] <= d <= WIN_B[1]:
            rows_b.append([code, d, hm, x["open"], x["high"], x["low"], x["close"],
                           x.get("volume", ""), x.get("amount", ""), "新浪CN_MarketDataService"])
    print("B", code, "bars", sum(1 for r in rows_b if r[0] == code))
    time.sleep(0.4)

HDR = ["代码", "名称", "日期", "时间HHMM", "开盘", "最高", "最低", "收盘", "量_原始", "额_原始", "来源"]


def wcsv(path, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(HDR)
        for r in rows:
            w.writerow([r[0], NAMES[r[0]]] + r[1:])
    print("WROTE", path, len(rows))


wcsv(os.path.join(OUT, "五分钟线_2026-07-20至07-24.csv"), rows_a)
wcsv(os.path.join(OUT, "五分钟线_2026-10-26至11-05.csv"), rows_b)

# ---- 单位定标：与日线总量比对（日线：成交量手、成交额元）----
daily = defaultdict(dict)
with open(os.path.join(ROOT, "2026-11-04", "日线.csv"), encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        daily[r["代码"]][r["日期"]] = r

print("\n=== 单位定标（按日汇总 / 日线总量）===")
for tag, rows in (("A(腾讯,7月)", rows_a), ("B(新浪,10-11月)", rows_b)):
    agg = defaultdict(lambda: [0.0, 0.0, [], []])
    for r in rows:
        k = (r[0], r[1])
        agg[k][0] += float(r[7] or 0)
        agg[k][1] += float(r[8] or 0)
        agg[k][2].append(float(r[4])); agg[k][3].append(float(r[7 - 0]))  # high list, close
    for (code, d), (v, a, his, cls) in sorted(agg.items()):
        dd = "%s-%s-%s" % (d[:4], d[4:6], d[6:8])
        dr = daily.get(code, {}).get(dd)
        if not dr:
            continue
        dv, da = float(dr["成交量"]), float(dr["成交额"])
        rv = dv / v if v else 0
        ra = da / a if a else 0
        print("%s %s %s 量比(日线/分时)=%.4f 额比=%.4f  分时量合计=%.0f 分时额合计=%.2f 日线量=%.0f 日线额=%.0f"
              % (tag, code, dd, rv, ra, v, a, dv, da))
