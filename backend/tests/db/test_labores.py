"""Labores y costos (RF-08, RF-09, RF-10, RF-21, RF-27, RN-01, RN-02, RN-10, RN-11, RN-12, RN-13, RN-16, RN-17, RN-29).

Historias de usuario que son casos de prueba: HU-01 (la labor confirmada queda en su ciclo, con el stock
descontado y el costo guardado), HU-03 (deshacer revierte stock y costos) y HU-20 (no se cargan labores en un
ciclo cerrado; solo el dueño lo reabre).
"""
from decimal import Decimal as D

import psycopg
import pytest
from helpers import crear_establecimiento, ctx, falla, filas, uno
from psycopg.rows import dict_row


@pytest.fixture
def m(admin):
    """Establecimiento nuevo por test (lote de 100 ha limpias), para que ciclos, stock y valores arranquen de cero."""
    return crear_establecimiento(admin, "Labores")


@pytest.fixture(scope="module")
def dolar(admin):
    """Cotizaciones globales de prueba en noviembre de 2026."""
    for fecha_hora, valor, fuente in (("2026-11-19 11:00-03", 1000, "automatico"),
                                      ("2026-11-20 16:00-03", 1050, "manual")):
        admin.execute("insert into tipo_cambio (fecha_hora, valor, fuente) values (%s, %s, %s) "
                      "on conflict do nothing", (fecha_hora, valor, fuente))


# Ayudas ---------------------------------------------------------------------------------------------

def tipo(app, codigo):
    return uno(app, "select id from tipo_labor where codigo = %s", codigo)


def cultivo(app, nombre):
    return uno(app, "select id from cultivo where nombre = %s", nombre)


def ref(app, m, concepto, valor, tipo_labor=None):
    """El dueño carga un valor de referencia: rige desde hoy."""
    tl = tipo(app, tipo_labor) if tipo_labor else None
    return uno(app, "insert into valor_referencia (establecimiento_id, concepto, tipo_labor_id, valor) "
                    "values (%s, %s, %s, %s) returning id", m["est"], concepto, tl, valor)


def ref_historico(admin, m, concepto, valor, desde, tipo_labor=None):
    """Un valor cargado en otra fecha (el backend no puede elegirla: se arma como administrador)."""
    admin.execute("insert into valor_referencia (establecimiento_id, concepto, tipo_labor_id, valor, vigente_desde, creado_por) "
                  "values (%s, %s, (select id from tipo_labor where codigo = %s), %s, %s, %s)",
                  (m["est"], concepto, tipo_labor, valor, desde, m["dueno"]))


def labor(app, m, codigo, fecha="2026-11-20", ha=50, lote=None, **extra):
    cols = ["establecimiento_id", "lote_id", "tipo_labor_id", "fecha", "ha", *extra]
    vals = [m["est"], lote or m["lote"], tipo(app, codigo), fecha, ha, *extra.values()]
    return uno(app, f"insert into labor ({', '.join(cols)}) values ({', '.join(['%s'] * len(vals))}) returning id", *vals)


def insumo(app, m, lab, prod, dosis=None, unidad="l", cantidad=None):
    return uno(app, "insert into labor_insumo (establecimiento_id, labor_id, producto_id, dosis_ha, cantidad, unidad) "
                    "values (%s, %s, %s, %s, %s, %s) returning id", m["est"], lab, prod, dosis, cantidad, unidad)


def carpida(app, m, lab, personas, dias, horas=None, pago=None):
    app.execute("insert into carpida (establecimiento_id, labor_id, personas, dias, horas_dia, pago_hora) "
                "values (%s, %s, %s, %s, %s, %s)", (m["est"], lab, personas, dias, horas, pago))


def producto(app, m, nombre="Glifosato 48%", categoria="herbicida", unidad="l", precio=None, **extra):
    cols = ["establecimiento_id", "nombre", "categoria", "unidad", "precio_inicial_usd", *extra]
    vals = [m["est"], nombre, categoria, unidad, precio, *extra.values()]
    return uno(app, f"insert into producto ({', '.join(cols)}) values ({', '.join(['%s'] * len(vals))}) returning id", *vals)


def comprar(app, m, prod, cantidad, precio, fecha="2026-11-01"):
    c = uno(app, "insert into compra (establecimiento_id, fecha) values (%s, %s) returning id", m["est"], fecha)
    app.execute("insert into compra_item (establecimiento_id, compra_id, producto_id, cantidad, precio_unitario) "
                "values (%s, %s, %s, %s, %s)", (m["est"], c, prod, cantidad, precio))


def fila(app, tabla, id_):
    return app.cursor(row_factory=dict_row).execute(f"select * from {tabla} where id = %s", (id_,)).fetchone()


def stock(app, prod):
    return uno(app, "select stock from stock_producto where producto_id = %s", prod)


def anular(app, tabla, id_, usuario):
    app.execute(f"update {tabla} set anulada_en = now(), anulada_por = %s, motivo_anulacion = 'me equivoqué' "
                "where id = %s", (usuario, id_))


def rechaza(app, texto, sql, *params, error=psycopg.errors.CheckViolation):
    """La base rechaza la carga con un mensaje que contiene `texto`."""
    with pytest.raises(error, match=texto):
        with app.transaction():
            app.execute(sql, params)


def sql_labor(codigo_extra=""):
    return ("insert into labor (establecimiento_id, lote_id, tipo_labor_id, fecha, ha" + codigo_extra + ") "
            "values (%s, %s, (select id from tipo_labor where codigo = %s), %s, %s")


def ciclo(app, lab):
    return fila(app, "ciclo", fila(app, "labor", lab)["ciclo_id"])


# Tipo de cambio (RN-16, RF-21) -----------------------------------------------------------------------

class _Deshacer(Exception):
    pass


def test_tipo_de_cambio_vigente_a_una_fecha_local(admin):
    with pytest.raises(_Deshacer):  # al salir se deshace todo: no quedan cotizaciones para los demás tests
        with admin.transaction():
            for fh, valor in (("2020-03-01 10:00-03", 80), ("2020-03-01 16:00-03", 81),
                              ("2020-03-03 01:00+00", 83)):  # 02/03 22:00 en Buenos Aires
                admin.execute("insert into tipo_cambio (fecha_hora, valor, fuente) values (%s, %s, 'automatico')", (fh, valor))
            vigente = lambda f: uno(admin, "select valor from app.tipo_cambio_vigente(%s::date)", f)  # noqa: E731
            assert vigente("2020-03-01") == 81           # la última del día
            assert vigente("2020-03-02") == 83           # cargada el 02/03 hora argentina (03/03 en UTC)
            assert vigente("2020-03-10") == 83           # sin cotización nueva, sigue la anterior
            assert admin.execute("select * from app.tipo_cambio_vigente('2010-01-01')").fetchone() is None
            raise _Deshacer


