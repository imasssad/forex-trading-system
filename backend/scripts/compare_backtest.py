import os, sys, copy, json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from backtest.engine import BacktestEngine
from config.settings import DEFAULT_CONFIG
from database import db as database

pair = 'EUR_USD'
start = '2024-01-01'
end = '2024-12-31'

out_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
os.makedirs(out_dir, exist_ok=True)

# Load config from DB (overrides defaults if present)
cfg = copy.deepcopy(DEFAULT_CONFIG)
cfg = database.load_settings_to_config(cfg)

# Baseline backtest (server config)
engine_base = BacktestEngine(config=cfg)
res_base = engine_base.run(pair=pair, start_date=start, end_date=end)

# Modified backtest (overrides)
cfg_mod = copy.deepcopy(cfg)
cfg_mod.risk.ATR_MULTIPLIER = 3.0
cfg_mod.risk.RISK_PER_TRADE_PERCENT = 2.0
cfg_mod.risk.RISK_REWARD_RATIO = 2.5
engine_mod = BacktestEngine(config=cfg_mod)
res_mod = engine_mod.run(pair=pair, start_date=start, end_date=end)

# Save compare JSON
report = {'pair': pair, 'start': start, 'end': end, 'baseline': res_base, 'modified': res_mod}
json_path = os.path.join(out_dir, f'backtest_compare_{pair}_{start}.json')
with open(json_path, 'w') as f:
    json.dump(report, f, indent=2)

# Build a simple SVG comparing equity curves
def make_svg(baseline_curve, modified_curve, pair_label):
    W, H = 900, 360
    PAD = 60
    def pts(curve):
        vals = [p['equity'] for p in curve]
        dates = [p['date'] for p in curve]
        mn, mx = min(vals), max(vals)
        rng = mx - mn if mx != mn else 1
        out = []
        for i, v in enumerate(vals):
            x = PAD + (i / max(1, len(vals)-1)) * (W - PAD*2)
            y = PAD + (1 - (v - mn) / rng) * (H - PAD*2)
            out.append((x,y, dates[i], v))
        return out, mn, mx

    bpts, bmin, bmax = pts(baseline_curve)
    mpts, mmin, mmax = pts(modified_curve)
    gmin = min(bmin, mmin)
    gmax = max(bmax, mmax)

    def path(pts):
        return ' '.join(f'{x:.1f},{y:.1f}' for x,y,_,_ in pts)

    svg = [f'<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg">']
    svg.append(f'<rect x="0" y="0" width="{W}" height="{H}" fill="#071427" />')
    # y grid
    for t in range(5):
        y = PAD + t*(H-2*PAD)/4
        val = gmax - (t*(gmax-gmin)/4)
        svg.append(f'<line x1="{PAD}" y1="{y:.1f}" x2="{W-PAD}" y2="{y:.1f}" stroke="#0f2a33" stroke-width="1" />')
        svg.append(f'<text x="{PAD-10}" y="{y+4:.1f}" font-size="12" fill="#9aa6b2" text-anchor="end">${val:,.0f}</text>')
    # paths
    svg.append(f'<polyline fill="none" stroke="#22c55e" stroke-width="2.5" points="{path(bpts)}" opacity="0.95" />')
    svg.append(f'<polyline fill="none" stroke="#ff6b6b" stroke-width="2.5" points="{path(mpts)}" opacity="0.95" />')
    # legend + title
    svg.append(f'<circle cx="{W-PAD-200}" cy="{PAD-20}" r="6" fill="#22c55e" />')
    svg.append(f'<text x="{W-PAD-186}" y="{PAD-15}" font-size="12" fill="#9aa6b2">Server config</text>')
    svg.append(f'<circle cx="{W-PAD-86}" cy="{PAD-20}" r="6" fill="#ff6b6b" />')
    svg.append(f'<text x="{W-PAD-72}" y="{PAD-15}" font-size="12" fill="#9aa6b2">Overrides (ATR×3, Risk 2%)</text>')
    svg.append(f'<text x="{PAD}" y="30" font-size="16" fill="#e6eef3">Equity Curve — {pair_label} — {start}</text>')
    # x labels (start/mid/end)
    def xlabels(pts):
        if not pts: return []
        idxs = [0, len(pts)//2, len(pts)-1]
        out = []
        for ii in idxs:
            try: lab = pts[ii][2].split('T')[0]
            except: lab = pts[ii][2]
            out.append((pts[ii][0], lab))
        return out
    for x,lab in xlabels(bpts):
        svg.append(f'<text x="{x:.1f}" y="{H-12:.1f}" font-size="12" fill="#9aa6b2" text-anchor="middle">{lab}</text>')
    svg.append('</svg>')
    return '\n'.join(svg)

svg_content = make_svg(res_base['equity_curve'], res_mod['equity_curve'], pair.replace('_','/'))
svg_path = os.path.join(out_dir, f'backtest_compare_{pair}_{start}.svg')
with open(svg_path, 'w', encoding='utf-8') as f:
    f.write(svg_content)

print(json.dumps({
    'json': json_path,
    'svg': svg_path,
    'baseline_total_trades': res_base['total_trades'],
    'modified_total_trades': res_mod['total_trades'],
    'baseline_net': res_base['net_profit'],
    'modified_net': res_mod['net_profit'],
    'baseline_max_dd': res_base['max_drawdown'],
    'modified_max_dd': res_mod['max_drawdown'],
    'sample_baseline_trades': res_base['trades'][:8],
    'sample_modified_trades': res_mod['trades'][:8],
}, indent=2))
