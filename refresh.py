#!/usr/bin/env python3
"""Daily refresh of the free lead-sample site (FMCSA new carriers + SAM.gov set-aside bids).
Stdlib only. Usage: python3 refresh.py <site_dir> [--push]
Shows ~20% of each day's rows; email/phone masked; full feed = Apify actor."""
import json, sys, os, re, csv, html, time, subprocess, datetime as dt, urllib.request, urllib.parse

SITE = "https://nidhi-bhai.github.io/daily-leads"
FMCSA_ACTOR = "https://apify.com/prospect_antechamber/fmcsa-new-carrier-leads"
SAM_ACTOR = "https://apify.com/prospect_antechamber/sam-gov-contract-opportunities"
PDUFA_ACTOR = "https://apify.com/prospect_antechamber/pdufa-fda-catalyst-calendar"
PDUFA_SITE = "https://nidhi-bhai.github.io/pdufa-calendar/"
INDEXNOW_KEY = "7f3c1a9e5b2d4c8f9a0e6b1d3c5f7a92"
UA = {"User-Agent": "Mozilla/5.0 (daily-leads sample builder)", "Accept": "application/hal+json, application/json;q=0.9, */*;q=0.8"}
STATES = {"AL":"Alabama","AK":"Alaska","AZ":"Arizona","AR":"Arkansas","CA":"California","CO":"Colorado","CT":"Connecticut","DE":"Delaware","FL":"Florida","GA":"Georgia","HI":"Hawaii","ID":"Idaho","IL":"Illinois","IN":"Indiana","IA":"Iowa","KS":"Kansas","KY":"Kentucky","LA":"Louisiana","ME":"Maine","MD":"Maryland","MA":"Massachusetts","MI":"Michigan","MN":"Minnesota","MS":"Mississippi","MO":"Missouri","MT":"Montana","NE":"Nebraska","NV":"Nevada","NH":"New Hampshire","NJ":"New Jersey","NM":"New Mexico","NY":"New York","NC":"North Carolina","ND":"North Dakota","OH":"Ohio","OK":"Oklahoma","OR":"Oregon","PA":"Pennsylvania","RI":"Rhode Island","SC":"South Carolina","SD":"South Dakota","TN":"Tennessee","TX":"Texas","UT":"Utah","VT":"Vermont","VA":"Virginia","WA":"Washington","WV":"West Virginia","WI":"Wisconsin","WY":"Wyoming","DC":"District of Columbia"}
SETASIDES = [  # (sam code(s), slug, label)
    ("SBA,SBP", "total-small-business", "Total Small Business Set-Aside"),
    ("8A,8AN", "8a", "8(a) Set-Aside / Sole Source"),
    ("SDVOSBC,SDVOSBS", "sdvosb", "Service-Disabled Veteran-Owned (SDVOSB)"),
    ("WOSB,WOSBSS,EDWOSB,EDWOSBSS", "wosb", "Women-Owned Small Business (WOSB/EDWOSB)"),
    ("HZC,HZS", "hubzone", "HUBZone Set-Aside"),
]

