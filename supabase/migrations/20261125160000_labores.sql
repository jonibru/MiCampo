-- 0005 Labores y costos: tipo de cambio, valores de referencia, tipos de labor, labores, insumos y carpidas.
-- Diseño: RF-08, RF-09, RF-10, RF-21, RF-27, RN-01, RN-02, RN-10, RN-11, RN-12, RN-13, RN-16, RN-17, RN-29.
-- Decisiones del 25/11/2026:
--   * El tipo de cambio es global. La descarga automática y la carga manual las hace el administrador o una
--     tarea interna; el backend (micampo_app) solo lo lee. Quien dice otro dólar en una carga, queda en esa carga.
--   * Tipos de labor: siembra, pulverización (mosquito, dron, avión), fertilización, carpidor, disco, rastra cadena,
--     rolo picador, carpida y otra. El barbecho no es un tipo: es la etapa "en preparación" del ciclo. La cosecha no
--     es una labor: tiene su propio módulo.
--   * Carpida y "otra" se costean con temporales (personas × días × horas por día × pago por hora), con un costo
--     dicho o, si la hizo personal propio, con costo de servicio cero (ya está en el sueldo). Si no hay nada de eso,
--     la labor queda con "costo incompleto". "Otra" lleva una descripción.
--   * Las compras en pesos toman solas el tipo de cambio vigente a su fecha, salvo que se diga otro (manual).
--   * Una labor con más hectáreas que las limpias del ciclo se rechaza.
--   * Un valor de referencia rige desde el día en que se carga (el dueño no elige la fecha). Una labor usa el que
--     regía en su fecha; si es anterior al primer valor cargado, usa ese primero.
--   * Si falta un valor (de referencia o el precio de un insumo), la labor queda con "costo incompleto". Cuando
--     aparece el valor, todas las líneas incompletas lo toman y quedan fijas (excepción de RN-10, con auditoría):
--     al cargar el valor de referencia, al fijar el dueño un precio pendiente o al llegar una compra con precio.
--   * El dueño elige si los encargados de su establecimiento ven costos (por defecto, no: RB-18).

-- Tipo de cambio (RN-01, RN-16, RF-21): global, dólar divisa mayorista ---------------------------
create table public.tipo_cambio (
  id uuid primary key default gen_random_uuid(),
  fecha_hora timestamptz not null,
  tipo_dolar text not null default 'divisa_mayorista' check (tipo_dolar in ('divisa_mayorista')),
  valor numeric(14, 4) not null check (valor > 0),
  fuente text not null check (fuente in ('automatico', 'manual')),
  creado_en timestamptz not null default now(),
  unique (tipo_dolar, fecha_hora)
);
alter table public.tipo_cambio enable row level security;
alter table public.tipo_cambio force row level security;
revoke all on public.tipo_cambio from public;
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'anon') then
    revoke all on public.tipo_cambio from anon, authenticated;
  end if;
end
$$;
grant select on public.tipo_cambio to micampo_app;
create policy tipo_cambio_select on public.tipo_cambio for select to micampo_app using (true);

-- Cotización vigente a una fecha local de Argentina: la última cargada hasta ese día inclusive.
create function app.tipo_cambio_vigente(p_fecha date)
returns table (id uuid, valor numeric, fuente text, fecha_hora timestamptz)
language sql stable set search_path = ''
as $$
  select t.id, t.valor, t.fuente, t.fecha_hora
  from public.tipo_cambio t
  where t.tipo_dolar = 'divisa_mayorista'
    and (t.fecha_hora at time zone 'America/Argentina/Buenos_Aires')::date <= p_fecha
  order by t.fecha_hora desc
  limit 1
$$;

-- Tipos de labor: global (RN-11). El equipo va solo en las pulverizaciones, una fila por equipo.
--   costeo 'por_ha':      valor de referencia del servicio × ha (o el costo real si fue contratada)
--   costeo 'temporales':  personas × días × horas por día × pago por hora, o un costo dicho (RN-17)
create table public.tipo_labor (
  id uuid primary key default gen_random_uuid(),
  codigo text not null unique,
  nombre text not null unique,
  equipo text check (equipo in ('mosquito', 'dron', 'avion')),
  costeo text not null check (costeo in ('por_ha', 'temporales')),
  creado_en timestamptz not null default now(),
  check (equipo is null or costeo = 'por_ha')
);
alter table public.tipo_labor enable row level security;
alter table public.tipo_labor force row level security;
revoke all on public.tipo_labor from public;
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'anon') then
    revoke all on public.tipo_labor from anon, authenticated;
  end if;
end
$$;
grant select on public.tipo_labor to micampo_app;
create policy tipo_labor_select on public.tipo_labor for select to micampo_app using (true);

insert into public.tipo_labor (codigo, nombre, equipo, costeo) values
  ('siembra', 'Siembra', null, 'por_ha'),
  ('pulverizacion_mosquito', 'Pulverización con mosquito', 'mosquito', 'por_ha'),
  ('pulverizacion_dron', 'Pulverización con dron', 'dron', 'por_ha'),
  ('pulverizacion_avion', 'Pulverización con avión', 'avion', 'por_ha'),
  ('fertilizacion', 'Fertilización', null, 'por_ha'),
  ('carpidor', 'Carpidor', null, 'por_ha'),
  ('disco', 'Disco', null, 'por_ha'),
  ('rastra_cadena', 'Rastra cadena', null, 'por_ha'),
  ('rolo_picador', 'Rolo picador', null, 'por_ha'),
  ('carpida', 'Carpida', null, 'temporales'),
  ('otra', 'Otra', null, 'temporales');

