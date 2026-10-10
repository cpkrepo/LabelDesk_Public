# LabelDesk — ConnectWise integration (dev notes)

## ConnectWise (0.4)
- Cloud, **na.myconnectwise.net** → API `https://api-na.myconnectwise.net/v4_6_release/apis/3.0` (codebase discovered
  via `na.myconnectwise.net/login/companyinfo/{companyId}` when it answers). Auth: Basic `companyId+public:private`
  + `clientId` header. **The shop owner administers ConnectWise**; the user has no System menu → setup via
  docs/connectwise-setup.md. Read-only role; LabelDesk never writes to ConnectWise (ask before adding any write).
- Tag = **company name** (bold), with the optional **customer name** after it on the same line ("Destify - Chris
  Killion"; contact; "On the tag" checkbox, remembered per PC; left off when the company already is that name — a home
  customer's company IS their name) + Received + Ticket#. Ticket # is the first field; lookup 450 ms after typing; fields typed by hand are never replaced.
- **Optional and invisible unless ON** (owner must approve it; LabelDesk must work fully without it): `on` = keys stored
  AND a live read-only check passes (cached 10 min). Off → no ConnectWise text anywhere, no ConnectWise calls at all.
  Setup card appears only with keys stored or at `…/#connectwise` (Settings). Keep it that way.
- Keys are entered per PC in Settings, stored in the OS keyring, the private key never returned to the browser.
  Never ask the user to paste keys into chat.
- Not yet tested against the real ConnectWise (no keys yet) — only tests/fake_connectwise.py. First real test:
  Settings → Test connection, then a known ticket.
- 0.10 (O): `connectwise.device()` = company/configurations?conditions=serialNumber="…" (any company; serial limited to
  [A-Za-z0-9-_./ ] so nothing can be injected into the condition). Not yet tried against the real ConnectWise — check the
  condition syntax there on first use. "Picked up" (P) is LabelDesk's own record (printed.collected), never written to CW.