def test_el_backend_solo_lee_el_tipo_de_cambio(app, mundo, dolar):
    a = mundo["A"]
    ctx(app, a["dueno"], a["est"])
    assert uno(app, "select valor from app.tipo_cambio_vigente('2026-11-20')") == 1050
    falla(app, psycopg.errors.InsufficientPrivilege,
          "insert into tipo_cambio (fecha_hora, valor, fuente) values (now(), 1, 'manual')")
    falla(app, psycopg.errors.InsufficientPrivilege, "update tipo_cambio set valor = 1")


# Valores de referencia (RN-29) ---------------------------------------------------------------------

def test_solo_el_dueno_carga_valores_de_referencia(app, m):
    ctx(app, m["encargado"], m["est"])
    falla(app, psycopg.errors.InsufficientPrivilege,
          "insert into valor_referencia (establecimiento_id, concepto, tipo_labor_id, valor) "
          "values (%s, 'servicio_labor', (select id from tipo_labor where codigo = 'siembra'), 30)", m["est"])
    ctx(app, m["dueno"], m["est"])
    ref(app, m, "servicio_labor", 30, tipo_labor="siembra")


def test_el_valor_rige_desde_el_dia_en_que_se_carga(app, m):
    ctx(app, m["dueno"], m["est"])
    r = ref(app, m, "servicio_labor", 30, tipo_labor="siembra")
    hoy = uno(app, "select (now() at time zone 'America/Argentina/Buenos_Aires')::date")
    assert uno(app, "select vigente_desde from valor_referencia where id = %s", r) == hoy
    falla(app, psycopg.errors.InsufficientPrivilege,
          "insert into valor_referencia (establecimiento_id, concepto, valor, vigente_desde) "
          "values (%s, 'pago_hora_temporal', 2, '2020-01-01')", m["est"])


def test_un_cambio_crea_una_fila_nueva_y_no_pisa_la_anterior(app, m):
    ctx(app, m["dueno"], m["est"])
    r = ref(app, m, "servicio_labor", 30, tipo_labor="siembra")
    falla(app, psycopg.errors.InsufficientPrivilege, "update valor_referencia set valor = 35 where id = %s", r)
    falla(app, psycopg.errors.InsufficientPrivilege, "delete from valor_referencia where id = %s", r)
    ref(app, m, "servicio_labor", 35, tipo_labor="siembra")
    assert uno(app, "select count(*) from valor_referencia") == 2
    # dos cambios el mismo día: rige el último
    assert uno(app, "select valor from app.valor_referencia_vigente('servicio_labor', '2030-01-01', %s)",
               tipo(app, "siembra")) == 35


def test_valor_vigente_por_fecha_y_concepto(app, m, admin):
    ref_historico(admin, m, "servicio_labor", 30, "2026-06-01", "siembra")
    ref_historico(admin, m, "servicio_labor", 35, "2026-11-15", "siembra")
    ref_historico(admin, m, "servicio_labor", 36, "2026-11-15", "siembra")   # corrección del mismo día: gana la última
    ref_historico(admin, m, "pulverizacion", 8, "2026-06-01", "pulverizacion_mosquito")
    ref_historico(admin, m, "pago_hora_temporal", D("2.5"), "2026-06-01")
    ctx(app, m["dueno"], m["est"])
    siembra, mosquito = tipo(app, "siembra"), tipo(app, "pulverizacion_mosquito")

    def vig(concepto, fecha, tipo_labor=None):
        r = app.execute("select valor from app.valor_referencia_vigente(%s, %s::date, %s)",
                        (concepto, fecha, tipo_labor)).fetchone()
        return r[0] if r else None
    assert vig("servicio_labor", "2026-05-31", siembra) == 30    # antes del primero: usa el primero
    assert vig("servicio_labor", "2026-11-14", siembra) == 30
    assert vig("servicio_labor", "2026-11-15", siembra) == 36
    assert vig("pulverizacion", "2026-12-01", mosquito) == 8
    assert vig("pulverizacion", "2026-12-01", siembra) is None    # nunca se cargó
    assert vig("pago_hora_temporal", "2026-12-01") == D("2.5")


def test_cada_concepto_lleva_su_clave(app, m):
    ctx(app, m["dueno"], m["est"])
    base = "insert into valor_referencia (establecimiento_id, concepto, tipo_labor_id, cultivo_id, campana_anio, valor) "
    soja, siembra, dron, carpida_ = cultivo(app, "Soja"), tipo(app, "siembra"), tipo(app, "pulverizacion_dron"), tipo(app, "carpida")
    for concepto, tl, cu, camp in (("servicio_labor", None, None, None),       # falta el tipo de labor
                                   ("precio_grano", None, soja, None),          # falta la campaña
                                   ("flete", None, None, 2026),                 # falta el grano
                                   ("pago_hora_temporal", siembra, None, None)):  # no lleva tipo de labor
        falla(app, psycopg.errors.CheckViolation, base + "values (%s, %s, %s, %s, %s, 1)",
              m["est"], concepto, tl, cu, camp)
    rechaza(app, "por equipo", base + "values (%s, 'servicio_labor', %s, null, null, 1)", m["est"], dron)
    rechaza(app, "por equipo", base + "values (%s, 'pulverizacion', %s, null, null, 1)", m["est"], siembra)
    rechaza(app, "temporales", base + "values (%s, 'servicio_labor', %s, null, null, 1)", m["est"], carpida_)
    falla(app, psycopg.errors.CheckViolation,
          base + "values (%s, 'horas_dia_temporal', null, null, null, 30)", m["est"])   # más de 24 h
    app.execute(base + "values (%s, 'precio_grano', null, %s, 2026, 300)", (m["est"], soja))


def test_los_valores_de_referencia_no_cruzan_establecimientos(app, admin):
    a, b = crear_establecimiento(admin, "Ref A"), crear_establecimiento(admin, "Ref B")
    ctx(app, a["dueno"], a["est"])
    ref(app, a, "servicio_labor", 30, tipo_labor="siembra")
    ctx(app, b["dueno"], b["est"])
    assert uno(app, "select count(*) from valor_referencia") == 0
    assert uno(app, "select count(*) from app.valor_referencia_vigente('servicio_labor', '2026-12-01', %s)",
               tipo(app, "siembra")) == 0
    falla(app, psycopg.errors.InsufficientPrivilege,
          "insert into valor_referencia (establecimiento_id, concepto, valor) "
          "values (%s, 'pago_hora_temporal', 1)", a["est"])


# Tipos de labor (RN-11) -----------------------------------------------------------------------------

