"""Cargas: quién las hizo, desde dónde, y que nada se borra (RN-09)."""
import psycopg
from helpers import ctx, falla, filas, uno


def test_la_carga_guarda_quien_origen_y_mensaje(app, mundo):
    a = mundo["A"]
    mensaje = "00000000-0000-0000-0000-0000000000aa"
    ctx(app, a["encargado"], a["est"], origen="bot", mensaje=mensaje)
    app.execute("insert into lluvia (establecimiento_id, fecha, mm) values (%s, '2026-11-20', 8)", (a["est"],))
    creado_por, origen, msg = filas(app, "select creado_por, origen, mensaje_id::text from lluvia")[0]
    assert (str(creado_por), origen, msg) == (str(a["encargado"]), "bot", mensaje)


def test_no_se_puede_falsificar_quien_cargo(app, mundo):
    a = mundo["A"]
    ctx(app, a["encargado"], a["est"])
    falla(app, psycopg.errors.InsufficientPrivilege,
          "insert into lluvia (establecimiento_id, fecha, mm, creado_por) values (%s, current_date, 5, %s)",
          a["est"], a["dueno"])


def test_el_origen_de_una_carga_es_bot_o_panel(app, mundo):
    a = mundo["A"]
    ctx(app, a["dueno"], a["est"], origen="sistema")
    falla(app, psycopg.errors.CheckViolation,
          "insert into lluvia (establecimiento_id, fecha, mm) values (%s, current_date, 5)", a["est"])


def test_una_carga_sin_contexto_de_usuario_falla(app, mundo):
    a = mundo["A"]
    ctx(app, None, a["est"])
    falla(app, psycopg.errors.InsufficientPrivilege,
          "insert into lluvia (establecimiento_id, fecha, mm) values (%s, current_date, 5)", a["est"])


def test_las_cargas_no_se_borran(app, mundo):
    a = mundo["A"]
    ctx(app, a["dueno"], a["est"])
    app.execute("insert into lluvia (establecimiento_id, fecha, mm) values (%s, current_date, 5)", (a["est"],))
    falla(app, psycopg.errors.InsufficientPrivilege, "delete from lluvia")
    falla(app, psycopg.errors.InsufficientPrivilege, "delete from desmonte")


def test_anular_exige_quien_y_cuando_juntos(app, mundo):
    a = mundo["A"]
    ctx(app, a["dueno"], a["est"])
    lluvia = uno(app, "insert into lluvia (establecimiento_id, fecha, mm) values (%s, current_date, 5) returning id",
                 a["est"])
    falla(app, psycopg.errors.CheckViolation, "update lluvia set anulada_en = now() where id = %s", lluvia)
    app.execute("update lluvia set anulada_en = now(), anulada_por = %s, motivo_anulacion = 'error de carga' where id = %s",
                (a["dueno"], lluvia))
    assert uno(app, "select anulada_por from lluvia where id = %s", lluvia) == a["dueno"]


def test_validaciones_de_valores(app, mundo):
    a = mundo["A"]
    ctx(app, a["dueno"], a["est"])
    falla(app, psycopg.errors.CheckViolation,
          "insert into lluvia (establecimiento_id, fecha, mm) values (%s, current_date, -1)", a["est"])
    falla(app, psycopg.errors.CheckViolation,
          "insert into lluvia (establecimiento_id, fecha, mm) values (%s, current_date, 5000)", a["est"])
    falla(app, psycopg.errors.CheckViolation,
          "insert into desmonte (establecimiento_id, lote_id, fecha, ha, costo_usd) values (%s, %s, current_date, 0, 1)",
          a["est"], a["lote"])
    falla(app, psycopg.errors.CheckViolation,
          "insert into desmonte (establecimiento_id, lote_id, fecha, ha, costo_usd) values (%s, %s, current_date, 5, -1)",
          a["est"], a["lote"])


def test_un_lote_con_carga_no_se_puede_borrar(app, mundo):
    a = mundo["A"]
    ctx(app, a["dueno"], a["est"])
    app.execute("insert into desmonte (establecimiento_id, lote_id, fecha, ha, costo_usd) values (%s, %s, current_date, 5, 100)",
                (a["est"], a["lote"]))
    falla(app, psycopg.errors.ForeignKeyViolation, "delete from lote where id = %s", a["lote"])


def test_un_lote_sin_uso_se_puede_borrar(app, mundo):
    a = mundo["A"]
    ctx(app, a["dueno"], a["est"])
    nuevo = uno(app, "insert into lote (establecimiento_id, campo_id, nombre) values (%s, %s, 'Temporal') returning id",
                a["est"], a["campo"])
    assert app.execute("delete from lote where id = %s", (nuevo,)).rowcount == 1
