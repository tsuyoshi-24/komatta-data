#!/usr/bin/env python3
from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


OUT = Path(__file__).resolve().parents[1] / "public"
OUT.mkdir(exist_ok=True)

MEDICAL_PAGE = (
    "https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/"
    "kenkou_iryou/iryou/newpage_43373.html"
)

FDMA_7119 = (
    "https://www.fdma.go.jp/mission/enrichment/"
    "appropriate/appropriate007.html"
)

MHLW_8000 = (
    "https://www.mhlw.go.jp/stf/seisakunitsuite/"
    "bunya/newpage_55223.html"
)

UA = {
    "User-Agent": "KomattaTokiNaviDataUpdater/1.0"
}

PREFS = [
    "北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県",
    "福島県", "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県",
    "東京都", "神奈川県", "新潟県", "富山県", "石川県", "福井県",
    "山梨県", "長野県", "岐阜県", "静岡県", "愛知県", "三重県",
    "滋賀県", "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県",
    "鳥取県", "島根県", "岡山県", "広島県", "山口県", "徳島県",
    "香川県", "愛媛県", "高知県", "福岡県", "佐賀県", "長崎県",
    "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県"
]


def fetch(url: str) -> requests.Response:
    r = requests.get(url, headers=UA, timeout=60)
    r.raise_for_status()
    return r


def clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def prefecture_short(prefecture: str) -> str:
    for suffix in ("都", "道", "府", "県"):
        if prefecture.endswith(suffix):
            return prefecture[:-1]
    return prefecture


# ==================================================
# 医療データ
# ==================================================

def latest_medical_links():
    soup = BeautifulSoup(fetch(MEDICAL_PAGE).text, "html.parser")
    text = soup.get_text(" ", strip=True)

    m = re.search(
        r"(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日時点",
        text
    )

    date = (
        f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        if m
        else None
    )

    found = {}

    for a in soup.find_all("a", href=True):
        href = urljoin(MEDICAL_PAGE, a["href"])
        filename = href.split("/")[-1].lower()

        if re.search(
            r"01-1_hospital_facility_info_\d{8}\.csv\.zip$",
            filename
        ):
            found["病院"] = href

        elif re.search(
            r"02-1_clinic_facility_info_\d{8}\.csv\.zip$",
            filename
        ):
            found["診療所"] = href

        elif re.search(
            r"03-1_dental_facility_info_\d{8}\.csv\.zip$",
            filename
        ):
            found["歯科診療所"] = href

        elif re.search(
            r"05_pharmacy_\d{8}\.csv\.zip$",
            filename
        ):
            found["薬局"] = href

    if len(found) < 4:
        raise RuntimeError(
            f"医療データURL取得失敗: {found}"
        )

    if date is None:
        first_url = next(iter(found.values()))
        fm = re.search(r"_(20\d{6})\.csv\.zip$", first_url)

        if fm:
            d = fm.group(1)
            date = f"{d[0:4]}-{d[4:6]}-{d[6:8]}"

    print("Medical source:", date)

    for kind, url in found.items():
        print(kind, url)

    return date, found


