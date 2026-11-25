"""Funciones auxiliares de los tests de base de datos."""
import uuid

import pytest


def nuevo_telefono() -> str:
    return "+54911" + str(uuid.uuid4().int)[:8]


def crear_establecimiento(admin, nombre="Establecimiento de prueba"):
    """Crea un establecimiento con un dueño y un encargado. Devuelve sus ids."""
    est = admin.execute("insert into establecimiento (nombre) values (%s) returning id", (nombre,)).fetchone()[0]
    dueno = admin.execute(
        "insert into usuario (nombre, telefono_whatsapp) values ('Dueño', %s) returning id", (nuevo_telefono(),)
    ).fetchone()[0]
    encargado = admin.execute(
        "insert into usuario (nombre, telefono_whatsapp) values ('Encargado', %s) returning id", (nuevo_telefono(),)
    ).fetchone()[0]
    admin.execute(
        "insert into membresia (usuario_id, establecimiento_id, rol) values (%s,%s,'dueno'), (%s,%s,'encargado')",
        (dueno, est, encargado, est),
    )
    campo = admin.execute(
        "insert into campo (establecimiento_id, nombre) values (%s, 'Campo') returning id", (est,)
    ).fetchone()[0]
    lote = admin.execute(
        "insert into lote (establecimiento_id, campo_id, nombre, ha_limpias, ha_monte) values (%s,%s,'Lote 1',100,20) returning id",
        (est, campo),
    ).fetchone()[0]
    return {"est": est, "dueno": dueno, "encargado": encargado, "campo": campo, "lote": lote}


def ctx(conn, usuario, est, origen="panel", mensaje=None):
    """Fija el contexto de la transacción actual, como hace el backend al abrir cada transacción."""
    conn.execute(
        "select app.fijar_contexto(%s::uuid, %s::uuid, %s, %s::uuid)", (usuario, est, origen, mensaje)
    )


def falla(conn, excepcion, sql, *params):
    """Verifica que una sentencia falle sin romper la transacción del test."""
    with pytest.raises(excepcion):
        with conn.transaction():
            conn.execute(sql, params)


def filas(conn, sql, *params):
    return conn.execute(sql, params).fetchall()


def uno(conn, sql, *params):
    return conn.execute(sql, params).fetchone()[0]
