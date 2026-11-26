create table kv (key text primary key, value jsonb);
alter table kv enable row level security;
create policy "demo all" on kv for all using (true) with check (true);