def csv_rows(url: str):
    raw = fetch(url).content

    if raw[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            names = [
                n
                for n in z.namelist()
                if n.lower().endswith(".csv")
            ]

            if not names:
                raise RuntimeError(
                    f"ZIP内にCSVがありません: {url}"
                )

            raw = z.read(names[0])

    text = None

    for enc in ("utf-8-sig", "cp932", "utf-8"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            pass

    if text is None:
        text = raw.decode("utf-8", errors="replace")

    return list(
        csv.DictReader(
            io.StringIO(text)
        )
    )


def norm(value: str | None) -> str:
    return re.sub(
        r"[\s　_\-（）()・/]",
        "",
        value or ""
    ).lower()


def find_column(headers, candidates):
    for candidate in candidates:
        for header in headers:
            if norm(header) == norm(candidate):
                return header

    for candidate in candidates:
        for header in headers:
            if norm(candidate) in norm(header):
                return header

    return None


def row_value(row, column):
    if not column:
        return ""

    return clean(
        row.get(column, "")
    )


def to_number(value):
    try:
        if not value:
            return None
        return float(value)
    except (ValueError, TypeError):
        return None


def convert_medical(kind, rows):
    if not rows:
        raise RuntimeError(
            f"{kind}: CSVが空です"
        )

    headers = list(rows[0].keys())

    id_col = find_column(
        headers,
        [
            "医療機関ID",
            "施設ID",
            "薬局ID",
            "機関ID",
            "ID"
        ]
    )

    name_col = find_column(
        headers,
        [
            "医療機関名",
            "施設名称",
            "施設名",
            "薬局名称",
            "薬局名",
            "名称"
        ]
    )

    pref_col = find_column(
        headers,
        [
            "都道府県名",
            "都道府県"
        ]
    )

    city_col = find_column(
        headers,
        [
            "市区町村名",
            "市町村名",
            "市区町村"
        ]
    )

    address_col = find_column(
        headers,
        [
            "所在地",
            "住所",
            "所在地住所"
        ]
    )

    phone_col = find_column(
        headers,
        [
            "電話番号",
        "代表電話番号",
        "電話",
        "案内用電話番号",
        "施設電話番号",
        "医療機関電話番号",
        "薬局電話番号"
        ]
    )

    lat_col = find_column(headers, ["緯度"])
    lon_col = find_column(headers, ["経度"])

    if not name_col:
        raise RuntimeError(
            f"{kind}: 名称列を特定できません"
        )

    result = []

    for index, row in enumerate(rows):
        name = row_value(row, name_col)

        if not name:
            continue

        address = row_value(row, address_col)

        record_id = (
            row_value(row, id_col)
            or
            f"{index}-{name}-{address}"
        )

        result.append(
            {
                "id": f"{kind}:{record_id}",
                "type": kind,
                "name": name,
                "prefecture": row_value(row, pref_col),
                "municipality": row_value(row, city_col),
                "address": address,
                "phone": (
                    row_value(row, phone_col)
                    or None
                ),
                "latitude": to_number(
                    row_value(row, lat_col)
                ),
                "longitude": to_number(
                    row_value(row, lon_col)
                )
            }
        )

    print(f"{kind}: {len(result)}件")

    return result


def update_medical():
    source_date, links = latest_medical_links()

    all_records = []

    for kind, url in links.items():
        print(f"Downloading {kind}")

        rows = csv_rows(url)
        converted = convert_medical(kind, rows)

        all_records.extend(converted)

    unique = {
        r["id"]: r
        for r in all_records
    }

    data = list(unique.values())

    data.sort(
        key=lambda r: (
            r["prefecture"],
            r["municipality"],
            r["name"]
        )
    )

    if len(data) == 0:
        raise RuntimeError(
            "医療データが0件のため保存を中止"
        )

    output = OUT / "medical_facilities.json"

    output.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            separators=(",", ":")
        ),
        encoding="utf-8"
    )

    print(f"Medical total: {len(data)}")

    return source_date, len(data)


# ==================================================
# #7119
# ==================================================

def extract_7119():
    soup = BeautifulSoup(
        fetch(FDMA_7119).text,
        "html.parser"
    )

    result = []

    for table in soup.find_all("table"):
        text = clean(
            table.get_text(" ", strip=True)
        )

        if "7119" not in text:
            continue

        rows = table.find_all("tr")

        for index, tr in enumerate(rows):
            cells = [
                clean(
                    x.get_text(" ", strip=True)
                )
                for x in tr.find_all(["th", "td"])
            ]

            if not cells:
                continue

            joined = " | ".join(cells)

            if "7119" not in joined:
                continue

            pref = None

            for p in PREFS:
                short = prefecture_short(p)

                if p in joined or short in joined:
                    pref = p
                    break

            phone_numbers = re.findall(
                r"0\d{1,4}-\d{1,4}-\d{3,4}",
                joined
            )

            result.append(
                {
                    "id": f"7119-{index}-{joined[:20]}",
                    "prefecture": pref,
                    "area": joined,
                    "title": "救急安心センター",
                    "shortNumber": "#7119",
                    "normalNumber": (
                        phone_numbers[0]
                        if phone_numbers
                        else None
                    ),
                    "hours": "公式情報をご確認ください",
                    "target": "救急車を呼ぶか迷うとき",
                    "sourceURL": FDMA_7119
                }
            )

    if not result:
        raise RuntimeError(
            "#7119取得失敗"
        )

    print(f"#7119: {len(result)}件")

    return result


