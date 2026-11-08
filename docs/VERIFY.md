# Verification log

| Date | Step | Shop (platform) | Checks disputed | Notes |
|---|---|---|---|---|
| 2026-11-08 | 1 (partial: fetch, D1, D3) — smoke, not a reference shop | www.hema.nl (not fingerprinted yet) | 0 | D1 pass, D3 pass. Manual: robots.txt has only `User-agent: *`; no rule blocks `/` or the `.html` product paths tested; sitemap_index referenced, lastmod 100% on 3,318 sampled URLs. Matches. |
| 2026-11-08 | 1 (partial: fetch, D1, D3) — smoke, not a reference shop | www.coolblue.nl (not fingerprinted yet) | 0 | robots.txt and sitemaps return HTTP 403 to our scanner UA → D1/D3 reported `error` (cannot verify) instead of RFC-default "allow all". Real AI-bot behaviour to be tested by D2. |