def test_tipos_de_labor_precargados_y_de_solo_lectura(app, mundo):
    obtenido = {c: (e, k) for c, e, k in filas(app, "select codigo, equipo, costeo from tipo_labor")}
    assert obtenido == {
        "siembra": (None, "por_ha"), "pulverizacion_mosquito": ("mosquito", "por_ha"),
        "pulverizacion_dron": ("dron", "por_ha"), "pulverizacion_avion": ("avion", "por_ha"),
        "fertilizacion": (None, "por_ha"),
        "carpidor": (None, "por_ha"), "disco": (None, "por_ha"), "rastra_cadena": (None, "por_ha"),
        "rolo_picador": (None, "por_ha"), "carpida": (None, "temporales"), "otra": (None, "temporales"),
    }
    falla(app, psycopg.errors.InsufficientPrivilege, "insert into tipo_labor (codigo, nombre, costeo) values ('x', 'X', 'por_ha')")
    falla(app, psycopg.errors.InsufficientPrivilege, "update tipo_labor set costeo = 'temporales'")


# Ciclos (RN-02, RF-08, HU-20) ------------------------------------------------------------------------

def test_la_primera_labor_crea_el_ciclo_en_preparacion_y_la_siembra_lo_abre(app, m):
    ctx(app, m["encargado"], m["est"])
    barbecho = labor(app, m, "pulverizacion_mosquito", "2026-09-10")
    c = ciclo(app, barbecho)
    assert (c["estado"], c["cultivo_id"], c["ha_limpias"], str(c["fecha_inicio"])) == ("en_preparacion", None, 100, "2026-09-10")
    siembra = labor(app, m, "siembra", "2026-11-20", cultivo_id=cultivo(app, "Soja"))
    c2 = ciclo(app, siembra)
    assert c2["id"] == c["id"]
    assert (c2["estado"], c2["cultivo_id"], c2["campana_anio"]) == ("abierto", cultivo(app, "Soja"), 2026)


def test_la_campana_sale_del_anio_agricola_de_la_siembra(app, m):
    ctx(app, m["dueno"], m["est"])
    s = labor(app, m, "siembra", "2027-02-10", cultivo_id=cultivo(app, "Maíz"))
    assert ciclo(app, s)["campana_anio"] == 2026


def test_una_labor_anterior_al_inicio_del_ciclo_corre_el_inicio(app, m):
    ctx(app, m["dueno"], m["est"])
    l1 = labor(app, m, "disco", "2026-09-10")
    l2 = labor(app, m, "rastra_cadena", "2026-08-01")
    assert ciclo(app, l1)["id"] == ciclo(app, l2)["id"]
    assert str(ciclo(app, l1)["fecha_inicio"]) == "2026-08-01"


def test_hu20_una_labor_en_un_ciclo_cerrado_se_rechaza_y_solo_el_dueno_reabre(app, m):
    ctx(app, m["encargado"], m["est"])
    s = labor(app, m, "siembra", "2026-06-01", cultivo_id=cultivo(app, "Trigo"))
    c = ciclo(app, s)["id"]
    app.execute("update ciclo set estado = 'cerrado', fecha_cierre = '2026-12-01' where id = %s", (c,))
    args = (m["est"], m["lote"], "pulverizacion_mosquito", "2026-10-15", 50)
    rechaza(app, r"cae en el ciclo de Trigo 2026/27 del lote, cerrado el 01/12/2026: solo el dueño puede reabrirlo",
            sql_labor() + ")", *args)
    # el encargado no puede reabrirlo
    falla(app, psycopg.errors.InsufficientPrivilege,
          "update ciclo set estado = 'abierto', fecha_cierre = null where id = %s", c)
    # lo del mismo día del cierre en adelante va a un ciclo nuevo
    nueva = labor(app, m, "pulverizacion_mosquito", "2026-12-01")
    assert ciclo(app, nueva)["id"] != c and ciclo(app, nueva)["estado"] == "en_preparacion"
    # una fecha anterior al cierre sigue rechazada aunque haya otro ciclo abierto
    rechaza(app, "cerrado el 01/12/2026", sql_labor() + ")", *args)


def test_hu20_si_el_dueno_reabre_el_ciclo_la_labor_entra(app, m):
    ctx(app, m["dueno"], m["est"])
    s = labor(app, m, "siembra", "2026-06-01", cultivo_id=cultivo(app, "Trigo"))
    c = ciclo(app, s)["id"]
    app.execute("update ciclo set estado = 'cerrado', fecha_cierre = '2026-12-01' where id = %s", (c,))
    app.execute("update ciclo set estado = 'abierto', fecha_cierre = null where id = %s", (c,))
    assert ciclo(app, labor(app, m, "pulverizacion_mosquito", "2026-10-15"))["id"] == c


def test_una_fecha_anterior_a_un_ciclo_cerrado_se_rechaza(app, m):
    ctx(app, m["dueno"], m["est"])
    s = labor(app, m, "siembra", "2026-06-01", cultivo_id=cultivo(app, "Trigo"))
    app.execute("update ciclo set estado = 'cerrado', fecha_cierre = '2026-12-01' where id = %s", (ciclo(app, s)["id"],))
    rechaza(app, "cerrado", sql_labor() + ")", m["est"], m["lote"], "disco", "2026-03-01", 50)


def test_sembrar_otro_cultivo_con_un_ciclo_abierto_se_rechaza(app, m):
    ctx(app, m["dueno"], m["est"])
    labor(app, m, "siembra", "2026-11-01", cultivo_id=cultivo(app, "Soja"))
    rechaza(app, "tiene abierto el ciclo de Soja 2026/27: hay que cerrarlo antes de sembrar Maíz",
            sql_labor(", cultivo_id") + ", %s)", m["est"], m["lote"], "siembra", "2026-12-01", 50, cultivo(app, "Maíz"))
    # resiembra del mismo cultivo: va al mismo ciclo
    r = labor(app, m, "siembra", "2026-11-15", ha=10, cultivo_id=cultivo(app, "Soja"))
    assert ciclo(app, r)["campana_anio"] == 2026


def test_la_siembra_fija_el_cultivo_aunque_en_preparacion_se_haya_indicado_otro(app, m):
    ctx(app, m["dueno"], m["est"])
    b = labor(app, m, "pulverizacion_mosquito", "2026-09-01")
    app.execute("update ciclo set cultivo_id = %s where id = %s", (cultivo(app, "Maíz"), ciclo(app, b)["id"]))
    s = labor(app, m, "siembra", "2026-11-01", cultivo_id=cultivo(app, "Soja"))
    assert ciclo(app, s)["cultivo_id"] == cultivo(app, "Soja")


def test_el_cultivo_va_solo_en_la_siembra(app, m):
    ctx(app, m["dueno"], m["est"])
    rechaza(app, "solo en la siembra", sql_labor() + ")", m["est"], m["lote"], "siembra", "2026-11-01", 50)
    rechaza(app, "solo en la siembra", sql_labor(", cultivo_id") + ", %s)",
            m["est"], m["lote"], "disco", "2026-11-01", 50, cultivo(app, "Soja"))


