import json, os
from PIL import Image, ImageDraw, ImageFont

in_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'backtest_compare_EUR_USD_2024-01-01.json')
out_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'backtest_compare_EUR_USD_2024-01-01.png')

with open(in_path, 'r', encoding='utf-8') as f:
    report = json.load(f)

b_curve = report['baseline']['equity_curve']
m_curve = report['modified']['equity_curve']

# Image settings
W, H = 1200, 600
PAD = 80
bg = (7,20,39)
grid = (20,50,60)
text_col = (154,166,178)
col_base = (34,197,94)   # green
col_mod = (255,107,107)  # red

img = Image.new('RGB', (W, H), bg)
d = ImageDraw.Draw(img)
font = ImageFont.load_default()

# get combined min/max
vals_b = [p['equity'] for p in b_curve]
vals_m = [p['equity'] for p in m_curve]
gmin = min(min(vals_b), min(vals_m))
gmax = max(max(vals_b), max(vals_m))
if gmax == gmin:
    gmax += 1

# helper to convert value to coords
def to_xy(i, v, curve):
    n = len(curve)
    x = PAD + (i / max(1, n-1)) * (W - PAD*2)
    y = PAD + (1 - (v - gmin) / (gmax - gmin)) * (H - PAD*2)
    return (x, y)

# draw horizontal grid + labels
for t in range(5):
    y = PAD + t*(H-2*PAD)/4
    d.line([(PAD, y), (W-PAD, y)], fill=grid)
    val = gmax - t*(gmax-gmin)/4
    d.text((PAD-10, y-6), f'${val:,.0f}', font=font, fill=text_col, anchor='rm')

# draw baseline polyline
pts_b = [to_xy(i, p['equity'], b_curve) for i, p in enumerate(b_curve)]
d.line(pts_b, fill=col_base, width=3)
# draw modified polyline
pts_m = [to_xy(i, p['equity'], m_curve) for i, p in enumerate(m_curve)]
d.line(pts_m, fill=col_mod, width=3)

# legend and title
d.rectangle([W-PAD-320, PAD-46, W-PAD-20, PAD-10], fill=(7,18,28))
d.ellipse((W-PAD-300-6, PAD-36, W-PAD-300+6, PAD-24), fill=col_base)
d.text((W-PAD-300+16, PAD-36), 'Server config (baseline)', font=font, fill=text_col)
d.ellipse((W-PAD-180-6, PAD-36, W-PAD-180+6, PAD-24), fill=col_mod)
d.text((W-PAD-180+16, PAD-36), 'Overrides (ATR×3, Risk 2%)', font=font, fill=text_col)

title = f"Equity Curve — {report['pair'].replace('_','/')} — {report['start']}"
d.text((PAD, 30), title, font=font, fill=(230,238,243))

# x-axis labels (start/mid/end of baseline)
for idx in [0, len(b_curve)//2, len(b_curve)-1]:
    lab = b_curve[idx]['date']
    x = PAD + (idx / max(1, len(b_curve)-1)) * (W - PAD*2)
    d.text((x, H-36), lab, font=font, fill=text_col, anchor='mm')

# save
img.save(out_path)
print('saved', out_path)