-- Valores de referencia (RN-29): por establecimiento. Un cambio es una fila nueva; nunca se pisa la anterior.
--   servicio_labor      US$/ha, por tipo de labor (sin equipo)
--   pulverizacion       US$/ha, por tipo de labor de pulverización (uno por equipo)
--   pago_hora_temporal  US$/hora
--   horas_dia_temporal  horas
--   precio_grano        US$/t, por grano y campaña
--   flete               US$ por camión, por grano y campaña
--   embolsado           US$/t, por grano y campaña
create table public.valor_referencia (
  id uuid primary key default gen_random_uuid(),
  establecimiento_id uuid not null references public.establecimiento (id),
  concepto text not null check (concepto in ('servicio_labor', 'pulverizacion', 'pago_hora_temporal',
                                             'horas_dia_temporal', 'precio_grano', 'flete', 'embolsado')),
  tipo_labor_id uuid references public.tipo_labor (id),
  cultivo_id uuid references public.cultivo (id),
  campana_anio smallint,
  valor numeric(14, 4) not null check (valor >= 0),
  -- Fecha local en que se cargó: desde ahí rige. La pone el sistema.
  vigente_desde date not null default (now() at time zone 'America/Argentina/Buenos_Aires')::date,
  creado_por uuid not null default app.usuario_id() references public.usuario (id),
  creado_en timestamptz not null default now(),
  -- Orden exacto de carga, para desempatar dos cambios del mismo día.
  orden bigint generated always as identity,
  unique (establecimiento_id, id),
  check ((concepto in ('servicio_labor', 'pulverizacion')) = (tipo_labor_id is not null)),
  check ((concepto in ('precio_grano', 'flete', 'embolsado')) = (cultivo_id is not null and campana_anio is not null)),
  check (concepto in ('precio_grano', 'flete', 'embolsado') or (cultivo_id is null and campana_anio is null)),
  check (concepto <> 'horas_dia_temporal' or (valor > 0 and valor <= 24))
);
create index valor_referencia_busqueda_idx
  on public.valor_referencia (establecimiento_id, concepto, vigente_desde desc, orden desc);

-- El servicio va con un tipo sin equipo y la pulverización con uno que tiene equipo.
create function app.valor_referencia_antes_de_insertar() returns trigger
language plpgsql set search_path = ''
as $$
declare v_tipo public.tipo_labor;
begin
  if new.tipo_labor_id is not null then
    select * into v_tipo from public.tipo_labor where id = new.tipo_labor_id;
    if v_tipo.costeo <> 'por_ha' then
      raise exception '% no tiene precio por ha: se costea con temporales o con un costo dicho', v_tipo.nombre
        using errcode = '23514';
    end if;
    if (new.concepto = 'pulverizacion') <> (v_tipo.equipo is not null) then
      raise exception 'el precio de una pulverización va por equipo y el de las demás labores como servicio'
        using errcode = '23514';
    end if;
  end if;
  return new;
end
$$;
create trigger valor_referencia_antes_de_insertar before insert on public.valor_referencia
  for each row execute function app.valor_referencia_antes_de_insertar();

-- Valor vigente a una fecha para un concepto del establecimiento del contexto: el último que rige desde esa
-- fecha o antes; si la fecha es anterior a todos, el primero que se cargó.
create function app.valor_referencia_vigente(
  p_concepto text, p_fecha date, p_tipo_labor uuid default null, p_cultivo uuid default null,
  p_campana integer default null
) returns table (id uuid, valor numeric)
language sql stable set search_path = ''
as $$
  select v.id, v.valor
  from public.valor_referencia v
  where v.establecimiento_id = app.establecimiento_id()
    and v.concepto = p_concepto
    and v.tipo_labor_id is not distinct from p_tipo_labor
    and v.cultivo_id is not distinct from p_cultivo
    and v.campana_anio is not distinct from p_campana
  order by (v.vigente_desde <= p_fecha) desc,
           case when v.vigente_desde <= p_fecha then v.vigente_desde end desc nulls last,
           v.vigente_desde, v.orden desc
  limit 1
$$;

-- Ciclos: a qué ciclo va una labor según su fecha (RN-02, RF-08) ---------------------------------

create function app.nombre_ciclo(p_ciclo uuid) returns text
language sql stable set search_path = ''
as $$
  select coalesce(cu.nombre || ' ' || c.campana_anio || '/' || lpad(((c.campana_anio + 1) % 100)::text, 2, '0'),
                  cu.nombre, 'sin cultivo')
  from public.ciclo c left join public.cultivo cu on cu.id = c.cultivo_id
  where c.id = p_ciclo
$$;

-- Devuelve el ciclo del lote para esa fecha:
--   * el ciclo que contiene la fecha (uno cerrado va desde su inicio hasta el día anterior a su cierre;
--     lo que se carga el mismo día del cierre o después va al ciclo siguiente);
--   * si la fecha es de antes del cierre de un ciclo cerrado, se rechaza: solo el dueño reabre (RB-23);
--   * si no, va al ciclo abierto o en preparación (si la fecha es anterior a su inicio, el inicio se corre);
--   * si el lote no tiene ninguno, se crea uno en preparación con las ha limpias del lote (RN-12).
-- Con p_cultivo_siembra (una siembra), el ciclo toma el cultivo y la campaña y pasa a abierto. Si ya está abierto
-- con otro cultivo, se rechaza: primero hay que cerrar el anterior (el bot pregunta, RN-02).
create function app.ciclo_para_labor(p_lote uuid, p_fecha date, p_cultivo_siembra uuid default null)
returns uuid
language plpgsql set search_path = ''
as $$
declare
  v_ciclo public.ciclo;
  v_cerrado public.ciclo;