def test_las_hectareas_no_superan_las_limpias_del_ciclo(app, m):
    ctx(app, m["dueno"], m["est"])
    labor(app, m, "disco", "2026-09-01", ha=100)
    rechaza(app, "el lote tiene 100.00 ha limpias en este ciclo y la labor dice 100.50 ha",
            sql_labor() + ")", m["est"], m["lote"], "disco", "2026-09-02", D("100.5"))
    # un desmonte posterior no cambia las ha del ciclo ya creado (RN-12)
    app.execute("update lote set ha_limpias = 120 where id = %s", (m["lote"],))
    rechaza(app, "100.00 ha limpias", sql_labor() + ")", m["est"], m["lote"], "disco", "2026-09-03", 110)


def test_el_backend_no_elige_el_ciclo_ni_los_costos(app, m):
    ctx(app, m["dueno"], m["est"])
    l1 = labor(app, m, "disco", "2026-09-01")
    for col, val in (("ciclo_id", ciclo(app, l1)["id"]), ("costo_total_usd", 1), ("costo_incompleto", False),
                     ("precio_servicio_ha_usd", 1)):
        falla(app, psycopg.errors.InsufficientPrivilege,
              f"insert into labor (establecimiento_id, lote_id, tipo_labor_id, fecha, ha, {col}) "
              "values (%s, %s, (select id from tipo_labor where codigo = 'disco'), '2026-09-02', 10, %s)",
              m["est"], m["lote"], val)
    for sql in ("update labor set ha = 10 where id = %s", "update labor set costo_total_usd = 0 where id = %s",
                "update labor set fecha = '2026-09-05' where id = %s"):
        falla(app, psycopg.errors.InsufficientPrivilege, sql, l1)


# Costo del servicio (RF-10, RN-10, RN-11) --------------------------------------------------------------

def test_costo_del_servicio_con_el_valor_de_referencia_vigente(app, m):
    ctx(app, m["dueno"], m["est"])
    r30 = ref(app, m, "servicio_labor", 30, tipo_labor="siembra")
    s = labor(app, m, "siembra", "2026-11-01", ha=50, cultivo_id=cultivo(app, "Soja"))
    f = fila(app, "labor", s)
    assert (f["precio_servicio_ha_usd"], f["costo_servicio_usd"], f["costo_total_usd"], f["costo_total_ha_usd"]) == (30, 1500, 1500, 30)
    assert f["valor_referencia_id"] == r30 and f["costo_incompleto"] is False
    # RN-10: un cambio posterior del valor no altera la labor ya cargada; vale para las nuevas
    ref(app, m, "servicio_labor", 40, tipo_labor="siembra")
    assert fila(app, "labor", s)["costo_servicio_usd"] == 1500
    otra = labor(app, m, "siembra", "2026-11-02", ha=10, cultivo_id=cultivo(app, "Soja"))
    assert fila(app, "labor", otra)["costo_servicio_usd"] == 400


def test_una_labor_cargada_tarde_usa_el_valor_que_regia_en_su_fecha(app, m, admin):
    ref_historico(admin, m, "servicio_labor", 30, "2026-06-01", "disco")
    ref_historico(admin, m, "servicio_labor", 35, "2026-12-01", "disco")
    ctx(app, m["dueno"], m["est"])
    assert fila(app, "labor", labor(app, m, "disco", "2026-11-10", ha=10))["costo_servicio_usd"] == 300
    assert fila(app, "labor", labor(app, m, "disco", "2026-12-05", ha=10))["costo_servicio_usd"] == 350


def test_pulverizacion_por_equipo_y_solo_con_equipos_propios(app, m):
    ctx(app, m["dueno"], m["est"])
    ref(app, m, "pulverizacion", 8, tipo_labor="pulverizacion_mosquito")
    ref(app, m, "pulverizacion", 12, tipo_labor="pulverizacion_dron")
    assert fila(app, "labor", labor(app, m, "pulverizacion_mosquito"))["costo_servicio_usd"] == 400
    rechaza(app, "el establecimiento no tiene dron propio: ¿la pulverización fue contratada?",
            sql_labor() + ")", m["est"], m["lote"], "pulverizacion_dron", "2026-11-20", 50)
    contratada = labor(app, m, "pulverizacion_dron", contratado=True)
    assert fila(app, "labor", contratada)["costo_servicio_usd"] == 600
    app.execute("update establecimiento set equipos_pulverizacion = array['mosquito', 'dron'] where id = %s", (m["est"],))
    assert fila(app, "labor", labor(app, m, "pulverizacion_dron"))["costo_servicio_usd"] == 600


def test_contratada_con_costo_real_por_ha_o_total(app, m):
    ctx(app, m["dueno"], m["est"])
    ref(app, m, "servicio_labor", 30, tipo_labor="siembra")
    soja = cultivo(app, "Soja")
    por_ha = labor(app, m, "siembra", ha=50, cultivo_id=soja, contratado=True, precio_ha_declarado=25)
    total = labor(app, m, "siembra", ha=40, cultivo_id=soja, contratado=True, costo_declarado=1100)
    assert fila(app, "labor", por_ha)["costo_servicio_usd"] == 1250
    assert fila(app, "labor", por_ha)["valor_referencia_id"] is None
    assert (fila(app, "labor", total)["costo_servicio_usd"], fila(app, "labor", total)["costo_total_ha_usd"]) == (1100, D("27.5"))
    rechaza(app, "solo si la labor fue contratada", sql_labor(", cultivo_id, precio_ha_declarado") + ", %s, 25)",
            m["est"], m["lote"], "siembra", "2026-11-20", 50, soja)
    falla(app, psycopg.errors.CheckViolation,
          "insert into labor (establecimiento_id, lote_id, tipo_labor_id, fecha, ha, contratado, precio_ha_declarado, costo_declarado) "
          "values (%s, %s, (select id from tipo_labor where codigo = 'disco'), '2026-11-20', 10, true, 1, 1)", m["est"], m["lote"])


def test_costo_en_pesos_con_el_dolar_vigente_o_el_dicho(app, m, dolar):
    ctx(app, m["dueno"], m["est"])
    auto = labor(app, m, "disco", "2026-11-19", ha=50, contratado=True, moneda="ARS", costo_declarado=1_500_000)
    f = fila(app, "labor", auto)
    assert (f["tipo_cambio"], f["tipo_cambio_fuente"], f["costo_servicio_usd"]) == (1000, "automatico", 1500)
    dicho = labor(app, m, "disco", "2026-11-19", ha=50, contratado=True, moneda="ARS", tipo_cambio=1200,
                  precio_ha_declarado=36_000)
    f = fila(app, "labor", dicho)
    assert (f["tipo_cambio_fuente"], f["precio_servicio_ha_usd"], f["costo_servicio_usd"]) == ("manual", 30, 1500)
    rechaza(app, "no hay tipo de cambio cargado para el 01/01/2010",
            sql_labor(", contratado, moneda, costo_declarado") + ", true, 'ARS', 1000)",
            m["est"], m["lote"], "disco", "2010-01-01", 10)
    rechaza(app, "solo con importes en pesos", sql_labor(", tipo_cambio") + ", 1000)",
            m["est"], m["lote"], "disco", "2026-11-19", 10)


