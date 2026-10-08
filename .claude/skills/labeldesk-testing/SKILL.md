---
name: labeldesk-testing
description: Test LabelDesk changes with or without the real DYMO printers: unit tests, render/barcode check, browser check, fake network printer, real-printer checklist. Use after any code change.
---

# Testing LabelDesk

Always say which level you reached (unit / render / browser / print pipeline with fake printer / real printer).

1. **Unit** (no CUPS needed): `python3 -m unittest discover -s tests`
2. **Render + barcode** (needs google-chrome, python3-pillow, zbar): `tests/render_check.sh` → asserts the tag image is
   391 × 960 (the 30321 printable area) and the Code 128 decodes; look at `render-out/*-reading.png`.
3. **Browser** (needs google-chrome, Xvfb, node 22+): `tests/browser_check.sh` → real Chrome against a throwaway
   server: pdf.js opens tests/samples/ups-sample.pdf, the same PDF saved to Downloads opens by itself on the Shipping
   tab with the label found, and the page logs no errors. Run it after ANY change to app.js — unit tests can't see the
   page (a pdf.js API slip and a CSP-blocked fetch both shipped past them once).
4. **Full print pipeline with a fake printer** — proves driver + SELinux + page size + the job reaching the "printer":
   ```bash
   python3 tests/fake_labelwriter.py /tmp/ldjobs &      # answers the DYMO status handshake; prints a line per job
   sudo lpadmin -p Test-550 -E -v socket://127.0.0.1:9100 -m lw550t.ppd -o PageSize=w102h252
   LABELDESK_TAG_QUEUE=Test-550 python3 server/app.py   # print from the UI, then look at /tmp/ldjobs/job1.pbm
   sudo lpadmin -x Test-550   # clean up
   ```
   Pass: the job bar goes ✓ Printed, `jobN.pbm` is the label (tag 392 dots wide, ~930 lines; 4×6 = 1200×1800) in the
   same orientation as the Windows output. Windows: point the DYMO printers' TCP port at the fake (VM: 10.0.2.2:9100).
5. **Real printer** (work): print a tag with a long name + barcode, scan the barcode with the shop scanner, check text
   direction and margins; print one real UPS label and scan its barcode.

Keep test queues and fake listeners out of the real queue names (`Dymo-550-Turbo`, `Dymo-5XL`).
