"""Spreadsheets for batch tags (Batch → Open spreadsheet…): CSV (any delimiter, Excel's UTF-8 BOM, Windows-1252) and
Excel .xlsx (the first sheet), standard library only. → {"columns": [header…], "rows": [[cell…]…]} — every cell text.

.xlsx is a zip of XML: xl/workbook.xml names the sheets, xl/_rels/workbook.xml.rels maps them to files, cells refer to
xl/sharedStrings.xml or hold inline strings / numbers. Numbers in a date format (xl/styles.xml numFmt) become
YYYY-MM-DD (Excel counts days from 1899-12-30). Old binary .xls isn't read: "save it as .xlsx or CSV".
"""
import csv
import datetime
import io
import re
import xml.etree.ElementTree as ET
import zipfile

MAX_ROWS = 2000
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
      "pr": "http://schemas.openxmlformats.org/package/2006/relationships"}
DATE_FORMATS = {14, 15, 16, 17, 22, 27, 30, 36, 50, 57, 58}       # Excel's built-in date number formats


def read(name, data):
    n = (name or "").lower()
    if n.endswith(".xls") and not data.startswith(b"PK"):
        raise ValueError("old .xls files can't be read — save it as .xlsx or CSV")
    if data.startswith(b"PK"):
        rows = read_xlsx(data)
    else:
        rows = read_csv(data)
    rows = [[str(c).strip() for c in r] for r in rows]
    rows = [r for r in rows if any(r)]
    if not rows:
        raise ValueError("the spreadsheet is empty")
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    head, body = rows[0], rows[1:MAX_ROWS + 1]
    columns = [h or f"Column {i + 1}" for i, h in enumerate(head)]
    return {"columns": columns, "rows": body, "truncated": len(rows) - 1 > MAX_ROWS}


def read_csv(data):
    for enc in ("utf-8-sig", "cp1252"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    return list(csv.reader(io.StringIO(text), dialect))


def _col(ref):
    """'BC12' → 54 (0-based column)."""
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def read_xlsx(data):
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise ValueError("not a spreadsheet LabelDesk can read (CSV or .xlsx)") from None
    names = set(z.namelist())
    if "xl/workbook.xml" not in names:
        raise ValueError("not an Excel .xlsx file")
    shared = []
    if "xl/sharedStrings.xml" in names:
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS):
            shared.append("".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t")))
    date_styles = set()
    if "xl/styles.xml" in names:
        st = ET.fromstring(z.read("xl/styles.xml"))
        custom = {int(f.get("numFmtId")): f.get("formatCode", "") for f in st.findall("m:numFmts/m:numFmt", NS)}
        for i, xf in enumerate(st.findall("m:cellXfs/m:xf", NS)):
            fid = int(xf.get("numFmtId", "0"))
            code = custom.get(fid, "")
            if fid in DATE_FORMATS or (code and re.search(r"[dy]", re.sub(r'"[^"]*"|\[[^\]]*\]', "", code), re.I)
                                       and not re.search(r"[h]", code, re.I)):
                date_styles.add(i)
    # the first sheet in the workbook's order
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    first = wb.find("m:sheets/m:sheet", NS)
    path = "xl/worksheets/sheet1.xml"
    if first is not None and "xl/_rels/workbook.xml.rels" in names:
        rid = first.get(f"{{{NS['r']}}}id")
        for rel in ET.fromstring(z.read("xl/_rels/workbook.xml.rels")).findall("pr:Relationship", NS):
            if rel.get("Id") == rid:
                target = rel.get("Target").lstrip("/")
                path = target if target.startswith("xl/") else "xl/" + target
    sheet = ET.fromstring(z.read(path))
    rows = []
    for row in sheet.iter(f"{{{NS['m']}}}row"):
        cells = {}
        for c in row.findall("m:c", NS):
            t, v = c.get("t"), c.find("m:v", NS)
            if t == "s" and v is not None:
                val = shared[int(v.text)]
            elif t == "inlineStr":
                val = "".join(x.text or "" for x in c.iter(f"{{{NS['m']}}}t"))
            elif t == "b" and v is not None:
                val = "TRUE" if v.text == "1" else "FALSE"
            elif v is not None and v.text is not None:
                val = v.text
                if int(c.get("s", "0")) in date_styles:
                    try:
                        val = (datetime.date(1899, 12, 30) + datetime.timedelta(days=int(float(val)))).isoformat()
                    except (ValueError, OverflowError):
                        pass
                elif re.fullmatch(r"-?\d+\.0", val):
                    val = val[:-2]                                  # 75013.0 → 75013 (ticket numbers stored as numbers)
            else:
                val = ""
            cells[_col(c.get("r")) if c.get("r") else len(cells)] = val       # some writers leave out r="B2"
        if cells:
            rows.append([cells.get(i, "") for i in range(max(cells) + 1)])
        if len(rows) > MAX_ROWS + 1:
            break
    return rows
