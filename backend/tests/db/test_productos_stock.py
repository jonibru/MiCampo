"""Productos, compras, stock y precio promedio (RF-03 a RF-07, RF-19, RN-03, RN-04, RN-13, RN-14, RN-32)."""
from decimal import Decimal as D

import psycopg
import pytest
from helpers import crear_establecimiento, ctx, falla, filas, uno


@pytest.fixture
def m(admin):
    """Establecimiento nuevo por test, para que el stock y los promedios arranquen de cero."""
    return crear_establecimiento(admin, "Productos")


def producto(app, m, nombre="Glifosato 48%", categoria="herbicida", unidad="l", precio=None, **extra):
    cols = ["establecimiento_id", "nombre", "categoria", "unidad", "precio_inicial_usd", *extra]
    vals = [m["est"], nombre, categoria, unidad, precio, *extra.values()]
    return uno(app, f"insert into producto ({', '.join(cols)}) values ({', '.join(['%s'] * len(vals))}) returning id", *vals)


def compra(app, m, items, fecha="2026-11-20", moneda="USD", tc=None):
    """items: lista de (producto, cantidad, precio en la moneda de la compra o None)."""
    fuente = "manual" if tc else None
    c = uno(app, "insert into compra (establecimiento_id, fecha, moneda, tipo_cambio, tipo_cambio_fuente) "
                 "values (%s, %s, %s, %s, %s) returning id", m["est"], fecha, moneda, tc, fuente)
    for prod, cant, precio in items:
        app.execute("insert into compra_item (establecimiento_id, compra_id, producto_id, cantidad, precio_unitario) "
                    "values (%s, %s, %s, %s, %s)", (m["est"], c, prod, cant, precio))
    return c


def salida(app, m, prod, cantidad, tipo="uso_repuesto", fecha="2026-11-21"):
    return uno(app, "insert into movimiento_stock (establecimiento_id, producto_id, fecha, cantidad, tipo) "
                    "values (%s, %s, %s, %s, %s) returning id", m["est"], prod, fecha, -cantidad, tipo)


def stock(app, prod):
    return uno(app, "select stock from stock_producto where producto_id = %s", prod)


def promedio(app, prod):
    return uno(app, "select precio_promedio_usd from producto where id = %s", prod)


def anular(app, tabla, id_, usuario):
    app.execute(f"update {tabla} set anulada_en = now(), anulada_por = %s, motivo_anulacion = 'prueba' where id = %s",
                (usuario, id_))


# Alta de productos -------------------------------------------------------------------------

def test_el_promedio_arranca_en_el_precio_inicial_o_pendiente(app, m):
    ctx(app, m["encargado"], m["est"])
    con = producto(app, m, precio=4.5)
    sin = producto(app, m, nombre="Atrazina")
    assert promedio(app, con) == D("4.5") and promedio(app, sin) is None
    assert stock(app, con) == 0


def test_no_se_puede_inventar_el_promedio_al_crear(app, m):
    ctx(app, m["dueno"], m["est"])
    falla(app, psycopg.errors.InsufficientPrivilege,
          "insert into producto (establecimiento_id, nombre, categoria, unidad, precio_promedio_usd) values (%s, 'X', 'otro', 'kg', 1)",
          m["est"])


def test_unidad_categoria_y_promedio_no_se_editan(app, m):
    ctx(app, m["dueno"], m["est"])
    p = producto(app, m, precio=4)
    for sql in ("update producto set unidad = 'kg' where id = %s",
                "update producto set categoria = 'fungicida' where id = %s",
                "update producto set precio_promedio_usd = 1 where id = %s"):
        falla(app, psycopg.errors.InsufficientPrivilege, sql, p)
    app.execute("update producto set nombre = 'Glifosato 48%% Atanor' where id = %s", (p,))


