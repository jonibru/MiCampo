-- 0002 Acceso: usuarios, establecimientos, membresías, auditoría y protección de tablas.
-- Diseño: sección 2 (roles), RF-23, RF-28, RN-09, RNF-05, RNF-16.

create table public.usuario (
  id uuid primary key default gen_random_uuid(),
  auth_user_id uuid unique references auth.users (id) on delete set null,
  nombre text not null check (length(btrim(nombre)) > 0),
  telefono_whatsapp text not null unique check (telefono_whatsapp ~ '^\+[1-9][0-9]{7,14}$'),
  email text,
  activo boolean not null default true,
  ultimo_establecimiento_id uuid,
  telefono_verificado_en timestamptz,
  codigo_verificacion_hash text,
  codigo_vencimiento timestamptz,
  codigo_intentos integer not null default 0 check (codigo_intentos >= 0),
  creado_en timestamptz not null default now()
);
create unique index usuario_email_uk on public.usuario (lower(email)) where email is not null;

create table public.establecimiento (
  id uuid primary key default gen_random_uuid(),
  nombre text not null check (length(btrim(nombre)) > 0),
  equipos_pulverizacion text[] not null default array['mosquito']
    check (equipos_pulverizacion <@ array['mosquito', 'dron', 'avion']),
  creado_en timestamptz not null default now()
);

alter table public.usuario
  add constraint usuario_ultimo_establecimiento_fk
  foreign key (ultimo_establecimiento_id) references public.establecimiento (id) on delete set null;

create table public.membresia (
  id uuid primary key default gen_random_uuid(),
  usuario_id uuid not null references public.usuario (id),
  establecimiento_id uuid not null references public.establecimiento (id),
  rol text not null check (rol in ('dueno', 'encargado')),
  activa boolean not null default true,
  creado_en timestamptz not null default now(),
  unique (usuario_id, establecimiento_id)
);
create index membresia_establecimiento_idx on public.membresia (establecimiento_id);

-- Quién soy en el contexto actual -------------------------------------------
-- SECURITY DEFINER: leen las tablas saltando RLS para evitar recursión en las políticas.
-- La baja de una membresía o de un usuario corta el acceso en el momento.

create function app.es_miembro() returns boolean
language sql stable security definer set search_path = ''
as $$
  select exists (
    select 1
    from public.membresia m
    join public.usuario u on u.id = m.usuario_id
    where m.usuario_id = app.usuario_id()
      and m.establecimiento_id = app.establecimiento_id()
      and m.activa and u.activo
  )
$$;

create function app.es_dueno() returns boolean
language sql stable security definer set search_path = ''
as $$
  select exists (
    select 1
    from public.membresia m
    join public.usuario u on u.id = m.usuario_id
    where m.usuario_id = app.usuario_id()
      and m.establecimiento_id = app.establecimiento_id()
      and m.rol = 'dueno' and m.activa and u.activo
  )
$$;
grant execute on function app.es_miembro(), app.es_dueno() to micampo_app;

-- Auditoría (RNF-05): una fila por cada cambio de datos, escrita por trigger ---

create table public.auditoria (
  id uuid primary key default gen_random_uuid(),
  establecimiento_id uuid,
  tabla text not null,
  registro_id uuid,
  accion text not null check (accion in ('insert', 'update', 'delete')),
  antes jsonb,
  despues jsonb,
  usuario_id uuid,
  origen text,
  mensaje_id uuid,
  creado_en timestamptz not null default now()
);
create index auditoria_establecimiento_idx on public.auditoria (establecimiento_id, creado_en desc);
create index auditoria_registro_idx on public.auditoria (tabla, registro_id);

create function app.auditar() returns trigger
language plpgsql security definer set search_path = ''
as $$
declare
  v_antes jsonb := case when tg_op in ('UPDATE', 'DELETE') then to_jsonb(old) - 'codigo_verificacion_hash' end;
  v_despues jsonb := case when tg_op in ('INSERT', 'UPDATE') then to_jsonb(new) - 'codigo_verificacion_hash' end;
  v_fila jsonb;
  v_est uuid;
begin
  if tg_op = 'UPDATE' and v_antes = v_despues then
    return null;
  end if;
  v_fila := coalesce(v_despues, v_antes);
  v_est := case
    when tg_table_name = 'establecimiento' then (v_fila ->> 'id')::uuid
    else coalesce((v_fila ->> 'establecimiento_id')::uuid, app.establecimiento_id())
  end;
  insert into public.auditoria
    (establecimiento_id, tabla, registro_id, accion, antes, despues, usuario_id, origen, mensaje_id)
  values
    (v_est, tg_table_name, (v_fila ->> 'id')::uuid, lower(tg_op), v_antes, v_despues,
     app.usuario_id(), app.origen(), app.mensaje_id());
  return null;