begin
  -- Serializa las cargas del mismo lote, para no crear dos ciclos a la vez.
  perform 1 from public.lote where id = p_lote for update;
  if not found then
    raise exception 'el lote no existe' using errcode = '22023';
  end if;

  select * into v_ciclo from public.ciclo
  where lote_id = p_lote and fecha_inicio <= p_fecha and (fecha_cierre is null or p_fecha < fecha_cierre)
  order by fecha_inicio desc
  limit 1;

  if found and v_ciclo.estado = 'cerrado' then
    v_cerrado := v_ciclo;
  elsif not found then
    select * into v_cerrado from public.ciclo
    where lote_id = p_lote and estado = 'cerrado' and fecha_cierre > p_fecha
    order by fecha_cierre
    limit 1;
    if not found then
      select * into v_ciclo from public.ciclo where lote_id = p_lote and estado <> 'cerrado';
      if found then
        update public.ciclo set fecha_inicio = p_fecha where id = v_ciclo.id returning * into v_ciclo;
      else
        insert into public.ciclo (establecimiento_id, lote_id, ha_limpias, fecha_inicio)
        select l.establecimiento_id, l.id, l.ha_limpias, p_fecha from public.lote l where l.id = p_lote
        returning * into v_ciclo;
      end if;
    end if;
  end if;

  if v_cerrado.id is not null then
    raise exception 'la labor del % cae en el ciclo de % del lote, cerrado el %: solo el dueño puede reabrirlo',
      to_char(p_fecha, 'DD/MM/YYYY'), app.nombre_ciclo(v_cerrado.id), to_char(v_cerrado.fecha_cierre, 'DD/MM/YYYY')
      using errcode = '23514', hint = 'ciclo_cerrado';
  end if;

  if p_cultivo_siembra is not null then
    if v_ciclo.estado = 'abierto' and v_ciclo.cultivo_id is distinct from p_cultivo_siembra then
      raise exception 'el lote tiene abierto el ciclo de %: hay que cerrarlo antes de sembrar %',
        app.nombre_ciclo(v_ciclo.id), (select nombre from public.cultivo where id = p_cultivo_siembra)
        using errcode = '23514', hint = 'otro_ciclo_abierto';
    end if;
    if v_ciclo.estado = 'en_preparacion' then
      update public.ciclo
      set cultivo_id = p_cultivo_siembra, campana_anio = app.anio_agricola(p_fecha), estado = 'abierto'
      where id = v_ciclo.id;
    end if;
  end if;
  return v_ciclo.id;
end
$$;

-- Labores (RF-08, RF-10, RN-10, RN-11) ----------------------------------------------------------
-- Lo que dice el usuario: lote, tipo, fecha, ha, si fue contratada, el cultivo (solo siembra), una descripción
-- (obligatoria en "otra") y, si lo sabe, el costo real del servicio por ha o total, en US$ o en pesos.
-- Lo que calcula el sistema al cargarla y queda fijo: el ciclo, el precio del servicio usado y los costos.
create table public.labor (
  id uuid primary key default gen_random_uuid(),
  establecimiento_id uuid not null,
  lote_id uuid not null,
  ciclo_id uuid not null,
  tipo_labor_id uuid not null references public.tipo_labor (id),
  fecha date not null,
  ha numeric(12, 2) not null check (ha > 0),
  contratado boolean not null default false,
  -- Carpida u "otra" hecha por personal propio: el servicio cuesta cero (el sueldo es costo del establecimiento, RN-15).
  personal_propio boolean not null default false,
  cultivo_id uuid references public.cultivo (id),
  descripcion text,
  -- Moneda de los importes dichos en esta carga (RN-01). En pesos, el tipo de cambio es el vigente a la fecha
  -- de la labor (automático o manual según la tabla), o el que diga el usuario (manual).
  moneda text not null default 'USD' check (moneda in ('USD', 'ARS')),
  tipo_cambio numeric(14, 4) check (tipo_cambio is null or tipo_cambio > 0),
  tipo_cambio_fuente text check (tipo_cambio_fuente in ('automatico', 'manual')),
  precio_ha_declarado numeric(16, 4) check (precio_ha_declarado is null or precio_ha_declarado >= 0),
  costo_declarado numeric(18, 2) check (costo_declarado is null or costo_declarado >= 0),
  -- Calculado por el sistema
  precio_servicio_ha_usd numeric(14, 4),
  valor_referencia_id uuid,
  costo_servicio_usd numeric(16, 2),
  costo_insumos_usd numeric(16, 2) not null default 0,
  costo_total_usd numeric(16, 2) not null default 0,
  costo_total_ha_usd numeric(14, 2) not null default 0,
  costo_incompleto boolean not null default true,
  creado_por uuid not null default app.usuario_id() references public.usuario (id),
  origen text not null default app.origen() check (origen in ('bot', 'panel')),
  mensaje_id uuid default app.mensaje_id(),
  anulada_en timestamptz,
  anulada_por uuid references public.usuario (id),
  motivo_anulacion text,
  creado_en timestamptz not null default now(),
  unique (establecimiento_id, id),
  foreign key (establecimiento_id, lote_id) references public.lote (establecimiento_id, id),
  foreign key (establecimiento_id, ciclo_id) references public.ciclo (establecimiento_id, id),
  foreign key (establecimiento_id, valor_referencia_id) references public.valor_referencia (establecimiento_id, id),
  check ((anulada_en is null) = (anulada_por is null)),
  check ((moneda = 'ARS') = (tipo_cambio is not null and tipo_cambio_fuente is not null)),
  check (precio_ha_declarado is null or costo_declarado is null),
  check (not personal_propio or (not contratado and precio_ha_declarado is null and costo_declarado is null))
);
create index labor_ciclo_idx on public.labor (establecimiento_id, ciclo_id);
create index labor_lote_fecha_idx on public.labor (establecimiento_id, lote_id, fecha);

