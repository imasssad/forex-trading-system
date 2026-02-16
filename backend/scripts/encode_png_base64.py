from PIL import Image
import io, base64, os
p='backend/data/backtest_compare_EUR_USD_2024-01-01.png'
out_txt='backend/data/backtest_compare_EUR_USD_2024-01-01.datauri.txt'
im=Image.open(p)
w=900
h=int(im.height * (w/im.width))
im2=im.resize((w,h), Image.LANCZOS)
b=io.BytesIO(); im2.save(b, format='PNG')
datauri = 'data:image/png;base64,'+base64.b64encode(b.getvalue()).decode()
with open(out_txt, 'w', encoding='utf-8') as f:
    f.write(datauri)
print('wrote', out_txt)
