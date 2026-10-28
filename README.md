# Daily Leads

Free daily samples of two US public-data lead lists, published at https://nidhi-bhai.github.io/daily-leads/

- **New DOT authority trucking companies** (FMCSA Company Census, last 7 days): [sample page](https://nidhi-bhai.github.io/daily-leads/new-dot-authority-trucking-leads-today/) · [CSV](data/fmcsa-new-carriers-sample.csv) · full feed with email and phone: [Apify actor](https://apify.com/prospect_antechamber/fmcsa-new-carrier-leads)
- **New SAM.gov small-business set-aside bids** (Total SB, 8(a), SDVOSB, WOSB, HUBZone): [sample page](https://nidhi-bhai.github.io/daily-leads/sam-gov-small-business-set-aside-bids-today/) · [CSV](data/sam-gov-set-aside-bids-sample.csv) · full feed with contracting-officer emails: [Apify actor](https://apify.com/prospect_antechamber/sam-gov-contract-opportunities)
- **PDUFA date calendar** for biotech traders: [site](https://nidhi-bhai.github.io/pdufa-calendar/) · [Apify actor](https://apify.com/prospect_antechamber/pdufa-fda-catalyst-calendar)

Samples show about 20% of each day's rows with contacts masked. Built by `refresh.py` (Python stdlib only): `python3 refresh.py . --push`