def test_sin_valor_de_referencia_queda_costo_incompleto_y_se_completa_al_cargarlo(app, m):
    ctx(app, m["encargado"], m["est"])
    vieja = labor(app, m, "disco", "2026-05-10", ha=20)
    nueva = labor(app, m, "disco", "2026-11-10", ha=50)
    assert fila(app, "labor", nueva)["costo_incompleto"] is True
    assert fila(app, "labor", nueva)["costo_servicio_usd"] is None
    ctx(app, m["dueno"], m["est"])
    r = ref(app, m, "servicio_labor", 15, tipo_labor="disco")
    # todas las incompletas toman el valor, sin importar su fecha
    f = fila(app, "labor", nueva)
    assert (f["costo_servicio_usd"], f["valor_referencia_id"], f["costo_incompleto"]) == (750, r, False)
    assert (fila(app, "labor", vieja)["costo_servicio_usd"], fila(app, "labor", vieja)["costo_incompleto"]) == (300, False)
    # quedan fijas: un cambio posterior del valor no las toca
    ref(app, m, "servicio_labor", 20, tipo_labor="disco")
    assert fila(app, "labor", nueva)["costo_servicio_usd"] == 750
    # queda registro en la auditoría, a nombre del dueño
    assert uno(app, "select count(*) from auditoria where tabla = 'labor' and registro_id = %s and accion = 'update' "
                    "and usuario_id = %s", nueva, m["dueno"]) >= 1


# Insumos (RF-09, RN-10, RN-13) -------------------------------------------------------------------------

def test_hu01_la_labor_queda_en_su_ciclo_con_el_stock_descontado_y_el_costo_guardado(app, m):
    ctx(app, m["dueno"], m["est"])
    ref(app, m, "pulverizacion", 8, tipo_labor="pulverizacion_mosquito")
    glifo = producto(app, m)
    comprar(app, m, glifo, 100, 4)
    ctx(app, m["encargado"], m["est"], origen="bot")
    lab = labor(app, m, "pulverizacion_mosquito", ha=50)
    li = insumo(app, m, lab, glifo, dosis=2)
    f, i = fila(app, "labor", lab), fila(app, "labor_insumo", li)
    assert (i["cantidad"], i["cantidad_producto"], i["precio_unitario_usd"], i["costo_usd"]) == (100, 100, 4, 400)
    assert (f["costo_servicio_usd"], f["costo_insumos_usd"], f["costo_total_usd"], f["costo_total_ha_usd"]) == (400, 400, 800, 16)
    assert f["costo_incompleto"] is False and f["ciclo_id"] == ciclo(app, lab)["id"]
    assert stock(app, glifo) == 0
    mov = app.cursor(row_factory=dict_row).execute(
        "select * from movimiento_stock where labor_insumo_id = %s", (li,)).fetchone()
    assert (mov["tipo"], mov["cantidad"], mov["precio_unitario_usd"], str(mov["fecha"])) == ("labor", -100, 4, "2026-11-20")
    assert (mov["creado_por"], mov["origen"]) == (m["encargado"], "bot")


def test_el_costo_del_insumo_queda_fijo_aunque_cambie_el_promedio(app, m):
    ctx(app, m["dueno"], m["est"])
    glifo = producto(app, m)
    comprar(app, m, glifo, 100, 4)
    lab = labor(app, m, "pulverizacion_mosquito")
    li = insumo(app, m, lab, glifo, dosis=1)
    comprar(app, m, glifo, 50, 10, fecha="2026-11-25")
    assert fila(app, "labor_insumo", li)["costo_usd"] == 200
    assert fila(app, "labor", lab)["costo_insumos_usd"] == 200


def test_cantidad_total_en_vez_de_dosis(app, m):
    ctx(app, m["dueno"], m["est"])
    glifo = producto(app, m, precio=4)
    i = fila(app, "labor_insumo", insumo(app, m, labor(app, m, "pulverizacion_mosquito", ha=50), glifo, cantidad=150))
    assert (i["dosis_ha"], i["cantidad_producto"], i["costo_usd"]) == (3, 150, 600)
    lab = labor(app, m, "pulverizacion_mosquito")
    falla(app, psycopg.errors.CheckViolation,
          "insert into labor_insumo (establecimiento_id, labor_id, producto_id, unidad) values (%s, %s, %s, 'l')", m["est"], lab, glifo)
    rechaza(app, "no las dos", "insert into labor_insumo (establecimiento_id, labor_id, producto_id, dosis_ha, cantidad, unidad) "
            "values (%s, %s, %s, 1, 50, 'l')", m["est"], lab, glifo)


def test_semilla_en_kg_por_ha_se_descuenta_en_bolsas(app, m):
    ctx(app, m["dueno"], m["est"])
    soja = cultivo(app, "Soja")
    sem = producto(app, m, "Soja DM 46i20", "semilla", "bolsa", cultivo_id=soja, kg_por_bolsa=40)
    comprar(app, m, sem, 30, 30)
    s = labor(app, m, "siembra", ha=10, cultivo_id=soja)
    i = fila(app, "labor_insumo", insumo(app, m, s, sem, dosis=80, unidad="kg"))
    assert (i["cantidad"], i["cantidad_producto"], i["costo_usd"]) == (800, 20, 600)
    assert stock(app, sem) == 10
    # también en bolsas por ha (maíz, girasol)
    i2 = fila(app, "labor_insumo", insumo(app, m, s, sem, dosis=D("0.5"), unidad="bolsa"))
    assert (i2["cantidad_producto"], i2["costo_usd"]) == (5, 150)


def test_insumos_que_no_corresponden_se_rechazan(app, m):
    ctx(app, m["dueno"], m["est"])
    soja, maiz = cultivo(app, "Soja"), cultivo(app, "Maíz")
    sem_maiz = producto(app, m, "Maíz DK 72-10", "semilla", "bolsa", cultivo_id=maiz, kg_por_bolsa=20)
    glifo = producto(app, m)
    filtro = producto(app, m, "Filtro", "repuesto", "unidad", tipo_repuesto="filtro", modelo="F1")
    pulv = labor(app, m, "pulverizacion_mosquito")
    siembra = labor(app, m, "siembra", cultivo_id=soja)
    base = "insert into labor_insumo (establecimiento_id, labor_id, producto_id, dosis_ha, unidad) values (%s, %s, %s, 1, %s)"
    rechaza(app, "solo se usa en una siembra de su cultivo", base, m["est"], pulv, sem_maiz, "bolsa")
    rechaza(app, "solo se usa en una siembra de su cultivo", base, m["est"], siembra, sem_maiz, "bolsa")
    rechaza(app, "se carga en l, no en kg", base, m["est"], pulv, glifo, "kg")
    rechaza(app, "uso de repuesto", base, m["est"], pulv, filtro, "unidad")