-- Insumos de una labor (RF-09, RN-13). Se dice la dosis por ha o la cantidad total, en la unidad del producto
-- (en semillas, también en kg: se convierte a bolsas con el peso por bolsa del producto).
create table public.labor_insumo (
  id uuid primary key default gen_random_uuid(),
  establecimiento_id uuid not null,
  labor_id uuid not null,
  producto_id uuid not null,
  dosis_ha numeric(14, 4) check (dosis_ha is null or dosis_ha > 0),
  cantidad numeric(14, 3) check (cantidad is null or cantidad > 0),
  unidad text not null check (unidad in ('l', 'kg', 'bolsa', 'unidad')),
  -- Calculado: lo que sale del stock, en la unidad del producto; precio del momento (RN-10) y costo.
  cantidad_producto numeric(14, 3),
  precio_unitario_usd numeric(14, 4),
  costo_usd numeric(16, 2),
  creado_en timestamptz not null default now(),
  unique (establecimiento_id, id),
  foreign key (establecimiento_id, labor_id) references public.labor (establecimiento_id, id),
  foreign key (establecimiento_id, producto_id) references public.producto (establecimiento_id, id),
  check (dosis_ha is not null or cantidad is not null)
);
create index labor_insumo_labor_idx on public.labor_insumo (establecimiento_id, labor_id);
create index labor_insumo_sin_precio_idx on public.labor_insumo (producto_id) where precio_unitario_usd is null;

-- Temporales de una carpida o de una labor "otra" (RN-17, RF-27). Horas por día y pago por hora salen de los
-- valores de referencia, salvo que se digan (el pago, en la moneda de la labor).
create table public.carpida (
  id uuid primary key default gen_random_uuid(),
  establecimiento_id uuid not null,
  labor_id uuid not null,
  personas integer not null check (personas > 0),
  dias numeric(6, 2) not null check (dias > 0),
  horas_dia numeric(5, 2) check (horas_dia is null or (horas_dia > 0 and horas_dia <= 24)),
  pago_hora numeric(16, 4) check (pago_hora is null or pago_hora >= 0),
  pago_hora_usd numeric(14, 4),
  costo_usd numeric(16, 2) generated always as (round(personas * dias * horas_dia * pago_hora_usd, 2)) stored,
  creado_en timestamptz not null default now(),
  unique (establecimiento_id, id),
  unique (labor_id),
  foreign key (establecimiento_id, labor_id) references public.labor (establecimiento_id, id)
);

-- Movimientos de stock de las labores: ahora sí, con su clave foránea (uno por línea de insumo).
alter table public.movimiento_stock
  add constraint movimiento_stock_labor_insumo_fk
  foreign key (establecimiento_id, labor_insumo_id) references public.labor_insumo (establecimiento_id, id);
alter table public.movimiento_stock add constraint movimiento_stock_labor_insumo_uk unique (labor_insumo_id);

-- Costos de una labor: servicio + insumos, total y por ha. "Costo incompleto" si falta el del servicio
-- o el precio de algún insumo. Se llama al cargar y en los recálculos permitidos (excepción de RN-10).
create function app.recalcular_costos_labor(p_labor uuid) returns void
language plpgsql security definer set search_path = ''
as $$
declare
  l public.labor;
  v_costeo text;
  v_servicio numeric;
  v_insumos numeric;
  v_sin_precio boolean;
begin
  select * into l from public.labor where id = p_labor;
  select costeo into v_costeo from public.tipo_labor where id = l.tipo_labor_id;
  v_servicio := case
    when l.personal_propio then 0
    when l.costo_declarado is not null then round(l.costo_declarado / coalesce(l.tipo_cambio, 1), 2)
    when l.precio_servicio_ha_usd is not null then round(l.precio_servicio_ha_usd * l.ha, 2)
    when v_costeo = 'temporales' then (select c.costo_usd from public.carpida c where c.labor_id = p_labor)
  end;
  select coalesce(sum(costo_usd), 0), coalesce(bool_or(precio_unitario_usd is null), false)
    into v_insumos, v_sin_precio
  from public.labor_insumo where labor_id = p_labor;
  update public.labor set
    costo_servicio_usd = v_servicio,
    costo_insumos_usd = v_insumos,
    costo_total_usd = coalesce(v_servicio, 0) + v_insumos,
    costo_total_ha_usd = round((coalesce(v_servicio, 0) + v_insumos) / l.ha, 2),
    costo_incompleto = v_servicio is null or v_sin_precio
  where id = p_labor;
end
$$;

