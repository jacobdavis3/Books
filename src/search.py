#!/usr/bin/env python3
"""
One search bar, four library catalogs.

Run:    pip install requests beautifulsoup4
        python library_search.py
Then open http://localhost:8765 in your browser.

Troubleshoot one library from the terminal (prints the raw responses):
        python library_search.py --debug "secret history"

Each search sends one request per library (a couple more for the Vega
catalogs on the very first search while it finds the right address),
only when you search.
"""

import json
import os
import re
import socket
import sys
import uuid
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote, quote_plus, urlparse, parse_qs, urljoin

import requests
from bs4 import BeautifulSoup

PORT = 8765
TIMEOUT = 15
MAX_RESULTS = 10
UA = "Mozilla/5.0 (personal multi-library search)"
DEBUG = False

# ---------------------------------------------------------------------------
# YOUR LIBRARIES
#   kind "vega"      -> Innovative Vega Discover catalogs (NYPL, DCPL)
#   kind "sierra"    -> classic Sierra WebPAC catalog page (Society Library)
#   kind "princeton" -> Princeton's public JSON search API
#   "link" is the results page the "Open full results" link goes to.
# ---------------------------------------------------------------------------
LIBRARIES = [
    {
        "name": "DC Public Library",
        "kind": "vega",
        "host": "catalog.dclibrary.org",
        "tenant": None,  # e.g. "dcpl.na2" -- found automatically if left as None
        "link": "https://catalog.dclibrary.org/search?query={q}&searchType=everything&pageSize=10",
    },
    {
        "name": "New York Public Library",
        "kind": "vega",
        "host": "borrow.nypl.org",
        "tenant": "nypl.na2",
        "link": "https://borrow.nypl.org/search?query={q}&searchType=everything&pageSize=10",
    },
    {
        "name": "New York Society Library",
        "kind": "sierra",
        "search_url": "https://library.nysoclib.org/search~/a?searchtype=Y&SORT=R&searcharg={q}",
        "link": "https://library.nysoclib.org/search~/a?searchtype=Y&SORT=R&searcharg={q}",
    },
    {
        "name": "Princeton University Library",
        "kind": "princeton",
        "link": "https://catalog.princeton.edu/catalog?q={q}&search_field=all_fields",
    },
]


def log(*a):
    if DEBUG:
        print(*a, file=sys.stderr)


def result(title="", author="", fmt="", location="", call_number="", status="", url=""):
    return {"title": title, "author": author, "format": fmt, "location": location,
            "call_number": call_number, "status": status, "url": url}


# ---------------------------------------------------------------------------
# Princeton
# ---------------------------------------------------------------------------

def search_princeton(lib, q):
    r = requests.get("https://allsearch-api.princeton.edu/search/catalog",
                     params={"query": q}, headers={"User-Agent": UA}, timeout=TIMEOUT)
    log("Princeton", r.status_code, r.text[:1500])
    r.raise_for_status()
    return parse_princeton(r.json())


def parse_princeton(data):
    out = []
    for rec in (data.get("records") or [])[:MAX_RESULTS]:
        f = rec.get("other_fields") or {}
        out.append(result(rec.get("title", ""), rec.get("creator", ""), rec.get("type", ""),
                          f.get("first_library", ""), f.get("first_call_number", ""),
                          f.get("first_status", ""), rec.get("url", "")))
    return out


# ---------------------------------------------------------------------------
# Sierra WebPAC (New York Society Library)
# ---------------------------------------------------------------------------

def search_sierra(lib, q):
    url = lib["search_url"].replace("{q}", quote_plus(q))
    r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
    log("Sierra", r.status_code, r.url, r.text[:1500])
    r.raise_for_status()
    return parse_sierra(r.text, r.url)


def _text(el):
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)) if el else ""


def _sierra_items(scope):
    row = scope.select_one("tr.bibItemsEntry")
    if not row:
        return "", "", ""
    cells = [_text(td) for td in row.find_all("td")] + ["", "", ""]
    return cells[0], cells[1], cells[2]