def test_un_insumo_sin_stock_queda_negativo_y_marcado(app, m):
    ctx(app, m["dueno"], m["est"])
    glifo = producto(app, m, precio=4)
    li = insumo(app, m, labor(app, m, "pulverizacion_mosquito"), glifo, dosis=1)
    assert stock(app, glifo) == -50
    assert uno(app, "select revisar from movimiento_stock where labor_insumo_id = %s", li) is True


def test_precio_pendiente_deja_costo_incompleto_hasta_que_el_dueno_lo_fija(app, m):
    ctx(app, m["dueno"], m["est"])
    ref(app, m, "pulverizacion", 8, tipo_labor="pulverizacion_mosquito")
    nuevo = producto(app, m, "Herbicida nuevo")           # sin precio: pendiente
    glifo = producto(app, m, precio=4)
    ctx(app, m["encargado"], m["est"])
    lab = labor(app, m, "pulverizacion_mosquito", ha=50)
    con_precio = insumo(app, m, lab, glifo, dosis=1)
    sin_precio = insumo(app, m, lab, nuevo, dosis=2)
    f = fila(app, "labor", lab)
    assert (f["costo_incompleto"], f["costo_insumos_usd"], f["costo_total_usd"]) == (True, 200, 600)
    assert fila(app, "labor_insumo", sin_precio)["costo_usd"] is None
    ctx(app, m["dueno"], m["est"])
    app.execute("select app.fijar_precio_pendiente(%s, 6)", (nuevo,))
    i = fila(app, "labor_insumo", sin_precio)
    assert (i["precio_unitario_usd"], i["costo_usd"]) == (6, 600)
    assert fila(app, "labor_insumo", con_precio)["costo_usd"] == 200     # las líneas con precio no se tocan
    f = fila(app, "labor", lab)
    assert (f["costo_incompleto"], f["costo_insumos_usd"], f["costo_total_usd"], f["costo_total_ha_usd"]) == (False, 800, 1200, 24)
    assert uno(app, "select precio_unitario_usd from movimiento_stock where labor_insumo_id = %s", sin_precio) == 6
    assert uno(app, "select count(*) from auditoria where tabla = 'labor_insumo' and registro_id = %s "
                    "and accion = 'update' and usuario_id = %s", sin_precio, m["dueno"]) == 1


def test_una_compra_con_precio_completa_los_insumos_sin_precio(app, m):
    ctx(app, m["dueno"], m["est"])
    ref(app, m, "pulverizacion", 8, tipo_labor="pulverizacion_mosquito")
    nuevo = producto(app, m, "Herbicida nuevo")           # sin precio: pendiente
    lab = labor(app, m, "pulverizacion_mosquito", ha=50)
    li = insumo(app, m, lab, nuevo, dosis=1)
    assert fila(app, "labor", lab)["costo_incompleto"] is True
    comprar(app, m, nuevo, 20, 5, fecha="2026-11-25")
    i = fila(app, "labor_insumo", li)
    assert (i["precio_unitario_usd"], i["costo_usd"]) == (5, 250)
    assert fila(app, "labor", lab)["costo_incompleto"] is False
    assert uno(app, "select precio_unitario_usd from movimiento_stock where labor_insumo_id = %s", li) == 5
    # una segunda compra a otro precio ya no la cambia (RN-10)
    comprar(app, m, nuevo, 100, 9, fecha="2026-11-26")
    assert fila(app, "labor_insumo", li)["costo_usd"] == 250


def test_una_compra_sin_precio_no_completa_los_insumos(app, m):
    ctx(app, m["dueno"], m["est"])
    nuevo = producto(app, m, "Herbicida nuevo")
    li = insumo(app, m, labor(app, m, "pulverizacion_mosquito"), nuevo, dosis=1)
    c = uno(app, "insert into compra (establecimiento_id, fecha) values (%s, '2026-11-25') returning id", m["est"])
    app.execute("insert into compra_item (establecimiento_id, compra_id, producto_id, cantidad) values (%s, %s, %s, 5)",
                (m["est"], c, nuevo))
    assert fila(app, "labor_insumo", li)["precio_unitario_usd"] is None


# Quién ve costos (RB-18) ---------------------------------------------------------------------------------

def test_el_encargado_ve_costos_solo_si_el_dueno_lo_habilita(app, m):
    puede = lambda: uno(app, "select app.puede_ver_costos()")  # noqa: E731
    ctx(app, m["encargado"], m["est"])
    assert puede() is False
    assert app.execute("update establecimiento set encargado_ve_costos = true where id = %s", (m["est"],)).rowcount == 0
    ctx(app, m["dueno"], m["est"])
    assert puede() is True
    app.execute("update establecimiento set encargado_ve_costos = true where id = %s", (m["est"],))
    ctx(app, m["encargado"], m["est"])
    assert puede() is True


def test_ver_costos_no_se_pasa_a_otro_establecimiento(app, admin):
    a, b = crear_establecimiento(admin, "Costos A"), crear_establecimiento(admin, "Costos B")
    ctx(app, a["dueno"], a["est"])
    app.execute("update establecimiento set encargado_ve_costos = true where id = %s", (a["est"],))
    ctx(app, b["encargado"], b["est"])
    assert uno(app, "select app.puede_ver_costos()") is False
    ctx(app, b["encargado"], a["est"])              # no es miembro de A
    assert uno(app, "select app.puede_ver_costos()") is False


# Carpida y "otra" (RN-17, RF-27) ------------------------------------------------------------------------

def test_carpida_con_valores_de_referencia_o_dichos(app, m):
    ctx(app, m["dueno"], m["est"])
    ref(app, m, "pago_hora_temporal", D("2.5"))
    ref(app, m, "horas_dia_temporal", 8)
    c1 = labor(app, m, "carpida", ha=20)
    carpida(app, m, c1, personas=3, dias=2)
    assert fila(app, "labor", c1)["costo_servicio_usd"] == 120           # 3 × 2 × 8 × 2,5
    c2 = labor(app, m, "carpida", ha=20)
    carpida(app, m, c2, personas=3, dias=2, horas=10, pago=3)
    assert fila(app, "labor", c2)["costo_servicio_usd"] == 180           # 3 × 2 × 10 × 3
    falla(app, psycopg.errors.UniqueViolation,
          "insert into carpida (establecimiento_id, labor_id, personas, dias) values (%s, %s, 1, 1)", m["est"], c2)