create function app.labor_antes_de_insertar() returns trigger
language plpgsql set search_path = ''
as $$
declare
  v_tipo public.tipo_labor;
  v_ciclo public.ciclo;
  v_equipos text[];
  v_tc record;
  v_ref record;
begin
  select * into v_tipo from public.tipo_labor where id = new.tipo_labor_id;
  if v_tipo.codigo = 'otra' and length(btrim(coalesce(new.descripcion, ''))) = 0 then
    raise exception 'una labor "otra" lleva una descripción de lo que se hizo' using errcode = '23514';
  end if;
  if (v_tipo.codigo = 'siembra') <> (new.cultivo_id is not null) then
    raise exception 'el cultivo se indica en la siembra, y solo en la siembra' using errcode = '23514';
  end if;
  if new.personal_propio and v_tipo.costeo <> 'temporales' then
    raise exception 'solo una carpida o una labor "otra" se marca como hecha por personal propio'
      using errcode = '23514';
  end if;
  -- RF-10: en las labores con precio por ha, el costo real se carga solo si fue contratada.
  if v_tipo.costeo = 'por_ha' and not new.contratado
     and (new.precio_ha_declarado is not null or new.costo_declarado is not null) then
    raise exception 'el costo real del servicio se carga solo si la labor fue contratada' using errcode = '23514';
  end if;
  -- RN-11: una pulverización propia solo con equipos que tiene el establecimiento.
  if v_tipo.equipo is not null and not new.contratado then
    select equipos_pulverizacion into v_equipos from public.establecimiento where id = new.establecimiento_id;
    if not (v_tipo.equipo = any (coalesce(v_equipos, '{}'))) then
      raise exception 'el establecimiento no tiene % propio: ¿la pulverización fue contratada?',
        case v_tipo.equipo when 'avion' then 'avión' else v_tipo.equipo end
        using errcode = '23514', hint = 'equipo_no_propio';
    end if;
  end if;
  -- RN-01: importes en pesos con el tipo de cambio vigente a la fecha de la labor, o el que se diga.
  new.tipo_cambio_fuente := null;
  if new.moneda = 'ARS' then
    if new.tipo_cambio is null then
      select * into v_tc from app.tipo_cambio_vigente(new.fecha);
      if v_tc.id is null then
        raise exception 'no hay tipo de cambio cargado para el %', to_char(new.fecha, 'DD/MM/YYYY')
          using errcode = '23514';
      end if;
      new.tipo_cambio := v_tc.valor;
      new.tipo_cambio_fuente := v_tc.fuente;
    else
      new.tipo_cambio_fuente := 'manual';
    end if;
  elsif new.tipo_cambio is not null then
    raise exception 'el tipo de cambio va solo con importes en pesos' using errcode = '23514';
  end if;

  -- RN-02: el ciclo sale de la fecha. RN-12 y RF-08: como máximo las ha limpias del ciclo.
  new.ciclo_id := app.ciclo_para_labor(new.lote_id, new.fecha, new.cultivo_id);
  select * into v_ciclo from public.ciclo where id = new.ciclo_id;
  if new.ha > v_ciclo.ha_limpias then
    raise exception 'el lote tiene % ha limpias en este ciclo y la labor dice % ha',
      v_ciclo.ha_limpias, new.ha using errcode = '23514', hint = 'ha_de_mas';
  end if;

  -- Precio del servicio por ha: el dicho o el de referencia vigente a la fecha (RN-10, RN-11).
  new.valor_referencia_id := null;
  new.precio_servicio_ha_usd := null;
  if new.precio_ha_declarado is not null then
    new.precio_servicio_ha_usd := round(new.precio_ha_declarado / coalesce(new.tipo_cambio, 1), 4);
  elsif new.costo_declarado is null and v_tipo.costeo = 'por_ha' then
    select * into v_ref from app.valor_referencia_vigente(
      case when v_tipo.equipo is null then 'servicio_labor' else 'pulverizacion' end, new.fecha, new.tipo_labor_id);
    new.valor_referencia_id := v_ref.id;
    new.precio_servicio_ha_usd := v_ref.valor;
  end if;
  -- Los costos los completa app.recalcular_costos_labor al terminar de insertar.
  new.costo_servicio_usd := null;
  new.costo_insumos_usd := 0;
  new.costo_total_usd := 0;
  new.costo_total_ha_usd := 0;
  new.costo_incompleto := true;
  return new;
end
$$;
create trigger labor_antes_de_insertar before insert on public.labor
  for each row execute function app.labor_antes_de_insertar();

create function app.labor_despues_de_insertar() returns trigger
language plpgsql security definer set search_path = ''
as $$
begin
  perform app.recalcular_costos_labor(new.id);
  return null;
end
$$;
create trigger labor_despues_de_insertar after insert on public.labor
  for each row execute function app.labor_despues_de_insertar();

-- Una labor de un ciclo cerrado no se anula hasta que el dueño lo reabra (RN-02).
create function app.labor_antes_de_actualizar() returns trigger
language plpgsql set search_path = ''
as $$
begin
  if current_user = 'micampo_app' and new.anulada_en is distinct from old.anulada_en
     and (select estado from public.ciclo where id = old.ciclo_id) = 'cerrado' then
    raise exception 'la labor es del ciclo de %, que está cerrado: solo se anula si el dueño lo reabre',
      app.nombre_ciclo(old.ciclo_id) using errcode = '23514', hint = 'ciclo_cerrado';
  end if;
  return new;
