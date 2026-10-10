"""Bonjour on Windows through Windows' own DNS-SD API (dnsapi.dll, Windows 10 1809+), via ctypes.

Why not LabelDesk's own multicast query (dymo.browse)? Windows Firewall drops the printers' replies to a per-user app
with no inbound rule (and a per-user install can't add one). The system's DNS Client service does mDNS itself and
already has its firewall rules, so asking it works on a normal shop PC.

  browse(seconds) → [{name, model, ip, port, host}]   DYMO printers announcing _pdl-datastream._tcp (raw port 9100)
  register(name, port, ip) → handle                   announce a fake printer (tests on the Windows VM only)

Structures from WinDNS.h (x64 layout checked in tests/windows/mdns_check.py on Windows 11).
"""
import ctypes
import socket
import struct
import threading
import time
from ctypes import wintypes

import dymo

DNS_QUERY_REQUEST_VERSION1 = 1
DNS_REQUEST_PENDING = 9506
SERVICE = "_pdl-datastream._tcp.local"


class DNS_RECORD(ctypes.Structure):                     # only the head + the first pointer of the Data union (PTR target)
    _fields_ = [("pNext", ctypes.c_void_p), ("pName", ctypes.c_wchar_p), ("wType", wintypes.WORD),
                ("wDataLength", wintypes.WORD), ("Flags", wintypes.DWORD), ("dwTtl", wintypes.DWORD),
                ("dwReserved", wintypes.DWORD), ("pNameHost", ctypes.c_wchar_p)]


class DNS_SERVICE_INSTANCE(ctypes.Structure):
    _fields_ = [("pszInstanceName", ctypes.c_wchar_p), ("pszHostName", ctypes.c_wchar_p),
                ("ip4Address", ctypes.POINTER(wintypes.DWORD)), ("ip6Address", ctypes.c_void_p),
                ("wPort", wintypes.WORD), ("wPriority", wintypes.WORD), ("wWeight", wintypes.WORD),
                ("dwPropertyCount", wintypes.DWORD), ("keys", ctypes.POINTER(ctypes.c_wchar_p)),
                ("values", ctypes.POINTER(ctypes.c_wchar_p)), ("dwInterfaceIndex", wintypes.DWORD)]


BROWSE_CB = ctypes.WINFUNCTYPE(None, wintypes.DWORD, ctypes.c_void_p, ctypes.POINTER(DNS_RECORD))
RESOLVE_CB = ctypes.WINFUNCTYPE(None, wintypes.DWORD, ctypes.c_void_p, ctypes.POINTER(DNS_SERVICE_INSTANCE))
REGISTER_CB = ctypes.WINFUNCTYPE(None, wintypes.DWORD, ctypes.c_void_p, ctypes.POINTER(DNS_SERVICE_INSTANCE))


class DNS_SERVICE_BROWSE_REQUEST(ctypes.Structure):
    _fields_ = [("Version", wintypes.ULONG), ("InterfaceIndex", wintypes.ULONG), ("QueryName", ctypes.c_wchar_p),
                ("pBrowseCallback", BROWSE_CB), ("pQueryContext", ctypes.c_void_p)]


class DNS_SERVICE_RESOLVE_REQUEST(ctypes.Structure):
    _fields_ = [("Version", wintypes.ULONG), ("InterfaceIndex", wintypes.ULONG), ("QueryName", ctypes.c_wchar_p),
                ("pResolveCompletionCallback", RESOLVE_CB), ("pQueryContext", ctypes.c_void_p)]


class DNS_SERVICE_REGISTER_REQUEST(ctypes.Structure):
    _fields_ = [("Version", wintypes.ULONG), ("InterfaceIndex", wintypes.ULONG),
                ("pServiceInstance", ctypes.POINTER(DNS_SERVICE_INSTANCE)), ("pRegisterCompletionCallback", REGISTER_CB),
                ("pQueryContext", ctypes.c_void_p), ("hCredentials", wintypes.HANDLE), ("unicastEnabled", wintypes.BOOL)]


class DNS_SERVICE_CANCEL(ctypes.Structure):
    _fields_ = [("reserved", ctypes.c_void_p)]


def _api():
    d = ctypes.WinDLL("dnsapi")
    for name in ("DnsServiceBrowse", "DnsServiceResolve", "DnsServiceRegister"):
        getattr(d, name).restype = wintypes.DWORD
    d.DnsServiceConstructInstance.restype = ctypes.POINTER(DNS_SERVICE_INSTANCE)
    return d