def parse_sierra(html, page_url):
    soup = BeautifulSoup(html, "html.parser")
    out = []
    rows = soup.select("tr.briefCitRow, td.briefCitRow, div.briefCitRow")
    if rows:
        for row in rows[:MAX_RESULTS]:
            # standard layout has a .briefcitTitle; customized layouts (like the
            # Society Library's) just use the first text link in the row
            a = row.select_one(".briefcitTitle a") or next(
                (x for x in row.find_all("a", href=True)
                 if _text(x) and not x.find("button")), None)
            if not a:
                continue
            title = _text(a)
            cell = row.select_one(".briefcitDetail") or a.find_parent("td") or row
            lines = [l.strip() for l in cell.get_text("\n").split("\n") if l.strip()]
            after = lines[lines.index(title) + 1:] if title in lines else lines
            author = next((l for l in after if not l.lower().startswith("availability")), "")

            img = row.select_one(".briefcitMedia img") or row.find("img", alt=True)
            fmt = humanize(img.get("alt", "")) if img else ""
            if fmt.lower().startswith(("most relevant", "very relevant", "other relevant")):
                fmt = ""

            loc, call, status = _sierra_items(row)
            if not status:  # "Availability: 1 copy available at Stack 2 Oversize"
                m = re.search(r"Availability:\s*(.+)", _text(cell), re.I)
                if m:
                    avail = m.group(1).strip()
                    parts = re.split(r"\s+at\s+", avail, maxsplit=1)
                    status = parts[0]
                    loc = loc or (parts[1] if len(parts) > 1 else "")
            out.append(result(title, author, fmt, loc, call, humanize(status),
                              urljoin(page_url, a.get("href", ""))))
        return out

    # one match: the catalog jumps straight to the record page
    fields = {}
    for tr in soup.select("table.bibDetail tr"):
        label, data = tr.select_one(".bibInfoLabel"), tr.select_one(".bibInfoData")
        if label and data:
            fields.setdefault(_text(label).lower(), _text(data))
    if fields.get("title"):
        loc, call, status = _sierra_items(soup)
        out.append(result(fields["title"], fields.get("author", ""), "", loc, call, status, page_url))
    return out


# ---------------------------------------------------------------------------
# Vega Discover (NYPL, DCPL)
#   API host: https://<region>.iiivega.com, anonymous, with the headers below
#   (confirmed from the open-source libcat project). The keyword-search call
#   isn't documented anywhere public, so a few likely shapes are tried in
#   turn; the one that works is remembered for later searches.
# ---------------------------------------------------------------------------

REGIONS = ["na", "na2", "na3", "na4", "na5", "na6", "ca"]
# catalog codes to guess if a library's code can't be looked up
SITE_GUESSES = {"catalog.dclibrary.org": ["dcpl", "dclibrary", "dcpubliclibrary", "dcpls", "dc"]}
ANON_ID = str(uuid.uuid4())
CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "library_search_cache.json")
TENANT_RE = re.compile(r"([a-z0-9-]+)\.((?:na|ca|eu|au)\d*)\.iiivega\.com", re.I)


def _load_cache():
    try:
        with open(CACHE_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_cache():
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(_vega_cache, f, indent=2)
    except OSError:
        pass


_vega_cache = _load_cache()  # host -> {"tenant": ..., "working": [api_host, customer_domain, attempt]}


def _vega_headers(customer_domain, api_version):
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": f"https://{customer_domain}",
        "Referer": f"https://{customer_domain}/",
        "iii-customer-domain": customer_domain,
        "iii-host-domain": customer_domain,
        "Anonymous-User-Id": ANON_ID,
        "api-version": api_version,
        "User-Agent": UA,
    }


def _search_body(q):
    return {"searchText": q, "sorting": "relevance", "sortOrder": "asc",
            "searchType": "everything", "pageNum": 0, "pageSize": MAX_RESULTS,
            "resourceType": "FormatGroup"}


# (method, path, api-version, how the query is sent)
ATTEMPTS = [
    ("POST", "/api/search-result/search/format-groups", "1", "body"),
    ("POST", "/api/search-result/search/format-groups", "2", "body"),
    ("GET", "/api/search-result/search/format-groups", "1", "params"),
    ("GET", "/api/search-result/search/format-groups", "2", "params"),
]