end
$$;
create trigger labor_antes_de_actualizar before update on public.labor
  for each row execute function app.labor_antes_de_actualizar();

-- Anular una labor devuelve sus insumos al stock (RN-09, HU-03). Si era la única siembra del ciclo,
-- el ciclo vuelve a estar en preparación, sin cultivo ni campaña.
create function app.labor_despues_de_anular() returns trigger
language plpgsql security definer set search_path = ''
as $$
begin
  update public.movimiento_stock m set
    anulada_en = new.anulada_en, anulada_por = new.anulada_por,
    motivo_anulacion = coalesce(new.motivo_anulacion, 'labor anulada')
  from public.labor_insumo i
  where i.labor_id = new.id and m.labor_insumo_id = i.id and m.anulada_en is null;
  if new.cultivo_id is not null and not exists (
       select 1 from public.labor
       where ciclo_id = new.ciclo_id and cultivo_id is not null and anulada_en is null and id <> new.id) then
    update public.ciclo set cultivo_id = null, campana_anio = null, estado = 'en_preparacion'
    where id = new.ciclo_id and estado = 'abierto';
  end if;
  return null;
end
$$;
create trigger labor_despues_de_anular after update of anulada_en on public.labor
  for each row when (old.anulada_en is null and new.anulada_en is not null)
  execute function app.labor_despues_de_anular();

-- Agregar insumos o temporales: a una labor vigente, de un ciclo no cerrado, quien la cargó o el dueño.
create function app.labor_admite_agregados(p_labor uuid) returns public.labor
language plpgsql stable set search_path = ''
as $$
declare l public.labor;
begin
  select * into l from public.labor where id = p_labor;
  if not found then
    raise exception 'la labor no existe' using errcode = '22023';
  end if;
  if l.anulada_en is not null then
    raise exception 'la labor está anulada' using errcode = '42501';
  end if;
  if l.creado_por is distinct from app.usuario_id() and not app.es_dueno() then
    raise exception 'el encargado solo puede completar sus propias labores' using errcode = '42501';
  end if;
  if (select estado from public.ciclo where id = l.ciclo_id) = 'cerrado' then
    raise exception 'la labor es de un ciclo cerrado' using errcode = '23514', hint = 'ciclo_cerrado';
  end if;
  return l;
end
$$;

create function app.labor_insumo_antes_de_insertar() returns trigger
language plpgsql set search_path = ''
as $$
declare
  l public.labor;
  v_codigo text;
  p public.producto;
  v_factor numeric;
begin
  l := app.labor_admite_agregados(new.labor_id);
  select codigo into v_codigo from public.tipo_labor where id = l.tipo_labor_id;
  select * into p from public.producto where id = new.producto_id;
  if not found then
    raise exception 'el producto no existe' using errcode = '22023';
  end if;
  if p.categoria = 'repuesto' then
    raise exception 'los repuestos no son insumos de una labor: se cargan como uso de repuesto' using errcode = '23514';
  end if;
  if p.categoria = 'semilla' and (v_codigo <> 'siembra' or p.cultivo_id is distinct from l.cultivo_id) then
    raise exception 'la semilla % solo se usa en una siembra de su cultivo', p.nombre using errcode = '23514';
  end if;
  if new.dosis_ha is not null and new.cantidad is not null then
    raise exception 'se carga la dosis por ha o la cantidad total, no las dos' using errcode = '23514';
  end if;
  -- RN-14: la unidad del producto. RN-13: las semillas, también en kg, se pasan a bolsas.
  if new.unidad = p.unidad then
    v_factor := 1;
  elsif p.unidad = 'bolsa' and new.unidad = 'kg' then
    v_factor := 1 / p.kg_por_bolsa;
  else
    raise exception '% se carga en %, no en %', p.nombre, p.unidad, new.unidad using errcode = '23514';
  end if;
  if new.dosis_ha is not null then
    new.cantidad := round(new.dosis_ha * l.ha, 3);
  else
    new.dosis_ha := round(new.cantidad / l.ha, 4);
  end if;
  new.cantidad_producto := round(new.cantidad * v_factor, 3);
  if new.cantidad_producto <= 0 then
    raise exception 'la cantidad es demasiado chica' using errcode = '23514';
  end if;
  -- Precio del momento (RN-10): el promedio vigente, el mismo que guarda el movimiento de stock.
  new.precio_unitario_usd := p.precio_promedio_usd;
  new.costo_usd := round(new.cantidad_producto * p.precio_promedio_usd, 2);
  return new;
end
$$;
create trigger labor_insumo_antes_de_insertar before insert on public.labor_insumo
  for each row execute function app.labor_insumo_antes_de_insertar();

create function app.labor_insumo_despues_de_insertar() returns trigger
language plpgsql security definer set search_path = ''
as $$
declare l public.labor;
begin
  select * into l from public.labor where id = new.labor_id;
  insert into public.movimiento_stock
    (establecimiento_id, producto_id, fecha, cantidad, tipo, labor_insumo_id, creado_por, origen, mensaje_id)
  values
    (new.establecimiento_id, new.producto_id, l.fecha, -new.cantidad_producto, 'labor', new.id,
     l.creado_por, l.origen, l.mensaje_id);
  perform app.recalcular_costos_labor(new.labor_id);
  return null;
end
$$;
create trigger labor_insumo_despues_de_insertar after insert on public.labor_insumo
  for each row execute function app.labor_insumo_despues_de_insertar();

