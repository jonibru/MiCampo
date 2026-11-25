-- 0004 Productos y stock: catálogo base, productos, compras, movimientos de stock y precio promedio.
-- Diseño: RF-03 a RF-07, RF-19, RF-36, RN-03, RN-04, RN-13, RN-14, RN-30, RN-32.
-- Decisión del 25/11/2026: los repuestos usan la unidad 'unidad' (RN-14 solo preveía l, kg y bolsa).

-- Reglas comunes de las cargas (sección 2 del diseño y RN-09) ------------------
-- 1. Quién la cargó, desde dónde y desde qué mensaje no se cambian nunca.
-- 2. Una carga anulada no se des-anula ni se modifica.
-- 3. Quien anula queda registrado como el usuario del contexto.
-- 4. El encargado corrige o anula solo sus propias cargas; el dueño, cualquiera.
-- Solo aplica a lo que hace el backend (micampo_app); los triggers internos del sistema no se frenan.
create function app.reglas_carga() returns trigger
language plpgsql set search_path = ''
as $$
begin
  if current_user <> 'micampo_app' then
    return new;
  end if;
  if new.creado_por is distinct from old.creado_por
     or new.origen is distinct from old.origen
     or new.mensaje_id is distinct from old.mensaje_id then
    raise exception 'no se puede cambiar quién, desde dónde ni desde qué mensaje se hizo una carga'
      using errcode = '42501';
  end if;
  if old.anulada_en is not null then
    raise exception 'la carga está anulada y no se puede modificar' using errcode = '42501';
  end if;
  if new.anulada_por is not null and new.anulada_por is distinct from app.usuario_id() then
    raise exception 'la anulación debe quedar a nombre de quien la hace' using errcode = '42501';
  end if;
  if old.creado_por is distinct from app.usuario_id() and not app.es_dueno() then
    raise exception 'el encargado solo puede corregir o anular sus propias cargas' using errcode = '42501';
  end if;
  return new;
end
$$;

create trigger lluvia_reglas_carga before update on public.lluvia
  for each row execute function app.reglas_carga();
create trigger desmonte_reglas_carga before update on public.desmonte
  for each row execute function app.reglas_carga();

-- Catálogo base (RN-30, RF-36): global, lo mantiene el administrador. El backend solo lo lee.
create table public.catalogo_producto (
  id uuid primary key default gen_random_uuid(),
  nombre text not null unique check (length(btrim(nombre)) > 0),
  categoria text not null check (categoria in
    ('herbicida', 'insecticida', 'fungicida', 'coadyuvante', 'fertilizante', 'semilla', 'repuesto', 'otro')),
  unidad text not null check (unidad in ('l', 'kg', 'bolsa', 'unidad')),
  principio_activo text,
  concentracion text,
  modelo text,
  precio_referencia_usd numeric(14, 4) check (precio_referencia_usd is null or precio_referencia_usd >= 0),
  activo boolean not null default true,
  creado_en timestamptz not null default now()
);
alter table public.catalogo_producto enable row level security;
alter table public.catalogo_producto force row level security;
revoke all on public.catalogo_producto from public;
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'anon') then
    revoke all on public.catalogo_producto from anon, authenticated;
  end if;
end
$$;
grant select on public.catalogo_producto to micampo_app;
create policy catalogo_producto_select on public.catalogo_producto for select to micampo_app using (true);
create index catalogo_producto_nombre_trgm on public.catalogo_producto
  using gin (nombre extensions.gin_trgm_ops);