def _find_tenant(lib):
    """Work out <site>.<region> for a custom-domain Vega catalog."""
    host = lib["host"]
    if lib.get("tenant"):
        return lib["tenant"]
    if _vega_cache.get(host, {}).get("tenant"):
        return _vega_cache[host]["tenant"]
    found = None
    # 1) the custom domain usually points (via DNS) at <site>.<region>.iiivega.com
    try:
        name, aliases, _ = socket.gethostbyname_ex(host)
        log("Vega DNS:", name, aliases)
        for n in [name] + aliases:
            m = TENANT_RE.search(n)
            if m:
                found = f"{m.group(1).lower()}.{m.group(2).lower()}"
                break
    except OSError as e:
        log("Vega DNS lookup failed:", e)
    # 2) or the catalog's own page names it
    if not found:
        try:
            html = requests.get(f"https://{host}/", headers={"User-Agent": UA}, timeout=TIMEOUT).text
            m = TENANT_RE.search(html)
            if m:
                found = f"{m.group(1).lower()}.{m.group(2).lower()}"
        except requests.RequestException as e:
            log("Vega page fetch failed:", e)
    if found:
        log("Vega tenant:", found)
        _vega_cache.setdefault(host, {})["tenant"] = found
        _save_cache()
    return found


def _vega_targets(lib):
    """(api_host, customer_domain) pairs to try, best guess first."""
    tenant = _find_tenant(lib)
    if tenant:
        site, region = tenant.split(".", 1)
        return [(f"{region}.iiivega.com", f"{site}.{region}.iiivega.com"),
                (f"{region}.iiivega.com", lib["host"])]
    targets = [(f"{r}.iiivega.com", lib["host"]) for r in REGIONS]
    for site in SITE_GUESSES.get(lib["host"], []):
        targets += [(f"{r}.iiivega.com", f"{site}.{r}.iiivega.com") for r in REGIONS]
    return targets


def _vega_request(api_host, customer_domain, attempt, q):
    method, path, ver, mode = attempt
    url = f"https://{api_host}{path}"
    h = _vega_headers(customer_domain, ver)
    if mode == "body":
        r = requests.request(method, url, headers=h, json=_search_body(q), timeout=TIMEOUT)
    else:
        params = {k: v for k, v in _search_body(q).items()}
        r = requests.request(method, url, headers=h, params=params, timeout=TIMEOUT)
    log(f"Vega {method} {url} [{customer_domain}] v{ver} -> {r.status_code}: {r.text[:800]}")
    return r


def search_vega(lib, q):
    host = lib["host"]
    cached = _vega_cache.get(host, {})
    if "working" in cached:
        api_host, cust, idx = cached["working"]
        try:
            r = _vega_request(api_host, cust, ATTEMPTS[idx], q)
            r.raise_for_status()
            return parse_vega(r.json(), host)
        except (requests.RequestException, ValueError):
            cached.pop("working", None)  # address changed; rediscover below

    last, unreachable = None, set()
    for api_host, cust in _vega_targets(lib):
        if api_host in unreachable:
            continue
        for idx, attempt in enumerate(ATTEMPTS):
            try:
                r = _vega_request(api_host, cust, attempt, q)
            except requests.RequestException:
                unreachable.add(api_host)  # that regional host doesn't exist
                break
            if r.status_code == 200 and "json" in r.headers.get("Content-Type", ""):
                data = r.json()
                if _vega_records(data) is not None:
                    _vega_cache.setdefault(host, {})["working"] = [api_host, cust, idx]
                    _save_cache()
                    return parse_vega(data, host)
            last = f"{api_host} as {cust}: HTTP {r.status_code} {r.text[:120]}"
            if r.status_code == 403 and "siteCode" in r.text:
                break  # wrong catalog code; try the next address
    raise RuntimeError(f"couldn't find this catalog's search address (last reply: {last}). "
                       "Run with --debug and paste the output.")


def _vega_records(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("data", "results", "items", "formatGroups", "content"):
            if isinstance(data.get(key), list):
                return data[key]
    return None


def _first(obj, keys, depth=0):
    """First non-empty value found under any of `keys`, searching nested data."""
    if depth > 5:
        return None
    if isinstance(obj, dict):
        for k in keys:
            v = obj.get(k)
            if v not in (None, "", [], {}):
                return v
        for v in obj.values():
            found = _first(v, keys, depth + 1)
            if found not in (None, "", [], {}):
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = _first(v, keys, depth + 1)
            if found not in (None, "", [], {}):
                return found
    return None


def _as_text(v):
    if isinstance(v, list):
        v = v[0] if v else ""
    if isinstance(v, dict):
        v = v.get("label") or v.get("name") or v.get("value") or v.get("general") or ""
    return str(v or "")


def humanize(s):
    """'CheckedOut' / 'CHECKED_OUT' -> 'Checked out'."""
    s = str(s or "").strip()
    if not s:
        return ""
    s = s.replace("_", " ")
    s = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s)
    return s[:1].upper() + s[1:].lower() if s.isupper() or " " in s else s


