"""Auditoría (RNF-05): cada cambio de datos deja una fila con quién, desde dónde y el antes y el después."""
import json

import psycopg
from helpers import ctx, falla, filas, nuevo_telefono, uno


def test_insert_update_y_delete_quedan_registrados(app, mundo):
    a = mundo["A"]
    mensaje = "00000000-0000-0000-0000-0000000000bb"
    ctx(app, a["dueno"], a["est"], origen="bot", mensaje=mensaje)
    campo = uno(app, "insert into campo (establecimiento_id, nombre) values (%s, 'Nuevo') returning id", a["est"])
    app.execute("update campo set nombre = 'Renombrado' where id = %s", (campo,))
    app.execute("delete from campo where id = %s", (campo,))
    registros = filas(
        app,
        "select accion, antes, despues, usuario_id, origen, mensaje_id::text, establecimiento_id "
        "from auditoria where tabla = 'campo' and registro_id = %s order by creado_en, accion desc",
        campo,
    )
    assert sorted(r[0] for r in registros) == ["delete", "insert", "update"]
    por_accion = {r[0]: r for r in registros}
    assert por_accion["insert"][1] is None and por_accion["insert"][2]["nombre"] == "Nuevo"
    assert por_accion["update"][1]["nombre"] == "Nuevo" and por_accion["update"][2]["nombre"] == "Renombrado"
    assert por_accion["delete"][2] is None and por_accion["delete"][1]["nombre"] == "Renombrado"
    for r in registros:
        assert r[3] == a["dueno"] and r[4] == "bot" and r[5] == mensaje and r[6] == a["est"]


def test_una_modificacion_sin_cambios_no_genera_registro(app, mundo):
    a = mundo["A"]
    ctx(app, a["dueno"], a["est"])
    antes = uno(app, "select count(*) from auditoria")
    app.execute("update campo set nombre = nombre where id = %s", (a["campo"],))
    assert uno(app, "select count(*) from auditoria") == antes


def test_el_backend_no_puede_escribir_en_la_auditoria(app, mundo):
    a = mundo["A"]
    ctx(app, a["dueno"], a["est"])
    falla(app, psycopg.errors.InsufficientPrivilege,
          "insert into auditoria (tabla, accion) values ('campo', 'insert')")
    falla(app, psycopg.errors.InsufficientPrivilege, "update auditoria set tabla = 'x'")
    falla(app, psycopg.errors.InsufficientPrivilege, "delete from auditoria")


def test_la_auditoria_de_un_establecimiento_no_se_ve_desde_otro(app, mundo):
    a, b = mundo["A"], mundo["B"]
    ctx(app, a["dueno"], a["est"])
    app.execute("update campo set nombre = 'Cambio A' where id = %s", (a["campo"],))
    ctx(app, b["dueno"], b["est"])
    assert uno(app, "select count(*) from auditoria where despues ->> 'nombre' = 'Cambio A'") == 0


def test_el_codigo_de_verificacion_nunca_se_audita(admin):
    u = uno(admin, "insert into usuario (nombre, telefono_whatsapp, codigo_verificacion_hash) values ('V', %s, 'secreto-hash') returning id",
            nuevo_telefono())
    admin.execute("update usuario set codigo_verificacion_hash = 'otro-hash' where id = %s", (u,))
    for antes, despues in filas(admin, "select antes, despues from auditoria where tabla = 'usuario' and registro_id = %s", u):
        assert "secreto-hash" not in json.dumps(antes) + json.dumps(despues)
        assert "otro-hash" not in json.dumps(antes) + json.dumps(despues)
        assert "codigo_verificacion_hash" not in (antes or {}) and "codigo_verificacion_hash" not in (despues or {})