create function app.carpida_antes_de_insertar() returns trigger
language plpgsql set search_path = ''
as $$
declare
  l public.labor;
  v_costeo text;
begin
  l := app.labor_admite_agregados(new.labor_id);
  select costeo into v_costeo from public.tipo_labor where id = l.tipo_labor_id;
  if v_costeo <> 'temporales' then
    raise exception 'los temporales se cargan solo en una carpida o en una labor "otra"' using errcode = '23514';
  end if;
  if l.costo_declarado is not null or l.precio_ha_declarado is not null then
    raise exception 'la labor ya tiene un costo dicho: va ese costo o los temporales, no los dos'
      using errcode = '23514';
  end if;
  if l.personal_propio then
    raise exception 'la labor la hizo personal propio: no lleva temporales' using errcode = '23514';
  end if;
  if new.horas_dia is null then
    new.horas_dia := (select valor from app.valor_referencia_vigente('horas_dia_temporal', l.fecha));
  end if;
  new.pago_hora_usd := case
    when new.pago_hora is not null then round(new.pago_hora / coalesce(l.tipo_cambio, 1), 4)
    else (select valor from app.valor_referencia_vigente('pago_hora_temporal', l.fecha))
  end;
  return new;
end
$$;
create trigger carpida_antes_de_insertar before insert on public.carpida
  for each row execute function app.carpida_antes_de_insertar();

create function app.carpida_despues_de_insertar() returns trigger
language plpgsql security definer set search_path = ''
as $$
begin
  perform app.recalcular_costos_labor(new.labor_id);
  return null;
end
$$;
create trigger carpida_despues_de_insertar after insert on public.carpida
  for each row execute function app.carpida_despues_de_insertar();

-- Cuando el dueño carga un valor de referencia, todas las labores que quedaron sin ese valor lo toman, sin
-- importar su fecha (excepción de RN-10, con registro en la auditoría). Las que ya tenían costo no cambian.
create function app.valor_referencia_despues_de_insertar() returns trigger
language plpgsql security definer set search_path = ''
as $$
declare r record;
begin
  if new.concepto in ('servicio_labor', 'pulverizacion') then
    for r in
      update public.labor l set precio_servicio_ha_usd = new.valor, valor_referencia_id = new.id
      where l.establecimiento_id = new.establecimiento_id and l.tipo_labor_id = new.tipo_labor_id
        and l.anulada_en is null and l.precio_servicio_ha_usd is null and l.costo_declarado is null
      returning l.id
    loop
      perform app.recalcular_costos_labor(r.id);
    end loop;
  elsif new.concepto in ('pago_hora_temporal', 'horas_dia_temporal') then
    for r in
      update public.carpida c set
        pago_hora_usd = case when new.concepto = 'pago_hora_temporal' then coalesce(c.pago_hora_usd, new.valor) else c.pago_hora_usd end,
        horas_dia = case when new.concepto = 'horas_dia_temporal' then coalesce(c.horas_dia, new.valor) else c.horas_dia end
      from public.labor l
      where c.establecimiento_id = new.establecimiento_id and l.id = c.labor_id and l.anulada_en is null
        and ((new.concepto = 'pago_hora_temporal' and c.pago_hora_usd is null)
          or (new.concepto = 'horas_dia_temporal' and c.horas_dia is null))
      returning c.labor_id
    loop
      perform app.recalcular_costos_labor(r.labor_id);
    end loop;
  end if;
  return null;
end
$$;
create trigger valor_referencia_despues_de_insertar after insert on public.valor_referencia
  for each row execute function app.valor_referencia_despues_de_insertar();

-- Insumos sin precio (RN-10, RN-30): cuando el producto tiene precio, se completan solo las líneas de labor
-- cargadas sin precio, y sus movimientos de stock. Las líneas que ya tenían precio no se tocan.
create function app.completar_insumos_sin_precio(p_producto uuid, p_precio_usd numeric) returns void
language plpgsql security definer set search_path = ''
as $$
declare r record;
begin
  if p_precio_usd is null then
    return;
  end if;
  update public.movimiento_stock set precio_unitario_usd = p_precio_usd
  where producto_id = p_producto and tipo = 'labor' and precio_unitario_usd is null and anulada_en is null;
  for r in
    with completadas as (
      update public.labor_insumo i
      set precio_unitario_usd = p_precio_usd, costo_usd = round(i.cantidad_producto * p_precio_usd, 2)
      from public.labor l
      where i.producto_id = p_producto and i.precio_unitario_usd is null
        and l.id = i.labor_id and l.anulada_en is null
      returning i.labor_id
    )
    select distinct labor_id from completadas
  loop
    perform app.recalcular_costos_labor(r.labor_id);
  end loop;
end
$$;

-- El dueño fija un precio pendiente: además del promedio, completa las líneas de labor sin precio.
create or replace function app.fijar_precio_pendiente(p_producto uuid, p_precio_usd numeric) returns void
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
  perform app.completar_insumos_sin_precio(p_producto, p_precio_usd);
end
$$;

