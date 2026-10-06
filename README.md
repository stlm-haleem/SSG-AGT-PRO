# SSG AGT Pro

Your Team Lead's SSG AGT app, professionalized: the account-monitoring engine and calculation
logic in `backend/ssg/logic_core.py` is the Team Lead's **V1.84** file, unmodified apart from the
data-folder path (his calculations always win), a proper unified auth/roles system,
a modern React UI, and a few extra charts. Your Wallet Monitoring app is not part of this build —
this is the SSG AGT side only, carried forward as-is.

## What you get

- **Command Center** — today's deposit/payout/STLM totals, limit utilization, and a Deposit vs
  Pay out vs STLM/Top-Up flow chart.
- **CIH Overview** — Summary (deposit type / merchant deposit / merchant pay out), Agent & Personal
  Wallet Balances (now with a wallet-share donut chart alongside the balance table), Limit
  Availability (now with an agent-vs-personal availability comparison chart).
- **Account Monitoring** — Agent / Personal / VIP / Withdrawal-only, searchable, filterable,
  sortable, paginated, exportable to Excel.
- **Account Overview** — Agent/Personal Overview, High Discrepancy, Limit Reached.
- **Data** — Data Import (Deposit/Pay Out History, Active/Locked/Disabled Accounts, Opening, Limit,
  Settlement/Top Up), Extended Opening Balance, Generate Summary, Active/Locked/Disabled account
  lists, Generated Statements.
- **Masterlist** — the persistent Wallet Account Master List, Pending Accounts, Unknown Accounts,
  Permanently Closed Accounts.
- **Administration** — Users, **Roles & Permissions** (fully custom, page-by-page and
  action-by-action — Admin always has everything), Integrations (Google Sheets + Telegram, same
  config format as before).

Every page that shows generated data (Command Center, CIH Summary, CIH Wallets, Statements) has an
explicit **Refresh** button, so if you run Generate Summary while already looking at one of these
pages, a click brings it current — no need to navigate away and back.

## Interface

- **Collapsible sidebar** — click "Collapse" at the bottom to shrink it to an icon rail (click
  again to expand); the choice is remembered. Each nav group can also be folded independently.
- **Command palette** — press **⌘K** / **Ctrl+K** anywhere (or click the search bar in the header)
  to jump straight to any page you have access to, or to switch theme / sign out, via keyboard.
- **User menu** — click your avatar, top right, for admin settings and sign out.
- **Light/dark mode**, a responsive layout down to phone width (the sidebar becomes a slide-in
  drawer), and skeleton loading placeholders shaped like the page that's loading, instead of a
  generic spinner.
- **Telegram reports now include a small chart** above the table — a bar chart for limit
  utilization and limit availability, a wallet-share donut for CIH agent/personal reports —
  drawn directly with Pillow (already a dependency), so sending a report isn't any slower and no
  new libraries were added. A report with no data yet is sent as a table only, with no empty chart.

## Setup

```bash
cd frontend
npm install
npm run build        # produces frontend/dist, served by the backend

cd ../backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```

Open **http://localhost:8000**.

- Default login: `admin` / `admin123` — **change this immediately** (Admin → Users → Reset
  password).
- `backend/ssg_agt.db` (created on first run) holds Users and Roles.
- `backend/data/wallet_account_master.csv` is your Team Lead's real Wallet Masterlist — it ships
  with this build so the app is usable from day one. `backend/data/integrations.json` and
  `backend/data/integrations/` carry over the same Google Sheets / Telegram config structure his
  app used (currently unfilled — no bot token or spreadsheet ID was actually configured in the
  copy you gave me — fill them in from **Admin → Integrations**). Daily operational imports
  (Deposit/Pay Out/Opening/Limit/etc.) are in-memory for the current server run only, exactly as
  in the original app — only the Masterlist and Permanently Closed list persist across restarts.
- `SSG_APP_SECRET` sets the JWT signing key; if unset, one is generated once and stored in
  `backend/data/.secret` so logins survive restarts.

## Roles & permissions

**Admin** always has full access to every page and action and can't be edited or demoted below
the last admin. Every other role — including the built-in `OPERATION`, `User` and `Viewer` — is
fully editable from **Admin → Roles & Permissions**: tick exactly which pages a role can see and
which actions (edit, delete, import) it can perform. A role needs the page's *view* permission
**and** the specific action permission to do something destructive.

## What's under the hood

- `backend/app.py` — auth, Users/Roles endpoints, mounts the SSG router, serves the built frontend.
- `backend/auth.py` — JWT auth + the permission-check dependency (`perm(...)`).
- `backend/perms.py` — the permission catalogue and default role definitions.
- `backend/ssg_api.py` — a JSON API wrapper around the SSG AGT engine so the React frontend can
  render it, instead of the original server-rendered Jinja templates.
- `backend/ssg/logic_core.py`, `integrations.py` — your Team Lead's engine (V1.84 sync; see CHANGELOG_V1_84_SYNC.md).
- `frontend/src/components/pages/` — one component per page (Command Center, CIH, Monitoring,
  Overview, Data Import, Masterlist, Pending/Unknown/Closed, Users, Roles, Integrations).
- `frontend/src/components/common/` — shared building blocks (DataTable, KpiCard, MiniBar,
  MiniDonut, Pagination, MultiSelect, SearchBox, Toast, Confirm).
