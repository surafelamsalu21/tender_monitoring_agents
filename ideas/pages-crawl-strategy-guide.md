# Monitored Pages — Crawl Strategy Reference

Use this as your copy-paste guide when adding pages in the app.

---

## Strategy Quick Reference

| Strategy | When to use |
|---|---|
| `crawl4ai` | Content visible in plain HTML — no JavaScript needed |
| `playwright` | JavaScript SPA / infinite scroll / filters / login walls |
| `hybrid` | Uncertain — tries crawl4ai first, falls back to Playwright automatically |

---

## Pages

### 1. EU Funding & Tenders Portal
| Field | Value |
|---|---|
| **URL** | `https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/calls-for-tenders?isExactMatch=true&order=DESC&pageNumber=1&pageSize=50&sortBy=startDate` |
| **Strategy** | `playwright` |
| **Why** | Pure React SPA — server returns a blank cookie-consent shell. Playwright navigates each `pageNumber=1…4` URL automatically. |

---

### 2. UN Global Marketplace (UNGM)
| Field | Value |
|---|---|
| **URL** | `https://www.ungm.org/Public/Notice` |
| **Strategy** | `playwright` |
| **Why** | Angular SPA with infinite scroll — AJAX loads batches of ~25 notices on each scroll. Playwright scrolls up to 4× automatically. |

---

### 3. African Development Bank — Corporate Procurement (Documents)
| Field | Value |
|---|---|
| **URL** | `https://www.afdb.org/en/documents/corporate-procurement` |
| **Strategy** | `playwright` |
| **Why** | Drupal site with JavaScript-driven pagination. Playwright follows the Next button through up to 4 pages. |

---

### 4. African Development Bank — Current Solicitations
| Field | Value |
|---|---|
| **URL** | `https://www.afdb.org/en/about-us/corporate-procurement/procurement-notices/current-solicitations` |
| **Strategy** | `hybrid` |
| **Why** | Static-looking Drupal page but pagination may need JS. Hybrid tries crawl4ai first and falls back automatically. |

---

### 5. African Development Bank — Projects & Operations Procurement
| Field | Value |
|---|---|
| **URL** | `https://www.afdb.org/en/projects-and-operations/procurement` |
| **Strategy** | `hybrid` |
| **Why** | Server-rendered Drupal page, but some filters are JS-driven. Hybrid is safest. |

---

### 6. UNDP Procurement Notices — Africa Region Only
| Field | Value |
|---|---|
| **URL** | `https://procurement-notices.undp.org/?region=RAF` |
| **Strategy** | `playwright` |
| **Why** | JS-driven listing. The `?region=RAF` tells the system to automatically click the Africa checkbox before extracting. Without it, you get all global notices. |

---

### 7. East African Development Bank (EADB)
| Field | Value |
|---|---|
| **URL** | `https://eadb.org/procurement/` |
| **Strategy** | `crawl4ai` |
| **Why** | Static HTML page. Content is server-rendered. Note: EADB does not always list individual tender notices publicly — may return few results. |

---

### 8. Trade and Development Bank (TDB)
| Field | Value |
|---|---|
| **URL** | `https://www.tdbgroup.org/consulting-procurement/` |
| **Strategy** | `crawl4ai` |
| **Why** | Server-rendered HTML with tenders listed directly on the page as headings. Already confirmed working. |

---

### 9. Uganda e-Government Procurement (EGP)
| Field | Value |
|---|---|
| **URL** | `https://egpuganda.go.ug/bid-notices` |
| **Strategy** | `crawl4ai` |
| **Why** | Full HTML table rendered server-side. Already confirmed working. |

---

### 10. Tanzania National e-Procurement System (NeST)
| Field | Value |
|---|---|
| **URL** | `https://nest.go.tz/tenders/published-tenders` |
| **Strategy** | `playwright` |
| **Why** | Returns "Loading…" with crawl4ai — content is fully JavaScript-rendered. |

---

### 11. South Sudan Public Procurement Portal
| Field | Value |
|---|---|
| **URL** | `https://tenderportal.ppdaa.gov.ss/current-bids` |
| **Strategy** | `crawl4ai` |
| **Why** | Server-rendered HTML — tender listings are visible directly in the page source. |

---

### 12. Djibouti Marchés Publics
| Field | Value |
|---|---|
| **URL** | `https://marchespublics.gouv.dj/marches` |
| **Strategy** | `crawl4ai` |
| **Why** | Server-rendered PHP/Drupal site with tenders in the HTML. Note: page is in French — the AI agents handle French language extraction correctly. |

---

### 13. African Union — Bids
| Field | Value |
|---|---|
| **URL** | `https://au.int/en/bids` |
| **Strategy** | `crawl4ai` |
| **Why** | Server-rendered HTML table. Already confirmed working. |

---

## Summary Table

| Site | Exact URL to paste | Strategy |
|---|---|---|
| EU Funding Portal | `https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/calls-for-tenders?isExactMatch=true&order=DESC&pageNumber=1&pageSize=50&sortBy=startDate` | `playwright` |
| UNGM | `https://www.ungm.org/Public/Notice` | `playwright` |
| AfDB Corporate Procurement | `https://www.afdb.org/en/documents/corporate-procurement` | `playwright` |
| AfDB Current Solicitations | `https://www.afdb.org/en/about-us/corporate-procurement/procurement-notices/current-solicitations` | `hybrid` |
| AfDB Projects Procurement | `https://www.afdb.org/en/projects-and-operations/procurement` | `hybrid` |
| UNDP Africa | `https://procurement-notices.undp.org/?region=RAF` | `playwright` |
| EADB | `https://eadb.org/procurement/` | `crawl4ai` |
| TDB | `https://www.tdbgroup.org/consulting-procurement/` | `crawl4ai` |
| Uganda EGP | `https://egpuganda.go.ug/bid-notices` | `crawl4ai` |
| Tanzania NeST | `https://nest.go.tz/tenders/published-tenders` | `playwright` |
| South Sudan PPDAA | `https://tenderportal.ppdaa.gov.ss/current-bids` | `crawl4ai` |
| Djibouti Marchés Publics | `https://marchespublics.gouv.dj/marches` | `crawl4ai` |
| African Union | `https://au.int/en/bids` | `crawl4ai` |