def test_semillas_en_bolsas_con_peso_y_cultivo(app, m):
    ctx(app, m["dueno"], m["est"])
    soja = uno(app, "select id from cultivo where nombre = 'Soja'")
    producto(app, m, "Soja DM 46i20", "semilla", "bolsa", 30, cultivo_id=soja, variedad="DM 46i20", kg_por_bolsa=40)
    falla(app, psycopg.errors.CheckViolation,
          "insert into producto (establecimiento_id, nombre, categoria, unidad) values (%s, 'Semilla sin peso', 'semilla', 'bolsa')", m["est"])
    falla(app, psycopg.errors.CheckViolation,
          "insert into producto (establecimiento_id, nombre, categoria, unidad, cultivo_id, kg_por_bolsa) values (%s, 'Semilla en kg', 'semilla', 'kg', %s, 40)",
          m["est"], soja)
    falla(app, psycopg.errors.CheckViolation,
          "insert into producto (establecimiento_id, nombre, categoria, unidad) values (%s, 'Urea en bolsas', 'fertilizante', 'bolsa')", m["est"])


def test_repuestos_por_unidad_y_con_modelo(app, m):
    ctx(app, m["dueno"], m["est"])
    producto(app, m, "Filtro de aceite", "repuesto", "unidad", 25, modelo="W 940")
    falla(app, psycopg.errors.CheckViolation,
          "insert into producto (establecimiento_id, nombre, categoria, unidad) values (%s, 'Filtro sin modelo', 'repuesto', 'unidad')", m["est"])
    falla(app, psycopg.errors.CheckViolation,
          "insert into producto (establecimiento_id, nombre, categoria, unidad, modelo) values (%s, 'Correa', 'repuesto', 'kg', 'B52')", m["est"])
    falla(app, psycopg.errors.CheckViolation,
          "insert into producto (establecimiento_id, nombre, categoria, unidad) values (%s, 'Glifo por unidad', 'herbicida', 'unidad')", m["est"])


def test_dos_concentraciones_son_dos_productos_y_el_nombre_no_se_repite(app, m):
    ctx(app, m["dueno"], m["est"])
    producto(app, m, "Glifosato 48%")
    producto(app, m, "Glifosato 66%")
    falla(app, psycopg.errors.UniqueViolation,
          "insert into producto (establecimiento_id, nombre, categoria, unidad) values (%s, 'glifosato 48%%', 'herbicida', 'l')", m["est"])


def test_el_catalogo_es_de_solo_lectura(app, admin, m):
    admin.execute("insert into catalogo_producto (nombre, categoria, unidad, precio_referencia_usd) values ('Cat 2,4-D', 'herbicida', 'l', 6)")
    ctx(app, m["encargado"], m["est"])
    assert uno(app, "select precio_referencia_usd from catalogo_producto where nombre = 'Cat 2,4-D'") == 6
    falla(app, psycopg.errors.InsufficientPrivilege, "insert into catalogo_producto (nombre, categoria, unidad) values ('X', 'otro', 'kg')")
    falla(app, psycopg.errors.InsufficientPrivilege, "update catalogo_producto set precio_referencia_usd = 1")


# Precio promedio (RN-04) ---------------------------------------------------------------------

def test_compras_con_precio_promedio_ponderado(app, m):
    ctx(app, m["dueno"], m["est"])
    p = producto(app, m, precio=10)
    compra(app, m, [(p, 100, 12)])          # stock en 0: el promedio pasa a ser el precio de la compra
    assert (stock(app, p), promedio(app, p)) == (100, 12)
    compra(app, m, [(p, 100, 14)], fecha="2026-11-21")
    assert (stock(app, p), promedio(app, p)) == (200, 13)
    compra(app, m, [(p, 50, 18)], fecha="2026-11-22")   # (200*13 + 50*18) / 250 = 14
    assert promedio(app, p) == 14


def test_compra_sin_precio_suma_stock_y_mantiene_el_promedio(app, m):
    ctx(app, m["encargado"], m["est"])
    p = producto(app, m, precio=10)
    compra(app, m, [(p, 100, 12)])
    compra(app, m, [(p, 40, None)], fecha="2026-11-21")
    assert (stock(app, p), promedio(app, p)) == (140, 12)


def test_producto_pendiente_toma_el_precio_de_la_primera_compra_con_precio(app, m):
    ctx(app, m["encargado"], m["est"])
    p = producto(app, m)
    compra(app, m, [(p, 10, None)])
    assert promedio(app, p) is None
    compra(app, m, [(p, 10, 7.5)], fecha="2026-11-21")
    assert promedio(app, p) == D("7.5")