def _tab_status(tab):
    return humanize(_as_text(_first(tab, ["general"]) or _first(tab, ["availabilityStatus", "status"])))


def parse_vega(data, host):
    out = []
    for rec in (_vega_records(data) or [])[:MAX_RESULTS]:
        title = _as_text(rec.get("title") or rec.get("$title") or _first(rec, ["title", "$title"]))
        author = _as_text(rec.get("primaryAgent") or _first(rec, ["primaryAgent", "author", "creator"]))
        tabs = [t for t in (rec.get("materialTabs") or []) if isinstance(t, dict)]
        formats = [{"name": t.get("name") or t.get("type") or "", "status": _tab_status(t)} for t in tabs]
        fmt = ", ".join(dict.fromkeys(f["name"] for f in formats if f["name"])) or _as_text(
            _first(rec, ["materialType", "format"]))
        status = next((f["status"] for f in formats if f["status"]), "") or humanize(
            _as_text(_first(rec, ["general", "availabilityStatus"])))
        rid = rec.get("id", "")
        url = f"https://{host}/search/card?recordId={quote(str(rid))}&entityType=FormatGroup" if rid else ""
        r = result(title, author, fmt, "", "", status, url)
        if len(formats) > 1:
            r["formats"] = formats
        out.append(r)
    return out


# ---------------------------------------------------------------------------
# Search everything
# ---------------------------------------------------------------------------

ADAPTERS = {"princeton": search_princeton, "sierra": search_sierra, "vega": search_vega}


def run_library(lib, q):
    out = {"name": lib["name"], "link": lib["link"].replace("{q}", quote_plus(q)),
           "results": [], "error": None}
    try:
        out["results"] = ADAPTERS[lib["kind"]](lib, q)
    except Exception as e:  # one library failing never breaks the others
        out["error"] = f"{type(e).__name__}: {e}"
    return out


def search_all(q):
    with ThreadPoolExecutor(max_workers=len(LIBRARIES)) as pool:
        return list(pool.map(lambda lib: run_library(lib, q), LIBRARIES))


# ---------------------------------------------------------------------------
# Web page
# ---------------------------------------------------------------------------

PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Library Search</title>
<style>
:root{--bg:#f7f5f0;--card:#fff;--ink:#1d1d1b;--mute:#6b6a65;--line:#e4e1d8;--acc:#2f5d50;--ok:#2e7d32;--wait:#a15c00}
@media (prefers-color-scheme:dark){:root{--bg:#161614;--card:#21211e;--ink:#eeece6;--mute:#a3a19a;--line:#34332f;--acc:#7fb8a6;--ok:#81c784;--wait:#e0a050}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.45 system-ui,-apple-system,sans-serif}
main{max-width:1200px;margin:0 auto;padding:32px 16px}
h1{font:600 26px/1.2 Georgia,serif;margin:0 0 16px}
form{display:flex;gap:8px;margin-bottom:24px}
input{flex:1;min-width:0;padding:12px 14px;font-size:17px;border:1px solid var(--line);border-radius:10px;background:var(--card);color:var(--ink)}
button{padding:12px 20px;font-size:16px;border:0;border-radius:10px;background:var(--acc);color:#fff;cursor:pointer}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}
.lib{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px}
.lib h2{font-size:16px;margin:0 0 2px}.lib .open{font-size:13px;color:var(--acc)}
.count{font-size:13px;color:var(--mute)}
.item{border-top:1px solid var(--line);padding:10px 0}
.item a{color:var(--ink);font-weight:600;text-decoration:none}.item a:hover{text-decoration:underline}
.meta{font-size:14px;color:var(--mute)}
.status{font-size:13px;font-weight:600}.status.ok{color:var(--ok)}.status.no{color:var(--wait)}
.note{font-size:14px;color:var(--mute);margin-top:8px}
.filters{margin:-12px 0 20px;font-size:15px;color:var(--mute)}
select{margin-left:6px;padding:6px 8px;font-size:15px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink)}
.fmtline{display:flex;gap:6px;align-items:baseline}
</style></head><body><main>
<h1>Search all my libraries</h1>
<form id="f"><input id="q" placeholder="Title, author, or keyword" autofocus><button>Search</button></form>
<div class="filters"><label>Show
  <select id="fmt">
    <option value="all">All formats</option>
    <option value="noaudio">Everything except audiobooks</option>
    <option value="print">Print books only</option>
  </select></label></div>
<div id="out" class="grid"></div>
</main><script>
const esc=s=>String(s||"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const okWords=/avail|on shelf|in library|check shelf/i, noWords=/not avail|unavail|checked out|due |on hold|\b0 cop|no cop/i;
const AUDIO=/audio|sound recording|spoken|playaway|\bcd\b|music/i, DIGITAL=/^e[- ]?(book|audio|magazine|video|comic|music)|electronic|online|digital|kindle|stream|internet/i;
const fmtSel=document.getElementById("fmt");
try{fmtSel.value=localStorage.getItem("fmt")||"all"}catch(e){}
let last=null;

function keepFormat(name){
  if(!name) return true;              // unknown format: keep it
  const mode=fmtSel.value;
  if(mode==="all") return true;
  if(AUDIO.test(name)) return false;
  if(mode==="print" && DIGITAL.test(name.trim())) return false;
  return true;
}
function filterResult(r){
  if(r.formats){                       // several formats: keep only the wanted ones
    const kept=r.formats.filter(f=>keepFormat(f.name));
    if(!kept.length) return null;
    return {...r,formats:kept};
  }
  const names=(r.format||"").split(/,\s*/).filter(Boolean);
  if(names.length && !names.some(keepFormat)) return null;
  return r;
}
const statusDiv=s=>s?`<div class="status ${okWords.test(s)&&!noWords.test(s)?"ok":"no"}">${esc(s)}</div>`:"";

function render(){
  const out=document.getElementById("out");
  if(!last){out.innerHTML="";return}
  out.innerHTML=last.map(l=>{
    let body, shown=[];
    if(l.error) body=`<p class="note">Couldn't load results here. Use the link above.<br><small>${esc(l.error)}</small></p>`;
    else{
      shown=l.results.map(filterResult).filter(Boolean);
      if(!l.results.length) body=`<p class="note">No matches.</p>`;
      else if(!shown.length) body=`<p class="note">No matches in this format.</p>`;
      else body=shown.map(r=>`<div class="item">
        ${r.url?`<a href="${esc(r.url)}" target="_blank">${esc(r.title)}</a>`:`<strong>${esc(r.title)}</strong>`}
        <div class="meta">${[r.author, r.formats?"":r.format].filter(Boolean).map(esc).join(" · ")}</div>
        <div class="meta">${[r.location,r.call_number].filter(Boolean).map(esc).join(" · ")}</div>
        ${r.formats? r.formats.map(f=>`<div class="fmtline"><span class="meta">${esc(f.name)}</span> ${statusDiv(f.status)}</div>`).join("") : statusDiv(r.status)}
      </div>`).join("");
    }
    const n=l.error?"":`<span class="count">${shown.length} shown · </span>`;
    return `<section class="lib"><h2>${esc(l.name)}</h2>${n}
      <a class="open" href="${esc(l.link)}" target="_blank">Open full results ↗</a>${body}</section>`;
  }).join("");
}
fmtSel.onchange=()=>{try{localStorage.setItem("fmt",fmtSel.value)}catch(e){} render()};

document.getElementById("f").onsubmit=async e=>{
  e.preventDefault();const q=document.getElementById("q").value.trim();if(!q)return;
  const out=document.getElementById("out");out.innerHTML="<p class='note'>Searching all four…</p>";
  try{last=await (await fetch("/api/search?q="+encodeURIComponent(q))).json()}
  catch(err){last=null;out.innerHTML="<p class='note'>The search program isn't responding. Is it still running?</p>";return}
  render();
};
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/api/search":
            q = (parse_qs(u.query).get("q") or [""])[0].strip()
            self._send(200, "application/json", json.dumps(search_all(q) if q else []).encode())
        elif u.path == "/":
            self._send(200, "text/html; charset=utf-8", PAGE.encode())
        else:
            self._send(404, "text/plain", b"not found")

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def main():
    global DEBUG
    if len(sys.argv) > 1 and sys.argv[1] == "--debug":
        DEBUG = True
        q = " ".join(sys.argv[2:]) or "secret history"
        for lib in search_all(q):
            print(f"\n=== {lib['name']} ===")
            print("error:", lib["error"]) if lib["error"] else None
            for r in lib["results"]:
                print(" -", r["title"], "|", r["author"], "|", r["format"], "|", r["status"])
        return
    url = f"http://localhost:{PORT}"
    print(f"Library search running at {url}  (Ctrl+C to stop)")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()