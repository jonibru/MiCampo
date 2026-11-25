# Mi Campo

Software de gestión para productores agropecuarios. Registra lotes, labores, insumos, cosecha, stock de granos y ventas, y calcula costos y márgenes por lote.

La carga y las consultas se hacen principalmente por un **bot de WhatsApp que entiende audios**. El panel web sirve para consultar, corregir y cargar a mano.

## Cómo funciona

1. La persona manda un audio o texto al bot ("Hoy pulvericé el lote 3 con 2 litros de glifosato por hectárea").
2. El bot transcribe, un modelo de lenguaje arma un **borrador** y el sistema lo valida con reglas fijas.
3. El bot repite lo entendido y pide confirmación (Sí / Corregir / Cancelar).
4. Solo tras el "Sí" se ejecuta la carga, en una única transacción de base de datos.

El modelo de lenguaje nunca escribe en la base: propone, el sistema valida y ejecuta. El panel web usa las mismas operaciones que el bot.

## Herramientas

| Pieza | Tecnología |
|---|---|
| Backend (API y worker del bot) | Python, FastAPI |
| Base de datos, cuentas y audios | Supabase (PostgreSQL con Row Level Security, Auth, Storage) |
| Panel web | PWA instalable, pensada primero para el celular |
| Canal del bot | WhatsApp Cloud API (Meta) |
| Transcripción y modelo de lenguaje | Proveedores intercambiables |

## Estructura del repo

```
supabase/migrations/   Esquema de la base (archivos .sql versionados)
backend/               API, operaciones, bot y tests
frontend/              Panel web (PWA)
docs/                  Documentación
```

El diseño completo está en el Google Doc "MiC - Documento de Diseño". Los requisitos se citan por ID (RN-10, RF-19, RB-05).

## Primeros pasos: instalar y clonar

**Instalar** es tener en tu computadora los programas con los que se trabaja:

- [Git](https://git-scm.com): guarda el historial del código y lo sincroniza con GitHub.
- [Python 3.12 o superior](https://www.python.org): para correr el backend.
- [Docker Desktop](https://www.docker.com/products/docker-desktop): para correr la base de datos local.
- [Supabase CLI](https://supabase.com/docs/guides/local-development): maneja la base local y las migraciones.
- Una cuenta de GitHub con acceso al repo (pedíselo a quien lo administra).

**Clonar** es bajar una copia completa del repo a tu computadora, conectada con GitHub para poder traer y subir cambios. Se hace una sola vez:

```bash
git clone https://github.com/jonibru/micampo.git
cd micampo
git switch development
```

Para levantar la base local (con Docker abierto):

```bash
supabase start        # Postgres, Auth y Storage locales
supabase db reset     # aplica todas las migraciones desde cero
```

La configuración local de Supabase (`supabase/config.jsonc`) ya está en el repo: no hace falta correr `supabase init`. Los tests de la base están explicados en `backend/README.md`.

## Cómo trabajamos con git

```
main  <──  development  <──  ramas de trabajo (una por tarea)
```

- **main:** producción. Casi no se toca; solo recibe `development` cuando hay algo probado.
- **development:** integración y prueba. Todo lo nuevo llega primero acá.
- **Ramas de trabajo:** una por tarea, siempre salen de `development`, con nombre `area/descripcion`:

| Prefijo | Para qué | Ejemplo |
|---|---|---|
| `backend/` | API, operaciones, bot | `backend/modulo-productos` |
| `frontend/` | Panel web | `frontend/formulario-labores` |
| `database/` | Migraciones y RLS | `database/tablas-acceso` |
| `docs/` | Documentación | `docs/readme` |
| `fix/` | Corrección de un error | `fix/precio-promedio` |

Nadie hace commit directo en `main` ni en `development`: todo entra con pull request.

### Paso a paso para una tarea

```bash
git switch development && git pull        # 1. traer lo último
git switch -c backend/modulo-productos    # 2. crear tu rama
git add archivo.py                        # 3. elegir qué guardar
git commit -m "Agrega alta de producto (RF-03)"   # 4. guardar (commit)
git push -u origin backend/modulo-productos       # 5. subir a GitHub
```

6. En GitHub, abrí un **pull request** (botón "Compare & pull request") con **base `development`** y pedí revisión a otra persona.
7. Con la aprobación y los tests en verde, se hace merge y se borra la rama. Para la próxima tarea, volvé al paso 1.

Para publicar, se abre un pull request de `development` a `main`.

### Reglas prácticas

- Una rama, una tarea. Si se alarga, dividila.
- Si tardás más de un día, traé los cambios nuevos: `git merge development` estando en tu rama.
- Ante un conflicto (git marca `<<<<<<<` en el archivo), dejá la versión correcta, borrá las marcas y hacé `git add` y `git commit`. Si dudás, preguntá.
- Commits en español y en presente, con el ID del requisito si corresponde.
- Una migración ya mergeada a `development` no se edita: se crea otra nueva.
- Claves y tokens van en `.env` (git lo ignora), nunca en el código.

¿Querés más? Buscá "git flow para principiantes" o la guía oficial en [git-scm.com/book/es](https://git-scm.com/book/es).

## Estado

Piloto 1 (todo menos cosecha y granos): antes del 15 de diciembre de 2026. Piloto 2 (cosecha, envíos, ventas y márgenes): primera quincena de enero.
