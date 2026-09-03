def latest_medical_links():
    soup = BeautifulSoup(fetch(MEDICAL_PAGE).text, "html.parser")
    text = soup.get_text(" ", strip=True)

    m = re.search(r"(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日時点", text)
    date = (
        f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        if m else None
    )

    found = {}

    for a in soup.find_all("a", href=True):
        href = urljoin(MEDICAL_PAGE, a["href"])
        filename = href.split("/")[-1].lower()

        if re.search(r"01-1_hospital_facility_info_\d{8}\.csv\.zip$", filename):
            found["病院"] = href
        elif re.search(r"02-1_clinic_facility_info_\d{8}\.csv\.zip$", filename):
            found["診療所"] = href
        elif re.search(r"03-1_dental_facility_info_\d{8}\.csv\.zip$", filename):
            found["歯科診療所"] = href
        elif re.search(r"05_pharmacy_\d{8}\.csv\.zip$", filename):
            found["薬局"] = href

    if len(found) < 4:
        raise RuntimeError(f"医療データURL取得失敗: {found}")

    return date, found