end
$$;

-- Protege una tabla de un establecimiento: RLS forzado, permisos mínimos, auditoría.
-- Uso en cada migración que crea una tabla con establecimiento_id.
--   p_carga:    tabla de cargas (exige creado_por = usuario del contexto al insertar)
--   p_borrable: se permite DELETE (por defecto no: nada se borra, se anula)
create function app.proteger_tabla(
  p_tabla regclass,
  p_carga boolean default false,
  p_borrable boolean default false
) returns void
language plpgsql set search_path = ''
as $$
declare
  v_nombre text := (select relname from pg_catalog.pg_class where oid = p_tabla);
  v_filtro text := 'establecimiento_id = app.establecimiento_id() and (select app.es_miembro())';
  v_insert text := v_filtro || case when p_carga then ' and creado_por = app.usuario_id()' else '' end;
begin
  execute format('alter table %s enable row level security', p_tabla);
  execute format('alter table %s force row level security', p_tabla);
  execute format('revoke all on %s from public', p_tabla);
  if exists (select 1 from pg_catalog.pg_roles where rolname = 'anon') then
    execute format('revoke all on %s from anon, authenticated', p_tabla);
  end if;
  execute format('grant select, insert, update on %s to micampo_app', p_tabla);
  execute format('create policy %I on %s for select to micampo_app using (%s)',
                 v_nombre || '_select', p_tabla, v_filtro);
  execute format('create policy %I on %s for insert to micampo_app with check (%s)',
                 v_nombre || '_insert', p_tabla, v_insert);
  execute format('create policy %I on %s for update to micampo_app using (%s) with check (%s)',
                 v_nombre || '_update', p_tabla, v_filtro, v_filtro);
  if p_borrable then
    execute format('grant delete on %s to micampo_app', p_tabla);
    execute format('create policy %I on %s for delete to micampo_app using (%s)',
                   v_nombre || '_delete', p_tabla, v_filtro);
  end if;
  execute format('create trigger %I after insert or update or delete on %s for each row execute function app.auditar()',
                 v_nombre || '_auditar', p_tabla);
end
$$;
-- Solo el dueño de la base (migraciones) la ejecuta: sin grant para micampo_app.

-- Políticas de las tablas de acceso (no usan proteger_tabla: tienen reglas propias) ----

