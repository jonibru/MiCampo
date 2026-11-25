"""Importación del catálogo base desde CSV (RN-30, RF-36)."""
import uuid

import pytest
from helpers import uno
from micampo.catalogo import CatalogoInvalido, importar, leer_csv

ENCABEZADO = "nombre,categoria,unidad,principio_activo,concentracion,precio_usd,tipo_repuesto,modelo,rodado,kg_por_bolsa,cultivo\n"


@pytest.fixture
def csv_tmp(tmp_path):
    def escribir(cuerpo: str, encabezado: str = ENCABEZADO, separador: str = ","):
        ruta = tmp_path / f"catalogo_{uuid.uuid4().hex[:6]}.csv"
        ruta.write_text((encabezado + cuerpo).replace(",", separador), encoding="utf-8-sig")
        return leer_csv(ruta)
    return escribir


@pytest.fixture
def admin_tx(admin):
    """Cada test ve un catálogo vacío y no deja rastro: se trabaja dentro de una transacción que se revierte."""
    admin.autocommit = False
    admin.execute("update catalogo_producto set activo = false")
    admin.execute("savepoint inicio")
    yield admin
    admin.rollback()
    admin.autocommit = True


def activos(conn):
    return {r[0] for r in conn.execute("select nombre from catalogo_producto where activo").fetchall()}


def test_carga_productos_de_cada_tipo(admin_tx, csv_tmp):
    filas = csv_tmp(
        "Glifosato 48% CSV,herbicida,l,glifosato,48%,\"4,5\",,,,,\n"
        "Soja DM 40R16 CSV,semilla,bolsa,,,30,,,,40,soja\n"
        "Cubierta 18.4-38 CSV,repuesto,unidad,,,900,cubierta,Firestone,18.4-38,,\n"
        "Correa 48cm CSV,repuesto,unidad,,,12,correa,correa 48cm,,,\n"
        "Urea CSV,fertilizante,kg,,,,,,,,\n"
    )
    res = importar(admin_tx, filas, aplicar=True)
    assert len(res.agregados) == 5
    assert uno(admin_tx, "select precio_referencia_usd from catalogo_producto where nombre = %s", "Glifosato 48% CSV") == 4.5
    assert uno(admin_tx, "select c.nombre from catalogo_producto p join cultivo c on c.id = p.cultivo_id where p.nombre = 'Soja DM 40R16 CSV'") == "Soja"
    assert uno(admin_tx, "select precio_referencia_usd is null from catalogo_producto where nombre = 'Urea CSV'") is True


def test_volver_a_importar_actualiza_sin_duplicar_y_desactiva_lo_que_falta(admin_tx, csv_tmp):
    importar(admin_tx, csv_tmp("Prod A CSV,herbicida,l,,,1,,,,,\nProd B CSV,herbicida,l,,,2,,,,,\n"), aplicar=True)
    res = importar(admin_tx, csv_tmp("prod a csv,herbicida,l,,,1.5,,,,,\n"), aplicar=True)
    assert res.actualizados == ["prod a csv"] and res.desactivados == ["Prod B CSV"]
    assert uno(admin_tx, "select count(*) from catalogo_producto where lower(nombre) = 'prod a csv'") == 1
    assert activos(admin_tx) == {"prod a csv"}
    res = importar(admin_tx, csv_tmp("prod a csv,herbicida,l,,,1.5,,,,,\nProd B CSV,herbicida,l,,,2,,,,,\n"), aplicar=True)
    assert res.sin_cambios == ["prod a csv"] and res.actualizados == ["Prod B CSV"]
    assert activos(admin_tx) == {"prod a csv", "Prod B CSV"}


def test_sin_aplicar_no_cambia_nada(admin_tx, csv_tmp):
    res = importar(admin_tx, csv_tmp("Solo mirar CSV,herbicida,l,,,1,,,,,\n"), aplicar=False)
    assert res.agregados == ["Solo mirar CSV"]
    assert uno(admin_tx, "select count(*) from catalogo_producto where nombre = 'Solo mirar CSV'") == 0


def test_una_fila_mala_no_carga_ninguna_y_avisa_todos_los_errores(admin_tx, csv_tmp):
    filas = csv_tmp(
        "Bueno CSV,herbicida,l,,,1,,,,,\n"
        "Malo 1 CSV,herbicid,l,,,1,,,,,\n"
        "Malo 2 CSV,semilla,bolsa,,,30,,,,,soja\n"
        "Malo 3 CSV,repuesto,unidad,,,10,filtro,,,,\n"
        "Malo 4 CSV,repuesto,unidad,,,10,cubierta,Pirelli,,,\n"
        "Malo 5 CSV,herbicida,l,,,abc,,,,,\n"
        "Bueno CSV,herbicida,l,,,1,,,,,\n"
        "Malo 6 CSV,semilla,bolsa,,,30,,,,40,cebolla\n"
    )
    with pytest.raises(CatalogoInvalido) as e:
        importar(admin_tx, filas, aplicar=True)
    texto = "\n".join(e.value.errores)
    for esperado in ("línea 3: categoría", "línea 4: una semilla necesita kg_por_bolsa", "línea 5: un repuesto necesita modelo",
                     "línea 6: el rodado", "línea 7: precio_usd no es un número", "línea 8: 'Bueno CSV' está repetido",
                     "línea 9: cultivo 'cebolla' desconocido"):
        assert esperado in texto, esperado
    assert uno(admin_tx, "select count(*) from catalogo_producto where nombre like '%% CSV'") == 0


def test_acepta_el_csv_de_excel_con_punto_y_coma(admin_tx, csv_tmp):
    res = importar(admin_tx, csv_tmp("Excel CSV,herbicida,l,,,7,,,,,\n", separador=";"), aplicar=True)
    assert res.agregados == ["Excel CSV"]


def test_faltan_columnas(admin_tx, csv_tmp):
    with pytest.raises(CatalogoInvalido, match="faltan columnas"):
        importar(admin_tx, csv_tmp("X,herbicida,l\n", encabezado="nombre,categoria,unidad\n"), aplicar=True)


def test_el_archivo_del_repo_es_valido(admin_tx):
    import pathlib
    ruta = pathlib.Path(__file__).resolve().parents[3] / "supabase" / "catalogo" / "catalogo_base.csv"
    importar(admin_tx, leer_csv(ruta), aplicar=False)