def _ip(inst):
    if not inst.ip4Address:
        return ""
    return socket.inet_ntoa(struct.pack("<I", inst.ip4Address.contents.value))   # IP4_ADDRESS is stored in network order


def resolve(d, instance_name, wait=3.0):
    """'DYMO LabelWriter 5XL._pdl-datastream._tcp.local' → {host, ip, port, txt} or None."""
    done, out = threading.Event(), {}

    def cb(status, ctx, inst):
        try:
            if status == 0 and inst:
                i = inst.contents
                txt = {i.keys[k]: i.values[k] for k in range(i.dwPropertyCount)} if i.dwPropertyCount else {}
                out.update(host=i.pszHostName or "", ip=_ip(i), port=i.wPort, txt=txt)
                d.DnsServiceFreeInstance(inst)
        finally:
            done.set()
    fn = RESOLVE_CB(cb)
    req = DNS_SERVICE_RESOLVE_REQUEST(DNS_QUERY_REQUEST_VERSION1, 0, instance_name, fn, None)
    cancel = DNS_SERVICE_CANCEL()
    if d.DnsServiceResolve(ctypes.byref(req), ctypes.byref(cancel)) != DNS_REQUEST_PENDING:
        return None
    if not done.wait(wait):
        d.DnsServiceResolveCancel(ctypes.byref(cancel))
        done.wait(1)
    return out or None


def browse(seconds=3.0):
    """→ [{name, model, ip, port, host}] for DYMO printers on _pdl-datastream._tcp. [] when the API isn't there."""
    try:
        d = _api()
    except (OSError, AttributeError):
        return []
    names, lock = set(), threading.Lock()

    def cb(status, ctx, rec):
        try:
            p = rec
            while p:
                r = p.contents
                if r.wType == 12 and r.pNameHost:                 # PTR → an instance of the service
                    with lock:
                        names.add(r.pNameHost)
                p = ctypes.cast(r.pNext, ctypes.POINTER(DNS_RECORD)) if r.pNext else None
        finally:
            if rec:
                d.DnsRecordListFree(rec, 1)
    fn = BROWSE_CB(cb)
    req = DNS_SERVICE_BROWSE_REQUEST(DNS_QUERY_REQUEST_VERSION1, 0, SERVICE, fn, None)
    cancel = DNS_SERVICE_CANCEL()
    if d.DnsServiceBrowse(ctypes.byref(req), ctypes.byref(cancel)) != DNS_REQUEST_PENDING:
        return []
    time.sleep(seconds)
    d.DnsServiceBrowseCancel(ctypes.byref(cancel))
    time.sleep(0.2)
    found = []
    for inst in sorted(names):
        label = inst.split("._", 1)[0]
        info = resolve(d, inst)
        if not info:
            continue
        extra = " ".join(f"{k}={v}" for k, v in info["txt"].items() if k in ("ty", "product", "usb_MDL"))
        model = dymo.model_of(f"{label} {extra} {info['host']}")
        if model and info["ip"]:
            found.append({"name": label, "model": model, "ip": info["ip"], "port": info["port"] or dymo.PORT, "host": info["host"]})
    return found


def register(name, port, ip="127.0.0.1", txt=None):
    """Announce `name` on _pdl-datastream._tcp (the Windows VM test's fake printer). → the instance (keep it alive)."""
    d = _api()
    keys = list((txt or {}).keys())
    karr = (ctypes.c_wchar_p * max(1, len(keys)))(*keys)
    varr = (ctypes.c_wchar_p * max(1, len(keys)))(*[(txt or {})[k] for k in keys])
    addr = wintypes.DWORD(struct.unpack("<I", socket.inet_aton(ip))[0])
    host = socket.gethostname() + ".local"
    inst = d.DnsServiceConstructInstance(f"{name}.{SERVICE}", host, ctypes.byref(addr), None, port, 0, 0,
                                         len(keys), karr, varr)
    done = threading.Event()
    fn = REGISTER_CB(lambda status, ctx, i: done.set())
    req = DNS_SERVICE_REGISTER_REQUEST(DNS_QUERY_REQUEST_VERSION1, 0, inst, fn, None, None, False)
    rc = d.DnsServiceRegister(ctypes.byref(req), None)
    if rc != DNS_REQUEST_PENDING:
        raise OSError(f"DnsServiceRegister: {rc}")
    done.wait(5)
    return (inst, fn, req, karr, varr, addr)                     # keep every buffer alive while announced
