"""Qué puede hacer el dueño y qué el encargado (sección 2 del diseño)."""
import psycopg
from helpers import ctx, falla, filas, nuevo_telefono, uno


def test_el_encargado_puede_cargar_lluvias(app, mundo):
    a = mundo["A"]
    ctx(app, a["encargado"], a["est"], origen="bot")
    app.execute("insert into lluvia (establecimiento_id, fecha, mm) values (%s, current_date, 12.5)", (a["est"],))
    assert uno(app, "select count(*) from lluvia") == 1


def test_el_encargado_no_puede_invitar_ni_modificar_membresias(app, mundo):
    a = mundo["A"]
    ctx(app, a["encargado"], a["est"])
    falla(app, psycopg.errors.InsufficientPrivilege, "select app.invitar_encargado('Nuevo', %s)", nuevo_telefono())
    assert app.execute("update membresia set activa = false where usuario_id = %s", (a["dueno"],)).rowcount == 0
    assert app.execute("update membresia set rol = 'dueno' where usuario_id = %s", (a["encargado"],)).rowcount == 0


def test_nadie_crea_usuarios_ni_membresias_por_fuera_de_las_funciones(app, mundo):
    a = mundo["A"]
    ctx(app, a["dueno"], a["est"])
    falla(app, psycopg.errors.InsufficientPrivilege,
          "insert into usuario (nombre, telefono_whatsapp) values ('X', %s)", nuevo_telefono())
    falla(app, psycopg.errors.InsufficientPrivilege,
          "insert into membresia (usuario_id, establecimiento_id, rol) values (%s, %s, 'dueno')", a["encargado"], a["est"])


def test_el_encargado_no_puede_cambiar_el_establecimiento(app, mundo):
    a = mundo["A"]
    ctx(app, a["encargado"], a["est"])
    assert app.execute("update establecimiento set nombre = 'otro' where id = %s", (a["est"],)).rowcount == 0


def test_el_encargado_no_ve_la_auditoria_y_el_dueno_si(app, mundo):
    a = mundo["A"]
    ctx(app, a["encargado"], a["est"])
    app.execute("insert into lluvia (establecimiento_id, fecha, mm) values (%s, current_date, 3)", (a["est"],))
    assert uno(app, "select count(*) from auditoria") == 0
    ctx(app, a["dueno"], a["est"])
    assert uno(app, "select count(*) from auditoria where tabla = 'lluvia'") >= 1


def test_el_dueno_invita_a_un_encargado(app, mundo):
    a = mundo["A"]
    ctx(app, a["dueno"], a["est"])
    tel = nuevo_telefono()
    nuevo = uno(app, "select app.invitar_encargado('Nuevo', %s)", tel)
    assert uno(app, "select count(*) from membresia where establecimiento_id = %s and activa", a["est"]) == 3
    assert filas(app, "select rol from membresia where usuario_id = %s", nuevo) == [("encargado",)]
    # invitar de nuevo al mismo número no duplica nada
    assert uno(app, "select app.invitar_encargado('Nuevo', %s)", tel) == nuevo
    assert uno(app, "select count(*) from membresia where establecimiento_id = %s", a["est"]) == 3


def test_reinvitar_a_alguien_dado_de_baja_lo_reactiva_sin_cambiarle_el_rol(app, admin):
    from helpers import crear_establecimiento
    m = crear_establecimiento(admin, "Reinvitar")
    ctx(app, m["dueno"], m["est"])
    app.execute("update membresia set activa = false where usuario_id = %s", (m["encargado"],))
    tel = uno(app, "select telefono_whatsapp from usuario where id = %s", m["encargado"])
    assert uno(app, "select app.invitar_encargado('Otro nombre', %s)", tel) == m["encargado"]
    assert filas(app, "select rol, activa from membresia where usuario_id = %s", m["encargado"]) == [("encargado", True)]


def test_el_dueno_no_puede_verificar_telefonos_ni_cambiar_datos_sensibles(app, mundo):
    a = mundo["A"]
    ctx(app, a["dueno"], a["est"])
    falla(app, psycopg.errors.InsufficientPrivilege,
          "update usuario set telefono_whatsapp = %s where id = %s", nuevo_telefono(), a["encargado"])
    falla(app, psycopg.errors.InsufficientPrivilege,
          "update usuario set activo = false where id = %s", a["encargado"])
    falla(app, psycopg.errors.InsufficientPrivilege,
          "update usuario set telefono_verificado_en = now() where id = %s", a["encargado"])


def test_el_dueno_modifica_el_establecimiento(app, mundo):
    a = mundo["A"]
    ctx(app, a["dueno"], a["est"])
    assert app.execute("update establecimiento set equipos_pulverizacion = array['mosquito','dron'] where id = %s",
                       (a["est"],)).rowcount == 1
    falla(app, psycopg.errors.CheckViolation,
          "update establecimiento set equipos_pulverizacion = array['cohete'] where id = %s", a["est"])
