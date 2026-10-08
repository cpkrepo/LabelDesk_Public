# Connecting LabelDesk to ConnectWise — for the ConnectWise admin

LabelDesk prints the shop's inventory tags. With ConnectWise connected, staff type a **ticket number** and the tag's
**company** and **customer name** fill in from ConnectWise — no retyping. LabelDesk only **reads** tickets, companies,
contacts and configurations; the role below gives it no way to change anything.

## What LabelDesk does and doesn't do
- **It's optional and off by default.** LabelDesk prints tags and shipping labels with no ConnectWise at all; nothing
  about ConnectWise shows on screen until a PC has working keys.
- **Local only.** Each PC runs its own copy; it answers only on that PC (127.0.0.1) and rejects requests from other
  sites or machines. There's no LabelDesk server, cloud service or shared database.
- **Read-only.** It only ever sends `GET` requests (tickets, companies, contacts, configurations); there is no code that
  creates, edits or deletes anything, and the role below doesn't allow it anyway.
- **Talks to ConnectWise and nothing else** (apart from asking GitHub for the newest LabelDesk version number after a
  print, which carries nothing from ConnectWise or the labels). With keys, the only
  traffic is those `GET`s to your ConnectWise, when someone types a ticket # (plus a connection check).
- **Keys stay on the PC,** encrypted by the OS (Windows: DPAPI for that user; Fedora: the login keyring). The private
  key is never shown again or sent anywhere but ConnectWise. Revoke the API member's keys and it simply turns off.

It takes about 10 minutes and three things: a read-only **security role**, an **API member** with **API keys**, and a
free **Client ID** from ConnectWise's developer site. (Menu names are from the current cloud version; they may differ
slightly on your screen.)

## 1. A read-only security role
**System → Security Roles → + (New)** — name it `LabelDesk (read-only)`. Set **Inquire = All** on these, and leave
**Add / Edit / Delete = None** everywhere:

| Module | Line | Inquire |
|---|---|---|
| Service Desk | Service Tickets | All |
| Project | Project Tickets | All *(only if tags are made for project tickets)* |
| Companies | Company Maintenance | All |
| Companies | Contacts | All |
| Companies | Configurations | All |

Everything else: None. Save.

## 2. An API member and its keys
1. **System → Members → API Members tab → + (New)**
   - Member ID: `labeldesk` · Member Name: `LabelDesk`
   - **Role ID: `LabelDesk (read-only)`** (the role from step 1) · Level: Corporate
   - fill the required Location / Business Unit / Territory with your defaults → **Save**
2. Open the new member → **API Keys tab → + (New)** → Description: `LabelDesk shop PCs` → **Save**.
3. Copy the **Public Key** and **Private Key** right away — **the private key is shown only once**.

## 3. A Client ID (free)
ConnectWise requires every integration to identify itself with a Client ID:
1. Go to **https://developer.connectwise.com/ClientID** and sign in (create a free developer account if needed).
2. **Create** a Client ID — name `LabelDesk (internal)`, type: internal/private integration.
3. Copy the Client ID (a long code like `1a2b3c4d-…`). It's the same for every PC.

## 4. Enter it on each PC
On each computer: open **LabelDesk → Settings → ConnectWise** and fill in
- **Company ID** — the company name you type on the ConnectWise login screen
- **Client ID** — from step 3
- **Public key** and **Private key** — from step 2

then **Save** and **Test connection**. The test says which of tickets / companies / configurations it can read; if one
shows ✗, that line in the role (step 1) needs Inquire = All.

**Keep the private key out of email and chat.** Type it into each PC yourself, or share it through the company password
manager. LabelDesk stores it in each computer's own secure keyring (Windows: encrypted for the Windows user), sends it
only to ConnectWise, and never shows it again. To revoke access anytime: delete the key on the API member (step 2) —
nothing else in ConnectWise is affected.

## What LabelDesk reads (all read-only, cloud NA: api-na.myconnectwise.net)
`system/info` (connection test) · `service/tickets/{id}` and `project/tickets/{id}` (company, contact, summary, status)
· `service/tickets/{id}/configurations` and `company/configurations` (the customer's devices, for upcoming features).
