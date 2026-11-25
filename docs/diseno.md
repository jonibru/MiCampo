> **Copia de solo lectura.** La fuente de verdad es el Google Doc [MiC - Documento de Diseño](https://docs.google.com/document/d/1aVzFFHTz8UpFb6uz9HPc7R_-zppUurh4wddaSe1antg). Copia exportada el 25 de noviembre de 2026, después de sumar la unidad de repuestos y las categorías de producto. No se edita acá: los cambios se hacen en el Doc y esta copia se vuelve a exportar (File → Download → Markdown).

# **Mi Campo: documento de diseño**

Nov 17, 2026 · @Jonathan

El documento tiene tres partes: **Producto** (qué hace el sistema), **Técnico** (cómo se construye) y **Decisiones y pendientes** (lo decidido, con el porqué, y lo que sigue abierto).

# **Parte 1: Producto**

## **1\. Resumen y alcance**

Mi Campo se rearma desde cero sobre PostgreSQL con un backend propio. Casi toda la carga y las consultas se hacen por un bot de WhatsApp que entiende audios; el panel web sirve para consultar, corregir y también cargar a mano.

**Objetivo.** Una app de gestión agrícola comercializable que registre lotes, labores, insumos, cosecha, stock de granos y ventas, y que calcule costos y márgenes por lote. No registra caja ni pagos: un costo cuenta cuando se carga. La producción no vendida se valúa al precio de referencia vigente y la vendida, a su precio de venta.

**Decisiones tomadas**

| Tema | Decisión | Estado |
| :---- | :---- | :---- |
| Base de datos | PostgreSQL gestionado en Supabase (alternativas: Neon, Render, Railway, DigitalOcean, Fly.io) | Decidido |
| Backend | Python (FastAPI) en un servicio siempre activo; US\$5-10 por mes es aceptable | Decidido |
| App en el celular | PWA instalable desde el navegador, diseñada primero para el celular; Play Store más adelante si hace falta | Decidido |
| Orden de construcción | Modelo de datos → operaciones del sistema → panel web → bot; los audios de prueba se graban en paralelo | Decidido |
| Datos actuales | Se empieza de cero; no se migra Firestore | Decidido |
| Bot | Vía principal (cerca del 100 %) para cargar y consultar; confirma una carga por vez | Decidido |
| Panel web | Consulta, corrección y carga manual | Decidido |
| Offline | No hace falta, porque el bot ya requiere internet | Decidido |
| Roles | Dueño (todo) y encargado (carga, consulta cargas y ve precios de referencia, pero no costos totales, márgenes ni ventas); un establecimiento por usuario en el piloto | Decidido |
| Cosecha y granos | La cosecha registra solo los kilos producidos; el stock de granos (bolsón y acopios), los envíos y las ventas van aparte | Decidido |
| Campaña | Grano más año agrícola de la siembra (mayo a abril), por ejemplo Soja 2026/27 | Decidido |
| Fiabilidad | Cada carga es una transacción completa; el bot debe tolerar audios imperfectos | Decidido |
| Piloto | Con productores desde la siembra de soja (antes del 15 de diciembre); cosecha y granos en una segunda entrega | Decidido |
| Escala | Hasta 20 usuarios a corto y mediano plazo; el diseño debe poder crecer a cientos o miles | Decidido |

**Principio de diseño: valor de referencia, ajuste por carga.** Los valores de referencia (servicio de cada labor, precio de los granos, flete, embolsado) se cargan una vez y después se usan solos. El usuario los cambia cuando quiere o dice el valor real en una carga puntual. Así la carga por audio es corta y la precisión queda a elección de cada usuario (sección 3). Regla general: lo más simple y práctico posible; cada configuración o paso extra tiene que justificarse, porque aleja al usuario.

**Cómo leer este documento.** Cada requisito indica su origen: **App** (ya existe), **Notas** (relevamiento o tus definiciones) o **Propuesta** (sugerido, a validar). La columna Etapa indica cuándo entra: **Piloto 1** (siembra, antes del 15 de diciembre), **Piloto 2** (cosecha y granos), **Opcional** (si hay tiempo) o **Después**. Los IDs no se renumeran al editar, para no romper referencias.

## **2\. Actores y roles**

Hay dos roles de usuario: el dueño hace todo; el encargado carga datos, consulta las cargas y ve precios de referencia, pero no ve costos totales, márgenes, utilidad ni ventas. Las reglas finas se definen más adelante. En el piloto, cada usuario tiene un solo establecimiento.

| Actor | Qué puede hacer | Cómo accede | Origen |
| :---- | :---- | :---- | :---- |
| Dueño | Carga, consulta, corrige y anula datos; ve stock, costos, márgenes y ventas; configura valores de referencia; da de alta y de baja encargados; reabre ciclos cerrados | WhatsApp y panel web | App, Notas |
| Encargado | Carga cualquier dato, incluidos productos nuevos y cosechas; consulta cargas y stock; ve precios de referencia; corrige solo sus propias cargas y hace ajustes de stock; no ve costos totales por lote, márgenes, utilidad ni ventas | WhatsApp y panel web (sin costos totales ni ventas) | Notas |
| Bot de WhatsApp | Recibe el audio, propone la carga o responde la consulta, pide confirmación y ejecuta tras el "Sí" | Número de WhatsApp Business | Notas |
| Administrador de plataforma (vos) | Revisa las trazas del bot, mantiene el catálogo base con sus precios de referencia y mide la calidad; cada ingreso a los datos de un establecimiento queda registrado | Vista de administración interna | Propuesta |

Los empleados (mensuales o temporales) son datos que se cargan, no usuarios del sistema.

**Reglas de acceso**

* Cada dato pertenece a un establecimiento; un usuario accede solo a los establecimientos en los que tiene un rol (en el piloto, uno).  
* El bot identifica a la persona por su número de teléfono registrado; un número desconocido no ejecuta cargas. Si el dueño da de baja un número, el acceso se corta en el momento.  
* Al encargado, el bot le responde consultas sobre cargas, stock y precios de referencia, pero no sobre costos totales, márgenes, utilidad ni ventas.  
* Toda carga guarda quién la hizo; el dueño ve el historial completo (RF-38).  
* Más adelante, una persona podrá ser dueña de un establecimiento y encargada en otro; el bot usará el último establecimiento con el que trabajó y lo mostrará en cada confirmación.  
* Acceso al panel con cuenta propia, requisitos de contraseña y pantalla separada para crear cuenta (Notas).

## **3\. Glosario y reglas de negocio**

Todos los valores de referencia siguen el mismo patrón: se cargan al dar de alta el establecimiento, se usan solos, y el usuario puede cambiarlos cuando quiera o decir el valor real en una carga.

### **Valores de referencia**

| Valor | Cuándo se pide | Cómo se cambia |
| :---- | :---- | :---- |
| Precio del servicio por tipo de labor (US\$/ha) | Al dar de alta el establecimiento | Cuando el dueño quiera, o diciendo el costo real en la carga |
| Precio de pulverización por equipo: mosquito, dron, avión (US\$/ha) | Al dar de alta el establecimiento | Igual |
| Pago por hora y horas por día de temporales | Al dar de alta el establecimiento | Diciendo los valores reales de esa carpida |
| Precio de referencia de cada grano (US\$/t) | Al dar de alta, y aviso al dueño al arrancar la cosecha de cada grano en cada campaña | Cuando el dueño quiera |
| Flete (US\$ por camión) | Igual que el precio del grano | Diciendo otro valor en el envío |
| Costo de embolsar (US\$/t) | Igual que el precio del grano | Diciendo otro valor al embolsar |
| Precio de un producto | Lo trae el catálogo base; si no está, lo carga el usuario o queda pendiente para el dueño | Diciendo el precio en una compra |
| Peso promedio por bolsa de semilla | Al agregar la semilla | — |
| Tipo de cambio | Dólar divisa (mayorista), automático 2 veces por día | Cargándolo a mano |

### **Reglas**

| ID | Tema | Regla | Origen | Estado |
| :---- | :---- | :---- | :---- | :---- |
| RN-01 | Moneda | Los importes se guardan en US\$, con el monto original en ARS, el tipo de cambio y su fuente (automático o manual) | App | Vigente |
| RN-02 | Ciclo | Cada lote tiene un ciclo por cultivo y un solo ciclo abierto a la vez. El ciclo empieza en preparación con la primera labor del lote (por ejemplo, un barbecho); si ya se sabe qué se va a sembrar, se puede indicar el cultivo desde ahí, y la siembra lo fija junto con la campaña. Si se carga la siembra de un cultivo nuevo con otro ciclo abierto, el bot pregunta si terminó la cosecha anterior y lo cierra. El ciclo se cierra cuando el usuario avisa que terminó de cosechar y lo que se carga después va al ciclo siguiente. Una labor va al ciclo según su fecha; si ese ciclo está cerrado, el bot avisa y solo el dueño puede reabrirlo. Un ciclo cerrado no acepta labores, pero sí cosechas | Notas | Vigente |
| RN-03 | Productos | Al agregar un producto al establecimiento se cargan su unidad y su precio promedio (el del catálogo o el que diga el usuario). Los repuestos (cubiertas, filtros, correas) también son productos, identificados por su modelo; al usarse descuentan stock y su costo va a mantenimiento | Notas | Vigente |
| RN-04 | Productos | En las compras el precio es opcional: si se dice, el promedio se actualiza (ponderado); si no, se mantiene el vigente. Si el stock está en 0 o negativo al cargar la compra, el promedio pasa a ser el precio de esa compra. El promedio se calcula a partir de los movimientos de stock, que guardan su precio (ver Notas a tener en cuenta) | Notas, App | Vigente |
| RN-05 | Cosecha | Los kilos se cargan como se pesaron y pueden no coincidir con el destino. Si se carga la humedad, la merma (humedad base: soja 13,5; maíz 14,5; trigo 14; girasol 11; sorgo 15; cebada 12,5; algodón sin merma) es solo informativa | App, Notas | Vigente |
| RN-07 | Integridad | No se puede borrar un registro que esté en uso | App | Vigente |
| RN-08 | Envíos | Si se carga la carta de porte, se avisa cuando está duplicada | App | Vigente |
| RN-09 | Integridad | Relaciones por id, no por nombre; ninguna carga se borra: se anula (también una cosecha mal cargada), revierte su efecto en stock y costos, y queda registro de quién y cuándo | Propuesta | Vigente |
| RN-10 | Labores | El costo de cada carga (servicio, insumos, embolsado, flete, al valor del momento) se calcula y se guarda al cargarla; un cambio posterior de valores no altera costos pasados. Excepción: si un producto tenía el precio pendiente, cuando el dueño lo fija se recalculan solo las líneas que se cargaron sin precio, con registro en la auditoría; hasta entonces la carga se muestra con "costo incompleto" | Propuesta | Vigente |
| RN-11 | Labores | El costo operativo de una labor es el precio de referencia del servicio para ese tipo de labor × ha, sea propia o contratada; con "contraté servicio" se puede cargar el costo real. Toda pulverización tiene equipo: mosquito por defecto, o dron o avión solo si el usuario lo dice explícitamente; la confirmación siempre muestra el equipo. Una pulverización propia solo puede usar equipos que el establecimiento tiene (por defecto, solo mosquito); si no, el bot pregunta si fue contratada. El combustible no se calcula por ahora | Notas | Vigente |
| RN-12 | Lotes | Cada lote tiene ha limpias y ha de monte (las totales son la suma); labores, costos por ha, rinde y márgenes usan solo ha limpias. Cada ciclo guarda las ha limpias que tenía, para que un desmonte posterior no cambie márgenes pasados | Notas | Vigente |
| RN-13 | Productos | Las semillas se cuentan en bolsas con un peso promedio por bolsa. La dosis de siembra se carga en kg/ha (soja, trigo) o bolsas/ha (girasol, maíz) y el sistema convierte con ese peso | Notas | Vigente |
| RN-14 | Productos | La unidad (litros o kilos; bolsas para semillas; unidades para repuestos) se elige al crear el producto y todas sus cargas se hacen en esa unidad. Dos concentraciones del mismo principio activo son dos productos distintos. Categorías: herbicida, insecticida, fungicida, coadyuvante, fertilizante, semilla, repuesto u otro | Notas | Vigente |
| RN-15 | Costos del establecimiento | Sueldos, viáticos, mantenimiento (repuestos usados), fletes, desmontes y otros gastos son costos del establecimiento: no entran en el costo de una labor ni en el margen por lote | Notas | Vigente |
| RN-16 | Moneda | El tipo de cambio se descarga 2 veces por día y se usa el vigente a la fecha de la carga. Es el dólar divisa (mayorista), el mismo para todos los establecimientos | Notas | Vigente |
| RN-17 | Labores | Una carpida la hacen uno o más temporales pagados por hora: costo \= personas × días × horas por día × pago por hora; es costo de la labor y del lote | Notas | Vigente |
| RN-18 | Lotes | Un desmonte pasa ha de monte a limpias; su costo (\~US\$2000/ha) va solo al resultado del establecimiento, no al margen del lote | Notas | Vigente |
| RN-20 | Cosecha | La cosecha registra solo los kilos producidos por un ciclo, tal como se pesaron (humedad opcional), y a dónde fueron: al bolsón del grano o directo a un acopio. De ahí sale el rinde. Si va al bolsón, el costo de embolsar se suma al ciclo en ese momento | Notas | Vigente |
| RN-22 | Márgenes | Margen por ciclo \= producción × precio de referencia vigente − (insumos \+ costo operativo de labores \+ carpidas \+ embolsado), sobre las ha limpias del ciclo. El resultado del establecimiento suma las ventas reales y el stock no vendido a precio de referencia, y resta los costos de producción y los del establecimiento | Notas | Vigente |
| RN-23 | Granos | Cada grano tiene un precio de referencia en US\$/t (precio de venta de una tonelada) que el dueño actualiza cuando quiere | Notas | Vigente |
| RN-24 | Ingresos | Lo vendido vale su precio de venta bruto, sin descontar secado (ingreso real). Lo no vendido, en el bolsón o en un acopio, vale kg × el último precio de referencia vigente del grano, sin importar la campaña (ingreso proyectado), sin restar fletes futuros ni merma | Notas | Vigente |
| RN-25 | Costos | Un costo cuenta cuando se carga, sin importar si está pagado: no se modelan caja, cheques ni cuentas corrientes | Notas | Vigente |
| RN-27 | Envíos | Cada envío lleva una cantidad de camiones (1 por defecto); su flete (US\$ por camión) se cuenta como costo del establecimiento en el momento del envío. Los datos del camión (patente, carta de porte, kilos brutos y tara) son opcionales | Notas | Vigente |
| RN-29 | Valores de referencia | Se cargan al dar de alta el establecimiento. Cuando arranca la cosecha de un grano en una campaña, el dueño recibe un aviso para actualizar precio del grano, flete y embolsado. Después se usan solos; el dueño los cambia cuando quiere y cualquier usuario puede reemplazarlos en una carga | Notas | Vigente |
| RN-30 | Productos | Hay un catálogo base de productos con precios de referencia, cargado y actualizado por el administrador a partir de una lista de una persona del rubro. El usuario elige de ahí; si el producto no está, lo crea, y si no sabe el precio, queda pendiente para el dueño | Notas | Vigente |
| RN-31 | Campaña | Una campaña es un grano más el año agrícola de su siembra, de mayo a abril (por ej., Soja 2026/27). Se arma sola: el ciclo toma su campaña al cargar la siembra, y el dueño puede pasarlo a otra a mano | Notas, Propuesta | Vigente |
| RN-32 | Stock | Si una carga deja stock negativo (de productos o de granos), se permite, se avisa y queda marcada para revisar. Lo mismo al anular una carga cuyo efecto ya se usó | Notas | Vigente |
| RN-33 | Stock de granos | El stock de granos está en el bolsón (uno por grano, sin importar lote ni variedad) o en un acopio, sin vender o vendido. Se mueve con la cosecha (entra), el envío (del bolsón a un acopio) y la venta (pasa a vendido, con precio, por todo o una parte, desde un acopio o directo desde el bolsón). Si el acopio liquida algo distinto, no se ajusta: vale lo que el usuario dice que vendió. Cualquier salida de grano que no es una venta (merma real, consumo propio, pérdidas en el bolsón u otras) se carga como ajuste de stock: kilos, fecha, de dónde sale y un motivo opcional, sin precio; no cuenta como ingreso. En la venta lo central son las toneladas: el precio es bruto y los costos (flete) quedan asentados en plata | Notas | Vigente |

Se eliminaron RN-06 (venta directa), RN-19 (consumo de combustible), RN-21 y RN-26 (reemplazadas por RN-33 y RN-22) y RN-28 (embolsado, ahora en RN-20).

### **Glosario**

* **Ciclo:** período de un lote con un solo cultivo; empieza en preparación con la primera labor y termina con su cosecha.  
* **Campaña:** grano más año agrícola de la siembra (mayo a abril); agrupa los ciclos de ese grano.  
* **Valor de referencia:** costo o precio que se carga una vez y se usa solo hasta que alguien lo cambie.  
* **Catálogo base:** lista de productos con precios de referencia, precargada para todos los establecimientos.  
* **Lote:** parcela de un campo; tiene ha limpias (productivas) y ha de monte.  
* **Labor:** trabajo sobre un lote (siembra, pulverización, carpida, cosecha) con insumos y costo.  
* **Costo operativo:** precio de referencia del servicio para esa labor, o el costo real si se contrató.  
* **Carpida:** labor de desmalezado manual hecha por temporales pagados por hora.  
* **Costos del establecimiento:** gastos que no son de un lote (sueldos, viáticos, mantenimiento, fletes, desmontes, otros).  
* **Producción:** kilos cosechados por un ciclo; de ahí sale el rinde.  
* **Stock de granos:** kilos de cada grano en el bolsón o en cada acopio, sin vender o vendidos.  
* **Bolsón:** stock de un grano guardado en silo bolsa en el campo; hay uno por grano.  
* **Envío:** traslado de grano del bolsón a un acopio, en uno o más camiones.  
* **Venta:** fijar precio a kilos de un grano; pasan a vendidos.  
* **Ingreso real / proyectado:** lo vendido / lo no vendido, a precio de referencia vigente.  
* **Flete:** costo por camión de un envío; va a los costos del establecimiento.  
* **Encargado:** usuario que carga datos y consulta cargas, sin ver costos totales, márgenes ni ventas.  
* **Carta de porte:** documento de traslado de granos.  
* **Merma por humedad:** descuento de peso según la humedad base del grano; acá es solo informativo.  
* **Anulación:** marca una carga como anulada sin borrarla y revierte su efecto.

## **4\. Requisitos funcionales por módulo**

Cada carga que acepta el bot también se puede hacer en el panel web, con las mismas validaciones; los formularios se hacen por prioridad (labores, compras y lluvias primero). La columna Etapa sigue el plan de la sección 6\.

| ID | Módulo | Requisito | Origen | Etapa |
| :---- | :---- | :---- | :---- | :---- |
| RF-01 | Campos y lotes | Crear, editar y listar campos y lotes con ha limpias y ha de monte (las totales son la suma) | App, Notas | Piloto 1 |
| RF-02 | Campos y lotes | Registrar un desmonte: pasa ha de monte a limpias y carga su costo al establecimiento | Notas | Piloto 1 |
| RF-03 | Productos y stock | Agregar un producto al establecimiento (del catálogo o propio) con categoría, unidad (litros, kilos, bolsas o unidades) y precio promedio; si no se sabe el precio, queda pendiente para el dueño | Notas | Piloto 1 |
| RF-04 | Productos y stock | Registrar la compra de un producto existente: suma stock, usa el precio si se dice y, si no, el promedio; si el producto no existe, ofrece agregarlo primero | Notas | Piloto 1 |
| RF-05 | Productos y stock | Recalcular el precio promedio con cada compra que trae precio | App, Notas | Piloto 1 |
| RF-06 | Productos y stock | Cargar semillas por cultivo y variedad, en bolsas con peso promedio por bolsa | Notas | Piloto 1 |
| RF-07 | Productos y stock | Tratar cada concentración de un principio activo como un producto distinto | Notas | Piloto 1 |
| RF-08 | Labores | Registrar labores por lote con fecha, tipo, insumos y ha trabajadas (como máximo las ha limpias); la labor va al ciclo según su fecha | App, Notas | Piloto 1 |
| RF-09 | Labores | Descontar del stock los insumos usados (convirtiendo kg/ha a bolsas en semillas) y guardar el costo total y por ha | App, Notas | Piloto 1 |
| RF-10 | Labores | Costear la labor con el precio de referencia del servicio; con "contraté servicio" marcado, permitir cargar el costo real; en pulverización, mosquito por defecto, o dron o avión si el usuario lo indica | Notas | Piloto 1 |
| RF-13 | Integridad | Anular cualquier carga en vez de borrarla, revirtiendo su efecto en stock y costos | Propuesta | Piloto 1 |
| RF-14 | Envíos | Registrar envíos del bolsón a un acopio con grano, kilos y cantidad de camiones (1 por defecto); el flete se suma a los costos del establecimiento. Patente, carta de porte, kilos brutos y tara son opcionales | App, Notas | Piloto 2 |
| RF-15 | Envíos | Si se carga la carta de porte, avisar cuando ya existe | App | Piloto 2 |
| RF-16 | Ventas | Registrar ventas de granos en toneladas, desde un acopio o directo desde el bolsón, por todo o una parte, con el precio de venta bruto por tonelada, la humedad (opcional) y, si sale del bolsón, los camiones y su flete. Lo principal es la cantidad vendida; el descuento por secado, que varía por acopio, no se calcula por ahora | App, Notas | Piloto 2 |
| RF-17 | Rinde y márgenes | Calcular rinde y margen por ciclo (producción × precio de referencia vigente − costos de producción) y el resultado del establecimiento (ventas reales \+ stock a precio de referencia − costos de producción y del establecimiento) | App, Notas | Piloto 2 |
| RF-18 | Rinde y márgenes | Resumen por lote y ciclo: toneladas cosechadas, rinde (kg/ha), costos, ingreso proyectado y margen, con gráficos | Notas | Piloto 2 |
| RF-19 | Repuestos | Repuestos (cubiertas, filtros, correas) como productos con su modelo; las compras suman stock y el uso ("cambié 2 filtros") lo descuenta como movimiento de stock con su costo, que suma a mantenimiento; se consulta el stock por modelo. Por ahora no se asigna a una máquina (va con el módulo de maquinaria) | Notas | Piloto 1 |
| RF-20 | Costos del establecimiento | Dar de alta empleados con sueldo mensual y cargar viáticos mensuales y otros gastos | Notas | Opcional |
| RF-21 | Tipo de cambio | Actualizar el tipo de cambio (dólar divisa, mayorista) 2 veces por día y permitir cargarlo a mano | App, Notas | Piloto 1 |
| RF-22 | Exportación | Exportar datos a Excel y hacer respaldo, respetando lo que cada rol puede ver | App | Piloto 1 |
| RF-23 | Usuarios | Alta del dueño en pantalla separada: nombre, email (confirmado por correo), contraseña, teléfono de WhatsApp (verificado mandando al bot un código que muestra el panel), nombre del establecimiento y aceptación de términos y consentimiento de audios. El dueño invita encargados con nombre y teléfono; el email y la contraseña del encargado son opcionales si solo usa el bot. El dueño puede dar de baja un número | Notas | Piloto 1 |
| RF-24 | Integridad | Impedir borrar registros en uso; relaciones por id | App, Propuesta | Piloto 1 |
| RF-27 | Labores | Registrar una carpida con temporales: personas y días; pago por hora y horas por día salen de los valores de referencia | Notas | Piloto 1 |
| RF-28 | Usuarios | Roles dueño y encargado; un establecimiento por usuario en el piloto (varios, opcional) | Notas | Piloto 1 |
| RF-29 | Panel web | Formularios de carga manual para todo lo que acepta el bot, por prioridad | Notas | Piloto 1 |
| RF-30 | Cosecha | Registrar la producción de un ciclo: kilos como se pesaron, humedad opcional y destino (bolsón del grano o un acopio); si va al bolsón, suma el costo de embolsar al ciclo | Notas | Piloto 2 |
| RF-31 | Stock de granos | Ver el stock de cada grano por ubicación: bolsón y cada acopio, sin vender y vendido | Notas | Piloto 2 |
| RF-32 | Panel web | Panel instalable en el celular (PWA), diseñado primero para pantalla chica | App | Piloto 1 |
| RF-33 | Granos | Lista de granos con humedad base y precio de referencia (US\$/t) | Notas | Piloto 1 |
| RF-34 | Ciclos | Cerrar el ciclo de un lote cuando el usuario avisa que terminó de cosechar; solo el dueño puede reabrirlo | Notas | Piloto 1 |
| RF-35 | Lluvias | Registrar lluvias por establecimiento (fecha y mm), solo como registro; se pueden consultar en el panel y por el bot | Notas | Piloto 1 |
| RF-36 | Productos y stock | Catálogo base de productos con precios de referencia, mantenido por el administrador; el usuario elige de ahí y, si no está, crea uno propio | Notas | Piloto 1 |
| RF-37 | Valores de referencia | Cargar los valores de referencia al dar de alta el establecimiento; avisar al dueño al arrancar la cosecha de cada grano en cada campaña para actualizar precio, flete y embolsado | Notas | Piloto 1 (aviso: Piloto 2\) |
| RF-38 | Historial | Historial de cargas para el dueño: quién cargó qué y cuándo, por bot o panel, con correcciones y anulaciones; filtrable por persona, tipo y fecha; desde una carga del bot se puede escuchar el audio original | Notas | Piloto 1 |
| RF-39 | Campañas | Asignar cada ciclo a su campaña (grano \+ año agrícola de la siembra, mayo a abril) al cargar la siembra; el dueño puede cambiarla | Notas, Propuesta | Piloto 1 |
| RF-40 | Notificaciones | Avisos al celular por WhatsApp con plantillas aprobadas por Meta (arranque de cosecha, productos con precio pendiente, stock negativo); cada aviso tiene costo por mensaje. Notificaciones de la PWA, más adelante (en iPhone solo funcionan con la app agregada a la pantalla de inicio) | Notas | Piloto 2 |
| RF-41 | Stock de granos | Registrar ajustes de stock de granos para las salidas que no son una venta (merma real, consumo propio, pérdidas en el bolsón u otras): kilos, fecha, ubicación y motivo opcional, sin precio; no cuentan como ingreso | Notas | Piloto 2 |

Se descartaron RF-25 (migración de Firestore), RF-11 y RF-12 (caja y pagos), RF-26 (consumo de combustible) y la carga de maquinaria de RF-19.

## **5\. Historias de usuario**

Cada historia lleva criterios de aceptación verificables, que después se vuelven casos de prueba.

| ID | Historia | Criterios de aceptación | Requisitos |
| :---- | :---- | :---- | :---- |
| HU-01 | Como productor, quiero cargar una labor por audio para no escribir en el campo | El bot repite lote, labor, insumos y cantidades; nada se guarda hasta el "Sí"; al confirmar, la labor queda en el ciclo que corresponde a su fecha, el stock descontado y el costo guardado. Si carga el encargado, la confirmación muestra cantidades, nunca costos | RB-05, RB-07, RB-09, RF-09 |
| HU-02 | Como productor, quiero corregir un dato mal entendido sin repetir todo | Con "Corregir" el bot pregunta solo el campo erróneo y vuelve a pedir confirmación | RB-07, RB-08 |
| HU-03 | Como productor, quiero deshacer la última carga si me equivoqué | Tras "deshacer" la carga queda anulada, el stock y los costos se revierten y queda registro | RB-10, RF-13 |
| HU-04 | Como productor, quiero que el bot no duplique una carga si WhatsApp reenvía el mensaje | El mismo id de mensaje procesado dos veces genera una sola carga | RB-02 |
| HU-06 | Como productor, quiero registrar que mandé grano del bolsón al acopio | Digo grano, kilos, acopio y, si quiero, cantidad de camiones, patente o carta de porte; el stock pasa del bolsón al acopio y el flete se suma al establecimiento | RF-14, RF-31 |
| HU-07 | Como dueño, quiero ver el margen de cada ciclo de un lote, también preguntándole al bot | El margen es producción × precio de referencia vigente − costos de producción, sobre las ha limpias del ciclo; el bot responde con los mismos números que el panel | RF-17, RB-17 |
| HU-08 | Como encargado, quiero cargar y consultar sin acceder a la información financiera | Puedo cargar todo, consultar cargas y stock y ver precios de referencia; si consulto márgenes, costos totales o ventas, el bot responde que no tengo permiso. En la confirmación del bot y en las listas del panel veo cantidades, nunca costos | RF-28, RB-18 |
| HU-09 | Como administrador, quiero revisar qué entendió el bot de cada audio | Hay una línea de tiempo por mensaje con audio, transcripción, borrador, correcciones y resultado | RNF-05, RNF-12 |
| HU-10 | Como administrador, quiero apagar el bot ante un problema | El interruptor detiene las cargas y el bot avisa que está en pausa | RB-12 |
| HU-12 | Como productor, quiero saber cuántos repuestos tengo de cada modelo | Si digo "cambié 2 filtros de aceite X", se descuentan del stock y su costo suma a mantenimiento; puedo consultar el stock por modelo | RF-19, RF-03 |
| HU-13 | Como productor o encargado, quiero nombrar un producto nuevo y que el bot lo agregue | El bot lo busca en el catálogo y propone unidad y precio de referencia; si no está y no digo el precio, lo crea con el precio pendiente para el dueño; después sigue con la compra o la labor | RB-19, RF-03 |
| HU-14 | Como productor, quiero registrar la cosecha de un lote | Digo lote, kilos y si fue al bolsón o a un acopio; suma al rinde del ciclo y al stock del grano; si va al bolsón, el embolsado suma al costo del ciclo | RF-30 |
| HU-18 | Como productor, quiero registrar una venta | Digo grano, kilos, precio y desde dónde (acopio o bolsón); esos kilos pasan a vendidos y cuentan como ingreso real | RF-16 |
| HU-19 | Como dueño, quiero ver quién cargó qué | Historial filtrable por persona, tipo y fecha, con correcciones, anulaciones y el audio original | RF-38 |
| HU-20 | Como dueño, quiero que no se carguen labores en un ciclo ya cosechado | Si una labor cae en un ciclo cerrado, el bot avisa y solo yo puedo reabrirlo | RF-34, RB-23 |
| HU-21 | Como productor, quiero mandar un audio con varias cargas | El bot las separa y confirma de a una; si cancelo una, las otras siguen | RB-05, RB-22 |
| HU-22 | Como productor sin señal en el lote, quiero grabar audios y que se carguen cuando vuelva la señal | Los audios llegan juntos; el bot los confirma de a uno, en el orden en que los grabé, y muestra la fecha de cada carga para que la corrija si hace falta | RB-22, RB-25 |

## **6\. Plan del piloto**

El piloto arranca con la siembra de soja (mediados a fines de diciembre) y se completa con la cosecha y el stock de granos. Va en dos entregas, para tener listo primero lo que se usa primero.

| Etapa | Fecha objetivo | Qué incluye | Requisitos |
| :---- | :---- | :---- | :---- |
| Piloto 1: todo menos cosecha y granos | Antes del 15 de diciembre (propuesta) | Cuenta y roles (un establecimiento por usuario); lotes, ciclos y campañas; cierre de ciclo; desmonte; lluvias; valores de referencia; tipo de cambio; catálogo con precios, productos, compras, stock y repuestos; labores con insumos y costo (siembra, pulverización con equipo, fertilización, carpida); anulación; historial; exportación; bot con audio y texto, una carga por confirmación y consultas; panel con carga manual y trazas del bot | RF-01 a RF-10, RF-13, RF-19, RF-21 a RF-24, RF-27 a RF-29, RF-32 a RF-39; RB-01 a RB-15, RB-17 a RB-19, RB-22 a RB-24 |
| Piloto 2: cosecha y granos | Primera quincena de enero | Producción por ciclo (al bolsón o a un acopio); envíos con camiones y flete; stock de granos por ubicación; ventas; rinde, margen y resultado del establecimiento; aviso al dueño para actualizar precios al arrancar la cosecha (plantilla de WhatsApp) | RF-14 a RF-18, RF-30, RF-31, RF-41; RB-16, RB-21 |
| Opcional, si hay tiempo | En cualquiera de las dos entregas | Empleados, sueldos, viáticos y otros gastos; varios establecimientos por usuario | RF-20, RF-28 (varios establecimientos), RB-20 |
| Después | Durante la campaña | Ideas para más adelante (abajo) | — |

**Cosecha en una segunda entrega, sin cortes:** todas las tablas se crean desde el piloto 1, así la segunda entrega solo suma operaciones y pantallas. El cierre de ciclo va en el piloto 1, para que las labores cargadas después de una cosecha caigan en el ciclo correcto. Si llega un audio de cosecha, envío o venta antes de tiempo, el bot avisa y guarda el mensaje para cargarlo después (RB-24).

**Para llegar a tiempo:** dar de alta ya la app y el número en Meta (sin verificación de empresa alcanza para el piloto: hasta 250 clientes por día en mensajes que inicia el negocio, sin tope en los que inicia el usuario); cargar el catálogo base con sus precios antes de dar de alta a los productores; hacer los formularios del panel por prioridad (labores, compras y lluvias primero).

**Arranque controlado:** primero un solo productor de confianza durante 3 o 4 días, con revisión diaria de las trazas; recién después se suma el resto.

**Si no se llega al 15 de diciembre:** pueden pasar a enero, sin frenar la siembra, escuchar el audio original desde el historial (RF-38), exportar a Excel (RF-22), el panel de métricas (mientras tanto, consultas SQL en Supabase), el modo sombra, el desmonte por el bot (queda solo en el panel), más de 4 o 5 consultas fijas y RF-20. No se recortan: operaciones con anulación, aislamiento entre establecimientos, idempotencia y confirmación.

**Queda afuera:** modo offline y publicación en tiendas de apps (la app es una PWA instalable).

**Ideas para más adelante:**

* Panel que funciona sin conexión: guarda las cargas en el teléfono y las manda cuando vuelve la señal (sin señal, el bot ya funciona por WhatsApp).  
* Mapa de los campos y lotes.  
* Stock de combustible (difícil de controlar sin fugas).  
* Costo propio de las labores por combustible.  
* Carga de empleados con nombre y asignaciones.  
* Carga de maquinaria por campo, con el uso de repuestos por máquina si hace falta.  
* Lectura de imágenes por el bot.

* Notificaciones al celular del dueño sobre los eventos que elija (por ejemplo, cargas del encargado, stock bajo o negativo, lluvias), más allá de los avisos por WhatsApp de RF-40.

* Consultas abiertas con un agente: si el conjunto fijo de consultas del bot (RB-17) se queda corto, un agente de solo lectura puede elegir y combinar herramientas de consulta para responder preguntas libres, por ejemplo comparar gastos entre campañas. Cada herramienta aplica los permisos por rol (RB-18) y ninguna escribe en la base; las cargas siguen el flujo de borrador, validación y confirmación.

### **Revisión del bot durante el piloto**

El bot trabaja en modo confirmado desde el primer día: el "Sí" del usuario guarda la carga en el momento. Vos revisás las trazas una vez por día y anulás o corregís lo que esté mal, avisándole al usuario.

El modo sombra (cada carga queda pendiente hasta que la aprobás) queda como interruptor por usuario. Se activa si un usuario baja de 85 % de cargas sin corrección en sus últimos 50 mensajes o tiene un error grave (un número o lote equivocado que confirmó sin notarlo), hasta corregir la causa.

**Cuentas de prueba.** WhatsApp ofrece un número de prueba gratuito con hasta 5 destinatarios autorizados y sin verificación de empresa; la verificación tarda de 2 a 7 días hábiles. El token temporal dura 24 h, por lo que hay que crear un usuario de sistema con token permanente.

# 

# **Parte 2: Técnico**

Cómo se construye Mi Campo: arquitectura, modelo de datos, bot, requisitos no funcionales y alta en WhatsApp.

## **1\. Arquitectura**

Un solo backend en Python atiende al panel y al bot, y los datos, los audios y las cuentas viven en Supabase.

### **Contexto**

![][image1]

diagrama de contexto · actores y servicios externos

El dueño y el encargado usan WhatsApp y el panel desde el celular; Mi Campo depende de cuatro servicios externos: WhatsApp, transcripción, modelo de lenguaje y tipo de cambio.

### **Contenedores**

![][image2]

diagrama de contenedores · piezas internas de Mi Campo

| Contenedor | Tecnología | Responsabilidad |
| :---- | :---- | :---- |
| Panel web | PWA (HTML y JS), servida como sitio estático | Carga manual, consultas, vista de administración del bot |
| API backend | Python, FastAPI | Webhook de WhatsApp, API del panel y operaciones del sistema (cada una en una transacción) |
| Worker del bot | Python, mismo código que la API | Toma mensajes de la cola, transcribe, arma el borrador, valida, pide confirmación y responde por WhatsApp |
| Tarea programada | Python | Descarga el tipo de cambio (dólar divisa, mayorista) 2 veces por día |
| PostgreSQL | Supabase, con Row Level Security | Datos, auditoría y cola de mensajes |
| Almacenamiento | Supabase Storage | Audios recibidos |
| Autenticación | Supabase Auth | Cuentas y sesiones del panel |

Propuesta: la cola de mensajes empieza como una tabla de PostgreSQL y el worker corre en el mismo servicio que la API; si el volumen crece, se separan sin cambiar el código de las operaciones.

**Adaptador de canal.** El bot habla con WhatsApp a través de una capa chica que traduce tres cosas: llegó un mensaje, bajar el audio y mandar una respuesta. Transcripción, borradores, validación, operaciones y trazas no saben por qué canal vino el mensaje. Solo se implementa WhatsApp; si Meta restringe el bot o bloquea el número, Telegram es el plan B y se agrega escribiendo otro adaptador, sin tocar el resto.

### **Flujo de una carga por audio**

![][image3]

flujo de una carga por audio · 7 pasos

WhatsApp no manda el audio en el webhook, solo un aviso con el id del archivo: la API lo deja en la cola y responde 200 al instante, y el worker baja el audio desde Meta. Si la persona corrige, el bot pregunta solo ese dato y vuelve a validar; si cancela, no se guarda nada. Cada paso queda registrado en mensaje\_bot. El panel web usa las mismas operaciones y validaciones que el bot.

## **2\. Modelo de datos**

El modelo tiene 28 tablas en 8 grupos. Casi todas cuelgan de un establecimiento, que es la unidad de aislamiento entre clientes; las globales se indican en cada tabla.

![][image4]

modelo de datos · 28 tablas en 8 grupos

**Columnas comunes.** Todas las tablas llevan id (UUID) y fecha de creación; las de un establecimiento llevan establecimiento\_id. Las tablas de cargas suman creado\_por (usuario), origen (bot o panel), mensaje\_id (el mensaje del bot que la generó, si lo hay) y una marca de anulación (quién, cuándo y por qué). Los importes son NUMERIC, nunca decimales de coma flotante.

**Costos e ingresos.** No hay caja: un costo cuenta cuando se carga. Los costos de producción (insumos, servicio de la labor, carpidas, embolsado) van al ciclo; los del establecimiento (sueldos, viáticos, mantenimiento, fletes, desmontes) no. Lo vendido es ingreso real; lo no vendido se valúa a precio de referencia vigente.

### **Acceso**

| Tabla | Campos principales | Notas |
| :---- | :---- | :---- |
| usuario | nombre, teléfono de WhatsApp (único), email, activo, último establecimiento usado, código de verificación del teléfono (con hash), vencimiento del código e intentos | Global; la contraseña la maneja Supabase Auth |
| establecimiento | nombre, equipos propios de pulverización (por defecto, mosquito) | Los valores de referencia van en su propia tabla |
| membresia | usuario, establecimiento, rol (dueño o encargado), activa | Dar de baja una membresía corta el acceso en el momento |

### **Campo**

| Tabla | Campos principales | Notas |
| :---- | :---- | :---- |
| campo | nombre |  |
| lote | campo, nombre, ha limpias, ha de monte | Las ha totales son la suma |
| ciclo | lote, cultivo (opcional en preparación), campaña (grano \+ año agrícola, se fija con la siembra), ha limpias, fecha de inicio, fecha de cierre, estado (en preparación, abierto o cerrado) | Guarda las ha limpias del momento; un solo ciclo abierto por lote; solo el dueño lo reabre |
| desmonte | lote, fecha, ha, costo en US\$ | Pasa ha de monte a limpias en la misma transacción; costo al establecimiento |
| lluvia | fecha, mm | Por establecimiento; solo registro |

### **Productos y stock**

| Tabla | Campos principales | Notas |
| :---- | :---- | :---- |
| catalogo\_producto | nombre, categoría, unidad, principio activo, concentración, modelo (repuestos), precio de referencia | Global; lo mantiene el administrador |
| producto | catálogo (si viene de ahí), nombre, categoría, unidad (l, kg, bolsa o unidad), precio promedio (o pendiente), cultivo, variedad, kg por bolsa, modelo (repuestos) | Uno por establecimiento; cada concentración es un producto |
| compra | fecha, proveedor, total en US\$, monto en ARS, tipo de cambio | Suma stock al producto |
| compra\_item | compra, producto, cantidad, precio unitario (vacío si no se dijo) |  |
| movimiento\_stock | producto, fecha, cantidad (+ entra, − sale), precio unitario, origen (compra, labor, uso de repuesto, ajuste, anulación) | El stock es la suma de movimientos; puede quedar negativo con aviso |

### **Labores**

| Tabla | Campos principales | Notas |
| :---- | :---- | :---- |
| tipo\_labor | nombre, equipo (solo pulverización: mosquito, dron o avión) | Global; su precio está en valor\_referencia |
| labor | ciclo, lote, tipo, fecha, ha, contratado (sí o no), costo del servicio, costo de insumos, costo total | El ciclo sale de la fecha; costos guardados al cargar (RN-10) |
| labor\_insumo | labor, producto, dosis por ha, unidad de la dosis, cantidad total, precio unitario, costo | La dosis en kg/ha se convierte a bolsas para el stock |
| carpida | labor, personas, días, horas por día, pago por hora, costo | Solo en labores de carpida |

### **Costos del establecimiento**

| Tabla | Campos principales | Notas |
| :---- | :---- | :---- |
| empleado | nombre, sueldo mensual, activo |  |
| costo\_general | mes, tipo (sueldo, viático, mantenimiento u otro), empleado, monto en US\$ | Fuera del margen por lote; los fletes y desmontes viven en sus propias tablas |

### **Cosecha y granos**

| Tabla | Campos principales | Notas |
| :---- | :---- | :---- |
| cultivo | nombre, humedad base | Global; su precio de referencia está en valor\_referencia |
| acopio | nombre | Lista del establecimiento; el bot empareja el nombre dicho con esta lista |
| cosecha | ciclo, cultivo, fecha, kg, humedad (opcional), destino (bolsón o acopio), costo de embolsar | La producción del ciclo; de acá sale el rinde |
| movimiento\_grano | cultivo, fecha, kg, tipo (cosecha, envío, venta o ajuste), desde y hacia (bolsón, acopio sin vender, vendido), acopio, precio bruto por t y humedad (ventas), motivo (ajustes), camiones y flete (envíos y ventas desde el bolsón), patente, carta de porte, kg brutos y tara (opcionales), cosecha | Un solo registro de movimientos para todo el stock de granos |

El stock de granos no es una tabla: para cada grano y cada ubicación (bolsón, cada acopio sin vender, vendido) es la suma de sus movimientos, sin importar lote ni variedad. Puede quedar negativo con aviso.

### **Moneda**

| Tabla | Campos principales | Notas |
| :---- | :---- | :---- |
| tipo\_cambio | fecha y hora, tipo de dólar, valor, fuente (automático o manual) | Global; dólar divisa (mayorista), se carga 2 veces por día y pasa a US\$ los importes en ARS |

### **Valores de referencia**

| Tabla | Campos principales | Notas |
| :---- | :---- | :---- |
| valor\_referencia | concepto (servicio de labor, pulverización por equipo, flete, embolsado, pago por hora y horas de carpida, precio de grano), tipo de labor o grano según el concepto, campaña (para precios de granos, flete y embolsado), valor, desde cuándo | Un cambio crea una fila nueva, así queda el historial |

### **Bot y auditoría**

| Tabla | Campos principales | Notas |
| :---- | :---- | :---- |
| mensaje\_bot | canal (WhatsApp), id del mensaje en el canal (único), usuario, establecimiento, tipo (audio o texto), ruta del audio, transcripción, borrador, correcciones, estado, modo (sombra o confirmado), versión del prompt y de los modelos, proveedor, tokens, costo, duración total, error | Uno por mensaje; también funciona como cola |
| evento\_bot | mensaje, paso (recibido, audio descargado, transcripto, borrador, validación, pregunta, respuesta del usuario, confirmado, ejecutado, error), fecha y hora, duración, detalle | Una fila por paso: arma la línea de tiempo de cada mensaje |
| auditoria | tabla, registro, acción, valores antes y después, usuario, origen, mensaje, fecha | Una fila por cada cambio de datos; también registra los ingresos del administrador |

## **3\. Requisitos del bot de WhatsApp**

El bot carga todo lo que acepta el panel y responde consultas, pero nunca escribe en la base por sí solo: un modelo de lenguaje propone un borrador y el sistema lo valida y lo ejecuta solo tras la confirmación.

**Acciones.** Todas las cargas de la Parte 1 (sección 4\) y consultas de un conjunto fijo de preguntas (stock, cargas, lluvias, márgenes, costos, ventas), según lo que permita el rol.

| ID | Requisito | Etapa |
| :---- | :---- | :---- |
| RB-01 | Recibir mensajes por la API oficial de WhatsApp Cloud, responder 200 rápido y procesar en segundo plano | Piloto 1 |
| RB-02 | Idempotencia: un mismo mensaje (por su id) no genera dos cargas | Piloto 1 |
| RB-03 | Descargar y guardar el audio (el id de medio de WhatsApp vale 7 días) | Piloto 1 |
| RB-04 | Transcribir el audio con un proveedor intercambiable | Piloto 1 |
| RB-05 | Clasificar el mensaje (carga o consulta) y convertirlo en uno o más borradores; si un audio trae varias cargas, se confirman de a una | Piloto 1 |
| RB-06 | Validar el borrador con reglas deterministas (por ej., una pulverización propia con dron solo si el establecimiento tiene dron) y emparejar nombres contra el catálogo con coincidencia aproximada | Piloto 1 |
| RB-07 | Repetir los números y datos clave y pedir confirmación con Sí, Corregir o Cancelar | Piloto 1 |
| RB-08 | Preguntar solo lo que falta o es ambiguo, sin repetir lo ya entendido | Piloto 1 |
| RB-09 | Ejecutar la carga en una sola transacción de base de datos | Piloto 1 |
| RB-10 | Deshacer la última carga mediante anulación | Piloto 1 |
| RB-11 | Aceptar texto además de audio | Piloto 1 |
| RB-12 | Interruptor de apagado y límite diario de mensajes | Piloto 1 |
| RB-13 | Modo confirmado por defecto, con revisión posterior; modo sombra (cargas pendientes de aprobación) como interruptor por usuario (ver Parte 1, sección 6\) | Piloto 1 |
| RB-14 | Guardar las correcciones de la persona como conjunto de evaluación | Piloto 1 |
| RB-15 | Rechazar números no registrados o dados de baja y mensajes fuera del tema | Piloto 1 |
| RB-16 | Respetar la ventana de 24 h de WhatsApp; fuera de ella, plantillas aprobadas | Piloto 2 |
| RB-17 | Responder consultas de un conjunto fijo de preguntas con datos calculados por el sistema; el modelo de lenguaje solo elige la pregunta y sus parámetros, nunca arma consultas libres a la base | Piloto 1 (márgenes y ventas: Piloto 2\) |
| RB-18 | Aplicar permisos por rol: al encargado le responde sobre cargas, stock y precios de referencia, no sobre costos totales, márgenes, utilidad ni ventas | Piloto 1 |
| RB-19 | Si nombra un producto que no está en su establecimiento, buscarlo en el catálogo base y ofrecer agregarlo con el precio del catálogo; si tampoco está ahí y no se dice el precio, se crea con el precio pendiente para el dueño | Piloto 1 |
| RB-20 | Si la persona tiene varios establecimientos, usar el último y permitir cambiarlo por nombre | Opcional |
| RB-21 | Al arrancar la cosecha de un grano en una campaña, avisar al dueño para actualizar precio del grano, flete y embolsado | Piloto 2 |
| RB-22 | Un borrador en confirmación por vez por usuario. Si llegan varios mensajes juntos (por ejemplo, audios grabados sin señal), se encolan y se confirman de a uno en el orden en que se grabaron ("Tengo 5 cargas tuyas. La primera: …"). El vencimiento de 30 minutos cuenta desde la pregunta del bot | Piloto 1 |
| RB-23 | Si una labor cae en un ciclo cerrado, avisar; solo el dueño puede reabrirlo | Piloto 1 |
| RB-24 | Si llega un audio de cosecha, envío o venta antes del piloto 2, avisar que todavía no está disponible y guardar el mensaje para cargarlo después | Piloto 1 |
| RB-25 | La fecha de cada carga sale de lo que dice el audio (hoy, ayer, el martes) y se muestra siempre en la confirmación; no se usa la hora de llegada del mensaje, que puede ser horas después si se grabó sin señal. Las fechas se resuelven en la hora de Argentina (America/Argentina/Buenos\_Aires) y se guardan como fecha local; antes del piloto hay que probar con WhatsApp real si la hora del mensaje es la de grabación o la de envío | Piloto 1 |

## **4\. Requisitos no funcionales**

Las metas numéricas son propuestas para el piloto y se ajustan con los datos reales.

| ID | Área | Requisito | Meta propuesta |
| :---- | :---- | :---- | :---- |
| RNF-01 | Fiabilidad | Cada carga se ejecuta completa o no se ejecuta (transacción única); sin duplicados | 0 cargas parciales o duplicadas |
| RNF-02 | Precisión del bot | Porcentaje de cargas confirmadas sin ninguna corrección, medido desde el día 1 | 85 % por usuario; por debajo, pasa a modo sombra |
| RNF-03 | Seguridad | Aislamiento por establecimiento con Row Level Security; claves fuera del código; tokens permanentes de sistema | Sin acceso cruzado entre establecimientos |
| RNF-04 | Privacidad | Consentimiento expreso para guardar audios, plazo de retención y destrucción; inscripción de la base en la AAIP (Ley 25.326) | Consulta con abogado, pendiente |
| RNF-05 | Auditoría | Tres capas: traza del bot por mensaje, auditoría de datos con valor anterior y nuevo, y logs técnicos con id de correlación | Todo cambio rastreable hasta su mensaje |
| RNF-06 | Trazabilidad | Ninguna carga se borra; se anula y queda registro | 100 % de cargas conservadas |
| RNF-07 | Rendimiento | Tiempo desde que llega el audio hasta que el bot pide confirmación | Menos de 15 s en 9 de cada 10 mensajes |
| RNF-08 | Disponibilidad | Servicio siempre activo para recibir webhooks; reintentos si falla un paso | Ningún mensaje perdido |
| RNF-09 | Respaldo | Copias de la base: el plan gratuito de Supabase no tiene copias automáticas y se pausa tras una semana sin uso | Plan pago o respaldo diario propio durante el piloto |
| RNF-10 | Costo | Servidor de US\$5-10 por mes aceptable; resto en planes gratuitos durante el piloto | Presupuesto total a definir |
| RNF-11 | Usabilidad | Español rioplatense, interfaz usable desde el celular en el campo, respuestas del bot cortas | Validar con usuarios |
| RNF-12 | Observabilidad | Métricas: % confirmado sin corrección, campos corregidos, cancelados, tiempo hasta confirmar, costo por mensaje | Revisión semanal |
| RNF-13 | Portabilidad | Proveedores de transcripción, lenguaje y hosting intercambiables; canal de mensajería detrás de un adaptador | Sin dependencia exclusiva |
| RNF-14 | Mantenibilidad | Pruebas automatizadas con audios y casos reales; migraciones versionadas de la base | Cada corrección del piloto se vuelve un caso de prueba |
| RNF-15 | Escalabilidad | Hasta 20 usuarios a corto plazo; arquitectura multiestablecimiento, backend sin estado y cola de mensajes para crecer a cientos o miles sin rediseño | Crecer solo cambiando de plan |
| RNF-16 | Seguridad | El aislamiento por establecimiento lo aplica la base: al abrir cada transacción, el backend fija el establecimiento y el usuario (SET LOCAL app.establecimiento\_id y app.usuario\_id) y las políticas de Row Level Security comparan contra esos valores (current\_setting). Cubre al panel y al bot, que no tiene sesión de Supabase. El backend se conecta con un rol propio sin permiso para saltear RLS (no postgres ni service\_role) y las tablas usan FORCE ROW LEVEL SECURITY; la clave de servicio de Supabase, solo para tareas internas | Pruebas que intentan leer otro establecimiento y fallan |
| RNF-17 | Privacidad | Audios en almacenamiento privado, accesibles solo con enlaces temporales y según el rol | Ningún audio con enlace público |
| RNF-18 | Auditoría | Cada ingreso del administrador a los datos de un establecimiento queda registrado y se informa en el consentimiento | 100 % de accesos registrados |
| RNF-19 | Seguridad | Cuentas con Supabase Auth (contraseñas con hash, confirmación de email, recuperación de contraseña, sesiones que vencen); correo con SMTP propio; verificar la firma de cada webhook de WhatsApp; solo HTTPS; claves en variables de entorno; límite de intentos en login y en el bot | Ninguna contraseña ni clave en texto plano |
| RNF-20 | Mantenibilidad | La PWA pide primero a internet la página y los archivos de la app, y usa lo guardado en el celular solo sin conexión, para que cada arreglo llegue en la próxima apertura | Una versión nueva se ve en la primera apertura |

### **Seguridad: lo que no resuelve Supabase**

Supabase Auth ya cubre el hash de contraseñas, la confirmación de email, la recuperación de contraseña, el vencimiento de sesiones y el límite de intentos de login. Aparte hay que hacer:

* **Correo propio (SMTP):** el que trae Supabase es solo para pruebas y permite muy pocos envíos por hora; con usuarios reales hay que conectar un servicio de correo (Resend, SendGrid u otro).  
* **Firma de los webhooks:** verificar que cada mensaje que llega al backend lo firmó Meta; si no, cualquiera podría hacerse pasar por un productor.  
* **Verificación del teléfono:** el panel muestra un código y el usuario se lo manda al bot.  
* **Aislamiento por establecimiento en el backend** (RNF-16), audios privados (RNF-17) y registro de accesos del administrador (RNF-18).  
* **Lo básico:** solo HTTPS, claves en variables de entorno, límite diario de mensajes por usuario en el bot y respaldo diario.

### **Notificaciones**

Los avisos al celular van por WhatsApp con plantillas aprobadas por Meta (RF-40, RB-16): es donde ya está el usuario. Cada aviso que inicia el sistema tiene costo por mensaje, así que se usan solo para lo importante (arranque de cosecha, productos con precio pendiente, stock negativo). Las notificaciones de la PWA quedan para más adelante: en Android funcionan bien, pero en iPhone solo con la app agregada a la pantalla de inicio.

### **Observabilidad: trazas, métricas y alertas**

Las trazas se diseñan desde el principio, porque agregarlas después obliga a tocar cada operación. Todo se une por un mismo id: el del mensaje de WhatsApp.

| Capa | Dónde vive | Qué responde |
| :---- | :---- | :---- |
| Traza del bot | Tablas mensaje\_bot y evento\_bot (PostgreSQL) | Qué dijo el usuario, qué entendió el bot en cada paso, cuánto tardó y cuánto costó |
| Auditoría de datos | Tabla auditoria (PostgreSQL) | Qué cambió, quién, cuándo y desde qué mensaje |
| Logs técnicos | Logs en formato JSON con el id del mensaje, enviados a un servicio externo con plan gratuito | Qué falló en el servidor y por qué |
| Errores | Servicio de errores (por ej., Sentry, con plan gratuito) | Cada excepción, con su contexto y el id del mensaje |

**Panel de métricas del administrador** (por día y por usuario): mensajes recibidos; % confirmados sin corrección; campos más corregidos; cancelados; mensajes fuera de tema; tiempo por etapa (descarga, transcripción, borrador, respuesta); costo de transcripción y modelo por mensaje; errores; anulaciones; stock negativo.

**Alertas:** errores seguidos en el webhook o el worker; mensajes acumulados en la cola; respuesta de más de 15 s; costo diario por encima de un límite; servicio caído (monitor externo que consulta cada pocos minutos).

**Cuidados:** cada mensaje guarda la versión del prompt y de los modelos, para comparar antes y después de un cambio; los logs técnicos no guardan audios ni números de teléfono completos.

## **5\. Anexo: alta del bot en WhatsApp Cloud API**

El bot se da de alta en Meta en unos 9 pasos; los primeros 7 alcanzan para desarrollar con el número de prueba gratuito. Fuente: [guía oficial de Meta](https://developers.facebook.com/documentation/business-messaging/whatsapp/get-started).

1. Registrarse como desarrollador en Meta for Developers con una cuenta de Facebook.  
2. Crear una app de tipo Business y agregarle el caso de uso de WhatsApp; esto crea o vincula un portfolio de Meta Business.  
3. En API Setup, usar el número de prueba que da Meta y anotar el Phone number ID y el WhatsApp Business Account ID.  
4. Agregar hasta 5 números destinatarios para probar.  
5. Probar el envío con el token temporal, que vence en unas 24 h.  
6. Crear el token permanente: en Business Settings → System users, crear un usuario de sistema, asignarle la app y la cuenta de WhatsApp con control total y generar el token con los permisos whatsapp\_business\_messaging y whatsapp\_business\_management. Guardarlo como secreto del backend, nunca en el código.  
7. Configurar el webhook: en WhatsApp → Configuration, cargar la URL pública del backend y un token de verificación propio, y suscribirse al campo messages.  
8. Para el piloto: agregar un número propio que no esté en uso en la app de WhatsApp y cargar un medio de pago. Sin verificación de empresa alcanza: hasta 250 clientes por día en mensajes que inicia el negocio y sin tope en los que inicia el usuario, pero el chat muestra el número en lugar del nombre.  
9. Más adelante: verificar la empresa en Meta Business para subir esos límites y mostrar el nombre.

Los pasos de la consola cambian seguido; ante una diferencia, manda la guía oficial.

# **Parte 3: Decisiones y pendientes**

Lo decidido, con el porqué, para no volver a discutirlo; abajo, lo que sigue abierto.

## **Registro de decisiones**

| Fecha | Decisión | Por qué |
| :---- | :---- | :---- |
| Nov 2026 | Pasar de Firebase a PostgreSQL en Supabase y empezar de cero | Datos relacionales, transacciones confiables y cálculos de márgenes; los datos actuales no justifican migrar |
| Nov 2026 | Backend en Python (FastAPI), en un servicio siempre activo | Preferencia del equipo; US\$5-10 por mes es aceptable |
| Nov 2026 | Sin modo offline | El bot ya requiere internet |
| Nov 2026 | El bot de WhatsApp es la vía principal; confirma una carga por vez, con un solo borrador pendiente por usuario | Carga rápida desde el campo y correcciones simples |
| Nov 2026 | App como PWA instalable, no en tiendas | Un solo código, actualizaciones inmediatas y sin costo de tiendas |
| Nov 2026 | Orden: modelo de datos, operaciones, panel y bot | El bot se apoya en operaciones que ya funcionan |
| Nov 2026 | No se modelan caja ni pagos; un costo cuenta cuando se carga | Los productores usan cheques y cuentas corrientes; importa el costo, no el pago |
| Nov 2026 | Valores de referencia que se cargan una vez y se pueden reemplazar en cada carga | La carga por audio queda corta |
| Nov 2026 | Costo de una labor \= precio de referencia del servicio, sea propia o contratada; sin combustible por ahora | El precio de contratar ya incluye combustible, amortización y mano de obra; es más simple |
| Nov 2026 | Sin carga de maquinaria; los repuestos son productos con su modelo | Sin combustible, la maquinaria no cambiaba ningún número |
| Nov 2026 | La cosecha registra solo la producción; el stock de granos (bolsón por grano y acopios), los envíos y las ventas van aparte | En el bolsón se mezcla grano de varios lotes, así que una venta no se puede atribuir a un lote |
| Nov 2026 | Margen por ciclo a precio de referencia vigente; ventas reales, fletes y desmontes en el resultado del establecimiento | Consecuencia de la decisión anterior |
| Nov 2026 | Lo que liquida el acopio no se ajusta; sin descuento por merma en lo no vendido | El sistema no está conectado al acopio; el usuario acepta ese margen de error |
| Nov 2026 | Campaña \= grano \+ año agrícola de la siembra (mayo a abril) | Cubre girasol temprano y tardío sin botones de iniciar o terminar |
| Nov 2026 | Ciclo por lote que se cierra al terminar la cosecha; las labores van al ciclo según su fecha; solo el dueño reabre un ciclo | Evita labores en el ciclo equivocado |
| Nov 2026 | Roles dueño y encargado desde el piloto; un establecimiento por usuario | Algunos productores del piloto trabajan con encargado |
| Nov 2026 | El stock negativo se permite con aviso | En la práctica se usan productos antes de cargar la compra |
| Nov 2026 | Modo confirmado desde el primer día, con revisión diaria; modo sombra como interruptor por usuario | Aprobar cada carga a mano era demasiado asincrónico |
| Nov 2026 | Avisos por WhatsApp con plantillas; notificaciones de la PWA más adelante | El usuario ya está en WhatsApp; en iPhone la PWA solo notifica si está instalada |
| Nov 2026 | Piloto 1 (todo menos cosecha) antes del 15 de diciembre; piloto 2 (cosecha y granos) en enero | Llegar a la siembra de soja con lo que se usa primero |
| Nov 2026 | Sin señal, la carga se hace con audios de WhatsApp que se mandan solos al volver la señal; el bot los encola y confirma de a uno, con la fecha que dice el audio. El panel sin conexión queda para más adelante | WhatsApp ya guarda los mensajes sin señal; casi no requiere trabajo extra |
| Nov 2026 | Solo WhatsApp, desarrollado y probado con el número de prueba y lanzado sin verificación de empresa; el bot pasa por un adaptador de canal y Telegram queda como plan B, sin desarrollo ahora | Sin verificar alcanza para el piloto (los mensajes que inicia el usuario no tienen tope); el adaptador es barato y protege ante cambios de reglas de Meta |
| Nov 2026 | El tipo de cambio es el dólar divisa (mayorista), igual para todos los establecimientos | Es la cotización con la que se liquidan las operaciones del agro (granos, insumos) |
| Nov 2026 | El ciclo empieza en preparación con la primera labor del lote y la siembra le fija cultivo y campaña; un solo ciclo abierto por lote | Las labores antes de la siembra (barbecho) y el cultivo de segunda necesitaban un ciclo claro al que ir |
| Nov 2026 | La venta se carga en toneladas con el precio bruto por tonelada; el secado no se calcula por ahora y los costos (flete) quedan en plata | Lo que más importa de la venta son las toneladas, que el usuario cotiza cuando quiere; el descuento por secado varía por acopio |
| Nov 2026 | Repuestos: solo stock por modelo (las compras suman y el uso descuenta); el uso por máquina va con el módulo de maquinaria | Al cliente le interesa saber cuántos filtros, cubiertas y correas tiene; la maquinaria queda para más adelante |
| Nov 2026 | En la app solo se registran ventas; cualquier otra salida de grano es un ajuste de stock (kilos, ubicación y motivo opcional, sin precio), que no cuenta como ingreso | El rinde sale de la cosecha completa y el stock coincide con lo que hay en el campo, sin cargar en la app ventas que el productor no quiere registrar; el mismo ajuste sirve para merma, consumo propio y pérdidas |
| Nov 2026 | Los repuestos usan la unidad "unidad"; las categorías de producto son herbicida, insecticida, fungicida, coadyuvante, fertilizante, semilla, repuesto u otro | Los repuestos se cuentan por pieza ("cambié 2 filtros"), y una lista fija de categorías permite validar y filtrar sin configuración extra |

## **Preguntas abiertas**

Quedan cuatro temas abiertos; ninguno cambia el modelo de datos.

* ☐ **Permisos del encargado:** reglas finas de qué puede consultar y ver en el panel.  
* ☐ **Privacidad:** consulta con abogado sobre consentimiento, retención de audios e inscripción en la AAIP.  
* ☐ **Costo de WhatsApp en Argentina:** a confirmar con Meta.  
* ☐ **Precio al usuario:** en dólares; el monto se define al final.

## **Notas a tener en cuenta**

Puntos del diseño que alcanzan para el piloto pero pueden fallar en algunos casos; conviene revisarlos con los datos reales.

* Promedio con stock negativo (RN-04): lo que se usó mientras el stock estaba negativo se costeó con el promedio anterior y, como el costo queda fijo al cargar (RN-10), no se corrige cuando llega la compra. Si la compra trae un precio muy distinto, esas labores quedan con un costo de insumos más bajo o más alto que el real.

* Una compra chica con el stock en cero o negativo define sola el promedio: si trae un precio fuera de lo normal, ese precio se usa en todas las labores siguientes hasta la próxima compra.

* Anular una compra vieja recalcula el promedio desde ese momento, pero no cambia el costo de las labores ya cargadas con el promedio anterior.

* Para que estos casos sean pocos, el aviso de stock negativo (RN-32) le pide al usuario que cargue la compra que falta.

[image1]: diagramas/01-contexto.png
[image2]: diagramas/02-contenedores.png
[image3]: diagramas/03-flujo-audio.png
[image4]: diagramas/04-modelo-datos.png