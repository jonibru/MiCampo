-- 0003 Campo: cultivos, campos, lotes, ciclos, desmontes y lluvias.
-- Diseño: RF-01, RF-02, RF-34, RF-35, RF-39, RN-02, RN-12, RN-18, RN-31.
--
-- Convención: toda referencia entre tablas de un establecimiento usa clave compuesta
-- (establecimiento_id, id), así una referencia nunca cruza de un establecimiento a otro.

-- Cultivos: tabla global de consulta (humedad base, RN-05). El precio de referencia va en valor_referencia.
create table public.cultivo (
  id uuid primary key default gen_random_uuid(),
  nombre text not null unique,
  humedad_base numeric(4, 1) check (humedad_base is null or humedad_base between 0 and 100),
  creado_en timestamptz not null default now()
);
alter table public.cultivo enable row level security;
alter table public.cultivo force row level security;
revoke all on public.cultivo from public;
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'anon') then
    revoke all on public.cultivo from anon, authenticated;
  end if;
end
$$;
grant select on public.cultivo to micampo_app;
create policy cultivo_select on public.cultivo for select to micampo_app using (true);

insert into public.cultivo (nombre, humedad_base) values
  ('Soja', 13.5), ('Maíz', 14.5), ('Trigo', 14.0), ('Girasol', 11.0),
  ('Sorgo', 15.0), ('Cebada', 12.5), ('Algodón', null);

-- Campos y lotes ----------------------------------------------------------------

create table public.campo (
  id uuid primary key default gen_random_uuid(),
  establecimiento_id uuid not null references public.establecimiento (id),
  nombre text not null check (length(btrim(nombre)) > 0),
  creado_en timestamptz not null default now(),
  unique (establecimiento_id, id),
  unique (establecimiento_id, nombre)
);

create table public.lote (
  id uuid primary key default gen_random_uuid(),
  establecimiento_id uuid not null,
  campo_id uuid not null,
  nombre text not null check (length(btrim(nombre)) > 0),
  ha_limpias numeric(12, 2) not null default 0 check (ha_limpias >= 0),
  ha_monte numeric(12, 2) not null default 0 check (ha_monte >= 0),
  ha_totales numeric(12, 2) generated always as (ha_limpias + ha_monte) stored,
  creado_en timestamptz not null default now(),
  unique (establecimiento_id, id),
  unique (campo_id, nombre),
  foreign key (establecimiento_id, campo_id) references public.campo (establecimiento_id, id)
);
create index lote_campo_idx on public.lote (establecimiento_id, campo_id);

-- Ciclo: período de un lote con un solo cultivo (RN-02). Un solo ciclo abierto por lote.
create table public.ciclo (
  id uuid primary key default gen_random_uuid(),
  establecimiento_id uuid not null,
  lote_id uuid not null,
  cultivo_id uuid references public.cultivo (id),
  campana_anio smallint,
  ha_limpias numeric(12, 2) not null check (ha_limpias >= 0),
  fecha_inicio date not null,
  fecha_cierre date,
  estado text not null default 'en_preparacion'
    check (estado in ('en_preparacion', 'abierto', 'cerrado')),
  creado_en timestamptz not null default now(),
  unique (establecimiento_id, id),
  foreign key (establecimiento_id, lote_id) references public.lote (establecimiento_id, id),
  check ((estado = 'cerrado') = (fecha_cierre is not null)),
  check (fecha_cierre is null or fecha_cierre >= fecha_inicio),
  check (campana_anio is null or cultivo_id is not null)
);
create unique index ciclo_un_abierto_por_lote
  on public.ciclo (lote_id) where estado in ('en_preparacion', 'abierto');
create index ciclo_lote_idx on public.ciclo (establecimiento_id, lote_id);

-- Solo el dueño puede reabrir un ciclo cerrado (RN-02, RF-34).
create function app.ciclo_reabrir_solo_dueno() returns trigger
language plpgsql set search_path = ''
as $$
begin
  if old.estado = 'cerrado' and new.estado <> 'cerrado'
     and current_user = 'micampo_app' and not app.es_dueno() then
    raise exception 'solo el dueño puede reabrir un ciclo cerrado' using errcode = '42501';
  end if;
  return new;
end
$$;
create trigger ciclo_reabrir_solo_dueno before update on public.ciclo
  for each row execute function app.ciclo_reabrir_solo_dueno();

-- Cargas: desmonte y lluvia. Llevan quién, desde dónde, el mensaje del bot y la anulación (RN-09).

create table public.desmonte (
  id uuid primary key default gen_random_uuid(),
  establecimiento_id uuid not null,
  lote_id uuid not null,
  fecha date not null,
  ha numeric(12, 2) not null check (ha > 0),
  costo_usd numeric(14, 2) not null default 0 check (costo_usd >= 0),
  creado_por uuid not null default app.usuario_id() references public.usuario (id),
  origen text not null default app.origen() check (origen in ('bot', 'panel')),
  mensaje_id uuid default app.mensaje_id(),
  anulada_en timestamptz,
  anulada_por uuid references public.usuario (id),
  motivo_anulacion text,
  creado_en timestamptz not null default now(),
  unique (establecimiento_id, id),
  foreign key (establecimiento_id, lote_id) references public.lote (establecimiento_id, id),
  check ((anulada_en is null) = (anulada_por is null))
);
create index desmonte_lote_idx on public.desmonte (establecimiento_id, lote_id, fecha);

create table public.lluvia (
  id uuid primary key default gen_random_uuid(),
  establecimiento_id uuid not null references public.establecimiento (id),
  fecha date not null,
  mm numeric(6, 1) not null check (mm >= 0 and mm <= 1000),
  creado_por uuid not null default app.usuario_id() references public.usuario (id),
  origen text not null default app.origen() check (origen in ('bot', 'panel')),
  mensaje_id uuid default app.mensaje_id(),
  anulada_en timestamptz,
  anulada_por uuid references public.usuario (id),
  motivo_anulacion text,
  creado_en timestamptz not null default now(),
  unique (establecimiento_id, id),
  check ((anulada_en is null) = (anulada_por is null))
);
create index lluvia_fecha_idx on public.lluvia (establecimiento_id, fecha);

-- RLS forzado, permisos mínimos y auditoría. Campos y lotes se pueden borrar si no están en uso
-- (las claves foráneas lo impiden si lo están, RN-07); las cargas solo se anulan.
select app.proteger_tabla('public.campo', p_borrable => true);
select app.proteger_tabla('public.lote', p_borrable => true);
select app.proteger_tabla('public.ciclo');
select app.proteger_tabla('public.desmonte', p_carga => true);
select app.proteger_tabla('public.lluvia', p_carga => true);
