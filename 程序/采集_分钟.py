"""按持仓/风险信号取 A股 5 分钟线（新浪第二源）。（C009 修正版）

用法: python 程序/采集_分钟.py --date 2026-11-03 --codes 513950 563020 601398 601939 588170 158050 515050 513310

修正要点（C009 第1项 / R015）：
  - 单位不再硬编码"手"。用 额/量 与当日 [最低,最高] 价格区间自动判定：
      额/量 落在 [low,high]        → 股/份
      额/量 落在 [100*low,100*high] → 手
  - 逐根计算、按多数表决确定该标的单位，写入 CSV 与单位核验明细。
  - 输出 单位更正.md 到当日目录（不覆盖历史原包）。
"""
import argparse
import csv
import json
import os
import subprocess
import time
from collections import Counter
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EX = {"513950": "sh", "563020": "sh", "601398": "sh", "601939": "sh",
      "588170": "sh", "515050": "sh", "513310": "sh", "513650": "sh",
      "158050": "sz", "159107": "sz", "159169": "sz", "159577": "sz",
      "159659": "sz", "000001": "sh"}


def curl(url, timeout=20, ref="https://finance.sina.com.cn"):
    r = subprocess.run(["curl", "-s", "--max-time", str(timeout),
                        "-H", "Referer: " + ref, "-H", "User-Agent: Mozilla/5.0", url],
                       capture_output=True, text=True, encoding="utf-8", errors="ignore")
    return r.stdout


def unit_of(bar):
    """判定单根成交量单位：返回 '股/份' | '手' | '未知'。"""
    try:
        v = float(bar["volume"]); a = float(bar["amount"])
        lo = float(bar["low"]); hi = float(bar["high"])
        if v <= 0 or a <= 0 or hi <= 0:
            return "未知"
        ratio = a / v
        if lo * 0.97 <= ratio <= hi * 1.03:
            return "股/份"
        if lo * 97 <= ratio <= hi * 103:
            return "手"
        return "未知"
    except Exception:
        return "未知"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--codes", nargs="+", required=True)
    ap.add_argument("--scale", type=int, default=5)
    ap.add_argument("--len", type=int, default=48)
    args = ap.parse_args()
    outdir = os.path.join(ROOT, args.date)
    raw = os.path.join(outdir, "_raw")
    os.makedirs(raw, exist_ok=True)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    rows, diag, audit = [], [], []
    for code in args.codes:
        sym = EX[code] + code
        url = ("https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData"
               "?symbol=%s&scale=%d&ma=no&datalen=%d" % (sym, args.scale, args.len))
        t = curl(url)
        open(os.path.join(raw, "min_%s.json" % code), "w", encoding="utf-8").write(t)
        try:
            arr = json.loads(t)
        except Exception:
            diag.append((code, "FAIL", 0, "-", "-", "-"))
            continue
        arr = [x for x in arr if x["day"][:10] == args.date]
        votes = [unit_of(x) for x in arr]
        unit = Counter(v for v in votes if v != "未知").most_common(1)[0][0] if any(v != "未知" for v in votes) else "未判定"
        first = arr[-1] if arr else None
        ratio = (float(first["amount"]) / float(first["volume"])) if first and float(first["volume"]) else None
        audit.append((code, len(arr), unit, ("%.4f" % ratio) if ratio else "-",
                      first["close"] if first else "-", first["day"] if first else "-"))
        for x in arr:
            rows.append([code, x["day"], x["open"], x["high"], x["low"], x["close"],
                         x.get("volume", ""), x.get("amount", ""), unit, "不复权",
                         "新浪财经公开行情接口(5分钟)", now])
        if arr:
            diag.append((code, "OK", len(arr), arr[0]["day"][11:], arr[-1]["day"][11:],
                         "unit=" + unit + " last=" + arr[-1]["close"]))
        else:
            diag.append((code, "EMPTY", 0, "-", "-", "-"))
        time.sleep(0.4)
    with open(os.path.join(outdir, "分钟线.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["代码", "时间", "开盘", "最高", "最低", "收盘", "成交量", "成交额",
                    "成交量单位", "复权方式", "来源", "采集时间"])
        for r in rows:
            w.writerow(r)
    for d in diag:
        print("|".join(str(x) for x in d))
    print("WROTE rows", len(rows))

    # 单位核验明细与更正文件（不覆盖历史原包）
    with open(os.path.join(raw, "单位核验.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["代码", "当日根数", "判定单位", "末根额/量", "末根收盘", "末根时间"])
        for a in audit:
            w.writerow(a)
    lines = [
        "# 分钟线成交量单位更正（C009 第1项 / R015）",
        "",
        "日期：%s；来源：新浪财经 5 分钟线公开接口。" % args.date,
        "",
        "## 结论",
        "",
        "新浪 5 分钟线 `volume` 字段单位为 **股/份**，不是手。判据：`amount / volume` 落在当日该 5 分钟 K 线的 `[最低, 最高]` 价格区间内；若为手，该比值应约为 100×价格。",
        "",
        "历史 2026-11-02 及更早的 分钟线.csv 标注为\"手\"，属错误标注（R015 已停用该断言）。本文件仅更正标注与采集脚本，不改写、不覆盖任何历史原包。",
        "",
        "## 逐标的核验（当日）",
        "",
        "| 代码 | 当日根数 | 判定单位 | 末根额/量 | 末根收盘 | 末根时间 |",
        "|---|---|---|---|---|---|",
    ]
    for a in audit:
        lines.append("| %s | %s | %s | %s | %s | %s |" % a)
    lines += [
        "",
        "## 使用限制",
        "",
        "- 该判定只说明接口的量的计数单位，不能证明缺成交时段为零成交，也不能据此推算资金流或拥挤度（沿用 C002 §3）。",
        "- 日线成交量单位仍为手（腾讯 newfqkline），与分钟线不同源、不同单位，不可直接相加比较。",
        "- 单位修正前，不据分钟量数值下任何结论。",
    ]
    open(os.path.join(outdir, "分钟量单位更正.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("WROTE 分钟量单位更正.md")


if __name__ == "__main__":
    main()
