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
    response = requests.get(
        url,
        headers=UA,
        timeout=60
    )
    response.raise_for_status()
    return response


def clean(value: str | None) -> str:
    return re.sub(
        r"\s+",
        " ",
        value or ""
    ).strip()


def prefecture_short(prefecture: str) -> str:
    for suffix in ("都", "道", "府", "県"):
        if prefecture.endswith(suffix):
            return prefecture[:-1]
    return prefecture


# --------------------------------------------------
# 医療情報
# --------------------------------------------------

def latest_medical_links():
    soup = BeautifulSoup(
        fetch(MEDICAL_PAGE).text,
        "html.parser"
    )

    text = soup.get_text(
        " ",
        strip=True
    )

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
        href = urljoin(
            MEDICAL_PAGE,
            a["href"]
        )

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

    # ページ上で日付を取得できない場合は
    # ZIPファイル名の日付を利用
    if date is None:
        first_url = next(iter(found.values()))

        fm = re.search(
            r"_(20\d{6})\.csv\.zip$",
            first_url
        )

        if fm:
            d = fm.group(1)

            date = (
                f"{d[0:4]}-"
                f"{d[4:6]}-"
                f"{d[6:8]}"
            )

    print(
        "Medical source:",
        date
    )

    for kind, url in found.items():
        print(
            kind,
            url
        )

    return date, found


def csv_rows(url: str):
    raw = fetch(url).content

    if raw[:2] == b"PK":
        with zipfile.ZipFile(
            io.BytesIO(raw)
        ) as z:

            names = [
                name
                for name in z.namelist()
                if name.lower().endswith(".csv")
            ]

            if not names:
                raise RuntimeError(
                    f"ZIP内にCSVなし: {url}"
                )

            raw = z.read(names[0])

    text = None

    for enc in (
        "utf-8-sig",
        "cp932",
        "utf-8"
    ):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            pass

    if text is None:
        text = raw.decode(
            "utf-8",
            errors="replace"
        )

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


def find_column(
    headers,
    candidates
):
    for candidate in candidates:
        for header in headers:
            if norm(header) == norm(candidate):
                return header

    for candidate in candidates:
        for header in headers:
            if norm(candidate) in norm(header):
                return header

    return None


def value(
    row,
    column
):
    if not column:
        return ""

    return clean(
        row.get(
            column,
            ""
        )
    )


def number(value_string):
    try:
        if not value_string:
            return None

        return float(
            value_string
        )

    except (ValueError, TypeError):
        return None


def convert_medical(
    kind,
    rows
):
    if not rows:
        raise RuntimeError(
            f"{kind}: CSVが空です"
        )

    headers = list(
        rows[0].keys()
    )

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
            "電話"
        ]
    )

    lat_col = find_column(
        headers,
        ["緯度"]
    )

    lon_col = find_column(
        headers,
        ["経度"]
    )

    if not name_col:
        print(
            "Headers:",
            headers
        )

        raise RuntimeError(
            f"{kind}: 名称列を特定できません"
        )

    result = []

    for index, row in enumerate(rows):
        name = value(
            row,
            name_col
        )

        if not name:
            continue

        address = value(
            row,
            address_col
        )

        record_id = (
            value(
                row,
                id_col
            )
            or
            f"{index}-{name}-{address}"
        )

        result.append(
            {
                "id": f"{kind}:{record_id}",
                "type": kind,
                "name": name,
                "prefecture": value(
                    row,
                    pref_col
                ),
                "municipality": value(
                    row,
                    city_col
                ),
                "address": address,
                "phone": (
                    value(
                        row,
                        phone_col
                    )
                    or None
                ),
                "latitude": number(
                    value(
                        row,
                        lat_col
                    )
                ),
                "longitude": number(
                    value(
                        row,
                        lon_col
                    )
                )
            }
        )

    print(
        f"{kind}: {len(result)}件"
    )

    return result


def update_medical():
    source_date, links = (
        latest_medical_links()
    )

    all_records = []

    for kind, url in links.items():
        print(
            f"Downloading {kind}"
        )

        rows = csv_rows(url)

        converted = convert_medical(
            kind,
            rows
        )

        all_records.extend(
            converted
        )

    unique = {
        record["id"]: record
        for record in all_records
    }

    data = list(
        unique.values()
    )

    data.sort(
        key=lambda record: (
            record["prefecture"],
            record["municipality"],
            record["name"]
        )
    )

    if len(data) == 0:
        raise RuntimeError(
            "医療データが0件のため保存を中止"
        )

    output_file = (
        OUT /
        "medical_facilities.json"
    )

    output_file.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            separators=(",", ":")
        ),
        encoding="utf-8"
    )

    print(
        f"Medical total: {len(data)}"
    )

    return (
        source_date,
        len(data)
    )


# --------------------------------------------------
# #7119
# --------------------------------------------------

