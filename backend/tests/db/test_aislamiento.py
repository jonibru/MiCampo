"""Aislamiento entre establecimientos (RNF-16): un establecimiento nunca ve ni toca los datos de otro."""
import psycopg
from helpers import crear_establecimiento, ctx, falla, filas, uno

TABLAS = ["campo", "lote", "ciclo", "desmonte", "lluvia", "membresia", "establecimiento"]


def test_sin_contexto_no_se_ve_nada(app, mundo):
    for tabla in TABLAS + ["auditoria"]:
        assert uno(app, f"select count(*) from {tabla}") == 0, tabla


def test_sin_contexto_no_se_puede_insertar(app, mundo):
    falla(app, psycopg.errors.InsufficientPrivilege,
          "insert into campo (establecimiento_id, nombre) values (%s, 'X')", mundo["A"]["est"])


def test_cada_establecimiento_ve_solo_lo_suyo(app, mundo):
    a, b = mundo["A"], mundo["B"]
    ctx(app, a["dueno"], a["est"])
    assert {f[0] for f in filas(app, "select id from campo")} == {a["campo"]}
    assert {f[0] for f in filas(app, "select id from lote")} == {a["lote"]}
    ctx(app, b["dueno"], b["est"])
    assert {f[0] for f in filas(app, "select id from campo")} == {b["campo"]}


def test_no_se_puede_insertar_en_otro_establecimiento(app, mundo):
    a, b = mundo["A"], mundo["B"]
    ctx(app, a["dueno"], a["est"])
    falla(app, psycopg.errors.InsufficientPrivilege,
          "insert into campo (establecimiento_id, nombre) values (%s, 'Intruso')", b["est"])
    falla(app, psycopg.errors.InsufficientPrivilege,
          "insert into lluvia (establecimiento_id, fecha, mm) values (%s, current_date, 10)", b["est"])


def test_no_se_puede_modificar_ni_borrar_lo_de_otro(app, mundo):
    a, b = mundo["A"], mundo["B"]
    ctx(app, a["dueno"], a["est"])
    assert app.execute("update campo set nombre = 'hack' where id = %s", (b["campo"],)).rowcount == 0
    assert app.execute("delete from campo where id = %s", (b["campo"],)).rowcount == 0
    assert app.execute("update lote set ha_limpias = 1 where id = %s", (b["lote"],)).rowcount == 0


def test_no_se_puede_mover_una_fila_a_otro_establecimiento(app, mundo):
    a, b = mundo["A"], mundo["B"]
    ctx(app, a["dueno"], a["est"])
    falla(app, psycopg.errors.InsufficientPrivilege,
          "update campo set establecimiento_id = %s where id = %s", b["est"], a["campo"])


def test_una_referencia_no_puede_cruzar_de_establecimiento(app, mundo):
    """Aun con el contexto de A, un lote de A no puede colgar de un campo de B (clave compuesta)."""
    a, b = mundo["A"], mundo["B"]
    ctx(app, a["dueno"], a["est"])
    falla(app, psycopg.errors.ForeignKeyViolation,
          "insert into lote (establecimiento_id, campo_id, nombre) values (%s, %s, 'Cruzado')", a["est"], b["campo"])
    falla(app, psycopg.errors.ForeignKeyViolation,
          "insert into desmonte (establecimiento_id, lote_id, fecha, ha) values (%s, %s, current_date, 1)",
          a["est"], b["lote"])


def test_un_usuario_no_puede_fijar_el_contexto_de_un_establecimiento_ajeno(app, mundo):
    a, b = mundo["A"], mundo["B"]
    ctx(app, a["dueno"], b["est"])  # fijar el contexto no alcanza: no es miembro de B
    assert uno(app, "select count(*) from campo") == 0
    falla(app, psycopg.errors.InsufficientPrivilege,
          "insert into campo (establecimiento_id, nombre) values (%s, 'X')", b["est"])


def test_el_contexto_no_sobrevive_a_la_transaccion(app, mundo):
    a = mundo["A"]
    ctx(app, a["dueno"], a["est"])
    assert uno(app, "select count(*) from campo") == 1
    app.commit()
    assert uno(app, "select count(*) from campo") == 0
    assert uno(app, "select app.establecimiento_id() is null") is True


def test_un_usuario_ve_a_los_miembros_de_su_establecimiento_y_no_a_los_de_otros(app, mundo):
    a, b = mundo["A"], mundo["B"]
    ctx(app, a["dueno"], a["est"])
    ids = {f[0] for f in filas(app, "select id from usuario")}
    assert ids == {a["dueno"], a["encargado"]}
    assert b["dueno"] not in ids


def test_baja_de_membresia_corta_el_acceso_en_el_momento(app, admin):
    m = crear_establecimiento(admin, "Baja")
    ctx(app, m["dueno"], m["est"])
    app.execute("update membresia set activa = false where usuario_id = %s", (m["encargado"],))
    ctx(app, m["encargado"], m["est"])
    assert uno(app, "select count(*) from campo") == 0
    falla(app, psycopg.errors.InsufficientPrivilege,
          "insert into lluvia (establecimiento_id, fecha, mm) values (%s, current_date, 5)", m["est"])


def test_baja_del_usuario_corta_el_acceso_en_el_momento(app, admin):
    m = crear_establecimiento(admin, "Baja usuario")
    admin.execute("update usuario set activo = false where id = %s", (m["encargado"],))
    ctx(app, m["encargado"], m["est"])
    assert uno(app, "select count(*) from campo") == 0
    ctx(app, m["dueno"], m["est"])
    assert uno(app, "select count(*) from campo") == 1
