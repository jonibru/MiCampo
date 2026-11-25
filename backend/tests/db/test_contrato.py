"""Reglas que toda tabla debe cumplir. Si alguien agrega una tabla sin protegerla, estos tests fallan."""
from helpers import filas

TABLAS_PUBLIC = "select c.oid, c.relname from pg_class c where c.relkind = 'r' and c.relnamespace = 'public'::regnamespace"
TABLAS_GLOBALES = {"cultivo", "catalogo_producto"}  # sin establecimiento_id: solo lectura para el backend


def test_todas_las_tablas_tienen_rls_forzado(admin):
    for _, nombre, habilitado, forzado in filas(
        admin,
        "select c.oid, c.relname, c.relrowsecurity, c.relforcerowsecurity from pg_class c "
        "where c.relkind = 'r' and c.relnamespace = 'public'::regnamespace",
    ):
        assert habilitado and forzado, f"{nombre}: falta ENABLE/FORCE ROW LEVEL SECURITY"


def test_anon_y_authenticated_no_tienen_acceso(admin):
    for oid, nombre in filas(admin, TABLAS_PUBLIC):
        for rol in ("anon", "authenticated"):
            for privilegio in ("select", "insert", "update", "delete", "truncate", "references", "trigger"):
                ok = admin.execute("select has_table_privilege(%s, %s, %s)", (rol, oid, privilegio)).fetchone()[0]
                assert not ok, f"{rol} tiene {privilegio} sobre {nombre}"


def test_anon_y_authenticated_no_llegan_al_esquema_app(admin):
    for rol in ("anon", "authenticated"):
        assert not admin.execute("select has_schema_privilege(%s, 'app', 'usage')", (rol,)).fetchone()[0]


def test_el_backend_no_puede_borrar_salvo_campos_y_lotes(admin):
    borrables = {"campo", "lote"}
    for oid, nombre in filas(admin, TABLAS_PUBLIC):
        puede = admin.execute("select has_table_privilege('micampo_app', %s, 'delete')", (oid,)).fetchone()[0]
        assert puede == (nombre in borrables), f"{nombre}: permiso DELETE inesperado ({puede})"


def test_el_backend_no_puede_truncar_ni_alterar(admin):
    for oid, nombre in filas(admin, TABLAS_PUBLIC):
        assert not admin.execute("select has_table_privilege('micampo_app', %s, 'truncate')", (oid,)).fetchone()[0], nombre
    assert not admin.execute("select has_schema_privilege('micampo_app', 'public', 'create')").fetchone()[0]


def test_el_rol_del_backend_no_saltea_rls(admin):
    super_, bypass = filas(admin, "select rolsuper, rolbypassrls from pg_roles where rolname = 'micampo_app'")[0]
    assert not super_ and not bypass


def test_toda_tabla_de_un_establecimiento_tiene_auditoria(admin):
    for _, nombre in filas(admin, TABLAS_PUBLIC):
        if nombre in TABLAS_GLOBALES | {"auditoria"}:
            continue
        hay = admin.execute(
            "select count(*) from pg_trigger t join pg_proc p on p.oid = t.tgfoid "
            "where t.tgrelid = ('public.' || %s)::regclass and p.proname = 'auditar' and not t.tgisinternal",
            (nombre,),
        ).fetchone()[0]
        assert hay == 1, f"{nombre}: falta el trigger de auditoría"


def test_las_referencias_entre_tablas_de_un_establecimiento_son_compuestas(admin):
    """Una fila de un establecimiento nunca puede apuntar a una de otro (clave foránea con establecimiento_id)."""
    for hijo, padre, columnas in filas(
        admin,
        """
        select c.conrelid::regclass::text, c.confrelid::regclass::text,
               array(select a.attname::text from unnest(c.conkey) k
                     join pg_attribute a on a.attrelid = c.conrelid and a.attnum = k)
        from pg_constraint c
        where c.contype = 'f' and c.connamespace = 'public'::regnamespace
          and exists (select 1 from pg_attribute where attrelid = c.conrelid
                      and attname = 'establecimiento_id' and not attisdropped)
          and exists (select 1 from pg_attribute where attrelid = c.confrelid
                      and attname = 'establecimiento_id' and not attisdropped)
        """,
    ):
        assert "establecimiento_id" in columnas, f"{hijo} -> {padre}: la clave foránea debe incluir establecimiento_id"


def test_los_importes_no_son_de_coma_flotante(admin):
    for tabla, columna, tipo in filas(
        admin,
        "select table_name, column_name, data_type from information_schema.columns "
        "where table_schema = 'public' and data_type in ('real', 'double precision', 'money')",
    ):
        raise AssertionError(f"{tabla}.{columna} usa {tipo}: usar NUMERIC")


def test_el_backend_no_ejecuta_funciones_internas(admin):
    """Las funciones de mantenimiento (proteger tablas, auditar) no las puede llamar el backend."""
    for funcion in ("app.proteger_tabla(regclass, boolean, boolean)", "app.auditar()", "app.ciclo_reabrir_solo_dueno()"):
        assert not admin.execute("select has_function_privilege('micampo_app', %s, 'execute')", (funcion,)).fetchone()[0], funcion


def test_las_vistas_respetan_el_rls_de_quien_consulta(admin):
    """Una vista sin security_invoker leería con los permisos de su dueño y saltearía el RLS."""
    for nombre, opciones in filas(
        admin, "select relname, coalesce(reloptions, '{}') from pg_class where relkind = 'v' and relnamespace = 'public'::regnamespace"
    ):
        assert "security_invoker=true" in opciones, f"{nombre}: falta security_invoker"


def test_anon_y_authenticated_no_ven_las_vistas(admin):
    for (oid,) in filas(admin, "select oid from pg_class where relkind = 'v' and relnamespace = 'public'::regnamespace"):
        for rol in ("anon", "authenticated"):
            assert not admin.execute("select has_table_privilege(%s, %s, 'select')", (rol, oid)).fetchone()[0]


def test_toda_tabla_de_cargas_aplica_las_reglas_de_carga(admin):
    for (tabla,) in filas(
        admin,
        "select table_name from information_schema.columns where table_schema = 'public' and column_name = 'anulada_en'",
    ):
        hay = admin.execute(
            "select count(*) from pg_trigger t join pg_proc p on p.oid = t.tgfoid "
            "where t.tgrelid = ('public.' || %s)::regclass and p.proname = 'reglas_carga'", (tabla,)
        ).fetchone()[0]
        assert hay == 1, f"{tabla}: falta el trigger app.reglas_carga"
