"""Importa el catálogo base de productos desde un CSV (RN-30, RF-36).

Uso (desde la carpeta backend):
    python -m micampo.catalogo ../supabase/catalogo/catalogo_base.csv            # solo muestra qué cambiaría
    python -m micampo.catalogo ../supabase/catalogo/catalogo_base.csv --aplicar  # lo carga

La conexión sale de DATABASE_ADMIN_URL (por defecto, el Supabase local). Hace falta un usuario
administrador, porque el backend (micampo_app) solo puede leer el catálogo.

Reglas:
  * Valida el archivo completo antes de escribir; si una fila está mal, no se carga ninguna.
  * Busca cada producto por nombre: si existe lo actualiza, si no lo agrega.
  * Nunca borra: un producto que ya no está en la lista se marca como inactivo (puede estar en uso).
  * Todo ocurre en una sola transacción.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

import psycopg

COLUMNAS = ["nombre", "categoria", "unidad", "principio_activo", "concentracion", "precio_usd",
            "tipo_repuesto", "modelo", "rodado", "kg_por_bolsa", "cultivo"]
CATEGORIAS = {"herbicida", "insecticida", "fungicida", "coadyuvante", "fertilizante", "semilla", "repuesto", "otro"}
UNIDADES = {"l", "kg", "bolsa", "unidad"}
TIPOS_REPUESTO = {"cubierta", "filtro", "correa", "otro"}
URL_LOCAL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"


class CatalogoInvalido(Exception):
    def __init__(self, errores: list[str]):
        super().__init__("\n".join(errores))
        self.errores = errores


@dataclass
class Resultado:
    agregados: list[str] = field(default_factory=list)
    actualizados: list[str] = field(default_factory=list)
    sin_cambios: list[str] = field(default_factory=list)
    desactivados: list[str] = field(default_factory=list)


def _clave(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto.strip().lower())
    return " ".join("".join(c for c in texto if not unicodedata.combining(c)).split())


def _decimal(valor: str, columna: str, linea: int, errores: list[str]) -> Decimal | None:
    valor = valor.strip()
    if not valor:
        return None
    try:
        numero = Decimal(valor.replace(",", "."))
    except InvalidOperation:
        errores.append(f"línea {linea}: {columna} no es un número ('{valor}')")
        return None
    if numero < 0:
        errores.append(f"línea {linea}: {columna} no puede ser negativo")
    return numero


def leer_csv(ruta: Path) -> list[dict]:
    # utf-8-sig: acepta el CSV que guarda Excel. Acepta coma o punto y coma como separador.
    texto = ruta.read_text(encoding="utf-8-sig")
    dialecto = csv.Sniffer().sniff(texto.splitlines()[0], delimiters=",;") if texto.strip() else csv.excel
    filas = list(csv.DictReader(texto.splitlines(), dialect=dialecto))
    return filas


def validar(filas: list[dict], cultivos: dict[str, str]) -> list[dict]:
    """Devuelve las filas listas para cargar o lanza CatalogoInvalido con todos los errores juntos."""
    errores: list[str] = []
    if filas:
        faltan = [c for c in COLUMNAS if c not in filas[0]]
        if faltan:
            raise CatalogoInvalido([f"faltan columnas: {', '.join(faltan)}"])
    limpias, vistos = [], {}
    for i, fila in enumerate(filas, start=2):  # la línea 1 es el encabezado
        f = {c: (fila.get(c) or "").strip() for c in COLUMNAS}
        if not any(f.values()):
            continue
        nombre, categoria, unidad = f["nombre"], f["categoria"].lower(), f["unidad"].lower()
        tipo = f["tipo_repuesto"].lower()
        if not nombre:
            errores.append(f"línea {i}: falta el nombre")
        elif _clave(nombre) in vistos:
            errores.append(f"línea {i}: '{nombre}' está repetido (ya aparece en la línea {vistos[_clave(nombre)]})")
        else:
            vistos[_clave(nombre)] = i
        if categoria not in CATEGORIAS:
            errores.append(f"línea {i}: categoría '{f['categoria']}' inválida (válidas: {', '.join(sorted(CATEGORIAS))})")
        if unidad not in UNIDADES:
            errores.append(f"línea {i}: unidad '{f['unidad']}' inválida (válidas: {', '.join(sorted(UNIDADES))})")
        if (categoria == "semilla") != (unidad == "bolsa"):
            errores.append(f"línea {i}: las semillas van en 'bolsa' y solo las semillas")
        if (categoria == "repuesto") != (unidad == "unidad"):
            errores.append(f"línea {i}: los repuestos van en 'unidad' y solo los repuestos")
        precio = _decimal(f["precio_usd"], "precio_usd", i, errores)
        kg = _decimal(f["kg_por_bolsa"], "kg_por_bolsa", i, errores)
        cultivo_id = None
        if categoria == "semilla":
            if kg is None or kg == 0:
                errores.append(f"línea {i}: una semilla necesita kg_por_bolsa")
            cultivo_id = cultivos.get(_clave(f["cultivo"]))
            if cultivo_id is None:
                errores.append(f"línea {i}: cultivo '{f['cultivo']}' desconocido (válidos: {', '.join(sorted(cultivos))})")
        elif kg is not None or f["cultivo"]:
            errores.append(f"línea {i}: kg_por_bolsa y cultivo son solo para semillas")
        if categoria == "repuesto":
            if tipo not in TIPOS_REPUESTO:
                errores.append(f"línea {i}: tipo_repuesto '{f['tipo_repuesto']}' inválido (válidos: {', '.join(sorted(TIPOS_REPUESTO))})")
            if not f["modelo"]:
                errores.append(f"línea {i}: un repuesto necesita modelo")
            if (tipo == "cubierta") != bool(f["rodado"]):
                errores.append(f"línea {i}: el rodado va solo en las cubiertas, y toda cubierta lo lleva")
        elif tipo or f["rodado"]:
            errores.append(f"línea {i}: tipo_repuesto y rodado son solo para repuestos")
        limpias.append({
            "nombre": " ".join(nombre.split()), "categoria": categoria, "unidad": unidad,
            "principio_activo": f["principio_activo"] or None, "concentracion": f["concentracion"] or None,
            "precio_referencia_usd": precio, "tipo_repuesto": tipo or None, "modelo": f["modelo"] or None,
            "rodado": f["rodado"] or None, "kg_por_bolsa": kg if categoria == "semilla" else None,
            "cultivo_id": cultivo_id,
        })
    if errores:
        raise CatalogoInvalido(errores)
    return limpias


CAMPOS = ["categoria", "unidad", "principio_activo", "concentracion", "precio_referencia_usd",
          "tipo_repuesto", "modelo", "rodado", "kg_por_bolsa", "cultivo_id"]


def importar(conn: psycopg.Connection, filas: list[dict], aplicar: bool) -> Resultado:
    """Carga las filas en una transacción. Si aplicar es False, la revierte y solo informa."""
    res = Resultado()
    cultivos = {_clave(n): i for i, n in conn.execute("select id, nombre from cultivo").fetchall()}
    limpias = validar(filas, cultivos)
    with conn.transaction() as tx:
        existentes = {_clave(r[0]): r for r in conn.execute(
            f"select nombre, activo, id, {', '.join(CAMPOS)} from catalogo_producto").fetchall()}
        en_lista = set()
        for f in limpias:
            clave = _clave(f["nombre"])
            en_lista.add(clave)
            actual = existentes.get(clave)
            valores = [f[c] for c in CAMPOS]
            if actual is None:
                conn.execute(
                    f"insert into catalogo_producto (nombre, {', '.join(CAMPOS)}) values (%s, {', '.join(['%s'] * len(CAMPOS))})",
                    [f["nombre"], *valores])
                res.agregados.append(f["nombre"])
            elif list(actual[3:]) != valores or not actual[1] or actual[0] != f["nombre"]:
                conn.execute(
                    f"update catalogo_producto set nombre = %s, activo = true, {', '.join(c + ' = %s' for c in CAMPOS)} where id = %s",
                    [f["nombre"], *valores, actual[2]])
                res.actualizados.append(f["nombre"])
            else:
                res.sin_cambios.append(f["nombre"])
        for clave, actual in existentes.items():
            if clave not in en_lista and actual[1]:
                conn.execute("update catalogo_producto set activo = false where id = %s", (actual[2],))
                res.desactivados.append(actual[0])
        if not aplicar:
            raise psycopg.Rollback(tx)
    return res


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Importa el catálogo base de productos desde un CSV.")
    parser.add_argument("csv", type=Path)
    parser.add_argument("--aplicar", action="store_true", help="cargar los cambios (sin esto, solo los muestra)")
    parser.add_argument("--url", default=os.environ.get("DATABASE_ADMIN_URL", URL_LOCAL))
    args = parser.parse_args(argv)
    try:
        with psycopg.connect(args.url) as conn:
            res = importar(conn, leer_csv(args.csv), args.aplicar)
    except CatalogoInvalido as e:
        print("El catálogo tiene errores; no se cargó nada:", file=sys.stderr)
        for error in e.errores:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(f"Agregados: {len(res.agregados)}  Actualizados: {len(res.actualizados)}  "
          f"Sin cambios: {len(res.sin_cambios)}  Desactivados: {len(res.desactivados)}")
    for titulo, lista in (("Agregados", res.agregados), ("Actualizados", res.actualizados), ("Desactivados", res.desactivados)):
        for nombre in lista:
            print(f"  {titulo[:-1].lower()}: {nombre}")
    if not args.aplicar:
        print("\nNo se cargó nada. Para cargarlo, repetí el comando con --aplicar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