# ==================================================
# #8000
# ==================================================

def extract_8000():
    soup = BeautifulSoup(
        fetch(MHLW_8000).text,
        "html.parser"
    )

    result = []

    for table in soup.find_all("table"):
        text = clean(
            table.get_text(" ", strip=True)
        )

        if "8000" not in text:
            continue

        for tr in table.find_all("tr"):
            cells = [
                clean(
                    x.get_text(" ", strip=True)
                )
                for x in tr.find_all(["th", "td"])
            ]

            if not cells:
                continue

            joined = " | ".join(cells)

            pref = None

            for p in PREFS:
                short = prefecture_short(p)

                if p in joined or short in joined:
                    pref = p
                    break

            if not pref:
                continue

            phone_numbers = re.findall(
                r"0\d{1,4}-\d{1,4}-\d{3,4}",
                joined
            )

            result.append(
                {
                    "id": f"8000-{pref}",
                    "prefecture": pref,
                    "area": pref,
                    "title": "子ども医療電話相談",
                    "shortNumber": "#8000",
                    "normalNumber": (
                        phone_numbers[0]
                        if phone_numbers
                        else None
                    ),
                    "hours": "受付時間は公式情報をご確認ください",
                    "target": "子どもの症状で判断に迷うとき",
                    "sourceURL": MHLW_8000
                }
            )

    unique = {}

    for item in result:
        unique[item["prefecture"]] = item

    result = list(unique.values())

    if len(result) < 40:
        raise RuntimeError(
            f"#8000取得不足: {len(result)}件"
        )

    print(f"#8000: {len(result)}件")

    return result


# ==================================================
# メイン
# ==================================================

def main():
    now = datetime.now(
        timezone.utc
    ).isoformat()

    medical_date, medical_count = update_medical()

    emergency_file = OUT / "emergency_contacts.json"

    old_7119 = []
    old_8000 = []

    if emergency_file.exists():
        try:
            old_data = json.loads(
                emergency_file.read_text(
                    encoding="utf-8"
                )
            )

            old_7119 = old_data.get(
                "hotline7119",
                []
            )

            old_8000 = old_data.get(
                "hotline8000",
                []
            )

        except Exception as e:
            print(
                "WARNING: 前回救急データの読み込み失敗",
                e
            )

    try:
        hotline_7119 = extract_7119()

    except Exception as e:
        print(
            f"WARNING #7119更新失敗: {e}"
        )

        print(
            "前回の#7119データを維持します"
        )

        hotline_7119 = old_7119

    try:
        hotline_8000 = extract_8000()

    except Exception as e:
        print(
            f"WARNING #8000更新失敗: {e}"
        )

        print(
            "前回の#8000データを維持します"
        )

        hotline_8000 = old_8000

    emergency = {
        "generatedAt": now,
        "hotline7119": hotline_7119,
        "hotline8000": hotline_8000
    }

    emergency_file.write_text(
        json.dumps(
            emergency,
            ensure_ascii=False,
            separators=(",", ":")
        ),
        encoding="utf-8"
    )

    manifest = {
        "schemaVersion": 1,
        "generatedAt": now,
        "medicalSourceDate": medical_date,
        "emergencySourceDate": now[:10],
        "medicalFile": "medical_facilities.json",
        "emergencyFile": "emergency_contacts.json"
    }

    (
        OUT /
        "manifest.json"
    ).write_text(
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    print("")
    print("===== UPDATE COMPLETE =====")
    print(f"Medical: {medical_count}")
    print(f"#7119: {len(hotline_7119)}")
    print(f"#8000: {len(hotline_8000)}")
    print("===========================")


if __name__ == "__main__":
    main()
