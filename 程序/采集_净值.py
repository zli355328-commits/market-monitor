"""ETF 单位净值抓取（天天基金 f10 lsjz）。保留原始返回与抓取时刻。

用法: python 程序/采集_净值.py --date 2026-11-02
"""
import argparse
import json
import os
import re
import subprocess
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def curl(url, timeout=25):
    r = subprocess.run(["curl", "-s", "--max-time", str(timeout),
                        "-H", "Referer: http://fundf10.eastmoney.com/",
                        "-H", "User-Agent: Mozilla/5.0", url],
                       capture_output=True, text=True, encoding="utf-8", errors="ignore")
    return r.stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    args = ap.parse_args()
    cfg = json.loads(open(os.path.join(ROOT, "监测标的.json"), encoding="utf-8-sig").read())
    funds = [c for c in cfg["自选代码"] if c not in ("601398", "601939")]
    outdir = os.path.join(ROOT, args.date)
    raw = os.path.join(outdir, "_raw")
    os.makedirs(raw, exist_ok=True)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    res = {}
    for code in funds:
        url = ("https://api.fund.eastmoney.com/f10/lsjz?fundCode=%s&pageIndex=1&pageSize=8&_=%d"
               % (code, int(time.time() * 1000)))
        t = curl(url)
        open(os.path.join(raw, "nav_%s.txt" % code), "w", encoding="utf-8").write(t)
        m = re.search(r"\{.*\}", t, re.S)
        if not m:
            print("NAV_FAIL", code, t[:60])
            continue
        try:
            d = json.loads(m.group(0))
        except Exception:
            print("NAV_PARSE_FAIL", code)
            continue
        items = d.get("Data", {}).get("LSJZList", [])
        res[code] = items
        for it in items[:3]:
            print(code, it.get("FSRQ"), it.get("DWJZ"), it.get("JZZZL"))
        time.sleep(0.6)
    json.dump({"抓取时间": now, "数据": res},
              open(os.path.join(raw, "nav_all.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print("NAV_DONE", len(res), "at", now)


if __name__ == "__main__":
    main()
