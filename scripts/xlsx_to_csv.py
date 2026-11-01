#!/usr/bin/env python3
"""Dump every tab of an .xlsx to CSV using only the standard library (no openpyxl).

Usage: xlsx_to_csv.py book.xlsx out_dir
"""
import csv
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}


def col_index(ref: str) -> int:
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group():
        n = n * 26 + ord(ch) - 64
    return n - 1


def main(book: str, out: str) -> None:
    z = zipfile.ZipFile(book)
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS):
            shared.append("".join(t.text or "" for t in si.iter("{%s}t" % NS["m"])))
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    Path(out).mkdir(parents=True, exist_ok=True)
    for i, sh in enumerate(wb.find("m:sheets", NS)):
        name = sh.get("name")
        target = rels[sh.get("{%s}id" % NS["r"])]
        path = "xl/" + target.lstrip("/").replace("xl/", "")
        rows = []
        for row in ET.fromstring(z.read(path)).iter("{%s}row" % NS["m"]):
            cells = {}
            for c in row.findall("m:c", NS):
                v = c.find("m:v", NS)
                if c.get("t") == "inlineStr":
                    val = "".join(t.text or "" for t in c.iter("{%s}t" % NS["m"]))
                elif v is None:
                    continue
                elif c.get("t") == "s":
                    val = shared[int(v.text)]
                else:
                    val = v.text
                cells[col_index(c.get("r"))] = val
            if cells:
                rows.append([cells.get(k, "") for k in range(max(cells) + 1)])
        safe = re.sub(r"[^\w一-鿿-]+", "_", name)
        with open(Path(out) / f"{i:02d}_{safe}.csv", "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(rows)
        print(f"{i:02d} {name}: {len(rows)} rows")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