def test_carpida_pagada_en_pesos(app, m, dolar):
    ctx(app, m["dueno"], m["est"])
    ref(app, m, "horas_dia_temporal", 8)
    c = labor(app, m, "carpida", "2026-11-19", ha=20, moneda="ARS")
    carpida(app, m, c, personas=2, dias=1, pago=5000)                      # $5000 la hora con dólar a 1000
    assert fila(app, "labor", c)["costo_servicio_usd"] == 80               # 2 × 1 × 8 × 5


def test_los_temporales_van_solo_en_carpida_u_otra(app, m):
    ctx(app, m["dueno"], m["est"])
    rechaza(app, "solo en una carpida", "insert into carpida (establecimiento_id, labor_id, personas, dias) values (%s, %s, 1, 1)",
            m["est"], labor(app, m, "disco"))


def test_otra_lleva_descripcion_y_se_costea_con_un_costo_o_con_temporales(app, m):
    ctx(app, m["dueno"], m["est"])
    rechaza(app, "descripción", sql_labor() + ")", m["est"], m["lote"], "otra", "2026-11-20", 10)
    con_costo = labor(app, m, "otra", ha=10, descripcion="hacer canales", costo_declarado=200)
    assert fila(app, "labor", con_costo)["costo_servicio_usd"] == 200
    assert fila(app, "labor", con_costo)["costo_incompleto"] is False
    rechaza(app, "no los dos", "insert into carpida (establecimiento_id, labor_id, personas, dias, horas_dia, pago_hora) "
            "values (%s, %s, 1, 1, 8, 2)", m["est"], con_costo)
    con_temporales = labor(app, m, "otra", ha=10, descripcion="pisar algodón")
    carpida(app, m, con_temporales, personas=2, dias=1, horas=5, pago=2)
    assert fila(app, "labor", con_temporales)["costo_servicio_usd"] == 20
    sin_nada = labor(app, m, "otra", ha=10, descripcion="juntar semillas")
    assert fila(app, "labor", sin_nada)["costo_incompleto"] is True


def test_carpida_u_otra_hecha_por_personal_propio_cuesta_cero(app, m):
    ctx(app, m["dueno"], m["est"])
    urea = producto(app, m, "Urea", "fertilizante", "kg", precio=D("0.6"))
    c = labor(app, m, "carpida", ha=20, personal_propio=True)
    f = fila(app, "labor", c)
    assert (f["costo_servicio_usd"], f["costo_total_usd"], f["costo_incompleto"]) == (0, 0, False)
    o = labor(app, m, "otra", ha=10, descripcion="juntar semillas", personal_propio=True)
    insumo(app, m, o, urea, dosis=10, unidad="kg")                         # sus insumos sí cuestan
    f = fila(app, "labor", o)
    assert (f["costo_servicio_usd"], f["costo_insumos_usd"], f["costo_total_usd"], f["costo_incompleto"]) == (0, 60, 60, False)
    rechaza(app, "no lleva temporales", "insert into carpida (establecimiento_id, labor_id, personas, dias, horas_dia, pago_hora) "
            "values (%s, %s, 1, 1, 8, 2)", m["est"], c)


def test_personal_propio_solo_en_carpida_u_otra_y_sin_otro_costo(app, m):
    ctx(app, m["dueno"], m["est"])
    rechaza(app, "personal propio", sql_labor(", personal_propio") + ", true)",
            m["est"], m["lote"], "disco", "2026-11-20", 10)
    for extra in (", contratado) values (%s, %s, (select id from tipo_labor where codigo = 'carpida'), '2026-11-20', 10, true, true)",
                  ", costo_declarado) values (%s, %s, (select id from tipo_labor where codigo = 'carpida'), '2026-11-20', 10, true, 100)"):
        falla(app, psycopg.errors.CheckViolation,
              "insert into labor (establecimiento_id, lote_id, tipo_labor_id, fecha, ha, personal_propio" + extra, m["est"], m["lote"])


def test_fertilizacion_con_su_precio_por_ha(app, m):
    ctx(app, m["dueno"], m["est"])
    ref(app, m, "servicio_labor", 7, tipo_labor="fertilizacion")
    urea = producto(app, m, "Urea", "fertilizante", "kg", precio=D("0.6"))
    f_id = labor(app, m, "fertilizacion", ha=50)
    insumo(app, m, f_id, urea, dosis=100, unidad="kg")
    f = fila(app, "labor", f_id)
    assert (f["costo_servicio_usd"], f["costo_insumos_usd"], f["costo_total_usd"], f["costo_total_ha_usd"]) == (350, 3000, 3350, 67)


def test_carpida_sin_valores_de_referencia_se_completa_al_cargarlos(app, m):
    ctx(app, m["dueno"], m["est"])
    c = labor(app, m, "carpida", ha=20)
    carpida(app, m, c, personas=3, dias=2)
    assert fila(app, "labor", c)["costo_incompleto"] is True
    ref(app, m, "pago_hora_temporal", D("2.5"))
    assert fila(app, "labor", c)["costo_incompleto"] is True               # faltan las horas por día
    ref(app, m, "horas_dia_temporal", 8)
    f = fila(app, "labor", c)
    assert (f["costo_servicio_usd"], f["costo_incompleto"]) == (120, False)


# Anulación (RN-09, HU-03) -----------------------------------------------------------------------------

def test_hu03_anular_una_labor_devuelve_el_stock(app, m):
    ctx(app, m["dueno"], m["est"])
    glifo = producto(app, m)
    comprar(app, m, glifo, 100, 4)
    ctx(app, m["encargado"], m["est"])
    lab = labor(app, m, "pulverizacion_mosquito")
    li = insumo(app, m, lab, glifo, dosis=2)
    assert stock(app, glifo) == 0
    anular(app, "labor", lab, m["encargado"])
    assert stock(app, glifo) == 100
    mov = app.cursor(row_factory=dict_row).execute(
        "select * from movimiento_stock where labor_insumo_id = %s", (li,)).fetchone()
    assert mov["anulada_por"] == m["encargado"] and mov["motivo_anulacion"] == "me equivoqué"
    assert uno(app, "select precio_promedio_usd from producto where id = %s", glifo) == 4
    # una labor anulada no se des-anula ni acepta insumos
    falla(app, psycopg.errors.InsufficientPrivilege, "update labor set anulada_en = null, anulada_por = null where id = %s", lab)
    falla(app, psycopg.errors.InsufficientPrivilege,
          "insert into labor_insumo (establecimiento_id, labor_id, producto_id, dosis_ha, unidad) values (%s, %s, %s, 1, 'l')",
          m["est"], lab, glifo)


def test_anular_la_siembra_devuelve_el_ciclo_a_preparacion(app, m):
    ctx(app, m["dueno"], m["est"])
    s = labor(app, m, "siembra", cultivo_id=cultivo(app, "Soja"))
    anular(app, "labor", s, m["dueno"])
    c = ciclo(app, s)
    assert (c["estado"], c["cultivo_id"], c["campana_anio"]) == ("en_preparacion", None, None)