def get(url, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return json.load(r)
        except Exception as e:
            print("retry", i + 1, url[:90], e, file=sys.stderr); time.sleep(3 * (i + 1))
    return None

e = html.escape
def mask_email(m):
    if not m or "@" not in m: return "—"
    u, d = m.split("@", 1); return f"{u[:1]}•••@{d}"
def mask_phone(p):
    d = re.sub(r"\D", "", p or ""); return f"({d[:3]}) •••-••••" if len(d) >= 10 else "—"

# ---------------- data ----------------
def fmcsa(days=7):
    now = dt.datetime.now(dt.timezone.utc); since = (now - dt.timedelta(days=days)).strftime("%Y%m%d")
    where = f"add_date >= '{since}' AND status_code = 'A'"
    base = "https://data.transportation.gov/resource/az4n-8mr2.json?"
    rows, off = [], 0
    while True:
        q = urllib.parse.urlencode({"$where": where, "$order": "add_date DESC, dot_number DESC", "$limit": 5000, "$offset": off})
        d = get(base + q)
        if not d: break
        rows += d; off += 5000
        if len(d) < 5000: break
    out = []
    for r in rows:
        ad = r.get("add_date") or ""
        cls = [c.strip().title() for c in (r.get("classdef") or "").split(";") if c.strip()]
        out.append({"dot": r.get("dot_number"), "name": r.get("legal_name"), "added": f"{ad[:4]}-{ad[4:6]}-{ad[6:8]}" if len(ad) == 8 else "",
                    "city": (r.get("phy_city") or "").title(), "state": r.get("phy_state") or "", "units": r.get("power_units") or "",
                    "drivers": r.get("total_drivers") or "", "forhire": any("Authorized For Hire" in c for c in cls),
                    "hazmat": r.get("hm_ind") == "Y", "email": (r.get("email_address") or "").lower(), "phone": r.get("phone") or ""})
    return out, since

def sam_setaside(codes, n_detail):
    p = {"index": "opp", "page": 0, "size": 100, "mode": "search", "sort": "-modifiedDate", "is_active": "true", "set_aside": codes}
    d = get("https://sam.gov/api/prod/sgs/v1/search/?" + urllib.parse.urlencode(p))
    if not d: return 0, []
    total = (d.get("page") or {}).get("totalElements", 0)
    now = dt.datetime.now(dt.timezone.utc); res = []
    for r in (d.get("_embedded") or {}).get("results") or []:
        if r.get("isCanceled"): continue
        due = r.get("responseDateActual") or r.get("responseDate")
        try: dd = dt.datetime.fromisoformat(due.replace("Z", "+00:00")) if due else None
        except Exception: dd = None
        if dd and dd.tzinfo is None: dd = dd.replace(tzinfo=dt.timezone.utc)
        if dd and dd < now: continue
        org = [o.get("name") for o in sorted(r.get("organizationHierarchy") or [], key=lambda o: o.get("level", 0))]
        res.append({"id": r.get("_id"), "title": r.get("title"), "type": (r.get("type") or {}).get("value") or "",
                    "agency": org[0] if org else "", "sub": org[1] if len(org) > 1 else "", "posted": (r.get("publishDate") or "")[:10],
                    "due": dd.strftime("%Y-%m-%d") if dd else "", "days": (dd - now).days if dd else None,
                    "url": f"https://sam.gov/opp/{r.get('_id')}/view", "naics": "", "pop": "", "contact": ""})
    for row in res[:n_detail]:
        x = get("https://sam.gov/api/prod/opps/v2/opportunities/" + row["id"], tries=2) or {}
        d2 = x.get("data2") or {}
        row["naics"] = ",".join(c for nn in d2.get("naics") or [] for c in (nn.get("code") or []))
        pop = d2.get("placeOfPerformance") or {}
        row["pop"] = ", ".join(filter(None, [(pop.get("city") or {}).get("name"), (pop.get("state") or {}).get("code")]))
        em = [p.get("email") for p in d2.get("pointOfContact") or [] if p.get("email")]
        row["contact"] = em[0].lower() if em else ""
    return total, res

# ---------------- html ----------------
CSS = """body{font:16px/1.55 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;color:#111;background:#fafaf7}
main{max-width:1050px;margin:auto;padding:22px}h1{font-size:30px;line-height:1.2;margin:.2em 0}h2{margin-top:1.6em}
.hook{background:#111;color:#fff;padding:18px 22px;border-radius:12px}.hook b{color:#f5c518}
.cta{display:inline-block;background:#f5c518;color:#111;font-weight:700;padding:12px 18px;border-radius:10px;text-decoration:none;margin:8px 0}
table{border-collapse:collapse;width:100%;font-size:14px;background:#fff}th,td{border-bottom:1px solid #e5e5e5;padding:7px;text-align:left;vertical-align:top}
th{background:#f0f0ea}.lock{color:#999;letter-spacing:1px}.locked td{filter:blur(3.5px);user-select:none}.muted{color:#666;font-size:14px}
nav a{margin-right:12px}.grid a{display:inline-block;margin:4px 10px 4px 0}footer{margin-top:40px;font-size:13px;color:#666}"""

def page(path, title, desc, body, dataset=None):
    url = f"{SITE}/{path}" if path else SITE + "/"
    ld = ""
    if dataset:
        ld = '<script type="application/ld+json">' + json.dumps({"@context": "https://schema.org", "@type": "Dataset", "name": title, "description": desc,
              "url": url, "isAccessibleForFree": True, "license": "https://creativecommons.org/publicdomain/zero/1.0/",
              "creator": {"@type": "Person", "name": "Nidhi Karuturi"}, "dateModified": TODAY,
              "distribution": [{"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": f"{SITE}/{dataset}"}]}) + "</script>"
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title><meta name="description" content="{e(desc)}"><link rel="canonical" href="{url}">
<meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(desc)}"><style>{CSS}</style>{ld}</head>
<body><main><nav class="muted"><a href="{SITE}/">Daily Leads</a><a href="{SITE}/new-dot-authority-trucking-leads-today/">Trucking</a><a href="{SITE}/sam-gov-small-business-set-aside-bids-today/">SAM.gov bids</a><a href="{PDUFA_SITE}">PDUFA dates</a></nav>
{body}<footer>Updated {TODAY} (UTC). Sources: FMCSA Company Census (data.transportation.gov) and SAM.gov public opportunities. Public government data, free sample. Not affiliated with FMCSA, DOT, GSA or SAM.gov.</footer></main></body></html>"""

def write(root, path, content):
    fp = os.path.join(root, path, "index.html") if not path.endswith((".xml", ".txt", ".csv")) else os.path.join(root, path)
    os.makedirs(os.path.dirname(fp), exist_ok=True); open(fp, "w").write(content)

def carrier_table(rows, hidden):
    h = "<table><tr><th>Added</th><th>Company</th><th>City, State</th><th>Trucks</th><th>For-hire</th><th>USDOT</th><th>Email</th><th>Phone</th></tr>"
    for r in rows:
        h += (f"<tr><td>{e(r['added'])}</td><td>{e(r['name'] or '')}</td><td>{e(r['city'])}, {e(r['state'])}</td><td>{e(str(r['units']))}</td>"
              f"<td>{'Yes' if r['forhire'] else 'No'}</td><td><a href='https://safer.fmcsa.dot.gov/query.asp?searchtype=ANY&amp;query_type=queryCarrierSnapshot&amp;query_param=USDOT&amp;query_string={e(r['dot'] or '')}' rel='nofollow'>{e(r['dot'] or '')}</a></td>"
              f"<td class='lock'>{e(mask_email(r['email']))}</td><td class='lock'>{e(mask_phone(r['phone']))}</td></tr>")
    h += "".join("<tr class='locked'><td>2026-10-..</td><td>HIDDEN TRANSPORT LLC</td><td>Somewhere, US</td><td>3</td><td>Yes</td><td>4••••••</td><td>o•••@gmail.com</td><td>(•••) •••-••••</td></tr>" for _ in range(3))
    return h + f"</table><p class='muted'>+ {hidden:,} more rows with full email and phone in the full feed.</p>"

def build_fmcsa(root, rows, since):
    n = len(rows); show = max(5, min(60, n // 5)); emails = sum(1 for r in rows if r["email"]); fh = sum(1 for r in rows if r["forhire"])
    sd = dt.date(int(since[:4]), int(since[4:6]), int(since[6:]))
    hook = (f"<div class='hook'><b>{n:,}</b> US trucking companies got a USDOT number since {sd:%b %d}. "
            f"<b>{emails:,}</b> of them listed an email. Each one needs insurance, a factoring line, an ELD and loads in its first weeks.</div>")
    csvp = "data/fmcsa-new-carriers-sample.csv"
    with open(os.path.join(root, csvp), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["added", "company", "city", "state", "power_units", "for_hire", "usdot", "email", "phone"])
        for r in rows[:show]: w.writerow([r["added"], r["name"], r["city"], r["state"], r["units"], r["forhire"], r["dot"], mask_email(r["email"]), mask_phone(r["phone"])])
    by = {}
    for r in rows: by.setdefault(r["state"], []).append(r)
    top = sorted(((s, v) for s, v in by.items() if s in STATES), key=lambda x: -len(x[1]))
    links = "".join(f"<a href='{SITE}/new-trucking-companies/{STATES[s].lower().replace(' ', '-')}/'>{STATES[s]} ({len(v)})</a>" for s, v in top)
    cta = f"<a class='cta' href='{FMCSA_ACTOR}'>Get all {n:,} with email + phone → $3 per 1,000</a>"
    body = (f"<h1>New DOT authority trucking leads today: {n:,} new carriers this week</h1>{hook}"
            f"<p>Below are {show} of {n:,} ({100*show//max(n,1)}%) active carriers added to the FMCSA census in the last 7 days. "
            f"{fh:,} are authorized for-hire. Email and phone are hidden here. The full feed has them, plus filters by state, fleet size, cargo and hazmat.</p>{cta}"
            f"{carrier_table(rows[:show], n - show)}{cta}<p class='muted'>Free sample CSV (contacts masked): <a href='{SITE}/{csvp}'>{csvp}</a></p>"
            f"<h2>New trucking companies by state</h2><div class='grid'>{links}</div>"
            "<h2>What it costs</h2><p>New-carrier lead subscriptions list $39 to $599 a month on their own sites (PollyAI, Truckr, Carrier IQ, Rookiefeed; checked October 2026). This feed has no subscription: $3 per 1,000 rows, so a weekly pull of one state costs cents.</p><h2>Who uses this</h2><p>Commercial truck insurance agents (new authorities need coverage on file before they can haul for hire), "
            "freight factoring companies, ELD and dispatch services, fuel card programs, and truck dealers. "
            "The data is the official FMCSA Company Census. The full feed is the same data delivered as JSON/CSV/Excel, or straight into your CRM through the Apify API.</p>")
    write(root, "new-dot-authority-trucking-leads-today", page("new-dot-authority-trucking-leads-today/",
          f"New DOT Authority Trucking Leads Today: {n:,} New Carriers ({TODAY})",
          f"{n:,} new USDOT trucking companies registered in the last 7 days. Free daily sample with city, state, fleet size. Full list with email and phone.", body, csvp))
    paths = []
    for s, v in top:
        if len(v) < 5: continue
        name = STATES[s]; slug = name.lower().replace(" ", "-"); sh = max(3, len(v) // 5)
        b = (f"<h1>New trucking companies in {name} this week: {len(v):,}</h1>"
             f"<div class='hook'><b>{len(v):,}</b> new {name} carriers got a USDOT number since {sd:%b %d}. Here are {sh}. The other {len(v)-sh:,} are in the full feed.</div>"
             f"<p>New DOT numbers in {name} from the FMCSA census, refreshed daily. Email and phone are masked in the sample.</p>"
             f"<a class='cta' href='{FMCSA_ACTOR}'>Get all {len(v):,} {name} carriers with email + phone</a>{carrier_table(v[:sh], len(v)-sh)}"
             f"<p><a href='{SITE}/new-dot-authority-trucking-leads-today/'>← All states ({n:,})</a></p>")
        write(root, f"new-trucking-companies/{slug}", page(f"new-trucking-companies/{slug}/",
              f"New Trucking Companies in {name} This Week ({len(v):,}) – New DOT Numbers {TODAY}",
              f"{len(v):,} new {name} trucking companies registered with FMCSA in the last 7 days. Free daily sample; full list with email and phone.", b))
        paths.append(f"new-trucking-companies/{slug}/")
    return ["new-dot-authority-trucking-leads-today/"] + paths, n

def bid_table(rows, hidden):
    h = "<table><tr><th>Due</th><th>Bid</th><th>Agency</th><th>Type</th><th>NAICS</th><th>Place</th><th>Contracting officer</th></tr>"
    for r in rows:
        dl = f"{e(r['due'])}<br><span class='muted'>{r['days']} days</span>" if r["due"] else "—"
        h += (f"<tr><td>{dl}</td><td><a href='{e(r['url'])}' rel='nofollow'>{e(r['title'] or '')}</a></td><td>{e(r['agency'])}<br><span class='muted'>{e(r['sub'])}</span></td>"
              f"<td>{e(r['type'])}</td><td>{e(r['naics'])}</td><td>{e(r['pop'])}</td><td class='lock'>{e(mask_email(r['contact']))}</td></tr>")
    h += "".join("<tr class='locked'><td>2026-11-..</td><td>HIDDEN SOLICITATION TITLE</td><td>DEPT OF ...</td><td>Solicitation</td><td>5415..</td><td>..</td><td>j•••@agency.gov</td></tr>" for _ in range(3))
    return h + f"</table><p class='muted'>+ {hidden:,} more open bids in the full feed, with full contacts and descriptions.</p>"

def build_sam(root, sets):
    allrows, total = [], 0; paths = []
    for codes, slug, label in SETASIDES:
        tot, rows = sets[slug]; total += tot
        for r in rows: r["sa"] = label
        allrows += rows
        sh = max(5, min(30, len(rows) // 5))
        b = (f"<h1>New SAM.gov {label} bids today</h1>"
             f"<div class='hook'><b>{tot:,}</b> active {label} notices on SAM.gov right now. You're seeing {sh} of the newest. Missing one costs you the whole contract. Missing the deadline by a day costs the same.</div>"
             f"<p>Newest open {label} opportunities, refreshed daily. The contracting officer email is masked in the sample.</p>"
             f"<a class='cta' href='{SAM_ACTOR}'>Get every {label} bid with officer email → $2.50 per 1,000</a>{bid_table(rows[:sh], max(tot - sh, 0))}"
             f"<p><a href='{SITE}/sam-gov-small-business-set-aside-bids-today/'>← All set-aside bids</a></p>")
        write(root, f"sam-gov-bids/{slug}", page(f"sam-gov-bids/{slug}/", f"New SAM.gov {label} Bids Today ({TODAY})",
              f"{tot:,} active {label} federal contract opportunities. Free daily sample of the newest bids with deadline, agency and NAICS.", b))
        paths.append(f"sam-gov-bids/{slug}/")
    allrows.sort(key=lambda r: r["posted"], reverse=True)
    sh = max(10, min(60, len(allrows) // 5))
    csvp = "data/sam-gov-set-aside-bids-sample.csv"
    with open(os.path.join(root, csvp), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["posted", "due", "title", "set_aside", "agency", "type", "naics", "place", "contact", "url"])
        for r in allrows[:sh]: w.writerow([r["posted"], r["due"], r["title"], r["sa"], r["agency"], r["type"], r["naics"], r["pop"], mask_email(r["contact"]), r["url"]])
    links = "".join(f"<a href='{SITE}/sam-gov-bids/{s}/'>{l} ({sets[s][0]:,})</a>" for _, s, l in SETASIDES)
    b = (f"<h1>New SAM.gov small-business set-aside bids today</h1>"
         f"<div class='hook'><b>{total:,}</b> active small-business set-aside notices on SAM.gov. On SAM.gov you open each notice to find the officer's email. Here are the {sh} newest on one page, with the email shown in the full feed.</div>"
         f"<p>Total small business, 8(a), SDVOSB, WOSB and HUBZone, refreshed daily. The full feed adds filters by NAICS, keyword, state and deadline window, plus contracting-officer emails and full descriptions, as JSON/CSV/Excel or via API.</p>"
         f"<a class='cta' href='{SAM_ACTOR}'>Get the full daily feed → $2.50 per 1,000 bids</a>"
         f"<h2>By set-aside</h2><div class='grid'>{links}</div>{bid_table(allrows[:sh], max(total - sh, 0))}"
         f"<p class='muted'>Free sample CSV (contacts masked): <a href='{SITE}/{csvp}'>{csvp}</a></p>")
    write(root, "sam-gov-small-business-set-aside-bids-today", page("sam-gov-small-business-set-aside-bids-today/",
          f"New SAM.gov Small Business Set-Aside Bids Today: {total:,} Open ({TODAY})",
          f"Newest small business, 8(a), SDVOSB, WOSB and HUBZone federal bids from SAM.gov, refreshed daily. Free sample; full feed with contracting officer emails.", b, csvp))
    return ["sam-gov-small-business-set-aside-bids-today/"] + paths, total

def main():
    global TODAY
    root = sys.argv[1]; push = "--push" in sys.argv
    TODAY = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    os.makedirs(os.path.join(root, "data"), exist_ok=True)
    rows, since = fmcsa()
    if not rows: sys.exit("FMCSA fetch failed; site left unchanged")
    sets = {slug: sam_setaside(codes, 30) for codes, slug, _ in SETASIDES}
    if not any(v[1] for v in sets.values()): sys.exit("SAM fetch failed; site left unchanged")
    p1, nf = build_fmcsa(root, rows, since); p2, ns = build_sam(root, sets)
    b = (f"<h1>Daily Leads: free samples of fresh US public-data lead lists</h1>"
         f"<div class='hook'>Today: <b>{nf:,}</b> new trucking companies and <b>{ns:,}</b> open small-business federal bids. You get 20% free. The rest sits one click away.</div>"
         f"<h2><a href='{SITE}/new-dot-authority-trucking-leads-today/'>New DOT authority trucking leads →</a></h2><p>For truck insurance agents, factoring, ELD and dispatch. <a href='{FMCSA_ACTOR}'>Full feed</a></p>"
         f"<h2><a href='{SITE}/sam-gov-small-business-set-aside-bids-today/'>New SAM.gov set-aside bids →</a></h2><p>For small federal contractors and GovCon BD teams. <a href='{SAM_ACTOR}'>Full feed</a></p>"
         f"<h2><a href='{PDUFA_SITE}'>PDUFA date calendar →</a></h2><p>FDA decision dates pulled from SEC filings, for biotech traders. <a href='{PDUFA_ACTOR}'>Full feed</a></p>")
    write(root, "", page("", "Daily Leads – Free New Trucking Company & SAM.gov Bid Lists", "Free daily samples: new USDOT trucking companies and new SAM.gov small business set-aside bids.", b))
    urls = [SITE + "/"] + [f"{SITE}/{p}" for p in p1 + p2]
    open(os.path.join(root, "sitemap.xml"), "w").write('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' +
        "".join(f"<url><loc>{u}</loc><lastmod>{TODAY}</lastmod><changefreq>daily</changefreq></url>" for u in urls) + "</urlset>")
    open(os.path.join(root, "robots.txt"), "w").write(f"User-agent: *\nAllow: /\nSitemap: {SITE}/sitemap.xml\n")
    open(os.path.join(root, f"{INDEXNOW_KEY}.txt"), "w").write(INDEXNOW_KEY)
    open(os.path.join(root, ".nojekyll"), "w").write("")
    print(f"built {len(urls)} pages: {nf} carriers, {ns} bids")
    if push:
        g = lambda *a: subprocess.run(["git", "-C", root, *a], check=False)
        g("add", "-A"); g("commit", "-qm", f"Daily refresh {TODAY}"); g("pull", "-q", "--rebase", "-X", "ours"); r = g("push", "-q")
        if r.returncode == 0:
            body = json.dumps({"host": "nidhi-bhai.github.io", "key": INDEXNOW_KEY, "keyLocation": f"{SITE}/{INDEXNOW_KEY}.txt", "urlList": urls}).encode()
            try:
                time.sleep(60)
                resp = urllib.request.urlopen(urllib.request.Request("https://api.indexnow.org/indexnow", data=body, headers={"Content-Type": "application/json; charset=utf-8"}), timeout=30)
                print("IndexNow", resp.status)
            except Exception as ex: print("IndexNow error", ex)

if __name__ == "__main__":
    main()
