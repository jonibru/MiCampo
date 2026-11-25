"""Lotes, ciclos y campañas (RN-02, RN-12, RN-31)."""
import datetime as dt

import psycopg
import pytest
from helpers import crear_establecimiento, ctx, falla, filas, uno


def test_las_hectareas_totales_son_la_suma(app, mundo):
    a = mundo["A"]
    ctx(app, a["dueno"], a["est"])
    assert uno(app, "select ha_totales from lote where id = %s", a["lote"]) == 120


def test_las_hectareas_no_pueden_ser_negativas(app, mundo):
    a = mundo["A"]
    ctx(app, a["dueno"], a["est"])
    falla(app, psycopg.errors.CheckViolation, "update lote set ha_monte = -1 where id = %s", a["lote"])


def test_los_nombres_de_campo_y_lote_son_unicos(app, mundo):
    a = mundo["A"]
    ctx(app, a["dueno"], a["est"])
    falla(app, psycopg.errors.UniqueViolation,
          "insert into campo (establecimiento_id, nombre) values (%s, 'Campo')", a["est"])
    falla(app, psycopg.errors.UniqueViolation,
          "insert into lote (establecimiento_id, campo_id, nombre) values (%s, %s, 'Lote 1')", a["est"], a["campo"])


def _ciclo(app, m, estado="en_preparacion", cultivo=None, campana=None, cierre=None):
    return uno(
        app,
        "insert into ciclo (establecimiento_id, lote_id, cultivo_id, campana_anio, ha_limpias, fecha_inicio, estado, fecha_cierre) "
        "values (%s, %s, %s, %s, 100, '2026-10-01', %s, %s) returning id",
        m["est"], m["lote"], cultivo, campana, estado, cierre,
    )


def test_un_solo_ciclo_abierto_por_lote(app, admin):
    m = crear_establecimiento(admin, "Ciclos")
    ctx(app, m["dueno"], m["est"])
    _ciclo(app, m)
    falla(app, psycopg.errors.UniqueViolation,
          "insert into ciclo (establecimiento_id, lote_id, ha_limpias, fecha_inicio) values (%s, %s, 100, '2026-10-02')",
          m["est"], m["lote"])


def test_al_cerrar_un_ciclo_se_puede_abrir_otro(app, admin):
    m = crear_establecimiento(admin, "Ciclos 2")
    ctx(app, m["dueno"], m["est"])
    c1 = _ciclo(app, m)
    app.execute("update ciclo set estado = 'cerrado', fecha_cierre = '2027-05-01' where id = %s", (c1,))
    _ciclo(app, m)
    assert uno(app, "select count(*) from ciclo") == 2


def test_cierre_y_fecha_de_cierre_van_juntos(app, admin):
    m = crear_establecimiento(admin, "Ciclos 3")
    ctx(app, m["dueno"], m["est"])
    falla(app, psycopg.errors.CheckViolation,
          "insert into ciclo (establecimiento_id, lote_id, ha_limpias, fecha_inicio, estado) values (%s, %s, 10, '2026-10-01', 'cerrado')",
          m["est"], m["lote"])
    falla(app, psycopg.errors.CheckViolation,
          "insert into ciclo (establecimiento_id, lote_id, ha_limpias, fecha_inicio, fecha_cierre) values (%s, %s, 10, '2026-10-01', '2027-01-01')",
          m["est"], m["lote"])
    falla(app, psycopg.errors.CheckViolation,
          "insert into ciclo (establecimiento_id, lote_id, ha_limpias, fecha_inicio, estado, fecha_cierre) values (%s, %s, 10, '2026-10-01', 'cerrado', '2026-09-01')",
          m["est"], m["lote"])


def test_la_campana_exige_cultivo(app, admin):
    m = crear_establecimiento(admin, "Ciclos 4")
    ctx(app, m["dueno"], m["est"])
    falla(app, psycopg.errors.CheckViolation, "insert into ciclo (establecimiento_id, lote_id, ha_limpias, fecha_inicio, campana_anio) values (%s, %s, 10, '2026-10-01', 2026)",
          m["est"], m["lote"])
    soja = uno(app, "select id from cultivo where nombre = 'Soja'")
    _ciclo(app, m, estado="abierto", cultivo=soja, campana=2026)


def test_solo_el_dueno_reabre_un_ciclo_cerrado(app, admin):
    m = crear_establecimiento(admin, "Ciclos 5")
    ctx(app, m["dueno"], m["est"])
    c = _ciclo(app, m)
    app.execute("update ciclo set estado = 'cerrado', fecha_cierre = '2027-05-01' where id = %s", (c,))
    ctx(app, m["encargado"], m["est"])
    falla(app, psycopg.errors.InsufficientPrivilege,
          "update ciclo set estado = 'abierto', fecha_cierre = null where id = %s", c)
    ctx(app, m["dueno"], m["est"])
    assert app.execute("update ciclo set estado = 'abierto', fecha_cierre = null where id = %s", (c,)).rowcount == 1


def test_el_encargado_puede_cerrar_un_ciclo(app, admin):
    m = crear_establecimiento(admin, "Ciclos 6")
    ctx(app, m["encargado"], m["est"])
    c = _ciclo(app, m)
    assert app.execute("update ciclo set estado = 'cerrado', fecha_cierre = '2027-05-01' where id = %s", (c,)).rowcount == 1


@pytest.mark.parametrize("fecha,esperado", [
    ("2026-04-30", 2025), ("2026-05-01", 2026), ("2026-12-15", 2026),
    ("2027-02-10", 2026), ("2027-04-30", 2026), ("2027-05-01", 2027),
])
def test_anio_agricola(app, fecha, esperado):
    assert uno(app, "select app.anio_agricola(%s::date)", dt.date.fromisoformat(fecha)) == esperado


def test_cultivos_precargados_y_de_solo_lectura(app, mundo):
    esperado = {"Soja": 13.5, "Maíz": 14.5, "Trigo": 14.0, "Girasol": 11.0, "Sorgo": 15.0, "Cebada": 12.5, "Algodón": None}
    obtenido = {n: (float(h) if h is not None else None) for n, h in filas(app, "select nombre, humedad_base from cultivo")}
    assert obtenido == esperado
    falla(app, psycopg.errors.InsufficientPrivilege, "insert into cultivo (nombre) values ('Cebolla')")
    falla(app, psycopg.errors.InsufficientPrivilege, "update cultivo set humedad_base = 1")