-- Productos del establecimiento (RF-03, RN-03, RN-13, RN-14) --------------------
-- La unidad, la categoría y el peso por bolsa se eligen al crear el producto y no cambian.
-- precio_promedio_usd lo calcula el sistema; nulo = precio pendiente para el dueño.
create table public.producto (
  id uuid primary key default gen_random_uuid(),
  establecimiento_id uuid not null references public.establecimiento (id),
  catalogo_id uuid references public.catalogo_producto (id),
  nombre text not null check (length(btrim(nombre)) > 0),
  categoria text not null check (categoria in
    ('herbicida', 'insecticida', 'fungicida', 'coadyuvante', 'fertilizante', 'semilla', 'repuesto', 'otro')),
  unidad text not null check (unidad in ('l', 'kg', 'bolsa', 'unidad')),
  precio_inicial_usd numeric(14, 4) check (precio_inicial_usd is null or precio_inicial_usd >= 0),
  precio_promedio_usd numeric(14, 4),
  cultivo_id uuid references public.cultivo (id),
  variedad text,
  kg_por_bolsa numeric(8, 2) check (kg_por_bolsa is null or kg_por_bolsa > 0),
  modelo text,
  activo boolean not null default true,
  creado_por uuid not null default app.usuario_id() references public.usuario (id),
  creado_en timestamptz not null default now(),
  unique (establecimiento_id, id),
  -- semillas: en bolsas, con peso por bolsa y cultivo (RN-13)
  check ((categoria = 'semilla') = (unidad = 'bolsa')),
  check (categoria <> 'semilla' or (kg_por_bolsa is not null and cultivo_id is not null)),
  check (categoria = 'semilla' or (kg_por_bolsa is null and cultivo_id is null and variedad is null)),
  -- repuestos: por unidad y con su modelo (RF-19)
  check ((categoria = 'repuesto') = (unidad = 'unidad')),
  check (categoria <> 'repuesto' or length(btrim(coalesce(modelo, ''))) > 0)
);
create unique index producto_nombre_uk on public.producto (establecimiento_id, lower(nombre));
create index producto_nombre_trgm on public.producto using gin (nombre extensions.gin_trgm_ops);

-- Compras (RF-04, RN-01) ---------------------------------------------------------
-- Los importes se guardan en US$; si la compra fue en pesos, se guarda además el original y el tipo de cambio.
create table public.compra (
  id uuid primary key default gen_random_uuid(),
  establecimiento_id uuid not null references public.establecimiento (id),
  fecha date not null,
  proveedor text,
  moneda text not null default 'USD' check (moneda in ('USD', 'ARS')),
  tipo_cambio numeric(14, 4) check (tipo_cambio is null or tipo_cambio > 0),
  tipo_cambio_fuente text check (tipo_cambio_fuente in ('automatico', 'manual')),
  total_usd numeric(16, 2) not null default 0,
  monto_ars numeric(18, 2),
  creado_por uuid not null default app.usuario_id() references public.usuario (id),
  origen text not null default app.origen() check (origen in ('bot', 'panel')),
  mensaje_id uuid default app.mensaje_id(),
  anulada_en timestamptz,
  anulada_por uuid references public.usuario (id),
  motivo_anulacion text,
  creado_en timestamptz not null default now(),
  unique (establecimiento_id, id),
  check ((anulada_en is null) = (anulada_por is null)),
  check ((moneda = 'ARS') = (tipo_cambio is not null and tipo_cambio_fuente is not null))
);
create index compra_fecha_idx on public.compra (establecimiento_id, fecha);

-- precio_unitario está en la moneda de la compra (vacío si no se dijo, RN-04);
-- precio_unitario_usd lo calcula el sistema.
create table public.compra_item (
  id uuid primary key default gen_random_uuid(),
  establecimiento_id uuid not null,
  compra_id uuid not null,
  producto_id uuid not null,
  cantidad numeric(14, 3) not null check (cantidad > 0),
  precio_unitario numeric(16, 4) check (precio_unitario is null or precio_unitario >= 0),
  precio_unitario_usd numeric(14, 4),
  creado_en timestamptz not null default now(),
  unique (establecimiento_id, id),
  foreign key (establecimiento_id, compra_id) references public.compra (establecimiento_id, id),
  foreign key (establecimiento_id, producto_id) references public.producto (establecimiento_id, id)
);
create index compra_item_compra_idx on public.compra_item (establecimiento_id, compra_id);

