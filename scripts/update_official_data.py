#!/usr/bin/env python3
from __future__ import annotations
import csv,io,json,re,zipfile
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
OUT=Path(__file__).resolve().parents[1]/"public"; OUT.mkdir(exist_ok=True)
MEDICAL_PAGE="https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/kenkou_iryou/iryou/newpage_43373.html"
FDMA_7119="https://www.fdma.go.jp/mission/enrichment/appropriate/appropriate007.html"
MHLW_8000="https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/newpage_55223.html"
UA={"User-Agent":"KomattaTokiNaviDataUpdater/1.0"}
PREFS=["北海道","青森県","岩手県","宮城県","秋田県","山形県","福島県","茨城県","栃木県","群馬県","埼玉県","千葉県","東京都","神奈川県","新潟県","富山県","石川県","福井県","山梨県","長野県","岐阜県","静岡県","愛知県","三重県","滋賀県","京都府","大阪府","兵庫県","奈良県","和歌山県","鳥取県","島根県","岡山県","広島県","山口県","徳島県","香川県","愛媛県","高知県","福岡県","佐賀県","長崎県","熊本県","大分県","宮崎県","鹿児島県","沖縄県"]
def fetch(u):
 r=requests.get(u,headers=UA,timeout=60); r.raise_for_status(); return r
def clean(v): return re.sub(r"\s+"," ",(v or "")).strip()
def latest_medical_links():
 soup=BeautifulSoup(fetch(MEDICAL_PAGE).text,"html.parser"); text=soup.get_text(" ",strip=True); m=re.search(r"(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日時点",text); date=f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else None
 wanted={"病院":["病院","施設票"],"診療所":["診療所","施設票"],"歯科診療所":["歯科診療所","施設票"],"薬局":["薬局"]}; found={}
 for a in soup.find_all("a",href=True):
  href=urljoin(MEDICAL_PAGE,a["href"]); label=clean((a.parent or a).get_text(" ",strip=True))
  if not (".zip" in href.lower() or ".csv" in href.lower()): continue
  for kind,words in wanted.items():
   if kind not in found and all(w in label for w in words) and "診療時間" not in label: found[kind]=href
 if len(found)<4: raise RuntimeError(f"医療データURL取得失敗: {found}")
 return date,found
def rows(url):
 raw=fetch(url).content
 if raw[:2]==b"PK":
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   names=[n for n in z.namelist() if n.lower().endswith('.csv')]; raw=z.read(names[0])
 for enc in ('utf-8-sig','cp932','utf-8'):
  try: text=raw.decode(enc); break
  except UnicodeDecodeError: pass
 return list(csv.DictReader(io.StringIO(text)))
def norm(s): return re.sub(r"[\s　_\-（）()・/]","",s or '').lower()
def col(h,cands):
 for c in cands:
  for x in h:
   if norm(x)==norm(c): return x
 for c in cands:
  for x in h:
   if norm(c) in norm(x): return x
def val(r,c): return clean(r.get(c,'')) if c else ''
def num(s):
 try:return float(s) if s else None
 except:return None
def convert(kind,rs):
 h=list(rs[0].keys()); idc=col(h,["医療機関ID","施設ID","薬局ID","ID"]); nc=col(h,["医療機関名","施設名称","施設名","薬局名称","薬局名","名称"]); pc=col(h,["都道府県名","都道府県"]); cc=col(h,["市区町村名","市町村名"]); ac=col(h,["所在地","住所"]); ph=col(h,["電話番号","代表電話番号"]); la=col(h,["緯度"]); lo=col(h,["経度"])
 if not nc: raise RuntimeError(kind+' 名称列なし')
 out=[]
 for i,r in enumerate(rs):
  name=val(r,nc)
  if not name: continue
  rid=val(r,idc) or f"{i}-{name}-{val(r,ac)}"
  out.append({"id":f"{kind}:{rid}","type":kind,"name":name,"prefecture":val(r,pc),"municipality":val(r,cc),"address":val(r,ac),"phone":val(r,ph) or None,"latitude":num(val(r,la)),"longitude":num(val(r,lo))})
 return out
def update_medical():
 date,links=latest_medical_links(); all=[]
 for k,u in links.items(): all+=convert(k,rows(u))
 data=list({r['id']:r for r in all}.values()); data.sort(key=lambda r:(r['prefecture'],r['municipality'],r['name'])); (OUT/'medical_facilities.json').write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')),encoding='utf-8'); return date,len(data)
def extract7119():
 soup=BeautifulSoup(fetch(FDMA_7119).text,'html.parser'); out=[]
 for table in soup.find_all('table'):
  if '利用地域' not in clean(table.get_text(' ',strip=True)): continue
  for i,tr in enumerate(table.find_all('tr')[1:]):
   c=[clean(x.get_text(' ',strip=True)) for x in tr.find_all(['th','td'])]
   if len(c)<5: continue
   center,area,target,number,hours=c[:5]; nums=re.findall(r'0\d{1,4}-\d{1,4}-\d{3,4}',number); pref=next((p for p in PREFS if p in area or p.rstrip('県府都道') in area),None)
   out.append({"id":f"7119-{i}-{center}","prefecture":pref,"area":area,"title":center,"shortNumber":"#7119" if '7119' in number else None,"normalNumber":nums[0] if nums else None,"hours":hours,"target":target,"sourceURL":FDMA_7119})
  if out: break
 if not out: raise RuntimeError('7119取得失敗')
 return out
def extract8000():
 soup=BeautifulSoup(fetch(MHLW_8000).text,'html.parser'); out=[]
 for table in soup.find_all('table'):
  if '8000' not in clean(table.get_text(' ',strip=True)): continue
  for tr in table.find_all('tr'):
   c=[clean(x.get_text(' ',strip=True)) for x in tr.find_all(['th','td'])]; joined=' | '.join(c); pref=next((p for p in PREFS if p in c or p.rstrip('県府都道') in c),None)
   if not pref: continue
   nums=re.findall(r'0\d{1,4}-\d{1,4}-\d{3,4}',joined); times=re.findall(r'\d{1,2}:\d{2}[^|]{0,20}',joined)
   out.append({"id":f"8000-{pref}","prefecture":pref,"area":pref,"title":"子ども医療電話相談","shortNumber":"#8000","normalNumber":nums[0] if nums else None,"hours":" / ".join(dict.fromkeys(x.strip() for x in times)) or "公式情報をご確認ください","target":"子どもの症状で判断に迷うとき","sourceURL":MHLW_8000})
  if len(out)>=40: break
 if len(out)<40: raise RuntimeError(f'8000取得不足 {len(out)}')
 return out
def main():
 now=datetime.now(timezone.utc).isoformat(); date,count=update_medical(); a=extract7119(); b=extract8000(); (OUT/'emergency_contacts.json').write_text(json.dumps({"generatedAt":now,"hotline7119":a,"hotline8000":b},ensure_ascii=False,separators=(',',':')),encoding='utf-8'); (OUT/'manifest.json').write_text(json.dumps({"schemaVersion":1,"generatedAt":now,"medicalSourceDate":date,"emergencySourceDate":now[:10],"medicalFile":"medical_facilities.json","emergencyFile":"emergency_contacts.json"},ensure_ascii=False,indent=2),encoding='utf-8'); print('OK',count,len(a),len(b))
if __name__=='__main__': main()
