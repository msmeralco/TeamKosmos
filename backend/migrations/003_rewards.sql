-- Solar Passport owner link and redeemed vouchers (demo rewards). Safe to run more than once.

create table if not exists user_passports (
    user_id text primary key references users(id) on delete cascade,
    passport_id text not null
);
--;;
create table if not exists voucher_redemptions (
    user_id text not null references users(id) on delete cascade,
    voucher_id text not null,
    code text not null,
    redeemed_at double precision not null,
    primary key (user_id, voucher_id)
);
--;;
alter table user_passports enable row level security;
--;;
alter table voucher_redemptions enable row level security;
--;;
do $$
begin
    if exists (select 1 from pg_roles where rolname = 'anon') then
        revoke all on user_passports, voucher_redemptions from anon;
    end if;
    if exists (select 1 from pg_roles where rolname = 'authenticated') then
        revoke all on user_passports, voucher_redemptions from authenticated;
    end if;
end;
$$;