-- Movimientos de stock: el stock de un producto es la suma de sus movimientos no anulados.
-- Entradas positivas, salidas negativas. El precio de cada movimiento queda fijo al cargarlo (RN-10).
create table public.movimiento_stock (
  id uuid primary key default gen_random_uuid(),
  establecimiento_id uuid not null,
  producto_id uuid not null,
  fecha date not null,
  cantidad numeric(14, 3) not null check (cantidad <> 0),
  precio_unitario_usd numeric(14, 4),
  tipo text not null check (tipo in ('compra', 'labor', 'uso_repuesto', 'ajuste')),
  compra_item_id uuid unique,
  labor_insumo_id uuid,
  motivo text,
  stock_resultante numeric(16, 3),
  revisar boolean not null default false,
  creado_por uuid not null default app.usuario_id() references public.usuario (id),
  origen text not null default app.origen() check (origen in ('bot', 'panel')),
  mensaje_id uuid default app.mensaje_id(),
  anulada_en timestamptz,
  anulada_por uuid references public.usuario (id),
  motivo_anulacion text,
  creado_en timestamptz not null default now(),
  -- Orden exacto de carga: dentro de una misma transacción todos los movimientos tienen la misma hora.
  orden bigint generated always as identity,
  unique (establecimiento_id, id),
  foreign key (establecimiento_id, producto_id) references public.producto (establecimiento_id, id),
  foreign key (establecimiento_id, compra_item_id) references public.compra_item (establecimiento_id, id),
  check ((anulada_en is null) = (anulada_por is null)),
  check ((tipo = 'compra') = (compra_item_id is not null)),
  check (tipo <> 'compra' or cantidad > 0),
  check (tipo not in ('labor', 'uso_repuesto') or cantidad < 0),
  check ((tipo = 'labor') = (labor_insumo_id is not null))
);
create index movimiento_stock_producto_idx
  on public.movimiento_stock (producto_id, fecha, orden);

-- Stock actual por producto. security_invoker: respeta el RLS de quien consulta.
create view public.stock_producto with (security_invoker = true) as
select p.establecimiento_id, p.id as producto_id,
       coalesce(sum(m.cantidad) filter (where m.anulada_en is null), 0)::numeric(16, 3) as stock
from public.producto p
left join public.movimiento_stock m
  on m.establecimiento_id = p.establecimiento_id and m.producto_id = p.id
group by p.establecimiento_id, p.id;

-- Precio promedio (RN-04) ----------------------------------------------------------
-- Se recalcula recorriendo los movimientos no anulados en orden de fecha y, dentro de la fecha, de carga:
--   compra con precio y stock previo > 0:  promedio ponderado
--   compra con precio y stock previo <= 0: el promedio pasa a ser el precio de la compra
--   compra sin precio, salidas y ajustes:  no cambian el promedio
-- Así, anular una compra vieja recalcula el promedio desde ese momento (ver Notas del diseño).
create function app.recalcular_precio_promedio(p_producto uuid) returns void
language plpgsql security definer set search_path = ''
as $$
declare
  v_promedio numeric;
  v_stock numeric := 0;
  m record;
begin
  select precio_inicial_usd into v_promedio from public.producto where id = p_producto;
  for m in
    select cantidad, precio_unitario_usd, tipo
    from public.movimiento_stock
    where producto_id = p_producto and anulada_en is null
    order by fecha, orden
  loop
    if m.tipo = 'compra' and m.precio_unitario_usd is not null then
      if v_stock <= 0 or v_promedio is null then
        v_promedio := m.precio_unitario_usd;
      else
        v_promedio := (v_stock * v_promedio + m.cantidad * m.precio_unitario_usd) / (v_stock + m.cantidad);
      end if;
    end if;
    v_stock := v_stock + m.cantidad;
  end loop;
  update public.producto set precio_promedio_usd = round(v_promedio, 4) where id = p_producto;
end
$$;

create function app.producto_antes_de_insertar() returns trigger
language plpgsql set search_path = ''
as $$
begin
  new.precio_promedio_usd := new.precio_inicial_usd;
  return new;
end
$$;
create trigger producto_antes_de_insertar before insert on public.producto
  for each row execute function app.producto_antes_de_insertar();

-- El dueño fija el precio de un producto que quedó pendiente (RN-30). Solo si sigue pendiente.
-- El recálculo de las labores cargadas sin precio (RN-10) se suma con el módulo de labores.
create function app.fijar_precio_pendiente(p_producto uuid, p_precio_usd numeric) returns void
language plpgsql security definer set search_path = ''
as $$
begin
  if not app.es_dueno() then
    raise exception 'solo el dueño puede fijar el precio de un producto' using errcode = '42501';
  end if;
  if p_precio_usd is null or p_precio_usd < 0 then
    raise exception 'precio inválido' using errcode = '22023';
  end if;
  update public.producto set precio_inicial_usd = p_precio_usd
  where id = p_producto and establecimiento_id = app.establecimiento_id() and precio_promedio_usd is null;
  if not found then
    raise exception 'el producto no existe o ya tiene precio' using errcode = '22023';
  end if;
  perform app.recalcular_precio_promedio(p_producto);
