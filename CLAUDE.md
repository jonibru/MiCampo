# Mi Campo: instrucciones para Claude

Software de gestión agropecuaria con un bot de WhatsApp (audios) y un panel web. La especificación completa es el Google Doc "MiC - Documento de Diseño" (https://docs.google.com/document/d/1aVzFFHTz8UpFb6uz9HPc7R_-zppUurh4wddaSe1antg). Sus requisitos se citan por ID (RN, RF, RB, RNF, HU). Si existe una copia en `docs/diseno.md`, es solo de lectura y, ante cualquier diferencia, manda el Google Doc.

## Principios

El producto tiene que ser, antes que nada, **fácil de usar** y **consistente y confiable**. Cada decisión se juzga con esas dos preguntas: ¿esto le simplifica la vida a quien carga datos en el campo?, ¿esto puede dar un resultado distinto o incorrecto según el día? Cada paso o configuración extra tiene que justificarse.

- **Todo se testea.** Ningún cambio está terminado sin tests que pasen: los criterios de aceptación de las historias de usuario (HU-xx) son casos de prueba, y los cambios de seguridad llevan tests de aislamiento entre establecimientos.
- **Lo que choca con el diseño se consulta antes.** Si algo que se pide, o que surge al implementar, contradice el documento de diseño o sus decisiones registradas, no se resuelve por cuenta propia ni se avanza: se frena y se consulta.
- **Las mejoras se sugieren, no se aplican.** Una idea que no está en el diseño se propone con su motivo y se espera la respuesta. No se agrega por considerarla mejor.
- **Las decisiones de negocio ambiguas** (por ejemplo las "Notas a tener en cuenta" del documento) las toma el equipo.

## Al iniciar una sesión o tarea

Preguntar primero cómo quiere trabajar la persona, con tres opciones:

1. **En pasos explicados en criollo:** cada paso con qué se hace y por qué, sin jerga.
2. **En pasos técnicos:** cada paso con el detalle técnico, sin explicar lo básico.
3. **Directamente:** hacerlo completo y contar al final qué se hizo.

Respetar la elección durante toda la tarea, salvo que la persona la cambie.

## Stack

Python con FastAPI (API y worker del bot, mismo código), PostgreSQL en Supabase (RLS, Auth, Storage), panel PWA, WhatsApp Cloud API. Transcripción y modelo de lenguaje detrás de interfaces intercambiables. El canal de mensajería va detrás de un adaptador (WhatsApp es el único implementado).

## Estructura

- `supabase/migrations/`: esquema de la base, un archivo .sql por cambio.
- `backend/`: operaciones, API, bot, tests.
- `frontend/`: panel web.
- `docs/`: documentación.

## Reglas técnicas que no se negocian

**Datos**
- Todas las tablas llevan `id` (UUID) y fecha de creación. Las de un establecimiento llevan `establecimiento_id`. Las de cargas suman `creado_por`, `origen` (bot o panel), `mensaje_id` y marca de anulación (quién, cuándo, por qué).
- Importes en `NUMERIC`, nunca en float. Se guardan en US$, con el monto original en ARS, el tipo de cambio y su fuente (RN-01).
- Relaciones por id, nunca por nombre (RN-09).
- Nada se borra: se anula, se revierte el efecto en stock y costos y queda registro (RN-09, RF-13). No se borra un registro en uso (RN-07).
- El costo de cada carga se calcula y se guarda al cargarla; un cambio posterior de valores no altera costos pasados (RN-10).
- El stock es la suma de movimientos (`movimiento_stock`, `movimiento_grano`), no una columna. Puede quedar negativo: se permite, se avisa y se marca para revisar (RN-32).
- Un cambio de valores de referencia crea una fila nueva; no se pisa la anterior.

**Base de datos: convenciones ya implementadas (supabase/migrations)**
- Toda tabla de un establecimiento se protege al crearla con `select app.proteger_tabla('public.tabla', p_carga => ..., p_borrable => ...)`: RLS forzado, permisos mínimos para `micampo_app` y trigger de auditoría. No se escribe a mano.
- Las referencias entre tablas de un establecimiento usan clave compuesta `(establecimiento_id, id)`, para que nunca crucen de un establecimiento a otro.
- Las tablas de cargas llevan `creado_por`, `origen`, `mensaje_id` y anulación, con los valores por defecto tomados del contexto de la transacción. Toda tabla de cargas lleva además el trigger `app.reglas_carga` (no se cambia quién cargó, no se des-anula, el encargado solo corrige lo suyo).
- El backend solo hace DELETE donde se concedió de forma explícita (hoy, campos y lotes). Usuarios y membresías se crean con `app.crear_usuario`, `app.crear_establecimiento` y `app.invitar_encargado`.
- Toda migración que crea funciones en el esquema `app` termina con `revoke execute on all functions in schema app from public;` y concede a `micampo_app` solo lo necesario.
- `backend/tests/db` debe seguir en verde. `test_contrato.py` falla si una tabla nueva queda sin proteger.

**Operaciones**
- Cada carga es una sola transacción: completa o no se ejecuta (RNF-01).
- Idempotencia: el mismo id de mensaje de WhatsApp no genera dos cargas (RB-02).
- Toda escritura deja una fila en `auditoria` con valor anterior y nuevo.
- El panel web y el bot usan las mismas operaciones y validaciones.
- Fechas en `America/Argentina/Buenos_Aires`, guardadas como fecha local. La fecha de una carga sale de lo que dice el audio, no de la hora de llegada (RB-25).

**Seguridad (RNF-16)**
- Aislamiento por establecimiento con Row Level Security. Cada transacción fija `SET LOCAL app.establecimiento_id` y `app.usuario_id`; las políticas comparan con `current_setting`.
- El backend se conecta con un rol propio, sin permiso para saltear RLS (no `postgres` ni `service_role`). Las tablas usan `FORCE ROW LEVEL SECURITY`. La clave de servicio de Supabase es solo para tareas internas.
- Claves y tokens solo en variables de entorno. Verificar la firma de cada webhook de WhatsApp. Audios en almacenamiento privado, con enlaces temporales.

**Bot**
- El modelo de lenguaje nunca escribe en la base. Propone un borrador; el sistema lo valida con reglas fijas y lo ejecuta solo tras el "Sí" de la persona (RB-05, RB-07, RB-09).
- Un borrador en confirmación por vez por usuario; varios audios se encolan y se confirman de a uno (RB-22).
- Las consultas salen de un conjunto fijo con datos calculados por el sistema; el modelo solo elige la consulta y sus parámetros (RB-17).
- Permisos por rol en cada respuesta: el encargado no ve costos totales, márgenes, utilidad ni ventas (RB-18).
- El estado de la conversación vive en `mensaje_bot` y `evento_bot`, no en la memoria del modelo. Cada paso queda trazado.
- Respuestas cortas, en español rioplatense.

## Alcance por etapa

- **Piloto 1** (antes del 15/12/2026): todo menos cosecha y granos. Pero **todas las tablas se crean ya**, para que el piloto 2 solo sume operaciones y pantallas.
- **Piloto 2** (primera quincena de enero): cosecha, envíos, stock de granos, ventas, rinde y márgenes.
- **Opcional y después:** ver la sección 6 del documento de diseño. No implementar sin pedido.

## Git

`main` (producción, casi no se toca) ← `development` (integración) ← ramas de trabajo `area/descripcion` (`backend/`, `frontend/`, `database/`, `fix/`). Todo pasa por `development`; nada va directo a `main`. Rama propia solo para trabajo con peso (un módulo con sus tests, una pantalla, el bot), que entra por pull request; lo que no es código (docs, README, copia del diseño, catálogo CSV) va directo a `development`. No crear ramas para uno o dos commits. Una migración ya mergeada no se edita: se crea una nueva. Commits en español, citando el ID del requisito cuando corresponda.