do $$
declare t text;
begin
  foreach t in array array['usuario', 'establecimiento', 'membresia', 'auditoria'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('alter table public.%I force row level security', t);
    execute format('revoke all on public.%I from public', t);
    if exists (select 1 from pg_roles where rolname = 'anon') then
      execute format('revoke all on public.%I from anon, authenticated', t);
    end if;
  end loop;
end
$$;

-- usuario: cada uno se ve a sí mismo; el dueño y el encargado ven a los miembros de su establecimiento.
-- Los usuarios se crean con app.crear_usuario (alta) o app.invitar_encargado (invitación).
grant select on public.usuario to micampo_app;
grant update (nombre, email, ultimo_establecimiento_id) on public.usuario to micampo_app;
create policy usuario_select on public.usuario for select to micampo_app
  using (
    id = app.usuario_id()
    or ((select app.es_miembro()) and exists (
          select 1 from public.membresia m
          where m.usuario_id = usuario.id and m.establecimiento_id = app.establecimiento_id()))
  );
create policy usuario_update on public.usuario for update to micampo_app
  using (
    id = app.usuario_id()
    or ((select app.es_dueno()) and exists (
          select 1 from public.membresia m
          where m.usuario_id = usuario.id and m.establecimiento_id = app.establecimiento_id()))
  )
  with check (
    id = app.usuario_id()
    or ((select app.es_dueno()) and exists (
          select 1 from public.membresia m
          where m.usuario_id = usuario.id and m.establecimiento_id = app.establecimiento_id()))
  );

-- establecimiento: lo ven los miembros; solo el dueño lo modifica. Se crea con app.crear_establecimiento.
grant select on public.establecimiento to micampo_app;
grant update (nombre, equipos_pulverizacion) on public.establecimiento to micampo_app;
create policy establecimiento_select on public.establecimiento for select to micampo_app
  using (id = app.establecimiento_id() and (select app.es_miembro()));
create policy establecimiento_update on public.establecimiento for update to micampo_app
  using (id = app.establecimiento_id() and (select app.es_dueno()))
  with check (id = app.establecimiento_id() and (select app.es_dueno()));

-- membresia: la ven los miembros; solo el dueño cambia rol o da de baja. Se crea con app.invitar_encargado.
grant select on public.membresia to micampo_app;
grant update (rol, activa) on public.membresia to micampo_app;
create policy membresia_select on public.membresia for select to micampo_app
  using (establecimiento_id = app.establecimiento_id() and (select app.es_miembro()));
create policy membresia_update on public.membresia for update to micampo_app
  using (establecimiento_id = app.establecimiento_id() and (select app.es_dueno()))
  with check (establecimiento_id = app.establecimiento_id() and (select app.es_dueno()));

-- auditoria: solo lectura, y solo para el dueño (RF-38). Escribe únicamente el trigger.
grant select on public.auditoria to micampo_app;
create policy auditoria_select on public.auditoria for select to micampo_app
  using (establecimiento_id = app.establecimiento_id() and (select app.es_dueno()));

create trigger usuario_auditar after insert or update or delete on public.usuario
  for each row execute function app.auditar();
create trigger establecimiento_auditar after insert or update or delete on public.establecimiento
  for each row execute function app.auditar();
create trigger membresia_auditar after insert or update or delete on public.membresia
  for each row execute function app.auditar();

-- Operaciones previas a tener contexto (identificación y alta) ----------------

-- El bot identifica a la persona por su teléfono antes de saber de qué establecimiento habla.
create function app.identificar_usuario(p_telefono text)
returns table (usuario_id uuid, nombre text, activo boolean,
               ultimo_establecimiento_id uuid, telefono_verificado boolean)
language sql stable security definer set search_path = ''
as $$
  select u.id, u.nombre, u.activo, u.ultimo_establecimiento_id, u.telefono_verificado_en is not null
  from public.usuario u
  where u.telefono_whatsapp = p_telefono
$$;

-- Para el panel: la cuenta de Supabase Auth apunta a un usuario de Mi Campo.
create function app.usuario_por_auth(p_auth_user_id uuid) returns uuid
language sql stable security definer set search_path = ''
as $$ select u.id from public.usuario u where u.auth_user_id = p_auth_user_id and u.activo $$;

-- Establecimientos activos del usuario del contexto (primero fijar_contexto con establecimiento nulo).
create function app.membresias_de(p_usuario uuid)
returns table (establecimiento_id uuid, nombre text, rol text)
language sql stable security definer set search_path = ''
as $$
  select e.id, e.nombre, m.rol
  from public.membresia m
  join public.establecimiento e on e.id = m.establecimiento_id
  where m.usuario_id = p_usuario and m.activa and p_usuario = app.usuario_id()
$$;

create function app.crear_usuario(
  p_nombre text, p_telefono text, p_email text default null, p_auth_user_id uuid default null
) returns uuid
language sql security definer set search_path = ''
as $$
  insert into public.usuario (nombre, telefono_whatsapp, email, auth_user_id)
  values (p_nombre, p_telefono, p_email, p_auth_user_id)
  returning id
$$;

-- Alta del establecimiento: crea el establecimiento y deja al usuario como dueño (RF-23).
create function app.crear_establecimiento(p_usuario uuid, p_nombre text) returns uuid
language plpgsql security definer set search_path = ''
as $$
declare v_est uuid;
begin
  if p_usuario is distinct from app.usuario_id() then
    raise exception 'el usuario no coincide con el contexto' using errcode = '42501';
  end if;
  insert into public.establecimiento (nombre) values (p_nombre) returning id into v_est;
  insert into public.membresia (usuario_id, establecimiento_id, rol) values (p_usuario, v_est, 'dueno');
  update public.usuario set ultimo_establecimiento_id = v_est where id = p_usuario;
  return v_est;
end
$$;

-- Invitación (RF-23): el dueño crea al encargado (o suma a un usuario existente) en un solo paso.
create function app.invitar_encargado(p_nombre text, p_telefono text) returns uuid
language plpgsql security definer set search_path = ''
as $$
declare v_usuario uuid;
begin
  if not app.es_dueno() then
    raise exception 'solo el dueño puede invitar' using errcode = '42501';
  end if;
  select id into v_usuario from public.usuario where telefono_whatsapp = p_telefono;
  if v_usuario is null then
    insert into public.usuario (nombre, telefono_whatsapp) values (p_nombre, p_telefono)
    returning id into v_usuario;
  end if;
  insert into public.membresia (usuario_id, establecimiento_id, rol)
  values (v_usuario, app.establecimiento_id(), 'encargado')
  on conflict (usuario_id, establecimiento_id) do update set activa = true;
  return v_usuario;
end
$$;

grant execute on function app.identificar_usuario(text), app.usuario_por_auth(uuid),
  app.membresias_de(uuid), app.crear_usuario(text, text, text, uuid),
  app.crear_establecimiento(uuid, text), app.invitar_encargado(text, text) to micampo_app;

-- PostgreSQL deja ejecutar cualquier función nueva a todos (PUBLIC). Se quita, y el backend
-- solo ejecuta lo que se le concedió explícitamente arriba. Cada migración que crea funciones termina así.
revoke execute on all functions in schema app from public;
