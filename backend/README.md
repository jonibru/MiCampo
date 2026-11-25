# Backend

API, operaciones del sistema y bot (Python, FastAPI). Por ahora tiene los tests de la base de datos.

## Correr los tests de la base

Cada corrida crea una base de datos vacía y descartable, le aplica `supabase/migrations/` y la borra al final. No toca tus datos.

```bash
supabase start                     # desde la raíz del repo, con Docker abierto
cd backend
python -m venv .venv
.venv\Scripts\activate             # en Windows (en Mac/Linux: source .venv/bin/activate)
pip install -e ".[dev]"
pytest
```

Por defecto usa el Supabase local (`postgresql://postgres:postgres@127.0.0.1:54322/postgres`). Para otra base, definí `TEST_ADMIN_URL`.

Si agregás una tabla y no la protegés con `app.proteger_tabla(...)`, `tests/db/test_contrato.py` falla.

## Catálogo base de productos

La lista vive en `supabase/catalogo/catalogo_base.csv` (se puede editar con Excel o Google Sheets). Para cargarla:

```bash
python -m micampo.catalogo ../supabase/catalogo/catalogo_base.csv            # muestra qué cambiaría
python -m micampo.catalogo ../supabase/catalogo/catalogo_base.csv --aplicar  # lo carga
```

Por defecto carga en el Supabase local. Para la nube, definí `DATABASE_ADMIN_URL` con la conexión de administrador. El script valida todo el archivo antes de escribir, actualiza por nombre y nunca borra: lo que sale de la lista queda inactivo. Si cambiaste `pyproject.toml`, volvé a correr `pip install -e ".[dev]"`.

## Cómo usa la base el backend

El backend se conecta con el rol `micampo_app` (no puede saltear RLS ni borrar cargas). Cada operación abre una transacción y fija el contexto; al terminar, el contexto desaparece solo:

```python
with conn.transaction():
    conn.execute("select app.fijar_contexto(%s, %s, 'bot', %s)", (usuario_id, establecimiento_id, mensaje_id))
    # ... la operación completa, en esta misma transacción ...
```

Antes de tener contexto (el bot recibe un mensaje) se usan `app.identificar_usuario(telefono)` y `app.membresias_de(usuario)`. Para altas: `app.crear_usuario`, `app.crear_establecimiento` y `app.invitar_encargado`.

## Rol del backend en la nube

La migración crea el rol `micampo_app` sin login. En local, `supabase/seed.sql` le pone una contraseña de desarrollo. En la nube, ejecutá una vez en el SQL Editor de Supabase, con una contraseña larga y propia (nunca en el repo):

```sql
alter role micampo_app login password '<contraseña>';
```

Guardá la cadena de conexión en `.env` como `DATABASE_URL`. Con el pooler de Supabase el usuario es `micampo_app.<id-del-proyecto>`.
