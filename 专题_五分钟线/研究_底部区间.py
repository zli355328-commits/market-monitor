"""Daily exploratory bottom-zone study; no monitoring/trading configuration changes."""
import csv
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DAILY = ROOT.parent / '2026-11-04' / '日线.csv'


def load(code):
    result = []
    with DAILY.open(encoding='utf-8-sig', newline='') as stream:
        for row in csv.DictReader(stream):
            if row['代码'] != code:
                continue
            factor = 3 if code == '588170' and row['日期'] < '2026-07-06' else 1
            result.append({'day': row['日期'],
                           **{key: float(row[source]) / factor for key, source in
                              [('o', '开盘'), ('h', '最高'), ('l', '最低'), ('c', '收盘')]},
                           'v': float(row['成交量'])})
    return sorted(result, key=lambda row: row['day'])


def mean(values):
    return statistics.mean(values)


def summarize(rows):
    if not rows:
        return {'n': 0}
    returns = [row['return5'] for row in rows]
    return {'n': len(rows), 'profit_n': sum(value > 0 for value in returns),
            'mean5_pct': round(mean(returns) * 100, 2),
            'median5_pct': round(statistics.median(returns) * 100, 2),
            'worst5_pct': round(min(returns) * 100, 2),
            'best5_pct': round(max(returns) * 100, 2),
            'up8_n': sum(row['mfe'] >= .08 for row in rows),
            'down5_n': sum(row['mae'] <= -.05 for row in rows),
            'up8_and_down5_n': sum(row['mfe'] >= .08 and row['mae'] <= -.05 for row in rows),
            'median_mae_pct': round(statistics.median(row['mae'] for row in rows) * 100, 2),
            'median_mfe_pct': round(statistics.median(row['mfe'] for row in rows) * 100, 2),
            'return1': round(mean(row['return1'] for row in rows) * 100, 2),
            'return3': round(mean(row['return3'] for row in rows) * 100, 2)}


def spaced(rows):
    selected = []
    last = -100
    for row in rows:
        if row['index'] >= last + 5:
            selected.append(row)
            last = row['index']
    return selected


def main():
    bars = load('588170')
    market = {row['day']: row for row in load('000001')}
    records = []
    for i in range(21, len(bars) - 5):
        row = bars[i]
        past = bars[i - 19:i + 1]
        entry = bars[i + 1]['o']
        end = i + 5
        ret5 = row['c'] / bars[i - 5]['c'] - 1
        draw20 = row['c'] / max(old['h'] for old in past) - 1
        low5 = min(old['l'] for old in bars[i - 4:i + 1])
        previous5 = min(old['l'] for old in bars[i - 9:i - 4])
        low_slow = low5 / previous5 - 1
        close_pos = (row['c'] - row['l']) / (row['h'] - row['l']) if row['h'] > row['l'] else .5
        # Do not compare turnover across the share split.
        vol_valid = not (bars[i - 19]['day'] < '2026-07-06' <= row['day'])
        volume_ratio = row['v'] / mean(old['v'] for old in bars[i - 20:i]) if vol_valid else None
        m = market[row['day']]
        market5 = m['c'] / market[bars[i - 5]['day']]['c'] - 1
        record = {
            'day': row['day'], 'index': i, 'entry_day': bars[i + 1]['day'],
            'entry': entry, 'exit5_day': bars[end]['day'],
            'ret5': ret5, 'draw20': draw20, 'low_change': low_slow,
            'close_pos': close_pos, 'volume_ratio': volume_ratio,
            'weak': row['c'] < mean(old['c'] for old in past),
            'market5': market5,
            # Entry day cannot be exited under T+1, so first feasible close is i+2.
            'return1': bars[i + 2]['c'] / entry - 1 - .002,
            'return3': bars[i + 3]['c'] / entry - 1 - .002,
            'return5': bars[end]['c'] / entry - 1 - .002,
            'mfe': max(old['h'] for old in bars[i + 2:end + 1]) / entry - 1,
            'mae': min(old['l'] for old in bars[i + 1:end + 1]) / entry - 1,
            'entryday_up8': bars[i + 1]['h'] / entry - 1 >= .08,
        }
        records.append(record)

    filters = {
        '所有弱势日': lambda r: r['weak'],
        '深回撤20%': lambda r: r['weak'] and r['draw20'] <= -.2,
        '近5日急跌10%': lambda r: r['weak'] and r['ret5'] <= -.1,
        '深跌且仍急跌': lambda r: r['weak'] and r['draw20'] <= -.2 and r['ret5'] <= -.1,
        '深跌但跌速放缓': lambda r: r['weak'] and r['draw20'] <= -.2 and r['ret5'] > -.1,
        '深跌且5日低点下移不足3%': lambda r: r['weak'] and r['draw20'] <= -.2 and r['low_change'] >= -.03,
        '深跌收在日内上半部': lambda r: r['weak'] and r['draw20'] <= -.2 and r['close_pos'] >= .5,
        '深跌收在日内下半部': lambda r: r['weak'] and r['draw20'] <= -.2 and r['close_pos'] < .5,
        '深跌市场5日不跌': lambda r: r['weak'] and r['draw20'] <= -.2 and r['market5'] >= 0,
        '深跌市场5日跌': lambda r: r['weak'] and r['draw20'] <= -.2 and r['market5'] < 0,
        '深跌且相对缩量': lambda r: r['weak'] and r['draw20'] <= -.2 and r['volume_ratio'] is not None and r['volume_ratio'] < 1,
        '深跌且相对放量': lambda r: r['weak'] and r['draw20'] <= -.2 and r['volume_ratio'] is not None and r['volume_ratio'] >= 1,
    }
    panels = {}
    for name, keep in filters.items():
        sample = [r for r in records if keep(r)]
        panels[name] = {
            'all': summarize(sample), 'spaced5': summarize(spaced(sample)),
            'early': summarize([r for r in sample if r['day'] < '2026-07-01']),
            'late': summarize([r for r in sample if r['day'] >= '2026-07-01']),
            'since9': summarize([r for r in sample if r['day'] >= '2026-09-01']),
            'dates_spaced': [r['day'] for r in spaced(sample)],
        }
    thresholds = []
    for threshold in [.15, .20, .25, .30]:
        sample = [r for r in records if r['weak'] and r['draw20'] <= -threshold]
        thresholds.append({'drawdown': threshold, 'all': summarize(sample), 'spaced5': summarize(spaced(sample))})
    result = {'input': str(DAILY), 'first': bars[0]['day'], 'last': bars[-1]['day'],
              'last_signal_with_full5': records[-1]['day'], 'panels': panels,
              'thresholds': thresholds}
    (ROOT / '研究_底部区间结果.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    with (ROOT / '研究_底部区间逐日.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
