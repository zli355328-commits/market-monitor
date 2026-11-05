"""由 _raw/nav_all.json + 日线.csv 生成 产品与净值.csv（C009 修正版：全参数化）。

用法:
  python 程序/生成_产品净值.py --date 2026-11-03
  # 自测另一目标日输出位置（不覆盖历史包）：--date 2026-11-02 --out <临时目录>

修正要点（C009 第2项）：
  - 去掉写死 DATE/字段名/备注日期，全部由 --date 驱动。
  - 表头"<date>收盘价"动态生成；说明文字按净值日与市价日是否同日动态判定。
  - --out 可指定输出目录，便于测试另一目标日而不触写历史包。
  - 不把旧净值说明改成新数据；META 缓存的产品身份信息不含当日行情数值。
"""
import argparse
import csv
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 产品身份/规则缓存（首次核验后缓存，有变更公告才更新；不含当日行情数值）
META = {
    "588170": ("科创半导体ETF华夏", "上交所", "上证科创板半导体材料设备主题指数", "未取得",
               "未核验（950125.SH 已停用，见 R011）", "T+1",
               "419.46亿元(2026-09-30，媒体转引，沿用缓存)", "前十大合计73.59%(2026-09-30)"),
    "158050": ("创业板算力ETF易方达", "深交所", "创业板算力基础设施指数", "970083.SZ",
               "两家媒体一致，未见指数公司原始文件", "T+1", "未取得", "2026-09-18 上市"),
    "515050": ("通信ETF华夏", "上交所", "中证5G通信主题指数", "931079.CSI",
               "沿用缓存，本轮未独立核验", "T+1", "未取得", ""),
    "159107": ("创业板软件ETF富国", "深交所", "创业板软件指数", "399264.SZ",
               "已核验（C006 + 天天基金基本资料一致）", "T+1", "未取得",
               "成立2025-09-10；50只成分；前十大合计50.19%(2026-09-30)"),
    "513310": ("中韩半导体ETF华泰柏瑞", "上交所", "中证韩交所中韩半导体指数", "未取得",
               "未核验", "T+0(跨境ETF)", "约95.44亿元(2026-10-19，媒体转引，沿用缓存)",
               "成立日2022-11-02（R010）"),
    "159169": ("恒生生物科技ETF广发", "深交所", "恒生生物科技指数", "HSBIO.HI",
               "沿用缓存，本轮未独立核验", "T+0(跨境ETF)", "1.27亿元(2026-09-18口径，媒体转引)",
               "管理费0.50%/年"),
    "159577": ("美国50ETF汇添富", "深交所", "MSCI USA 50 Index", "—",
               "境外指数，代码口径未取得", "T+0(跨境ETF)", "未取得", ""),
    "513650": ("标普500ETF南方", "上交所", "标准普尔500指数", "SPX",
               "通用代码，未独立核验", "T+0(跨境ETF)", "未取得", ""),
    "159659": ("纳斯达克100ETF招商", "深交所", "纳斯达克100指数", "NDX",
               "通用代码，未独立核验", "T+0(跨境ETF)", "未取得", ""),
    "513950": ("恒生红利ETF富国", "上交所", "恒生港股通红利低波动指数", "HSHYLV",
               "沿用缓存，本轮未独立核验", "T+0(跨境ETF)", "29.41亿元(2026-09-17口径，媒体转引)",
               "最近除息 2026-10-22（已过）"),
    "563020": ("红利低波ETF易方达", "上交所", "中证红利低波动指数", "H30269.CSI",
               "沿用缓存，本轮未独立核验", "T+1", "未取得", "最近除息 2026-09-11（已过）"),
}

BANKS = [
    ("601939", "建设银行", "上交所", "2026-08-29 中期分红预案每10股2.01元，进度=预案，无除权除息日"),
    ("601398", "工商银行", "上交所", "最近一次分红已实施：登记日2026-10-20、除权除息日2026-10-21、每股0.1511元（R008）；董事会通过优先股'工行优1'股息属优先股、不影响普通股除权"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--out", default=None, help="输出目录，默认 ROOT/<date>")
    ap.add_argument("--seed", default=None, help="净值源目录，默认 ROOT/<date>")
    args = ap.parse_args()
    DATE = args.date
    OUT = args.out or os.path.join(ROOT, DATE)
    SEED = args.seed or OUT
    os.makedirs(OUT, exist_ok=True)

    nav = json.load(open(os.path.join(SEED, "_raw", "nav_all.json"), encoding="utf-8"))["数据"]
    close = {}
    for r in csv.DictReader(open(os.path.join(SEED, "日线.csv"), encoding="utf-8-sig")):
        if r["日期"] == DATE:
            close[r["代码"]] = r["收盘"]
    header = ["代码", "名称", "交易所", "跟踪指数(官方标的)", "指数代码", "指数代码状态",
              "回转交易规则", "最新单位净值", "净值所属日", "净值日涨跌%", "%s收盘价" % DATE,
              "市价日期", "相对最近已披露净值的价差%", "价差计算式", "价差可用性说明",
              "规模/份额(日期)", "来源", "备注"]
    rows = []
    for code, m in META.items():
        items = nav.get(code, [])
        if not items:
            continue
        it = items[0]
        nv, navday = it["DWJZ"], it["FSRQ"]
        px = close.get(code, "")
        diff = (float(px) / float(nv) - 1) * 100 if px else None
        same = (navday == DATE)
        note = ("同日净值且同日市价，可作参考；净值首次披露时刻未取得（延续 R013），亲自抓取时刻见 _raw/nav_all.json" if same
                else "非同日（净值日%s、市价日%s）：为相对最近已披露净值的价差，含对海外市场/时点的预期成分，不能单独证明低估、溢价或套利收敛" % (navday, DATE))
        rows.append([code, m[0], m[1], m[2], m[3], m[4], m[5], nv, navday, it.get("JZZZL", ""),
                     px, DATE if px else "", ("%+.2f" % diff) if diff is not None else "",
                     ("%s/%s-1" % (px, nv)) if px else "",
                     note, m[6], "天天基金 f10 lsjz 净值接口", m[7]])
    for code, name, ex, note in BANKS:
        rows.append([code, name, ex, "—", "—", "—", "T+1", "不适用（股票，无单位净值）", "—", "—",
                     close.get(code, ""), DATE, "不适用", "—", "—", "见市场背景/更新.md", "腾讯行情", note])
    dest = os.path.join(OUT, "产品与净值.csv")
    with open(dest, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            w.writerow(r)
    for r in rows:
        print(r[0], r[7], r[8], r[10], r[12])
    print("WROTE", dest, "rows", len(rows))


if __name__ == "__main__":
    main()
