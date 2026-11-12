# Solar Passport and Vouchers (MVP demo) - Design

## Intent
Sol's deck says the Solar Passport is a household's proof of going solar, and that a confirmed Passport unlocks vouchers and discounts. The Passport is issued and verifiable today, but nothing shows it to a user and no voucher code exists. This feature makes that part of the pitch demoable: one seeded "solar owner" account that already has a signed, installed Passport and a set of sample vouchers it can redeem.

## Goals
- A seeded demo account whose Passport is a real, signed, hash-chained record. `/verify/{id}` and `/api/passport/{id}/verify` pass for it.
- The signed body carries the "installed" fact (installer name, installed date), so no separate confirm event is needed.
- A Passport view in the app, in the existing visual language (calm cards, hairline borders, side panel like installers and packages): Passport summary, "Installed" seal, verify link, and a list of vouchers.
- Each voucher has a code, a title, a value text, a partner label and a state (available or redeemed). "Redeem" marks it used once and reveals the code. Redeemed state persists across restarts on SQLite and Postgres.

## Non-goals
- No confirm-install flow and no Passport for regular accounts. Regular accounts do not see the new view.
- No installer or partner accounts, dashboard, or real partner funding.
- No cash value, no Meralco integration, no usage-based rewards.
- Not a security feature: anyone signed in as the owner can redeem. Codes are sample values.

## Anti-goals
- A fake Passport. The record must come from `passport.issue()` so the verify page is honest.
- Copy that implies Meralco or a partner has agreed to anything. Every voucher is labelled a sample.

## Constraints
- Follow existing conventions: data in `backend/data/*.json`, repo methods on the abstract `Repository` implemented in both `sqlite_repo.py` and `pg_repo.py`, SQL in `backend/migrations/`, routes in `backend/app/routes/`, frontend panels in `frontend/src/components/`.
- The Passport ledger is append-only and signed; nothing edits an issued record.
- The Passport body must stay valid for `_reproduce` (it re-runs the engine from `inputs`/`package`/`results`), so the record is created from a real analysis, not hand-written JSON.
- Tests run fully offline (`conftest.py`).

## Approaches considered
- **A. Real signed Passport, vouchers in a data file, state in a new table (chosen).** Most files touched; honest verification and durable redeem state.
- **B. Same, but redeem state in the cache store.** No migration, but the cache is disposable, so clearing it silently un-redeems vouchers.
- **C. Front-end mock.** Fastest, but the verify link and signature would be fake.

## Design
1. **Seed.** Add a fourth account to `data/seed_users.json` (a solar-owner household, working name "Dela Cruz Family"). A new `scripts/seed_owner.py` (or an extension of `seed_users.py`) creates the user if missing, runs the offline analysis for that household (as `demo_run.py` does), calls `passport.issue()` with the installed fields added to `inputs`, and stores the Passport id against the user. Re-running is idempotent (no second Passport, no reset of redeemed vouchers).
2. **Voucher definitions.** `backend/data/vouchers.json`: id, title, value text, partner label, terms. Examples from the docs: free site survey, installer discount on the recommended package. Labelled "sample" in the data and the UI.
3. **Storage.** New migration `003_rewards.sql` adds a table keyed by (user_id, voucher_id) with redeemed_at and a signed or derived code, plus a place to record the owner's Passport id. New repo methods in `base.py`, `sqlite_repo.py`, `pg_repo.py`.
4. **Code per voucher.** Derive it from the Passport id and voucher id (for example a short HMAC with the signing key) so it is stable and tied to one Passport.
5. **API.** `GET /api/rewards` (auth required): returns `{passport, vouchers}` or `404`/empty for accounts without a Passport. `POST /api/rewards/{voucher_id}/redeem` (auth required): marks redeemed once; a second call returns a clear 409 and does not change the stored time.
6. **UI.** A Passport view reachable from the sidebar only when `GET /api/rewards` returns a Passport. Shows: Passport id and short hash, "Installed by X on date" seal, a "Verify" link to `/verify/{id}`, the package summary, and voucher cards with Redeem. Match tokens used in `ListingPanel.tsx` (colors, radii, 12-13px text, `Chevron`, `Monogram`-style tiles). Empty and error states follow the rest of the app.
7. **Deck honesty.** The UI and docs say vouchers are samples and nothing is agreed with Meralco or any business.

## Decided by the user
- MVP: no confirm step; anyone can be treated as confirmed. Only the seeded account shows the Passport.
- Approach A.

## Calls made by the designer (check these)
1. **Installer is fictional.** The signed body names "Sample Solar Installer (demo)", never a firm from `doe_installers.json`. The signed body also carries `"sample": true`, and the Passport panel and the verify page show "Demo installation, sample data". `DISCLOSURE` is left as is.
2. **Seed per backend.** The seed script is run once per database. `/api/rewards` returns 200 with `passport: null` when the stored Passport id is not in the active ledger, so the front end treats it as "no Passport" and shows nothing.
3. **Idempotency rule.** On re-run, if the stored id exists in the active ledger and `verify_stored` passes, do nothing. If the id is missing or verification fails, print a clear warning and issue a new Passport only when `--reissue` is passed. Redeemed rows are kept.
4. **Voucher code.** Generated and stored at redeem time (HMAC of Passport id and voucher id, keyed with a value derived from the signing key file). It is hidden before redeem. Later key changes do not alter stored codes.
5. **Analysis input.** The seed uses the Reyes-style demo household and demo outline flow from `demo_run.py` (offline, scripted). Voucher text in `vouchers.json` is static and does not name the computed package.
6. **No-Passport response.** `GET /api/rewards` returns 200 `{passport: null, vouchers: []}` for regular accounts, so no error toast and no 404 handling.
7. **Atomic redeem.** Redeem uses insert-if-absent on a unique (user_id, voucher_id); an unknown voucher id returns 404; a repeat returns 409 without changing `redeemed_at`.

## Left to the builder
- Exact sidebar placement and whether the view uses the side panel or a full page.
- Exact voucher list and wording (keep to the docs' examples).
- Whether seeding is its own script or part of `seed_users.py`.
- Code format and length.
- Test coverage beyond one redeem-once test and one verify-passes test for the seeded record.
