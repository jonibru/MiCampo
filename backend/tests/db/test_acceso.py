"""Identificación, alta de usuarios y establecimientos (RF-23, RF-28)."""
import psycopg
import pytest
from helpers import ctx, falla, filas, nuevo_telefono, uno


@pytest.mark.parametrize("telefono", ["1234", "5491122334455", "+0123456789", "+54 9 11 2233 4455", "+549112233445566778"])
def test_el_telefono_debe_estar_en_formato_internacional(admin, telefono):
    with pytest.raises(psycopg.errors.CheckViolation):
        admin.execute("insert into usuario (nombre, telefono_whatsapp) values ('X', %s)", (telefono,))


def test_el_telefono_y_el_email_son_unicos(admin):
    tel = nuevo_telefono()
    admin.execute("insert into usuario (nombre, telefono_whatsapp, email) values ('A', %s, 'Mail@Ejemplo.com')", (tel,))
    with pytest.raises(psycopg.errors.UniqueViolation):
        admin.execute("insert into usuario (nombre, telefono_whatsapp) values ('B', %s)", (tel,))
    with pytest.raises(psycopg.errors.UniqueViolation):
        admin.execute("insert into usuario (nombre, telefono_whatsapp, email) values ('C', %s, 'mail@ejemplo.com')", (nuevo_telefono(),))


def test_el_bot_identifica_a_la_persona_por_su_telefono_sin_contexto(app):
    telefono = nuevo_telefono()
    nuevo = uno(app, "select app.crear_usuario('Ana', %s)", telefono)
    fila = filas(app, "select usuario_id, nombre, activo, telefono_verificado from app.identificar_usuario(%s)", telefono)
    assert fila == [(nuevo, "Ana", True, False)]
    assert filas(app, "select * from app.identificar_usuario('+10000000000')") == []


def test_alta_completa_de_un_productor(app):
    """Flujo de RF-23: crear usuario, fijar su contexto, crear el establecimiento y trabajar en él."""
    usuario = uno(app, "select app.crear_usuario('Productor', %s)", nuevo_telefono())
    ctx(app, usuario, None)
    est = uno(app, "select app.crear_establecimiento(%s, 'Mi primer campo')", usuario)
    assert filas(app, "select establecimiento_id, nombre, rol from app.membresias_de(%s)", usuario) == [(est, "Mi primer campo", "dueno")]
    app.commit()
    ctx(app, usuario, est)
    assert uno(app, "select count(*) from establecimiento") == 1
    app.execute("insert into campo (establecimiento_id, nombre) values (%s, 'Campo uno')", (est,))
    assert uno(app, "select ultimo_establecimiento_id from usuario where id = %s", usuario) == est


def test_no_se_puede_crear_un_establecimiento_a_nombre_de_otro(app, mundo):
    a = mundo["A"]
    ctx(app, a["encargado"], None)
    falla(app, psycopg.errors.InsufficientPrivilege, "select app.crear_establecimiento(%s, 'Falso')", a["dueno"])


def test_las_membresias_solo_se_listan_para_uno_mismo(app, mundo):
    a = mundo["A"]
    ctx(app, a["encargado"], None)
    assert filas(app, "select * from app.membresias_de(%s)", a["dueno"]) == []
    assert len(filas(app, "select * from app.membresias_de(%s)", a["encargado"])) == 1


def test_origen_invalido_en_el_contexto(app):
    falla(app, psycopg.errors.InvalidParameterValue, "select app.fijar_contexto(null, null, 'hacker', null)")
    falla(app, psycopg.errors.InvalidParameterValue, "select app.fijar_contexto(null, null, null, null)")


def test_usuario_por_cuenta_de_auth(app, admin):
    cuenta = uno(admin, "insert into auth.users (id) values (gen_random_uuid()) returning id")
    usuario = uno(admin, "insert into usuario (nombre, telefono_whatsapp, auth_user_id) values ('Panel', %s, %s) returning id",
                  nuevo_telefono(), cuenta)
    assert uno(app, "select app.usuario_por_auth(%s)", cuenta) == usuario
    admin.execute("update usuario set activo = false where id = %s", (usuario,))
    assert uno(app, "select app.usuario_por_auth(%s)", cuenta) is None