def test_stock_negativo_se_permite_se_marca_y_la_compra_siguiente_define_el_promedio(app, m):
    ctx(app, m["dueno"], m["est"])
    p = producto(app, m, "Filtro", "repuesto", "unidad", 20, modelo="F1")
    mov = salida(app, m, p, 3)
    revisar, resultante, precio = filas(app, "select revisar, stock_resultante, precio_unitario_usd from movimiento_stock where id = %s", mov)[0]
    assert (revisar, resultante, precio) == (True, -3, 20)
    compra(app, m, [(p, 10, 30)], fecha="2026-11-22")
    assert (stock(app, p), promedio(app, p)) == (7, 30)


def test_una_salida_queda_costeada_al_promedio_del_momento(app, m):
    """RN-10: el costo queda fijo aunque después cambie el promedio."""
    ctx(app, m["dueno"], m["est"])
    p = producto(app, m, "Correa", "repuesto", "unidad", modelo="B52")
    compra(app, m, [(p, 10, 15)])
    uso = salida(app, m, p, 2, fecha="2026-11-23")
    compra(app, m, [(p, 10, 25)], fecha="2026-11-24")
    assert uno(app, "select precio_unitario_usd from movimiento_stock where id = %s", uso) == 15
    assert uno(app, "select revisar from movimiento_stock where id = %s", uso) is False


def test_compra_en_pesos_se_guarda_en_dolares_con_el_original(app, m):
    ctx(app, m["dueno"], m["est"])
    p = producto(app, m, precio=10)
    c = compra(app, m, [(p, 100, 12000), (p, 50, None)], moneda="ARS", tc=1000)
    assert uno(app, "select precio_unitario_usd from compra_item where compra_id = %s and precio_unitario is not null", c) == 12
    assert filas(app, "select total_usd, monto_ars, tipo_cambio_fuente from compra where id = %s", c) == [(D("1200.00"), D("1200000.00"), "manual")]
    assert promedio(app, p) == 12


def test_compra_en_pesos_exige_tipo_de_cambio(app, m):
    ctx(app, m["dueno"], m["est"])
    falla(app, psycopg.errors.CheckViolation,
          "insert into compra (establecimiento_id, fecha, moneda) values (%s, current_date, 'ARS')", m["est"])
    falla(app, psycopg.errors.CheckViolation,
          "insert into compra (establecimiento_id, fecha, moneda, tipo_cambio, tipo_cambio_fuente) values (%s, current_date, 'USD', 1000, 'manual')", m["est"])


def test_items_de_una_misma_compra_se_procesan_en_el_orden_de_carga(app, m):
    """Todos los movimientos de una transacción tienen la misma hora: el orden no puede quedar al azar."""
    ctx(app, m["dueno"], m["est"])
    for _ in range(5):
        p = producto(app, m, nombre=f"P{uno(app, 'select gen_random_uuid()')}", precio=10)
        compra(app, m, [(p, 100, 12), (p, 50, None), (p, 50, 20)])
        # 100 a 12 (stock 0 -> 12); 50 sin precio (sigue 12); 50 a 20 -> (150*12 + 50*20) / 200 = 14
        assert promedio(app, p) == 14


def test_una_compra_hacia_atras_en_el_tiempo_recalcula_en_orden_de_fecha(app, m):
    ctx(app, m["dueno"], m["est"])
    p = producto(app, m)
    compra(app, m, [(p, 100, 20)], fecha="2026-11-20")
    compra(app, m, [(p, 100, 10)], fecha="2026-11-01")   # cargada después, pero ocurrió antes
    assert (stock(app, p), promedio(app, p)) == (200, 15)


# Anulación (RN-09, RF-13) ---------------------------------------------------------------------

def test_anular_una_compra_revierte_el_stock_y_recalcula_el_promedio(app, m):
    ctx(app, m["dueno"], m["est"])
    p = producto(app, m)
    compra(app, m, [(p, 100, 10)])
    c2 = compra(app, m, [(p, 100, 20)], fecha="2026-11-21")
    assert promedio(app, p) == 15
    anular(app, "compra", c2, m["dueno"])
    assert (stock(app, p), promedio(app, p)) == (100, 10)
    assert uno(app, "select count(*) from movimiento_stock where anulada_en is not null") == 1


