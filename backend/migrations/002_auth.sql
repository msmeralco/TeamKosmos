-- Accounts, login tokens and per-user chat sessions. Safe to run more than once.

create table if not exists users (
    id text primary key,
    email text not null unique,
    password_hash text not null,
    name text not null,
    household_name text,
    city text,
    lat double precision,
    lon double precision,
    monthly_kwh double precision,
    household_template text,
    created_at double precision not null
);
--;;
create table if not exists auth_tokens (
    token_hash text primary key,
    user_id text not null references users(id) on delete cascade,
    expires_at double precision not null
);
--;;
alter table sessions add column if not exists user_id text;
--;;
alter table sessions add column if not exists title text;
--;;
create index if not exists sessions_user_idx on sessions (user_id, updated_at desc);
--;;
alter table users enable row level security;
--;;
alter table auth_tokens enable row level security;
--;;
do $$
begin
    if exists (select 1 from pg_roles where rolname = 'anon') then
        revoke all on users, auth_tokens from anon;
    end if;
    if exists (select 1 from pg_roles where rolname = 'authenticated') then
        revoke all on users, auth_tokens from authenticated;
    end if;
end;
$$;
