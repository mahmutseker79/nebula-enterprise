import json, csv, sys, io, os, re, time
from datetime import datetime
from pathlib import Path
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

OUTPUT_DIR = Path(r"C:\Nebula_Enterprise\outputs")
OUTPUT_DIR.mkdir(exist_ok=True)
TARGET = 100

opts = Options()
opts.add_argument("--headless=new")
opts.add_argument("--no-sandbox")
opts.add_argument("--disable-dev-shm-usage")
opts.add_argument("--disable-blink-features=AutomationControlled")
opts.add_experimental_option("excludeSwitches", ["enable-automation"])
opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
opts.add_argument("--window-size=1280,900")

JS_EXTRACT = """
const items = Array.from(document.querySelectorAll('ul.pl_v9 > li[data-pr]'));
return items.map(li => {
  const ptEl = li.querySelector('[class^="pt_"]');
  const rawPrice = ptEl ? (ptEl.childNodes[0]?.textContent?.trim() || '') : '';
  const img = li.querySelector('img')?.src || li.querySelector('img')?.dataset?.src || '';
  return {
    id:    li.dataset.pr || '',
    brand: li.dataset.mk || '',
    name:  li.querySelector('a.pw_v8')?.title || li.querySelector('h3')?.textContent?.trim() || '',
    price: rawPrice,
    url:   li.querySelector('a.pw_v8')?.href || '',
    img:   img.startsWith('//') ? 'https:' + img : img
  };
});
"""

# Sayfa URL'leri - gercek format: cep-telefonu.html, cep-telefonu,2.html ...
BASE = "https://www.akakce.com/cep-telefonu.html"
PAGES = [BASE] + [f"https://www.akakce.com/cep-telefonu,{i}.html" for i in range(2, 5)]

all_products = []
seen_ids = set()

print("\n" + "="*64)
print("  Nebula Enterprise - Akakce Selenium Scraper v2")
print("  Kategori : Cep Telefonu")
print(f"  Hedef    : {TARGET} urun")
print("="*64 + "\n")

driver = webdriver.Chrome(options=opts)
try:
    for pnum, url in enumerate(PAGES, 1):
        print(f"  [{pnum}/4] {url}")
        driver.get(url)
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "ul.pl_v9 > li[data-pr]"))
            )
            time.sleep(1.5)
        except Exception as e:
            print(f"  Sayfa {pnum}: ZAMAN ASIMI - {e}")
            continue

        products = driver.execute_script(JS_EXTRACT) or []
        new_c = 0
        for p in products:
            if p.get('id') and p['id'] not in seen_ids and p.get('name'):
                seen_ids.add(p['id'])
                all_products.append(p)
                new_c += 1
        print(f"  Sayfa {pnum}: {new_c} yeni urun | Toplam: {len(all_products)}")
        if len(all_products) >= TARGET:
            break
        time.sleep(1)
finally:
    driver.quit()

all_products = all_products[:TARGET]

def to_float(v):
    try: return float(re.sub(r'[^\d.]', '', str(v).replace(',','.')))
    except: return 0.0

print(f"\n" + "-"*64)
print(f"  TOPLAM CEKILDI: {len(all_products)} URUN")
print("-"*64)
for i,p in enumerate(all_products[:20],1):
    pv = to_float(p.get('price',''))
    ps = f"{pv:>12,.0f} TL" if pv else "         - TL"
    print(f"  {i:3}. {(p.get('name') or '')[:48]:<49} {ps}")
if len(all_products) > 20:
    print(f"  ... ve {len(all_products)-20} urun daha")

ts    = datetime.now().strftime("%Y%m%d_%H%M%S")
csv_p = str(OUTPUT_DIR / f"akakce_cep_telefonu_{ts}.csv")
xlsx_p= str(OUTPUT_DIR / f"akakce_cep_telefonu_{ts}.xlsx")

with open(csv_p,"w",newline="",encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=["no","name","price","brand","url","img"])
    w.writeheader()
    for i,p in enumerate(all_products,1):
        w.writerow({"no":i,"name":p.get('name',''),"price":p.get('price',''),
                    "brand":p.get('brand',''),"url":p.get('url',''),"img":p.get('img','')})
print(f"\n  CSV  : {csv_p}")

try:
    import pandas as pd
    df = pd.DataFrame([{
        "No": i+1, "Urun Adi": p.get('name',''), "Fiyat": p.get('price',''),
        "Fiyat (TL)": to_float(p.get('price','')), "Marka": p.get('brand',''),
        "URL": p.get('url',''), "Gorsel": p.get('img','')
    } for i,p in enumerate(all_products)])
    with pd.ExcelWriter(xlsx_p, engine="openpyxl") as wr:
        df.to_excel(wr, index=False, sheet_name="Cep Telefonu")
        ws = wr.sheets["Cep Telefonu"]
        for col, w in zip(ws.columns, [5,60,16,14,20,80,60]):
            ws.column_dimensions[col[0].column_letter].width = w
        for row in ws.iter_rows(min_row=2, min_col=4, max_col=4):
            for cell in row: cell.number_format = '#,##0.00 "TL"'
    print(f"  Excel: {xlsx_p}")
except Exception as e:
    print(f"  Excel hatasi: {e}")

print("="*64 + "\n")
