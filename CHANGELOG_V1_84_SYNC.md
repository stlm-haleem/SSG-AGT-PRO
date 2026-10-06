# Sync with Team Lead's SSG AGT V1.84

UI structure, React/FastAPI stack, letter avatar and theme are unchanged. His logic is taken as-is.

## Logic (backend/ssg/logic_core.py - replaced by his V1.84 file; only DATA_DIR path kept as yours)
- Monitoring remarks resolve Active > Disabled > Locked (an account in Active uses only its Active remark).
- Permanent Stop mixed view driven by Permanently Closed Accounts (Agent/Personal/VIP/Withdrawal classes untouched).
- Permanently Closed Wallet + Account type auto-correct from the Master List (vectorised), re-synced whenever the Master List changes.
- Master List auto-fields: MRC DP LIMIT, SDP PAID, WALLET, GROUP CODE, ACCOUNT TYPE (blank -> PERSONAL for BKASHC/NAGADC/ROCKETC/UPAYC else AGENT).
  HOURS / METHOD come from GROUP CODE rules (IBANKING/EBANKING; 14/16/18/24 Hours, 24H-0s Interval), otherwise your manual value is kept.
- Method values standardised (IBANKING / EBANKING, everything else upper-case).
- Caching: account-statement cache by date range; Generate Summary no longer invalidates operational caches.
- backend/ssg/filters.py rebuilt from his app.py: multi-term search (, ; | newline), W. HRS, R. BAL sort, Permanent Stop.
- backend/ssg/integrations.py: report timestamp in every Telegram caption, whole-number cells, up to 3 report destinations,
  Personal Limit Availability report with Daily + Monthly tables. (Your Pillow charts and Topic-ID validation kept.)

## Features
- Account Monitoring: Permanent Stop Accounts page, W. HRS filter, R. BAL sort, Enter-to-chip multi-account search; exports honour all filters.
- Overview (Agent/Personal/High Discrepancy/Limit Reached): same chip search + R. BAL sort.
- CIH Limit Availability: Personal Daily / Monthly (eligible count x 300,000).
- Master List: add/edit only WALLETNAME, HOURS, METHOD; Group Code filter; filtered export.
- Permanently Closed: Add / Edit / Delete, batch Edit + batch Delete via checkboxes, Group Code + Method filters, Wallet/Account type automatic.
- Data Import: Generate sends the PC's local time + UTC offset; per-user "Last Generate" shown in the top bar; Telegram Reports panel; Google Sync gated by its own permission.
- Integrations: choose up to 3 "Send reports" destinations (topic optional).
- Pagination 25 / 50 / 100 / 250; Admin sorted first in Users.
- New permissions: dashboard_generate, monitoring_permanent_stop, imports_google_sync, imports_telegram_reports, closed_delete.
  Existing OPERATION/User/Viewer roles receive the relevant new keys once on first start (custom roles: tick them in Roles & Permissions).
- users table gets a last_generate_at column automatically on first start.
