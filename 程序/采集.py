"""参数化日线/快照采集入口（C009 修正版）。

用法:
  python 程序/采集.py --date 2026-11-03 --seed 2026-11-02

以 --seed 日期的 日线.csv 为种子，对 监测标的.json 中的标的
回补最近 N 根并追加目标日；新标的(无种子)一次性建 250 根历史。
输出: <date>/日线.csv  <date>/_raw/*

C009 修正:
  1. 严格截断目标日：parse_kline 只保留 日期 <= --date 的记录，禁止混入未来。
  2. 请求不复权却只返回 qfqday（前复权）时拒用并记缺失，不再标"不复权"。
"""
import argparse
import csv
import json
import os
import subprocess
import sys
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

EX = {
    "588170": "SH", "515050": "SH", "513310": "SH", "513650": "SH",
    "513950": "SH", "563020": "SH", "601398": "SH", "601939": "SH",
    "000001": "SH", "158050": "SZ", "159107": "SZ", "159169": "SZ",
    "159577": "SZ", "159659": "SZ", "399001": "SZ", "399106": "SZ",
}
NAME_FALLBACK = {"159107": "创业板软件ETF富国"}


def curl(url, timeout=25, ref=None):
    cmd = ["curl", "-s", "--max-time", str(timeout)]
    if ref:
        cmd += ["-H", "Referer: " + ref, "-H", "User-Agent: Mozilla/5.0"]
    cmd.append(url)
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="ignore")
    return r.stdout


def tx_day(code, ex, n, retries=3):
    """返回 (k, qt, sym, rejected_qfq). rejected_qfq=True 表示仅返回了前复权序列，须拒用。"""
    sym = ("sh" if ex == "SH" else "sz") + code if ex in ("SH", "SZ") else code
    url = ("https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get"
           "?param=%s,day,,,%d," % (sym, n))
    for _ in range(retries):
        t = curl(url)
        if t.startswith("{"):
            try:
                d = json.loads(t)["data"][sym]
                k = d.get("day")          # 不复权序列
                if k:
                    return k, d.get("qt", {}), sym, False
                if d.get("qfqday"):       # 只给了前复权 → 拒绝，记缺失
                    return None, None, sym, True
            except Exception:
                pass
        time.sleep(2)
    return None, None, sym, False


def parse_kline(k, code, ex, max_date=None):
    """腾讯 day: [日期,开,收,高,低,量(手),{},换手%,额(万元),...]
    max_date: 严格截断，仅保留 日期 <= max_date 的记录。"""
    out = {}
    for r in k:
        if max_date and r[0] > max_date:
            continue
        try:
            amt = float(r[8]) * 10000 if len(r) > 8 and r[8] not in ("", None) else None
        except Exception:
            amt = None
        out[r[0]] = [code, ex, r[0], "", r[1], r[3], r[4], r[2],
                     ("%.0f" % float(r[5])) if r[5] not in ("", None) else "",
                     ("%.0f" % amt) if amt is not None else ""]
    return out


def merge(seed_rows, inc, header):
    """seed_rows: list[dict]; inc: dict date->list. 合并并按日期排序，重算昨收。"""
    merged = {}
    for r in seed_rows:
        merged[r["日期"]] = [r["代码"], r["交易所"], r["日期"], r["昨收"], r["开盘"],
                             r["最高"], r["最低"], r["收盘"], r["成交量"], r["成交额"]]
    merged.update(inc)
    rows = [merged[d] for d in sorted(merged)]
    out, prev = [], None
    for r in rows:
        out.append([r[0], r[1], r[2], ("%.4f" % prev if prev is not None else r[3]),
                    r[4], r[5], r[6], r[7], r[8], r[9]])
        try:
            prev = float(r[7])
        except Exception:
            prev = None
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--seed", default=None, help="种子日期目录，如 2026-11-02")
    ap.add_argument("--n", type=int, default=20, help="回补根数")
    args = ap.parse_args()

    cfg = json.loads(open(os.path.join(ROOT, "监测标的.json"), encoding="utf-8-sig").read())
    codes = list(cfg["自选代码"]) + [cfg["共同参照"]]
    outdir = os.path.join(ROOT, args.date)
    raw = os.path.join(outdir, "_raw")
    os.makedirs(raw, exist_ok=True)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    seed = {}
    seed_path = os.path.join(ROOT, args.seed, "日线.csv") if args.seed else None
    header = None
    if seed_path and os.path.isfile(seed_path):
        with open(seed_path, newline="", encoding="utf-8-sig") as f:
            rd = csv.DictReader(f)
            header = rd.fieldnames
            for r in rd:
                seed.setdefault(r["代码"], []).append(r)

    header = header or ["代码", "交易所", "日期", "昨收", "开盘", "最高", "最低", "收盘",
                        "成交量", "成交额", "成交量单位", "货币", "复权方式", "来源", "采集时间"]

    allrows, diag = [], []
    for code in codes:
        ex = EX[code]
        n = args.n if seed.get(code) else 250
        k, qt, sym, rejected = tx_day(code, ex, n)
        if not k:
            reason = "QFQ_REJECT(请求不复权却仅返回前复权)" if rejected else "FAIL(接口失败)"
            diag.append((code, reason, 0, "-", "-", "-", "-"))
            for r in seed.get(code, []):
                allrows.append([r[h] for h in header])
            continue
        json.dump(k, open(os.path.join(raw, "tx_day_%s.json" % code), "w", encoding="utf-8"),
                  ensure_ascii=False)
        inc = parse_kline(k, code, ex, max_date=args.date)
        rows = merge(seed.get(code, []), inc, header)
        for x in rows:
            allrows.append(x + ["手", "CNY", "不复权", "腾讯行情公开接口(newfqkline)", now])
        last = rows[-1]
        prevclose = float(last[3]) if last[3] else 0.0
        chg = (float(last[7]) / prevclose - 1) * 100 if prevclose else 0.0
        low = float(last[6])
        trig = (low / prevclose - 1) * 100 if prevclose else 0.0
        name = NAME_FALLBACK.get(code, qt.get(sym, ["", ""])[1] if qt and sym in qt else "")
        diag.append((code, name, len(rows), last[2], last[7], "%.2f%%" % chg,
                     "minlow=%.2f%%" % trig))

    with open(os.path.join(outdir, "日线.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in allrows:
            w.writerow(r)

    for d in diag:
        print("|".join(str(x) for x in d))
    print("WROTE", os.path.join(outdir, "日线.csv"), "rows", len(allrows), "at", now)

    # 快照
    snap_syms = ["sh000001", "hkHSI", "us.NDX", "us.INX", "us.DJI", "kr005930", "kr000660",
                 "sh588170", "sz158050", "sh515050", "sz159107", "sh513310", "sz159169",
                 "sz159577", "sh513650", "sz159659", "sh513950", "sh563020",
                 "sh601398", "sh601939", "sz399001", "sz399106"]
    snap = curl("https://qt.gtimg.cn/q=" + ",".join(snap_syms))
    open(os.path.join(raw, "snap.txt"), "w", encoding="utf-8").write(snap)
    print("SNAP_LEN", len(snap))


if __name__ == "__main__":
    main()