def extract_7119():
    soup = BeautifulSoup(
        fetch(FDMA_7119).text,
        "html.parser"
    )

    result = []

    for table in soup.find_all("table"):
        table_text = clean(
            table.get_text(
                " ",
                strip=True
            )
        )

        if (
            "利用地域" not in table_text
            and
            "#7119" not in table_text
            and
            "♯7119" not in table_text
        ):
            continue

        rows = table.find_all("tr")

        for index, tr in enumerate(rows):
            cells = [
                clean(
                    x.get_text(
                        " ",
                        strip=True
                    )
                )
                for x in tr.find_all(
                    ["th", "td"]
                )
            ]

            if len(cells) < 4:
                continue

            joined = " | ".join(cells)

            if (
                "7119" not in joined
                and
                index == 0
            ):
                continue

            center = (
                cells[0]
                if len(cells) > 0
                else ""
            )

            area = (
                cells[1]
                if len(cells) > 1
                else ""
            )

            target = (
                cells[2]
                if len(cells) > 2
                else ""
            )

            phone_text = joined

            hours = (
                cells[-1]
                if cells
                else ""
            )

            pref = None

            for p in PREFS:
                short = prefecture_short(p)

                if (
                    p in joined
                    or
                    short in area
                ):
                    pref = p
                    break

            phone_numbers = re.findall(
                r"0\d{1,4}-\d{1,4}-\d{3,4}",
                phone_text
            )

            result.append(
                {
                    "id": (
                        f"7119-"
                        f"{index}-"
                        f"{center}"
                    ),
                    "prefecture": pref,
                    "area": area,
                    "title": (
                        center
                        or
                        "救急安心センター"
                    ),
                    "shortNumber": (
                        "#7119"
                        if "7119" in joined
                        else None
                    ),
                    "normalNumber": (
                        phone_numbers[0]
                        if phone_numbers
                        else None
                    ),
                    "hours": hours,
                    "target": target,
                    "sourceURL": FDMA_7119
                }
            )

        if result:
            break

    if not result:
        raise RuntimeError(
            "#7119取得失敗"
        )

    print(
        f"#7119: {len(result)}件"
    )

    return result


# --------------------------------------------------
# #8000
# --------------------------------------------------

def extract_8000():
    soup = BeautifulSoup(
        fetch(MHLW_8000).text,
        "html.parser"
    )

    result = []

    for table in soup.find_all("table"):
        table_text = clean(
            table.get_text(
                " ",
                strip=True
            )
        )

        if "8000" not in table_text:
            continue

        for tr in table.find_all("tr"):
            cells = [
                clean(
                    x.get_text(
                        " ",
                        strip=True
                    )
                )
                for x in tr.find_all(
                    ["th", "td"]
                )
            ]

            if not cells:
                continue

            joined = (
                " | ".join(cells)
            )

            pref = None

            for p in PREFS:
                short = prefecture_short(p)

                if (
                    p in joined
                    or
                    re.search(
                        rf"(^|\s|\|){re.escape(short)}($|\s|\|)",
                        joined
                    )
                ):
                    pref = p
                    break

            if not pref:
                continue

            phone_numbers = re.findall(
                r"0\d{1,4}-\d{1,4}-\d{3,4}",
                joined
            )

            times = re.findall(
                r"\d{1,2}:\d{2}[^|]{0,30}",
                joined
            )

            hours = (
                " / ".join(
                    dict.fromkeys(
                        x.strip()
                        for x in times
                    )
                )
                or
                "受付時間は公式情報をご確認ください"
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
                    "hours": hours,
                    "target": (
                        "子どもの症状で"
                        "判断に迷うとき"
                    ),
                    "sourceURL": MHLW_8000
                }
            )

        if len(result) >= 40:
            break

    # 同一都道府県を重複排除
    unique = {}

    for item in result:
        unique[item["prefecture"]] = item

    result = list(
        unique.values()
    )

    if len(result) < 40:
        raise RuntimeError(
            f"#8000取得不足: {len(result)}件"
        )

    print(
        f"#8000: {len(result)}件"
    )

    return result


# --------------------------------------------------
# メイン処理
# --------------------------------------------------

def main():
    now = datetime.now(
        timezone.utc
    ).isoformat()

    medical_date, medical_count = (
        update_medical()
    )

    hotline_7119 = (
        extract_7119()
    )

    hotline_8000 = (
        extract_8000()
    )

    emergency = {
        "generatedAt": now,
        "hotline7119": hotline_7119,
        "hotline8000": hotline_8000
    }

    (
        OUT /
        "emergency_contacts.json"
    ).write_text(
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
    print(
        f"Medical: {medical_count}"
    )
    print(
        f"#7119: {len(hotline_7119)}"
    )
    print(
        f"#8000: {len(hotline_8000)}"
    )
    print("===========================")


if __name__ == "__main__":
    main()
