"""Historical exploratory study. Does not change monitoring or trading rules."""
import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / '五分钟线_连续_2026-05-06至11-05.csv'
EVENTS = {'20260721', '20261104'}


def load():
    groups = defaultdict(lambda: defaultdict(list))
    keys = Counter()
    with SOURCE.open(encoding='utf-8-sig', newline='') as stream:
        for raw in csv.DictReader(stream):
            code, day, time = raw['代码'], raw['日期'], raw['时间HHMM']
            keys[code, day, time] += 1
            factor = 3 if code == '588170' and day < '20260706' else 1
            row = {'time': time}
            for source, field in [('开盘', 'o'), ('最高', 'h'), ('最低', 'l'), ('收盘', 'c')]:
                row[field] = float(raw[source]) / factor
            groups[code][day].append(row)
    for daily in groups.values():
        for bars in daily.values():
            bars.sort(key=lambda row: row['time'])
    assert max(keys.values()) == 1
    return groups


def descriptors(groups, days, day_index, signal, end):
    day = days[day_index]
    bars = groups['588170'][day]
    low = min(row['l'] for row in bars[:signal + 1])
    initial = bars[signal]['c']
    test = bars[signal + 1:end + 1]
    retention = (min(row['l'] for row in test) - low) / (initial - low)
    pullback = any(bars[j]['c'] < bars[j - 1]['c'] for j in range(signal + 1, end + 1))
    sync = all(groups[code][day][end]['c'] > groups[code][day][signal]['c']
               for code in ['000001', '000688'])
    prior5 = None
    drawdown20 = None
    if day_index >= 5:
        prior5 = (groups['588170'][days[day_index - 1]][-1]['c'] /
                  groups['588170'][days[day_index - 6]][-1]['c'] - 1) if day_index >= 6 else None
    if day_index >= 20:
        peak = max(row['h'] for old_day in days[day_index - 20:day_index]
                   for row in groups['588170'][old_day])
        drawdown20 = groups['588170'][days[day_index - 1]][-1]['c'] / peak - 1
    context_known = prior5 is not None and drawdown20 is not None
    severe = context_known and (prior5 <= -.10 or drawdown20 <= -.20)
    return {
        'day': day, 'signal': bars[signal]['time'], 'test_end': bars[end]['time'],
        'signal_index': signal, 'end_index': end,
        'retention': retention, 'pullback': pullback, 'sync': sync,
        'push': bars[end]['c'] > initial,
        'hold_break': min(row['l'] for row in test) >= max(row['h'] for row in bars[:6]),
        'context_known': context_known, 'severe': severe,
        'prior5': prior5, 'drawdown20': drawdown20,
    }


def outcomes(groups, days, index, entry_bar):
    day = days[index]
    bars = groups['588170'][day]
    entry = bars[entry_bar]['o']
    result = {'entry': entry, 'entry_time': bars[entry_bar]['time'],
              'same_close': bars[-1]['c'] / entry - 1,
              'same_adverse': min(row['l'] for row in bars[entry_bar:]) / entry - 1}
    for distance in [1, 3, 5]:
        if index + distance >= len(days):
            continue
        future = groups['588170'][days[index + distance]]
        if distance == 1:
            result['next_open'] = future[0]['o'] / entry - 1
        if len(future) == 48:
            result[f'close{distance}'] = future[-1]['c'] / entry - 1
    return result


def summary(rows, field, cost=.002):
    values = [row[field] - cost for row in rows if field in row]
    if not values:
        return {'n': 0}
    return {'n': len(values), 'positive': sum(value > 0 for value in values),
            'mean_pct': round(statistics.mean(values) * 100, 3),
            'median_pct': round(statistics.median(values) * 100, 3),
            'worst_pct': round(min(values) * 100, 3),
            'best_pct': round(max(values) * 100, 3)}


