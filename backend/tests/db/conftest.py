"""Fixtures de los tests de base de datos.

Cada sesión de tests crea una base de datos vacía y descartable, le aplica las migraciones
de supabase/migrations y la borra al final. No toca los datos de tu Supabase local ni de la nube.

Variables de entorno:
  TEST_ADMIN_URL  conexión con un usuario administrador (por defecto, el Supabase local:
                  postgresql://postgres:postgres@127.0.0.1:54322/postgres)
"""
import os
import pathlib
import uuid

import psycopg
import pytest
from helpers import crear_establecimiento
from psycopg.conninfo import conninfo_to_dict, make_conninfo

RAIZ = pathlib.Path(__file__).resolve().parents[3]
MIGRACIONES = sorted((RAIZ / "supabase" / "migrations").glob("*.sql"))
STUB = pathlib.Path(__file__).with_name("stub_supabase.sql")
ADMIN_URL = os.environ.get("TEST_ADMIN_URL", "postgresql://postgres:postgres@127.0.0.1:54322/postgres")
PASSWORD_APP = "micampo_local"  # la misma que supabase/seed.sql, para no cambiar la de tu entorno local


def _conninfo(dbname: str, user: str | None = None, password: str | None = None) -> str:
    datos = conninfo_to_dict(ADMIN_URL)
    datos["dbname"] = dbname
    if user:
        datos["user"] = user
        datos["password"] = password
    return make_conninfo(**datos)


@pytest.fixture(scope="session")
def base_de_prueba():
    nombre = f"micampo_test_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(_conninfo(conninfo_to_dict(ADMIN_URL).get("dbname", "postgres")), autocommit=True) as c:
        c.execute(f'create database "{nombre}"')
    with psycopg.connect(_conninfo(nombre), autocommit=True) as admin:
        admin.execute(STUB.read_text(encoding="utf-8"))
        for archivo in MIGRACIONES:
            admin.execute(archivo.read_text(encoding="utf-8"))
        admin.execute(f"alter role micampo_app login password '{PASSWORD_APP}'")
    yield nombre
    with psycopg.connect(_conninfo(conninfo_to_dict(ADMIN_URL).get("dbname", "postgres")), autocommit=True) as c:
        c.execute(f'drop database "{nombre}" with (force)')


@pytest.fixture(scope="session")
def admin(base_de_prueba):
    """Conexión administradora (saltea RLS). Solo para preparar datos y mirar el catálogo."""
    with psycopg.connect(_conninfo(base_de_prueba), autocommit=True) as c:
        yield c


@pytest.fixture
def app(base_de_prueba):
    """Conexión como el backend (rol micampo_app). Cada test corre en una transacción que se revierte."""
    with psycopg.connect(_conninfo(base_de_prueba, "micampo_app", PASSWORD_APP)) as c:
        yield c
        c.rollback()


@pytest.fixture(scope="session")
def mundo(admin):
    """Dos establecimientos completos e independientes: A y B."""
    return {"A": crear_establecimiento(admin, "A"), "B": crear_establecimiento(admin, "B")}
