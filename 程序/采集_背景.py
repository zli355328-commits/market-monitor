"""市场背景增量：A股/港股/美股日线 + 韩股快照 + 沪深合计成交额（C009 修正版）。

用法: python 程序/采集_背景.py --date 2026-11-03 --seed 2026-11-02 --us-last 2026-11-02

C009 修正:
  1. 严格截断：每个市场按其截止日过滤，禁止混入未来日期。
     A股/港股 ≤ --date；美股 ≤ --us-last（最近已结束常规交易日，冬令时当晚未开盘）。
  2. 请求不复权却只返回 qfqday（前复权）时拒用并记缺失，不再沿用"不复权"标注。
"""
import argparse
import csv
import json
import os
import subprocess
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MAP = [
    ("000001", "sh000001", "A股", "上证指数", "Asia/Shanghai", "手/元"),
    ("399001", "sz399001", "A股", "深证成指", "Asia/Shanghai", "手/元"),
    ("399106", "sz399106", "A股", "深证综指", "Asia/Shanghai", "手/元"),
    ("HSI", "hkHSI", "港股", "恒生指数", "Asia/Hong_Kong", "点"),
    ("SPX", "us.INX", "美股", "标普500", "America/New_York", "点"),
    ("NDX", "us.NDX", "美股", "纳斯达克100", "America/New_York", "点"),
    ("DJI", "us.DJI", "美股", "道琼斯工业平均", "America/New_York", "点"),
]


def curl(url, timeout=25):
    r = subprocess.run(["curl", "-s", "--max-time", str(timeout), url],
                       capture_output=True, text=True, encoding="utf-8", errors="ignore")
    return r.stdout


def tx_day(sym, n=15, retries=3):
    """返回 (k, rejected_qfq)。仅用复权标志为空的 day 序列。"""
    url = ("https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get"
           "?param=%s,day,,,%d," % (sym, n))
    for _ in range(retries):
        t = curl(url)
        if t.startswith("{"):
            try:
                d = json.loads(t)["data"][sym]
                k = d.get("day")
                if k:
                    return k, False
                if d.get("qfqday"):
                    return None, True       # 只给前复权 → 拒绝
            except Exception:
                pass
        time.sleep(2)
    return None, False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--seed", required=True)
    ap.add_argument("--us-last", required=True, help="美股最近已结束常规交易日 YYYY-MM-DD")
    args = ap.parse_args()
    outdir = os.path.join(ROOT, args.date)
    raw = os.path.join(outdir, "_raw")
    os.makedirs(raw, exist_ok=True)
    header = ["市场", "指数/标的", "代码", "时区", "日期", "开盘", "最高", "最低", "收盘",
              "成交量", "成交额", "单位", "来源", "备注"]
    rows, meta = {}, {}
    with open(os.path.join(ROOT, args.seed, "市场背景.csv"), newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            rows[(r["代码"], r["日期"])] = r
            meta.setdefault(r["代码"], (r["市场"], r["指数/标的"], r["时区"], r["单位"]))

    for code, sym, mkt, name, tz, unit in MAP:
        cutoff = args.us_last if mkt == "美股" else args.date
        k, rejected = tx_day(sym)
        if not k:
            print("FAIL", code, "QFQ_REJECT" if rejected else "接口失败", "cutoff=", cutoff)
            continue
        json.dump(k, open(os.path.join(raw, "bg_%s.json" % code), "w", encoding="utf-8"),
                  ensure_ascii=False)
        kept = 0
        for x in k:
            d, o, c, h, l, v = x[0], x[1], x[2], x[3], x[4], x[5]
            if d > cutoff:               # 严格截断，禁止未来
                continue
            amt = ""
            if mkt == "A股" and len(x) > 8 and x[8] not in ("", None):
                try:
                    amt = "%.0f" % (float(x[8]) * 10000)
                except Exception:
                    amt = ""
            rows[(code, d)] = {"市场": mkt, "指数/标的": name, "代码": code, "时区": tz,
                               "日期": d, "开盘": o, "最高": h, "最低": l, "收盘": c,
                               "成交量": ("%.0f" % float(v)) if v not in ("", None) else "",
                               "成交额": amt, "单位": unit,
                               "来源": "腾讯行情公开接口", "备注": ""}
            kept += 1
        print("OK", code, "kept", kept, "cutoff", cutoff)
        time.sleep(0.4)

    # 沪深合计 = 上证综指成交额 + 深证综指成交额（元）
    for (code, d), r in list(rows.items()):
        if code == "000001" and r.get("成交额"):
            r2 = rows.get(("399106", d))
            if r2 and r2.get("成交额"):
                rows[("HS_SUM", d)] = {"市场": "A股", "指数/标的": "沪深合计成交额(上证综指+深证综指口径)",
                                       "代码": "HS_SUM", "时区": "Asia/Shanghai", "日期": d,
                                       "开盘": "", "最高": "", "最低": "", "收盘": "",
                                       "成交量": "", "成交额": "%.0f" % (float(r["成交额"]) + float(r2["成交额"])),
                                       "单位": "元", "来源": "由上证综指与深证综指成交额相加", "备注": "计算值"}

    # 韩股快照（当日收盘；腾讯快照，历史日线源不可得）
    snap_path = os.path.join(raw, "snap.txt")
    if os.path.isfile(snap_path):
        t = open(snap_path, encoding="utf-8").read()
        for line in t.split(";"):
            if "=" not in line:
                continue
            key = line.split("=", 1)[0].strip().replace("v_", "")
            body = line.split("=", 1)[1].strip().strip('"')
            f = body.split("~")
            mp = {"kr005930": ("005930.KS", "Samsung Electronics Co., Ltd."),
                  "kr000660": ("000660.KS", "SK hynix Inc.")}
            if key in mp and len(f) > 35:
                code, name = mp[key]
                rows[(code, args.date)] = {"市场": "韩股", "指数/标的": name, "代码": code,
                                           "时区": "Asia/Seoul", "日期": args.date,
                                           "开盘": f[5], "最高": f[33], "最低": f[34],
                                           "收盘": f[3], "成交量": f[6], "成交额": "",
                                           "单位": "KRW", "来源": "腾讯行情接口快照(历史日线源不可得)",
                                           "备注": "昨收=%s；快照时间=%s（Asia/Seoul 当地收盘）" % (f[4], f[30])}

    out = [rows[k] for k in sorted(rows, key=lambda x: (meta.get(x[0], ("", "", "", ""))[0], x[0], x[1]))]
    with open(os.path.join(outdir, "市场背景.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        for r in out:
            w.writerow({k: r.get(k, "") for k in header})
    print("WROTE 市场背景.csv rows", len(out), "at", datetime.now().strftime("%H:%M"))


if __name__ == "__main__":
    main()
