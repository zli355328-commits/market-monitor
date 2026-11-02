"""Read-only daily package validation; accepts optional --file for diagnostics."""
import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def check(target, path):
    errors, warnings = [], []
    if not path.is_file():
        return {'日期':target,'错误':['日线文件不存在'],'警告':[],'行数':0}
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        required = {'代码','日期','昨收','开盘','最高','最低','收盘','成交量','成交额','成交量单位','来源'}
        missing = required - set(reader.fieldnames or [])
        if missing:
            return {'日期':target,'错误':['缺字段:'+','.join(sorted(missing))],'警告':[],'行数':0}
        rows = list(reader)
    registry = json.loads((ROOT/'监测标的.json').read_text(encoding='utf-8-sig'))
    expected = set(registry['自选代码']) | {registry['共同参照']}
    if target < registry['生效日期']:
        expected.discard('159107')
    counts, groups = Counter(), defaultdict(list)
    for row in rows:
        code, day = row['代码'], row['日期']
        tag = code+' '+day
        counts[(code,day)] += 1
        try:
            date.fromisoformat(day)
            groups[code].append(day)
            if day > target:
                errors.append(tag+' 超过目标日期')
            vals = [float(row[k]) for k in ['开盘','最高','最低','收盘','成交量','成交额']]
            if not all(math.isfinite(v) for v in vals):
                raise ValueError('非有限值')
            o,h,l,c,v,a = vals
            if not 0 < l <= min(o,c) <= max(o,c) <= h:
                errors.append(tag+' OHLC不一致')
            if v < 0 or a < 0:
                errors.append(tag+' 负成交量或金额')
            if row['昨收']:
                prev = float(row['昨收'])
                if not math.isfinite(prev) or prev <= 0:
                    errors.append(tag+' 昨收无效')
            if row['成交量单位'] != '手':
                warnings.append(tag+' 成交量单位非约定手，核验换算')
            if not row['来源'].strip():
                warnings.append(tag+' 来源为空')
        except (ValueError, TypeError):
            errors.append(tag+' 日期或数值无效')
    errors += [f'{k} 重复记录' for k,n in counts.items() if n > 1]
    errors += [c+' 缺标的' for c in sorted(expected-set(groups))]
    for c in sorted(expected & set(groups)):
        if max(groups[c]) != target:
            warnings.append(c+' 最新日期非目标日，请核验休市/停牌/缺失')
    if not rows:
        errors.append('空数据表')
    return {'日期':target,'行数':len(rows),'错误':errors,'警告':warnings,'范围':'仅结构与表内一致性；未认证来源、交易日历、复权及消息真实性，未改原文件'}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('日期', type=lambda s: date.fromisoformat(s).isoformat())
    parser.add_argument('--file', type=Path)
    args = parser.parse_args()
    result = check(args.日期, args.file or ROOT/args.日期/'日线.csv')
    print(json.dumps(result,ensure_ascii=False))
    return 1 if result['错误'] else 0

if __name__ == '__main__':
    raise SystemExit(main())
