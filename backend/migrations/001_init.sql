-- Sol schema for Supabase Postgres. Safe to run more than once.
-- Run in the Supabase SQL editor (the `--;;` lines are just comments there), or: python -m app.db.migrate
-- The runner executes each block between `--;;` lines separately, so no multi-statement protocol is needed.
-- The backend connects with the database owner role (bypasses RLS). RLS is enabled with no policies,
-- so the public anon/authenticated roles can read and write nothing.

create table if not exists sessions (
    id text primary key,
    state jsonb not null,
    updated_at timestamptz not null default now()
);
--;;
create table if not exists products (
    id text primary key,
    category text not null,
    data jsonb not null,
    updated_at timestamptz not null default now()
);
--;;
-- body_json is TEXT on purpose: jsonb would reorder keys and break hash verification.
create table if not exists ledger (
    seq bigserial primary key,
    id text not null unique,
    body_json text not null,
    prev_hash text not null,
    hash text not null,
    signature text not null,
    created_at text not null
);
--;;
create table if not exists cache (
    key text primary key,
    value jsonb not null,
    expires_at double precision
);
--;;
alter table sessions enable row level security;
--;;
alter table products enable row level security;
--;;
alter table ledger enable row level security;
--;;
alter table cache enable row level security;
--;;
create or replace function ledger_append_only() returns trigger as $$
begin
    raise exception 'ledger is append-only';
end;
$$ language plpgsql;
--;;
drop trigger if exists ledger_no_update on ledger;
--;;
create trigger ledger_no_update before update or delete on ledger
    for each row execute function ledger_append_only();
--;;
do $$
begin
    if exists (select 1 from pg_roles where rolname = 'anon') then
        revoke all on sessions, products, ledger, cache from anon;
    end if;
    if exists (select 1 from pg_roles where rolname = 'authenticated') then
        revoke all on sessions, products, ledger, cache from authenticated;
    end if;
end;
$$;
