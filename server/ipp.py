"""Tiny IPP client for the local CUPS (http://localhost:631) — job and printer state straight from CUPS, no lpstat parsing.

Only what LabelDesk needs: Get-Job-Attributes (did the label actually print?) and Get-Printer-Attributes (is the
printer ready, out of labels, paused…). IPP is a small binary format over HTTP POST (RFC 8010); stdlib only.
"""
import struct
import urllib.request

CUPS = "http://localhost:631"
JOB_STATES = {3: "pending", 4: "held", 5: "processing", 6: "stopped", 7: "canceled", 8: "aborted", 9: "completed"}
PRINTER_STATES = {3: "idle", 4: "printing", 5: "stopped"}

# value tags (RFC 8010 §3.5)
_INT, _BOOL, _ENUM = 0x21, 0x22, 0x23
_TEXT, _NAME, _KEYWORD, _URI, _CHARSET, _LANG = 0x41, 0x42, 0x44, 0x45, 0x47, 0x48


def _attr(tag, name, value):
    v = value if isinstance(value, bytes) else (struct.pack(">i", value) if tag in (_INT, _ENUM) else value.encode())
    return struct.pack(">bh", tag, len(name)) + name.encode() + struct.pack(">h", len(v)) + v


def _request(op, attrs, path="/"):
    body = struct.pack(">bbhi", 2, 0, op, 1) + b"\x01"                       # IPP 2.0, operation attributes group
    body += _attr(_CHARSET, "attributes-charset", "utf-8") + _attr(_LANG, "attributes-natural-language", "en")
    for tag, name, value in attrs:
        body += _attr(tag, name, value)
    body += b"\x03"                                                            # end of attributes
    req = urllib.request.Request(CUPS + path, data=body, headers={"Content-Type": "application/ipp"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return _parse(r.read())


def _parse(data):
    """→ (status-code, {name: value | [values]}) — all groups merged (we ask for one job / one printer)."""
    status = struct.unpack(">h", data[2:4])[0]
    i, out, name = 8, {}, None
    while i < len(data):
        tag = data[i]
        i += 1
        if tag <= 0x0F:                                                        # delimiter
            if tag == 0x03:
                break
            continue
        nlen = struct.unpack(">h", data[i:i + 2])[0]; i += 2                   # noqa: E702
        n = data[i:i + nlen].decode(errors="replace"); i += nlen               # noqa: E702
        vlen = struct.unpack(">h", data[i:i + 2])[0]; i += 2                   # noqa: E702
        raw = data[i:i + vlen]; i += vlen                                      # noqa: E702
        if tag in (_INT, _ENUM):
            val = struct.unpack(">i", raw)[0]
        elif tag == _BOOL:
            val = bool(raw[0])
        else:
            val = raw.decode(errors="replace")
        if n:                                                                  # a new attribute
            name = n
            out[name] = val
        elif name:                                                             # additional value of the last one
            out[name] = (out[name] if isinstance(out[name], list) else [out[name]]) + [val]
    return status, out


def job(queue, job_id):
    """{state, reasons, message} for job `job_id` (the number from "Dymo-5XL-12") on `queue`."""
    st, a = _request(0x0009, [(_URI, "printer-uri", f"ipp://localhost/printers/{queue}"), (_INT, "job-id", int(job_id)),
                              (_KEYWORD, "requested-attributes", "job-state"), (_KEYWORD, "", "job-state-reasons"),
                              (_KEYWORD, "", "job-printer-state-message")], "/jobs")
    if st >= 0x0400:
        raise LookupError(f"CUPS doesn't know job {job_id} (status 0x{st:04x})")
    reasons = a.get("job-state-reasons", [])
    return {"state": JOB_STATES.get(a.get("job-state"), "unknown"), "reasons": reasons if isinstance(reasons, list) else [reasons],
            "message": a.get("job-printer-state-message", "")}


def printer(queue):
    """{state, reasons, message, accepting} for `queue`."""
    st, a = _request(0x000B, [(_URI, "printer-uri", f"ipp://localhost/printers/{queue}"),
                              (_KEYWORD, "requested-attributes", "printer-state"), (_KEYWORD, "", "printer-state-reasons"),
                              (_KEYWORD, "", "printer-state-message"), (_KEYWORD, "", "printer-is-accepting-jobs")],
                     f"/printers/{queue}")
    if st >= 0x0400:
        raise LookupError(f"no printer queue {queue!r} (status 0x{st:04x})")
    reasons = a.get("printer-state-reasons", [])
    return {"state": PRINTER_STATES.get(a.get("printer-state"), "unknown"),
            "reasons": [r for r in (reasons if isinstance(reasons, list) else [reasons]) if r != "none"],
            "message": a.get("printer-state-message", ""), "accepting": a.get("printer-is-accepting-jobs", True)}


# What the DYMO 550-series driver reports (raster2dymolw_v2 STATE:/INFO: lines, read from its source) → plain English
REASONS = {
    "com.dymo.out-of-paper-error": "out of labels — load a new roll",
    "com.dymo.counterfeit-error": "these aren't genuine DYMO labels — the 550 series only prints DYMO rolls",
    "com.dymo.paper-size-error": "the loaded labels are the wrong size for this label",
    "com.dymo.paper-size-undefine-error": "the printer can't tell which labels are loaded — reload the roll",
    "com.dymo.head-overheat-error": "the print head is too hot — wait a minute and print again",
    "com.dymo.busy-error": "the printer is busy with another job",
    "com.dymo.slot-status-error": "label roll problem — open the printer and reseat the roll",
    "com.dymo.general-error": "the printer reported an error — check it (lid, roll, lights)",
    "media-empty": "out of labels — load a new roll", "media-jam": "labels jammed — open the printer and clear it",
    "cover-open": "the printer's cover is open", "offline": "the printer is offline — check power and the network cable",
    "paused": "printing is paused on this PC", "connecting-to-device": "connecting to the printer…",
}


def plain(reasons, message=""):
    """The first reason we can explain, else CUPS' own message. "Printer is not ready" wins over a busy flag: the
    driver also raises com.dymo.busy-error when its status request goes unanswered (seen with no printer there)."""
    m = (message or "").strip()
    if "not ready" in m.lower() and set(reasons) <= {"com.dymo.busy-error", "job-completed-with-errors", "none"}:
        return "the printer isn't answering — check power, the network cable and that labels are loaded"
    for r in reasons:
        key = r.rsplit("-", 1)[0] if r.endswith(("-error", "-warning", "-report")) and r not in REASONS else r
        if r in REASONS:
            return REASONS[r]
        if key in REASONS:
            return REASONS[key]
    if "not ready" in m.lower():
        return "the printer isn't answering — check power, the network cable and that labels are loaded"
    return m