end
$$;

-- Compras: convertir precios, generar el movimiento de stock y mantener el total --------
create function app.compra_item_antes_de_insertar() returns trigger
language plpgsql set search_path = ''
as $$
declare v_compra record;
begin
  select moneda, tipo_cambio, anulada_en into v_compra
  from public.compra where id = new.compra_id;
  if v_compra.anulada_en is not null then
    raise exception 'la compra está anulada' using errcode = '42501';
  end if;
  new.precio_unitario_usd := case
    when new.precio_unitario is null then null
    when v_compra.moneda = 'ARS' then round(new.precio_unitario / v_compra.tipo_cambio, 4)
    else new.precio_unitario
  end;
  return new;
end
$$;
create trigger compra_item_antes_de_insertar before insert on public.compra_item
  for each row execute function app.compra_item_antes_de_insertar();

create function app.compra_item_despues_de_insertar() returns trigger
language plpgsql security definer set search_path = ''
as $$
declare v_compra record;
begin
  select fecha, moneda, creado_por, origen, mensaje_id into v_compra
  from public.compra where id = new.compra_id;
  insert into public.movimiento_stock
    (establecimiento_id, producto_id, fecha, cantidad, precio_unitario_usd, tipo, compra_item_id,
     creado_por, origen, mensaje_id)
  values
    (new.establecimiento_id, new.producto_id, v_compra.fecha, new.cantidad, new.precio_unitario_usd,
     'compra', new.id, v_compra.creado_por, v_compra.origen, v_compra.mensaje_id);
  update public.compra c set
    total_usd = t.total_usd,
    monto_ars = case when c.moneda = 'ARS' then t.total_original end
  from (
    select coalesce(round(sum(cantidad * precio_unitario_usd), 2), 0) as total_usd,
           round(sum(cantidad * precio_unitario), 2) as total_original
    from public.compra_item where compra_id = new.compra_id
  ) t
  where c.id = new.compra_id;
  return null;
end
$$;
create trigger compra_item_despues_de_insertar after insert on public.compra_item
  for each row execute function app.compra_item_despues_de_insertar();

-- Anular una compra anula sus movimientos de stock (y eso recalcula el promedio).
create function app.compra_despues_de_anular() returns trigger
language plpgsql security definer set search_path = ''
as $$
begin
  update public.movimiento_stock m set
    anulada_en = new.anulada_en, anulada_por = new.anulada_por,
    motivo_anulacion = coalesce(new.motivo_anulacion, 'compra anulada')
  from public.compra_item i
  where i.compra_id = new.id and m.compra_item_id = i.id and m.anulada_en is null;
  return null;
end
$$;
create trigger compra_despues_de_anular after update of anulada_en on public.compra
  for each row when (old.anulada_en is null and new.anulada_en is not null)
  execute function app.compra_despues_de_anular();

-- Movimientos: precio y control de stock negativo al cargar; recálculo del promedio después --
create function app.movimiento_antes_de_insertar() returns trigger
language plpgsql set search_path = ''
as $$
declare
  v_categoria text;
  v_promedio numeric;
  v_stock numeric;
begin
  if new.tipo = 'compra' and pg_catalog.pg_trigger_depth() < 2 then
    raise exception 'los movimientos de compra se generan solo al cargar la compra' using errcode = '42501';
  end if;
  select categoria, precio_promedio_usd into v_categoria, v_promedio
  from public.producto where id = new.producto_id;
  if new.tipo = 'uso_repuesto' and v_categoria <> 'repuesto' then
    raise exception 'solo los repuestos se cargan como uso de repuesto' using errcode = '23514';
  end if;
  if new.tipo in ('labor', 'uso_repuesto') then
    new.precio_unitario_usd := v_promedio;       -- costo al valor del momento (RN-10)
  elsif new.tipo = 'ajuste' then
    new.precio_unitario_usd := null;             -- un ajuste no tiene precio
  end if;
  select coalesce(sum(cantidad), 0) into v_stock
  from public.movimiento_stock where producto_id = new.producto_id and anulada_en is null;
  new.stock_resultante := v_stock + new.cantidad;
  new.revisar := new.stock_resultante < 0;       -- RN-32: se permite, se avisa y se marca
  return new;