def test_anular_una_compra_no_cambia_el_costo_de_lo_ya_usado(app, m):
    ctx(app, m["dueno"], m["est"])
    p = producto(app, m, "Cubierta", "repuesto", "unidad", modelo="18.4-38")
    c = compra(app, m, [(p, 4, 500)])
    uso = salida(app, m, p, 2)
    anular(app, "compra", c, m["dueno"])
    assert uno(app, "select precio_unitario_usd from movimiento_stock where id = %s", uso) == 500
    assert stock(app, p) == -2


def test_no_se_agregan_items_a_una_compra_anulada(app, m):
    ctx(app, m["dueno"], m["est"])
    p = producto(app, m, precio=1)
    c = compra(app, m, [(p, 1, 1)])
    anular(app, "compra", c, m["dueno"])
    falla(app, psycopg.errors.InsufficientPrivilege,
          "insert into compra_item (establecimiento_id, compra_id, producto_id, cantidad) values (%s, %s, %s, 1)", m["est"], c, p)


def test_una_anulacion_no_se_deshace(app, m):
    ctx(app, m["dueno"], m["est"])
    p = producto(app, m, precio=1)
    c = compra(app, m, [(p, 1, 1)])
    anular(app, "compra", c, m["dueno"])
    falla(app, psycopg.errors.InsufficientPrivilege,
          "update compra set anulada_en = null, anulada_por = null where id = %s", c)


def test_la_anulacion_queda_a_nombre_de_quien_anula(app, m):
    ctx(app, m["dueno"], m["est"])
    p = producto(app, m, precio=1)
    c = compra(app, m, [(p, 1, 1)])
    falla(app, psycopg.errors.InsufficientPrivilege,
          "update compra set anulada_en = now(), anulada_por = %s where id = %s", m["encargado"], c)


def test_el_encargado_anula_solo_sus_cargas(app, m):
    ctx(app, m["dueno"], m["est"])
    p = producto(app, m, precio=1)
    del_dueno = compra(app, m, [(p, 1, 1)])
    ctx(app, m["encargado"], m["est"])
    propia = compra(app, m, [(p, 1, 1)])
    falla(app, psycopg.errors.InsufficientPrivilege,
          "update compra set anulada_en = now(), anulada_por = %s where id = %s", m["encargado"], del_dueno)
    anular(app, "compra", propia, m["encargado"])
    ctx(app, m["dueno"], m["est"])
    lluvia = uno(app, "insert into lluvia (establecimiento_id, fecha, mm) values (%s, current_date, 5) returning id", m["est"])
    ctx(app, m["encargado"], m["est"])
    falla(app, psycopg.errors.InsufficientPrivilege, "update lluvia set mm = 50 where id = %s", lluvia)


def test_el_dueno_corrige_cargas_del_encargado(app, m):
    ctx(app, m["encargado"], m["est"])
    lluvia = uno(app, "insert into lluvia (establecimiento_id, fecha, mm) values (%s, current_date, 5) returning id", m["est"])
    ctx(app, m["dueno"], m["est"])
    assert app.execute("update lluvia set mm = 15 where id = %s", (lluvia,)).rowcount == 1


def test_no_se_cambia_quien_hizo_una_carga(app, m):
    ctx(app, m["dueno"], m["est"])
    lluvia = uno(app, "insert into lluvia (establecimiento_id, fecha, mm) values (%s, current_date, 5) returning id", m["est"])
    falla(app, psycopg.errors.InsufficientPrivilege, "update lluvia set creado_por = %s where id = %s", m["encargado"], lluvia)
    falla(app, psycopg.errors.InsufficientPrivilege, "update lluvia set origen = 'bot' where id = %s", lluvia)


def test_anular_un_uso_de_repuesto_devuelve_el_stock(app, m):
    ctx(app, m["encargado"], m["est"])
    p = producto(app, m, "Filtro aire", "repuesto", "unidad", 10, modelo="A1")
    compra(app, m, [(p, 5, 10)])
    uso = salida(app, m, p, 2)
    anular(app, "movimiento_stock", uso, m["encargado"])
    assert stock(app, p) == 5


# Reglas de los movimientos ---------------------------------------------------------------------

