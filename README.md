# ScribeUp Take-Home — Subscription Detection

Welcome! This is the starter repo for the ScribeUp coding challenge.

The take-home is intentionally under-specified — closer to how a real ticket lands at a small startup than a clean spec. We care more about your judgment than completeness; don't polish. Plan on roughly **3 hours** of your own time.

## What's here

- `backend/` — Django + SQLite project with a `Transaction` model and a **pre-seeded database** (`backend/db.sqlite3`) of realistic transaction data.
- `frontend/` — A minimal Vite + React app that lists transactions for a user.

The database holds several thousand transactions across ~50 users — a mix of real recurring subscriptions, near-recurring noise, and one-off purchases. The data is already seeded; there's nothing to generate. SQLite is used so there's nothing to install beyond Python and Node.

## Running locally

You'll need: Python 3.11+ and Node 20+.

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py finalize_subscriptions --all-users
python manage.py runserver

# Frontend (in another terminal)
cd frontend
npm install
npm run dev
```

Backend runs on `http://localhost:8000`, frontend on `http://localhost:5173`.

### Optional semantic review

Deterministic analysis works without OpenAI. To opt into review of only ambiguous candidates:

```bash
cp .env.example .env
# Set OPENAI_API_KEY=your-own-key and OPENAI_SUBSCRIPTION_REVIEW_ENABLED=true
```

Each developer or reviewer should use their own key; do not share keys or commit `.env`. The model
(default `gpt-5-mini`) and timeout are configurable. Calls happen only in Django. Missing, disabled,
or failed review leaves ambiguous cases `uncertain`. SQLite persists versioned assessments, so
unchanged transaction groups are not reviewed repeatedly.

```bash
cd backend
python manage.py finalize_subscriptions --all-users
python manage.py finalize_subscriptions --user 17
python manage.py finalize_subscriptions --all-users --no-llm
python manage.py finalize_subscriptions --all-users --force
```

The database ships pre-seeded, so the data is identical for every candidate. Please don't delete or recreate `backend/db.sqlite3` — work against the data as given.

## What's already wired up

- `GET /users/` — returns the list of seeded user IDs.
- `GET /users/<user_id>/transactions/` — returns all transactions for a user. The React page calls this.
- `GET /users/<user_id>/subscriptions/` — refreshes stale snapshots and returns finalized subscriptions.
- The React page has a user selector and a simple transaction list.

## The prompt

Build a `GET /users/<user_id>/subscriptions/` endpoint that returns the recurring subscriptions detected for that user. For each subscription, return at minimum:

- merchant
- cadence
- typical amount
- next predicted charge date

For cadence, weekly / monthly / yearly are the obvious ones — but look closely at the data before you commit to a fixed set of buckets. Real subscriptions bill on other rhythms too, and charge dates aren't perfectly regular.

Then wire it up to the React page so a user can see their detected subscriptions alongside their transactions.

## AI policy

Use any AI tools you'd normally use — Cursor, Copilot, Claude, ChatGPT, all fair game. We assume you will. We'll want to see how well you understand what you (and your AI) shipped, so use AI as a force multiplier, not a crutch.

## Tips

- Look at the seeded data before you start coding — there are interesting edge cases worth noticing.
- The schema is intentionally minimal — if you want to add fields or tables, that's a design decision worth defending.
- Don't polish — we'd rather see honest trade-offs than perfect code.
- If something is genuinely unclear, ask.

## What to submit

A zip file with your changes, plus a `NOTES.md` at the root covering:

1. What you'd do differently with more time.
2. Where you used AI tools and where you didn't.
3. Trade-offs you made and why.

Questions? Please reach out
