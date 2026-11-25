-- Piezas mínimas de Supabase para probar las migraciones en una base de datos de prueba vacía.
-- Solo lo usan los tests (conftest.py): en Supabase real estos objetos ya existen.
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then
    create role anon nologin noinherit;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then
    create role authenticated nologin noinherit;
  end if;
end
$$;
create schema if not exists auth;
create table if not exists auth.users (id uuid primary key);
create schema if not exists extensions;
