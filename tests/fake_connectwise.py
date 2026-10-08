#!/usr/bin/env python3
"""A stand-in for the ConnectWise PSA REST API (the few endpoints LabelDesk reads), for tests and for trying the UI
without real keys:  python3 tests/fake_connectwise.py [port]  →  LABELDESK_CW_BASE=http://127.0.0.1:<port>/v4_6_release/apis/3.0

Accepts company "shop", public "pub", private "priv", clientId "client" (anything else → 401). Tickets:
  75013 Acme Dental Group / Jane Smith · 75020 residential (company "Walk-In Customers", contact Bob Jones)
  81000 a project ticket · 99999 → 404.  Configurations are forbidden (403) for company 250 to test permission errors.
"""
import base64
import json
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

AUTH = "Basic " + base64.b64encode(b"shop+pub:priv").decode()
TICKETS = {
    75013: {"id": 75013, "summary": "Laptop won't boot", "company": {"id": 101, "name": "Acme Dental Group"},
            "contact": {"id": 7, "name": "Jane Smith"}, "status": {"name": "In Progress"}, "board": {"name": "Bench"},
            "type": {"name": "Repair"}},
    75020: {"id": 75020, "summary": "Virus removal", "company": {"id": 250, "name": "Walk-In Customers"},
            "contactName": "Bob Jones", "status": {"name": "New"}, "board": {"name": "Bench"}},
}
PROJECT = {81000: {"id": 81000, "summary": "Office move", "company": {"id": 101, "name": "Acme Dental Group"},
                   "contact": {"name": "Dr. Lee"}, "status": {"name": "Open"}, "board": {"name": "Projects"}}}
CONFIGS = {101: [
    {"id": 1, "name": "ACME-FRONT-01", "type": {"name": "Workstation"}, "serialNumber": "5CG123", "modelNumber": "EliteDesk 800",
     "manufacturer": {"name": "HP"}},
    {"id": 2, "name": "ACME-LT-07", "type": {"name": "Laptop"}, "serialNumber": "PF2ABC", "modelNumber": "ThinkPad T14",
     "manufacturer": {"name": "Lenovo"}}]}
TICKET_CONFIGS = {75013: [{"id": 2}]}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        path, q = u.path.split("/apis/3.0/", 1)[-1], urllib.parse.parse_qs(u.query)
        if self.headers.get("Authorization") != AUTH or self.headers.get("clientId") != "client":
            return self.reply(401, {"code": "Unauthorized"})
        if path == "system/info":
            return self.reply(200, {"version": "v2025.1.12345", "isCloud": True})
        if path in ("service/tickets", "company/companies", "company/configurations") and "conditions" not in q:
            return self.reply(200, [{"id": 1}])
        parts = path.split("/")
        if parts[:2] == ["service", "tickets"] and len(parts) >= 3 and parts[2].isdigit():
            t = TICKETS.get(int(parts[2]))
            if not t:
                return self.reply(404, {"code": "NotFound"})
            if len(parts) == 4 and parts[3] == "configurations":
                return self.reply(200, TICKET_CONFIGS.get(t["id"], []))
            return self.reply(200, t)
        if parts[:2] == ["project", "tickets"] and len(parts) == 3:
            t = PROJECT.get(int(parts[2]))
            return self.reply(200, t) if t else self.reply(404, {"code": "NotFound"})
        if path == "company/configurations":
            cid = int(q["conditions"][0].split("company/id=")[1].split()[0])
            if cid == 250:
                return self.reply(403, {"code": "Forbidden"})
            return self.reply(200, CONFIGS.get(cid, []))
        self.reply(404, {"code": "NotFound"})


def serve(port=0):
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    return srv


if __name__ == "__main__":
    s = serve(int(sys.argv[1]) if len(sys.argv) > 1 else 18900)
    print(f"fake ConnectWise on http://127.0.0.1:{s.server_port}/v4_6_release/apis/3.0", flush=True)
    s.serve_forever()
