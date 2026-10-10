"""server/sheet.py: spreadsheets for batch tags — CSV in the shapes Excel and others write, a real .xlsx (LibreOffice-made
sample with a date column), and the refusals. No network."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))
import sheet  # noqa: E402

SAMPLE = os.path.join(os.path.dirname(__file__), "samples", "intake.xlsx")


class Sheets(unittest.TestCase):
    def test_real_xlsx_with_dates_numbers_and_accents(self):
        with open(SAMPLE, "rb") as f:
            s = sheet.read("intake.xlsx", f.read())
        self.assertEqual(s["columns"], ["Ticket", "Company", "Contact", "Date In", "Serial Number", "Bin", "Accessories"])
        self.assertEqual(s["rows"][0], ["75013", "Acme Dental Group", "Jane Smith", "2026-10-09", "PF3XK2LQ", "B3", "Charger, Bag"])
        self.assertEqual(s["rows"][1][1:3], ["Peña & Hijos Café", "José Peña"])
        self.assertEqual(len(s["rows"]), 3)

    def test_csv_shapes(self):
        cases = {
            "comma": b"Ticket,Company\n75013,Acme\n",
            "excel utf-8 bom + semicolons": "﻿Ticket;Company\n75013;Acme\n".encode("utf-8"),
            "tabs": b"Ticket\tCompany\n75013\tAcme\n",
            "windows-1252": "Ticket,Company\n75013,Café Acme\n".encode("cp1252"),
            "quoted commas, blank lines": b'Ticket,Company\n\n75013,"Acme, Inc."\n,\n',
        }
        for what, data in cases.items():
            s = sheet.read("x.csv", data)
            self.assertEqual(s["columns"], ["Ticket", "Company"], what)
            self.assertEqual(s["rows"][0][0], "75013", what)
        self.assertEqual(sheet.read("x.csv", cases["windows-1252"])["rows"][0][1], "Café Acme")
        self.assertEqual(sheet.read("x.csv", cases["quoted commas, blank lines"])["rows"], [["75013", "Acme, Inc."]])

    def test_ragged_rows_and_missing_headings(self):
        s = sheet.read("x.csv", b"Ticket,,\n75013,Acme,B3\n75014\n")
        self.assertEqual(s["columns"], ["Ticket", "Column 2", "Column 3"])
        self.assertEqual(s["rows"][1], ["75014", "", ""])

    def test_refusals(self):
        with self.assertRaisesRegex(ValueError, "xlsx or CSV"):
            sheet.read("old.xls", b"\xd0\xcf\x11\xe0 binary excel")
        with self.assertRaisesRegex(ValueError, "empty"):
            sheet.read("x.csv", b"\n\n")
        with self.assertRaises(ValueError):
            sheet.read("x.xlsx", b"PK\x03\x04 not really a zip")


if __name__ == "__main__":
    unittest.main()