-- Compras en pesos (RN-01, RN-16): si no se dice el tipo de cambio, se toma el vigente a la fecha de la compra
-- con su fuente (automático o manual); si se dice, queda como manual. La fuente la pone el sistema.
create function app.compra_antes_de_insertar() returns trigger
language plpgsql set search_path = ''
as $$
declare v_tc record;
begin
  new.tipo_cambio_fuente := null;
  if new.moneda = 'ARS' then
    if new.tipo_cambio is null then
      select * into v_tc from app.tipo_cambio_vigente(new.fecha);
      if v_tc.id is null then
        raise exception 'no hay tipo de cambio cargado para el %', to_char(new.fecha, 'DD/MM/YYYY')
          using errcode = '23514';
      end if;
      new.tipo_cambio := v_tc.valor;
      new.tipo_cambio_fuente := v_tc.fuente;
    else
      new.tipo_cambio_fuente := 'manual';
    end if;
  elsif new.tipo_cambio is not null then
    raise exception 'el tipo de cambio va solo con importes en pesos' using errcode = '23514';
  end if;
  return new;
end
$$;
create trigger compra_antes_de_insertar before insert on public.compra
  for each row execute function app.compra_antes_de_insertar();
revoke insert (tipo_cambio_fuente) on public.compra from micampo_app;

-- Una compra con precio también completa las líneas de labor sin precio, con el promedio que queda después
-- de la compra (si el producto no tenía precio, es el de la compra, RN-04).
create or replace function app.compra_item_despues_de_insertar() returns trigger
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
  if new.precio_unitario_usd is not null then
    perform app.completar_insumos_sin_precio(
      new.producto_id, (select precio_promedio_usd from public.producto where id = new.producto_id));
  end if;
  return null;
end
$$;

-- Movimientos de stock: los de labor solo los genera la carga de insumos y solo se anulan anulando la labor. --
create or replace function app.movimiento_antes_de_insertar() returns trigger
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
  if new.tipo = 'labor' and pg_catalog.pg_trigger_depth() < 2 then
    raise exception 'los movimientos de labor se generan solo al cargar los insumos de la labor' using errcode = '42501';
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

create or replace function app.movimiento_antes_de_actualizar() returns trigger
language plpgsql set search_path = ''
as $$
begin
  if current_user = 'micampo_app' and old.tipo = 'compra'
     and new.anulada_en is distinct from old.anulada_en then
    raise exception 'un movimiento de compra se anula anulando la compra' using errcode = '42501';
  end if;
  if current_user = 'micampo_app' and old.tipo = 'labor'
     and new.anulada_en is distinct from old.anulada_en then
    raise exception 'un movimiento de labor se anula anulando la labor' using errcode = '42501';
  end if;
  return new;
end
$$;

revoke insert (labor_insumo_id) on public.movimiento_stock from micampo_app;

-- Quién ve costos (RB-18): el dueño siempre; los encargados, solo si el dueño lo habilitó en su establecimiento.
-- Lo cambia solo el dueño (la política de establecimiento ya lo exige). El bot y el panel lo consultan
-- antes de mostrar costos totales, márgenes, utilidad o ventas.
alter table public.establecimiento add column encargado_ve_costos boolean not null default false;
grant update (encargado_ve_costos) on public.establecimiento to micampo_app;

create function app.puede_ver_costos() returns boolean
language sql stable security definer set search_path = ''
as $$
  select app.es_dueno() or (app.es_miembro() and exists (
    select 1 from public.establecimiento e where e.id = app.establecimiento_id() and e.encargado_ve_costos))
$$;

-- Protección: RLS forzado, auditoría y permisos mínimos --------------------------------------------
select app.proteger_tabla('public.valor_referencia', p_carga => true);
select app.proteger_tabla('public.labor', p_carga => true);
select app.proteger_tabla('public.labor_insumo');
select app.proteger_tabla('public.carpida');

-- valor_referencia: solo se agregan filas, y solo el dueño (RN-29). La fecha desde la que rige la pone el sistema.
revoke insert, update on public.valor_referencia from micampo_app;
grant insert (establecimiento_id, concepto, tipo_labor_id, cultivo_id, campana_anio, valor)
  on public.valor_referencia to micampo_app;
create policy valor_referencia_solo_dueno on public.valor_referencia as restrictive for insert to micampo_app
  with check ((select app.es_dueno()));

-- labor: se carga y se anula; para corregirla se anula y se vuelve a cargar (RN-09).
revoke insert, update on public.labor from micampo_app;
grant insert (establecimiento_id, lote_id, tipo_labor_id, fecha, ha, contratado, personal_propio, cultivo_id,
              descripcion, moneda, tipo_cambio, precio_ha_declarado, costo_declarado)
  on public.labor to micampo_app;
grant update (anulada_en, anulada_por, motivo_anulacion) on public.labor to micampo_app;
create trigger labor_reglas_carga before update on public.labor
  for each row execute function app.reglas_carga();

-- labor_insumo y carpida: solo se agregan.
revoke insert, update on public.labor_insumo from micampo_app;
grant insert (establecimiento_id, labor_id, producto_id, dosis_ha, cantidad, unidad)
  on public.labor_insumo to micampo_app;
revoke insert, update on public.carpida from micampo_app;
grant insert (establecimiento_id, labor_id, personas, dias, horas_dia, pago_hora)
  on public.carpida to micampo_app;

grant execute on function app.tipo_cambio_vigente(date),
  app.valor_referencia_vigente(text, date, uuid, uuid, integer),
  app.nombre_ciclo(uuid), app.ciclo_para_labor(uuid, date, uuid),
  app.labor_admite_agregados(uuid), app.puede_ver_costos() to micampo_app;

-- PostgreSQL deja ejecutar cualquier función nueva a todos (PUBLIC). Se quita, y el backend
-- solo ejecuta lo que se le concedió explícitamente arriba. Cada migración que crea funciones termina así.
revoke execute on all functions in schema app from public;