def test_el_encargado_solo_anula_o_completa_sus_labores(app, m):
    ctx(app, m["dueno"], m["est"])
    glifo = producto(app, m, precio=4)
    del_dueno = labor(app, m, "pulverizacion_mosquito")
    ctx(app, m["encargado"], m["est"])
    falla(app, psycopg.errors.InsufficientPrivilege,
          "update labor set anulada_en = now(), anulada_por = %s where id = %s", m["encargado"], del_dueno)
    falla(app, psycopg.errors.InsufficientPrivilege,
          "insert into labor_insumo (establecimiento_id, labor_id, producto_id, dosis_ha, unidad) values (%s, %s, %s, 1, 'l')",
          m["est"], del_dueno, glifo)
    propia = labor(app, m, "disco")
    anular(app, "labor", propia, m["encargado"])
    ctx(app, m["dueno"], m["est"])
    anular(app, "labor", del_dueno, m["dueno"])


def test_una_labor_de_un_ciclo_cerrado_no_se_anula_ni_se_completa(app, m):
    ctx(app, m["dueno"], m["est"])
    glifo = producto(app, m, precio=4)
    lab = labor(app, m, "pulverizacion_mosquito", "2026-10-01")
    app.execute("update ciclo set estado = 'cerrado', fecha_cierre = '2026-12-01' where id = %s", (ciclo(app, lab)["id"],))
    rechaza(app, "que está cerrado: solo se anula si el dueño lo reabre",
            "update labor set anulada_en = now(), anulada_por = %s where id = %s", m["dueno"], lab)
    rechaza(app, "ciclo cerrado", "insert into labor_insumo (establecimiento_id, labor_id, producto_id, dosis_ha, unidad) "
            "values (%s, %s, %s, 1, 'l')", m["est"], lab, glifo)


def test_los_movimientos_de_labor_solo_los_maneja_la_labor(app, m):
    ctx(app, m["dueno"], m["est"])
    glifo = producto(app, m, precio=4)
    li = insumo(app, m, labor(app, m, "pulverizacion_mosquito"), glifo, dosis=1)
    mov = uno(app, "select id from movimiento_stock where labor_insumo_id = %s", li)
    falla(app, psycopg.errors.InsufficientPrivilege,
          "update movimiento_stock set anulada_en = now(), anulada_por = %s where id = %s", m["dueno"], mov)
    falla(app, psycopg.errors.InsufficientPrivilege,
          "insert into movimiento_stock (establecimiento_id, producto_id, fecha, cantidad, tipo, labor_insumo_id) "
          "values (%s, %s, '2026-11-20', -1, 'labor', %s)", m["est"], glifo, li)
    falla(app, psycopg.errors.InsufficientPrivilege,
          "insert into movimiento_stock (establecimiento_id, producto_id, fecha, cantidad, tipo) "
          "values (%s, %s, '2026-11-20', -1, 'labor')", m["est"], glifo)


def test_insumos_y_temporales_no_se_editan(app, m):
    ctx(app, m["dueno"], m["est"])
    lab = labor(app, m, "pulverizacion_mosquito")
    li = insumo(app, m, lab, producto(app, m, precio=4), dosis=1)
    falla(app, psycopg.errors.InsufficientPrivilege, "update labor_insumo set dosis_ha = 5 where id = %s", li)
    falla(app, psycopg.errors.InsufficientPrivilege, "update labor_insumo set costo_usd = 0 where id = %s", li)
    falla(app, psycopg.errors.InsufficientPrivilege,
          "insert into labor_insumo (establecimiento_id, labor_id, producto_id, dosis_ha, unidad, costo_usd) "
          "values (%s, %s, (select producto_id from labor_insumo where id = %s), 1, 'l', 0)", m["est"], lab, li)
    c = labor(app, m, "carpida")
    falla(app, psycopg.errors.InsufficientPrivilege,
          "insert into carpida (establecimiento_id, labor_id, personas, dias, pago_hora_usd) values (%s, %s, 1, 1, 1)", m["est"], c)


def test_el_backend_no_recalcula_costos_por_su_cuenta(admin):
    for funcion in ("app.recalcular_costos_labor(uuid)", "app.labor_antes_de_insertar()",
                    "app.valor_referencia_despues_de_insertar()"):
        assert not admin.execute("select has_function_privilege('micampo_app', %s, 'execute')", (funcion,)).fetchone()[0], funcion


# Aislamiento entre establecimientos (RNF-16) --------------------------------------------------------

def test_las_labores_no_cruzan_establecimientos(app, admin):
    a, b = crear_establecimiento(admin, "Lab A"), crear_establecimiento(admin, "Lab B")
    ctx(app, a["dueno"], a["est"])
    glifo_a = producto(app, a, precio=4)
    lab_a = labor(app, a, "carpida")
    insumo(app, a, labor(app, a, "pulverizacion_mosquito"), glifo_a, dosis=1)
    carpida(app, a, lab_a, 1, 1, 8, 2)
    ctx(app, b["dueno"], b["est"])
    for tabla in ("labor", "labor_insumo", "carpida", "ciclo"):
        assert uno(app, f"select count(*) from {tabla}") == 0, tabla
    # B no carga labores en el lote de A, ni en su nombre
    rechaza(app, "el lote no existe", sql_labor() + ")", b["est"], a["lote"], "disco", "2026-11-20", 10,
            error=psycopg.errors.InvalidParameterValue)
    falla(app, (psycopg.errors.InvalidParameterValue, psycopg.errors.InsufficientPrivilege),
          sql_labor() + ")", a["est"], a["lote"], "disco", "2026-11-20", 10)
    # B no usa productos de A ni agrega insumos o temporales a labores de A
    lab_b = labor(app, b, "pulverizacion_mosquito")
    rechaza(app, "el producto no existe",
            "insert into labor_insumo (establecimiento_id, labor_id, producto_id, dosis_ha, unidad) values (%s, %s, %s, 1, 'l')",
            b["est"], lab_b, glifo_a, error=psycopg.errors.InvalidParameterValue)
    falla(app, (psycopg.errors.InvalidParameterValue, psycopg.errors.InsufficientPrivilege),
          "insert into carpida (establecimiento_id, labor_id, personas, dias) values (%s, %s, 1, 1)", a["est"], lab_a)
    falla(app, psycopg.errors.InvalidParameterValue,
          "insert into carpida (establecimiento_id, labor_id, personas, dias) values (%s, %s, 1, 1)", b["est"], lab_a)
    # B no anula labores de A
    assert app.execute("update labor set anulada_en = now(), anulada_por = %s where id = %s",
                       (b["dueno"], lab_a)).rowcount == 0