def main():
    groups = load()
    days = sorted(groups['588170'])
    records = []
    # Freeze the earlier first-30-minute breakout anchor. Three bars = 15 trading minutes.
    for index, day in enumerate(days):
        bars = groups['588170'][day]
        if len(bars) != 48:
            continue
        ceiling = max(row['h'] for row in bars[:6])
        signal = next((j for j in range(6, 44) if bars[j]['c'] > ceiling), None)
        if signal is None:
            continue
        end = signal + 3
        record = descriptors(groups, days, index, signal, end)
        record.update(outcomes(groups, days, index, end + 1))
        record['immediate_next_open'] = outcomes(groups, days, index, signal + 1).get('next_open')
        records.append(record)

    selectors = {
        '全部回升': lambda row: True,
        '守住突破位置': lambda row: row['hold_break'],
        '守住且继续推高': lambda row: row['hold_break'] and row['push'],
        '守住推高且两指数同步': lambda row: row['hold_break'] and row['push'] and row['sync'],
        '回落后保留一半涨幅': lambda row: row['pullback'] and row['retention'] >= .5,
        '回落保留一半且推高': lambda row: row['pullback'] and row['retention'] >= .5 and row['push'],
    }
    result = {'audit': {'days': len(days), 'full_days': sum(len(a) == 48 for a in groups['588170'].values()),
                        'last_date': days[-1], 'last_bars': len(groups['588170'][days[-1]]),
                        'split': 'pre-20260706 ETF prices / 3, raw files unchanged'}, 'panels': {}}
    for scope, predicate in [('全部', lambda r: True),
                             ('深跌背景', lambda r: r['severe']),
                             ('非深跌背景', lambda r: r['context_known'] and not r['severe']),
                             ('剔除两次已知大涨', lambda r: r['day'] not in EVENTS),
                             ('9月至今', lambda r: r['day'] >= '20260901')]:
        panel = {}
        for name, select in selectors.items():
            selected = [row for row in records if predicate(row) and select(row)]
            panel[name] = {field: summary(selected, field)
                           for field in ['same_close', 'next_open', 'close1', 'close3', 'close5']}
            panel[name]['dates'] = [row['day'] for row in selected]
        result['panels'][scope] = panel
    result['cost_sensitivity'] = {
        name: {str(cost): summary([r for r in records if select(r)], 'next_open', cost)
               for cost in [0, .002, .005]} for name, select in selectors.items()}
    # Entry delay on the same days, so selection and later entry do not get conflated.
    result['delay'] = {name: {
        'immediate': summary([r for r in records if select(r) and r.get('immediate_next_open') is not None],
                             'immediate_next_open'),
        'delayed': summary([r for r in records if select(r)], 'next_open')}
        for name, select in selectors.items()}
    # Fixed 1/2/3/6-bar windows and 25/50/75% retention are sensitivity descriptions, not tuning.
    sensitivity = []
    for length in [1, 2, 3, 6]:
        for fraction in [.25, .5, .75]:
            selected = []
            for index, day in enumerate(days):
                bars = groups['588170'][day]
                if len(bars) != 48:
                    continue
                ceiling = max(row['h'] for row in bars[:6])
                signal = next((j for j in range(6, 47 - length) if bars[j]['c'] > ceiling), None)
                if signal is None:
                    continue
                end = signal + length
                row = descriptors(groups, days, index, signal, end)
                if row['pullback'] and row['retention'] >= fraction and row['push']:
                    row.update(outcomes(groups, days, index, end + 1))
                    selected.append(row)
            sensitivity.append({'bars': length, 'retention': fraction,
                                'next_open': summary(selected, 'next_open'),
                                'excluding_events': summary([r for r in selected if r['day'] not in EVENTS], 'next_open')})
    result['sensitivity'] = sensitivity
    (ROOT / '研究_卖压测试结果.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    with (ROOT / '研究_卖压测试逐次.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=sorted(set().union(*(row.keys() for row in records))))
        writer.writeheader()
        writer.writerows(records)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