end
$$;
create trigger movimiento_antes_de_insertar before insert on public.movimiento_stock
  for each row execute function app.movimiento_antes_de_insertar();

create function app.movimiento_antes_de_actualizar() returns trigger
language plpgsql set search_path = ''
as $$
begin
  if current_user = 'micampo_app' and old.tipo = 'compra'
     and new.anulada_en is distinct from old.anulada_en then
    raise exception 'un movimiento de compra se anula anulando la compra' using errcode = '42501';
  end if;
  return new;
end
$$;
create trigger movimiento_antes_de_actualizar before update on public.movimiento_stock
  for each row execute function app.movimiento_antes_de_actualizar();

create function app.movimiento_despues() returns trigger
language plpgsql security definer set search_path = ''
as $$
begin
  perform app.recalcular_precio_promedio(new.producto_id);
  return null;
end
$$;
create trigger movimiento_despues_insert after insert on public.movimiento_stock
  for each row execute function app.movimiento_despues();
create trigger movimiento_despues_anular after update of anulada_en on public.movimiento_stock
  for each row when (old.anulada_en is distinct from new.anulada_en)
  execute function app.movimiento_despues();

-- Protección: RLS forzado, auditoría y permisos mínimos ------------------------------------
select app.proteger_tabla('public.producto');
select app.proteger_tabla('public.compra', p_carga => true);
select app.proteger_tabla('public.compra_item');
select app.proteger_tabla('public.movimiento_stock', p_carga => true);

-- producto: se crea con su precio inicial; después solo se cambian nombre, variedad, modelo y si está activo.
revoke insert, update on public.producto from micampo_app;
grant insert (establecimiento_id, catalogo_id, nombre, categoria, unidad, precio_inicial_usd,
              cultivo_id, variedad, kg_por_bolsa, modelo) on public.producto to micampo_app;
grant update (nombre, variedad, modelo, activo) on public.producto to micampo_app;

-- compra: se carga y se anula; para corregirla se anula y se vuelve a cargar (RN-09).
revoke insert, update on public.compra from micampo_app;
grant insert (establecimiento_id, fecha, proveedor, moneda, tipo_cambio, tipo_cambio_fuente)
  on public.compra to micampo_app;
grant update (anulada_en, anulada_por, motivo_anulacion) on public.compra to micampo_app;
create trigger compra_reglas_carga before update on public.compra
  for each row execute function app.reglas_carga();

-- compra_item: solo se agrega.
revoke insert, update on public.compra_item from micampo_app;
grant insert (establecimiento_id, compra_id, producto_id, cantidad, precio_unitario)
  on public.compra_item to micampo_app;

-- movimiento_stock: el backend carga usos de repuestos y ajustes, y los anula o marca como revisados.
revoke insert, update on public.movimiento_stock from micampo_app;
grant insert (establecimiento_id, producto_id, fecha, cantidad, tipo, labor_insumo_id, motivo)
  on public.movimiento_stock to micampo_app;
grant update (anulada_en, anulada_por, motivo_anulacion, revisar) on public.movimiento_stock to micampo_app;
create trigger movimiento_stock_reglas_carga before update on public.movimiento_stock
  for each row execute function app.reglas_carga();

grant select on public.stock_producto to micampo_app;
revoke all on public.stock_producto from public;
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'anon') then
    revoke all on public.stock_producto from anon, authenticated;
  end if;
end
$$;

grant execute on function app.fijar_precio_pendiente(uuid, numeric) to micampo_app;

-- PostgreSQL deja ejecutar cualquier función nueva a todos (PUBLIC). Se quita, y el backend
-- solo ejecuta lo que se le concedió explícitamente arriba. Cada migración que crea funciones termina así.
revoke execute on all functions in schema app from public;
