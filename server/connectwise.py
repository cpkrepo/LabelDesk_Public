"""ConnectWise PSA (Manage) — read-only lookups for LabelDesk. Standard library only.

Type a ticket number → the tag's company (and, optionally, the contact) fill in. Uses a read-only API member created by
the ConnectWise admin (docs/connectwise-setup.md). Keys live in the OS keyring (keys.py), never in this repo.

  Auth: Basic base64("{companyId}+{publicKey}:{privateKey}") + header clientId (registered at developer.connectwise.com)
  Base: https://api-na.myconnectwise.net/v4_6_release/apis/3.0   (cloud NA; the site's codebase from
        https://na.myconnectwise.net/login/companyinfo/{companyId} when it answers)
Endpoints used — all GET: system/info (connection test) · service/tickets/{id} (then project/tickets/{id}) ·
service/tickets/{id}/configurations · company/configurations?conditions=company/id=N (the Configurations tab).
"""
import base64
import json
import time
import urllib.error
import urllib.parse
import urllib.request

SITE = "na.myconnectwise.net"
DEFAULT_BASE = "https://api-na.myconnectwise.net/v4_6_release/apis/3.0"
TIMEOUT = 8
_codebase = {}                                                 # companyId → discovered API base


class CWError(Exception):
    """A lookup failed; str() is a plain-English explanation (and who can fix it)."""


def base_url(creds):
    if creds.get("base"):                                      # override (tests, self-hosted)
        return creds["base"].rstrip("/")
    cid = creds["company"]
    if cid not in _codebase:
        try:
            with urllib.request.urlopen(f"https://{SITE}/login/companyinfo/{urllib.parse.quote(cid)}", timeout=TIMEOUT) as r:
                info = json.load(r)
            code, host = (info.get("Codebase") or "").strip("/"), info.get("SiteUrl") or "api-na.myconnectwise.net"
            _codebase[cid] = f"https://{host}/{code}/apis/3.0" if code else DEFAULT_BASE
        except (OSError, ValueError):
            _codebase[cid] = DEFAULT_BASE
    return _codebase[cid]


def _get(creds, path, params=None):
    for k in ("company", "public", "private", "client_id"):
        if not creds.get(k):
            raise CWError("ConnectWise isn't set up on this PC yet — open Settings")
    token = base64.b64encode(f"{creds['company']}+{creds['public']}:{creds['private']}".encode()).decode()
    url = base_url(creds) + "/" + path.lstrip("/") + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"Authorization": "Basic " + token, "clientId": creds["client_id"],
                                               "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise CWError("ConnectWise rejected the API keys — check them in Settings (Company ID, public and private key)")
        if e.code == 403:
            raise CWError(f"the API member isn't allowed to read {path.split('/')[0]} records — ConnectWise admin: add Inquire "
                          "permission to its security role (docs/connectwise-setup.md)")
        if e.code == 404:
            raise LookupError(path)
        raise CWError(f"ConnectWise answered {e.code} — try again in a minute")
    except (urllib.error.URLError, OSError) as e:
        raise CWError(f"can't reach ConnectWise ({getattr(e, 'reason', e)}) — check the internet connection")


def test(creds):
    """Connection + permission check for Settings: → {ok, version, checks: [{what, ok, message}]}."""
    info = _get(creds, "system/info")
    checks = []
    for what, path in (("tickets", "service/tickets"), ("companies", "company/companies"),
                       ("configurations", "company/configurations")):
        try:
            _get(creds, path, {"pageSize": 1, "fields": "id"})
            checks.append({"what": what, "ok": True, "message": "can read"})
        except CWError as e:
            checks.append({"what": what, "ok": False, "message": str(e)})
    return {"ok": all(c["ok"] for c in checks), "version": info.get("version", ""), "checks": checks}


_cache = {}                                                    # ticket → (time, result): typing/Tab re-asks within seconds


def ticket(creds, number):
    """Ticket #number → {ticket, company, companyId, contact, summary, status, board, type}. Service tickets first,
    then project tickets. LookupError if there's no such ticket."""
    n = str(number).strip().lstrip("#")
    if not n.isdigit():
        raise LookupError(n)
    hit = _cache.get(n)
    if hit and time.time() - hit[0] < 60:
        return hit[1]
    fields = "id,summary,company/id,company/name,contact/name,contactName,status/name,board/name,type/name"
    t, kind = None, "service"
    try:
        t = _get(creds, f"service/tickets/{n}", {"fields": fields})
    except LookupError:
        try:
            t, kind = _get(creds, f"project/tickets/{n}", {"fields": fields.replace(",type/name", "")}), "project"
        except LookupError:
            raise LookupError(n)
    company = t.get("company") or {}
    res = {"ticket": t.get("id"), "company": company.get("name", ""), "companyId": company.get("id"),
           "contact": (t.get("contact") or {}).get("name") or t.get("contactName") or "",
           "summary": t.get("summary", ""), "status": (t.get("status") or {}).get("name", ""),
           "board": (t.get("board") or {}).get("name", ""), "kind": kind}
    _cache[n] = (time.time(), res)
    return res


def device(creds, serial):
    """Configurations with this serial number, any company (read-only): [{id, name, type, serial, model, manufacturer,
    company, companyId}] — "been here before?" for a device that's dropped off."""
    s = str(serial).strip()
    if not s or not all(c.isalnum() or c in "-_./ " for c in s) or len(s) > 60:
        return []
    rows = _get(creds, "company/configurations", {
        "conditions": f'serialNumber="{s}"', "pageSize": 10,
        "fields": "id,name,type/name,serialNumber,modelNumber,manufacturer/name,company/id,company/name"})
    return [{"id": c.get("id"), "name": c.get("name", ""), "type": (c.get("type") or {}).get("name", ""),
             "serial": c.get("serialNumber") or "", "model": c.get("modelNumber") or "",
             "manufacturer": (c.get("manufacturer") or {}).get("name", ""),
             "company": (c.get("company") or {}).get("name", ""), "companyId": (c.get("company") or {}).get("id")} for c in rows]


def configurations(creds, company_id, ticket_no=None):
    """The company's configurations (Configurations tab), the ticket's own ones first. [{id, name, type, serial,
    model, manufacturer, onTicket}]"""
    linked = set()
    if ticket_no:
        try:
            linked = {c.get("id") for c in _get(creds, f"service/tickets/{int(ticket_no)}/configurations",
                                                 {"fields": "id", "pageSize": 100})}
        except (LookupError, CWError, ValueError):
            pass
    rows = _get(creds, "company/configurations", {
        "conditions": f"company/id={int(company_id)} and activeFlag=true", "orderBy": "name asc", "pageSize": 200,
        "fields": "id,name,type/name,serialNumber,modelNumber,tagNumber,manufacturer/name"})
    out = [{"id": c.get("id"), "name": c.get("name", ""), "type": (c.get("type") or {}).get("name", ""),
            "serial": c.get("serialNumber") or "", "model": c.get("modelNumber") or "",
            "manufacturer": (c.get("manufacturer") or {}).get("name", ""), "onTicket": c.get("id") in linked} for c in rows]
    return sorted(out, key=lambda c: (not c["onTicket"], c["name"].lower()))
