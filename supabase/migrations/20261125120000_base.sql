-- 0001 Base: extensiones, rol del backend y contexto de sesión.
-- Diseño: RNF-16 (aislamiento por establecimiento con RLS), RN-09 (nada se borra).
--
-- Convención del contexto: el backend abre una transacción y llama a
-- app.fijar_contexto(usuario, establecimiento, origen, mensaje). Las políticas
-- de RLS leen ese contexto. Al terminar la transacción el contexto se borra solo.

create schema if not exists extensions;
create extension if not exists pg_trgm with schema extensions;
create extension if not exists unaccent with schema extensions;

-- Rol con el que se conecta el backend: sin permiso para saltear RLS (RNF-16).
-- El login y la contraseña se configuran fuera de las migraciones (ver backend/README.md).
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'micampo_app') then
    create role micampo_app nologin noinherit nobypassrls;
  end if;
end
$$;

-- Esquema interno: no expuesto por la API de Supabase ni accesible para anon/authenticated.
create schema if not exists app;
revoke all on schema app from public;
grant usage on schema app to micampo_app;
grant usage on schema public to micampo_app;

-- Las tablas nuevas de public no deben quedar abiertas a la API de Supabase (anon/authenticated).
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'anon') then
    alter default privileges in schema public revoke all on tables from anon, authenticated;
    alter default privileges in schema public revoke all on sequences from anon, authenticated;
    alter default privileges in schema public revoke all on functions from anon, authenticated;
  end if;
end
$$;

-- Contexto de la sesión ------------------------------------------------------

create function app.usuario_id() returns uuid
language sql stable set search_path = ''
as $$ select nullif(current_setting('app.usuario_id', true), '')::uuid $$;

create function app.establecimiento_id() returns uuid
language sql stable set search_path = ''
as $$ select nullif(current_setting('app.establecimiento_id', true), '')::uuid $$;

create function app.origen() returns text
language sql stable set search_path = ''
as $$ select nullif(current_setting('app.origen', true), '') $$;

create function app.mensaje_id() returns uuid
language sql stable set search_path = ''
as $$ select nullif(current_setting('app.mensaje_id', true), '')::uuid $$;

-- Fija el contexto SOLO para la transacción en curso (equivale a SET LOCAL).
-- Debe llamarse dentro de una transacción explícita.
create function app.fijar_contexto(
  p_usuario uuid,
  p_establecimiento uuid,
  p_origen text,
  p_mensaje uuid default null
) returns void
language plpgsql set search_path = ''
as $$
begin
  if p_origen is null or p_origen not in ('bot', 'panel', 'sistema') then
    raise exception 'origen inválido: %', coalesce(p_origen, 'null') using errcode = '22023';
  end if;
  perform set_config('app.usuario_id', coalesce(p_usuario::text, ''), true);
  perform set_config('app.establecimiento_id', coalesce(p_establecimiento::text, ''), true);
  perform set_config('app.origen', p_origen, true);
  perform set_config('app.mensaje_id', coalesce(p_mensaje::text, ''), true);
end
$$;
grant execute on function app.usuario_id(), app.establecimiento_id(), app.origen(),
  app.mensaje_id(), app.fijar_contexto(uuid, uuid, text, uuid) to micampo_app;

-- Año agrícola (mayo a abril): la campaña "2026/27" tiene año 2026 (RN-31).
create function app.anio_agricola(p_fecha date) returns integer
language sql immutable set search_path = ''
as $$
  select (extract(year from p_fecha)::int
          - case when extract(month from p_fecha) < 5 then 1 else 0 end)
$$;
grant execute on function app.anio_agricola(date) to micampo_app;

-- PostgreSQL deja ejecutar cualquier función nueva a todos (PUBLIC). Se quita, y el backend
-- solo ejecuta lo que se le concedió explícitamente arriba. Cada migración que crea funciones termina así.
revoke execute on all functions in schema app from public;