def test_los_movimientos_de_compra_solo_los_genera_la_compra(app, m):
    ctx(app, m["dueno"], m["est"])
    p = producto(app, m, precio=1)
    falla(app, psycopg.errors.InsufficientPrivilege,
          "insert into movimiento_stock (establecimiento_id, producto_id, fecha, cantidad, tipo) values (%s, %s, current_date, 5, 'compra')",
          m["est"], p)
    c = compra(app, m, [(p, 1, 1)])
    mov = uno(app, "select m.id from movimiento_stock m join compra_item i on i.id = m.compra_item_id where i.compra_id = %s", c)
    falla(app, psycopg.errors.InsufficientPrivilege,
          "update movimiento_stock set anulada_en = now(), anulada_por = %s where id = %s", m["dueno"], mov)


def test_uso_de_repuesto_solo_para_repuestos(app, m):
    ctx(app, m["dueno"], m["est"])
    p = producto(app, m, precio=1)
    falla(app, psycopg.errors.CheckViolation,
          "insert into movimiento_stock (establecimiento_id, producto_id, fecha, cantidad, tipo) values (%s, %s, current_date, -1, 'uso_repuesto')",
          m["est"], p)


def test_un_ajuste_no_tiene_precio_ni_cambia_el_promedio(app, m):
    ctx(app, m["encargado"], m["est"])
    p = producto(app, m, precio=8)
    compra(app, m, [(p, 10, 8)])
    aj = uno(app, "insert into movimiento_stock (establecimiento_id, producto_id, fecha, cantidad, tipo, motivo) "
                  "values (%s, %s, current_date, -2, 'ajuste', 'pérdida') returning id", m["est"], p)
    assert uno(app, "select precio_unitario_usd from movimiento_stock where id = %s", aj) is None
    assert (stock(app, p), promedio(app, p)) == (8, 8)


def test_los_items_de_compra_no_se_editan(app, m):
    ctx(app, m["dueno"], m["est"])
    p = producto(app, m, precio=1)
    c = compra(app, m, [(p, 1, 1)])
    falla(app, psycopg.errors.InsufficientPrivilege, "update compra_item set cantidad = 100 where compra_id = %s", c)
    falla(app, psycopg.errors.InsufficientPrivilege, "update compra set total_usd = 0 where id = %s", c)


def test_la_compra_hereda_quien_y_desde_donde_en_sus_movimientos(app, m):
    msg = "00000000-0000-0000-0000-0000000000cc"
    ctx(app, m["encargado"], m["est"], origen="bot", mensaje=msg)
    p = producto(app, m, precio=1)
    compra(app, m, [(p, 3, 2)])
    assert filas(app, "select creado_por, origen, mensaje_id::text from movimiento_stock") == [(m["encargado"], "bot", msg)]


# Precio pendiente ------------------------------------------------------------------------------

def test_el_dueno_fija_un_precio_pendiente(app, m):
    ctx(app, m["encargado"], m["est"])
    p = producto(app, m)
    compra(app, m, [(p, 10, None)])
    falla(app, psycopg.errors.InsufficientPrivilege, "select app.fijar_precio_pendiente(%s, 9)", p)
    ctx(app, m["dueno"], m["est"])
    app.execute("select app.fijar_precio_pendiente(%s, 9)", (p,))
    assert promedio(app, p) == 9
    falla(app, psycopg.errors.InvalidParameterValue, "select app.fijar_precio_pendiente(%s, 11)", p)


# Aislamiento -----------------------------------------------------------------------------------

def test_productos_y_stock_aislados_entre_establecimientos(app, admin, m):
    otro = crear_establecimiento(admin, "Otro")
    ctx(app, otro["dueno"], otro["est"])
    ajeno = producto(app, otro, precio=1)
    compra(app, otro, [(ajeno, 10, 1)])
    ctx(app, m["dueno"], m["est"])
    assert uno(app, "select count(*) from producto") == 0
    assert uno(app, "select count(*) from stock_producto") == 0
    assert uno(app, "select count(*) from movimiento_stock") == 0
    c = uno(app, "insert into compra (establecimiento_id, fecha) values (%s, current_date) returning id", m["est"])
    falla(app, psycopg.errors.ForeignKeyViolation,
          "insert into compra_item (establecimiento_id, compra_id, producto_id, cantidad) values (%s, %s, %s, 1)", m["est"], c, ajeno)
    falla(app, psycopg.errors.InvalidParameterValue, "select app.fijar_precio_pendiente(%s, 5)", ajeno)
