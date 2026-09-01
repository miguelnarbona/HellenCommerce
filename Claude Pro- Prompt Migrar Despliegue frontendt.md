**Este prompt sera separado por etapas para lograr mejor compresion, ejecucion y aprovechamiento de los tokens disponibles. Cuando termines de interpretar el prompt de la ultima etapa lo unificaras en una solucion unica con la totalididad de la informacion, solo en ese momento comezaras a codificar y entregaras un proyecto terminado monolitico.**

# Etapa 1: Analisis del Proyecto
## Proposito de esta etapa
Analisis profundo del problema, caracteristicas, alcance, sistema de autenticacion y configuracion basica inicial.

# SYSTEM ROLE
Actúas como un Ingeniero de Software Principal y Arquitecto de Soluciones Web e Inteligencia Artificial de Nivel Enterprise. Tu especialidad es generar código de producción crítico Web en lenguaje Go, a partir de un Endpoints en fastapi (backend desarrollado en python 3.11) que se te facilitara el codigo, manteniendo la compatibilidad hacia atrás y optimizando la infraestructura en la nube.

# CONTEXTO INICIAL DEL SISTEMA Room-frontend: Componente 'Kitchen Core' y 'Kitchen' v 1.0.0
`Room` es la interfaz Web "Estilo X (Twitter)" que interactuara con el backend HellenCommerce. `Room` sera desarrollado enteramente en Go sin usar frameworks pesados (Node.js/React). Se comunica con el orquestador principal (residente en `c:\HellenCommerce\fastapi_service`) utilizando **WebSocket** para un flujo asíncrono y en tiempo real, e interactúa con el backend para la carga y gestión de publicaciones (posts) del muro. Adicionalmente maneja consultas o querys e interctua con el backend mediante prompts de IA.

Backend (existente): En la raíz del proyecto `c:\HellenCommerce\`, cuento con 8 servicios primarios críticos administrados por el Orquestador. Actualmente están configurados con una mezcla de microservicios locales y llamadas directas a APIs externas. El sistema web `Room` que programaremos en lenguaje Go estara vinculado al proyecto `c:\HellenCommerce\` mediante el microservicio de `fastapi_service` que es el endpoint ubicado en `c:\HellenCommerce\fastapi_service\` y es el encargado de recibir y procesar millones de peticiones de la app web `Room`.

- **El sistema web `Room`** sera similar en diseno a la app `X` anteriormente conocida como `Twitter` en su formato web. Divideremos verticalmente la pantalla en 4 partes iguales. La parte `principal` ocupara los dos cuartos centrales. Las dos restantes partes seran ocupadas para feeds en el lado derecho y menu adicionales el lado izquierdo. La app tendra en su parte `principal` superior 4 tabs, el primero se llamara `Kitchen`, el segundo `Youroom`, el tercero `Hallway` y el cuarto `Track`. Trabajaremos sobre el tab `kitchen` en esta ETAPA 1.

## Características
- **Go Nativo**: Servidor HTTP robusto implementado con la librería estándar de Go.
- **WebSocket Persistente**: Conexión constante y resiliente mediante Gorilla WebSocket.
- **Sin Dependencias de UI Pesadas**: Utiliza Plantillas HTML Nativas de Go (html/template) y Vanilla JS.
- **Diseño Simple**: Paleta moderna simple, minimalista y responsiva, diseñada sin TaildwindCSS, con CSS puro optimizado. La paleta de colores ira del blanco, pasando por el azul-gris y terminara en azul claro opaco. No usaras otros tonos. No usaras iconos llamativos o resaltados.
- **Integración con Firebase Auth**: Módulo preconfigurado para autenticación con Google (Firebase ID Tokens).
  Usaras las siguiente variables de configuracion en un fichero `.env` ubicado en la raiz del proyecto:

  ### --- Servidor Room ---
    ROOM_PORT=80
    ROOM_ENV=development

  ### --- FastAPI Backend (HellenCommerce) ---
    FASTAPI_URL=http://bunker-fastapi_service:8080

  ### --- Firebase (Google Auth) ---
    FIREBASE_API_KEY=AIzaSyBi-4rVra3fsIRqqa7Qput2JECpH8lfGx8
    FIREBASE_AUTH_DOMAIN=hellencommerce-6e39d.firebaseapp.com
    FIREBASE_PROJECT_ID=hellencommerce-6e39d
    FIREBASE_STORAGE_BUCKET=hellencommerce-6e39d.firebasestorage.app
    FIREBASE_MESSAGING_SENDER_ID=134035788746
    FIREBASE_APP_ID=1:134035788746:web:0e37642e317d8dab977533

  ### --- Seguridad ---
  ### Clave secreta para firmar tokens de sesión (mínimo 32 caracteres)
    JWT_SECRET=R85c0ab512939647f441a06146c4f477dc5a9d7a7202534520cfea878dc68612a

  ### --- CORS (orígenes permitidos, separados por coma) ---
    ALLOWED_ORIGINS=http://localhost:80,http://localhost:3000

# CONTINUIDAD
Esta es la primera etapa. Define las bases del proyecto para que las siguientes etapas se construyan sobre tu salida.

# Etapa 2: Arquitectura y diseno
## Diseno de la arquitectura del sistema: componentes, reglas, tecnologias, modelo de datos, requisitos funcionales y de implementacion.

# REGLAS
Trabajaremos sobre el componente `Kitchen Core` y en la interfaz web, sobre el tab `Kitchen` en la ETAPA 1. 
El componente `Kitchen Core` sera diseñado y operado como una librería interna (NO un microservicio).
Esta librería coordina, envia todo el flujo de peticiones desde la interfaz web de `Room`, desde el tab `Kitchen` hacia el backend de microservicios 
especializados `c:\HellenCommerce\fastapi_service\` y recibe y coordina las respuestas provenientes del backend especializado `c:\HellenCommerce\fastapi_service\` hacia el componente `Kitchen Core` de la interfaz de la app `Room`, sin importar que el backend `fastapi_service` no este disponible. Si no esta disponible emitira una alerta al usuario de conexion y re-intetara conectarse en intervalos de tiempo. El siguiente flujo secuencial define el componente `Kitchen Core`: 
1. El tab `Kitchen` de la interfaz web de la app `Room` recibe una peticion o solicitud de usuario.
2. El tab `Kitchen` de la interfaz web de la app `Room` pasa la solicitud al componente `Kitchen Core`.
3. El componente `Kitchen Core` tendra multiples endpoint que reciben cada petición especialida desde el tab `Kitchen`.
4. Todos los protocolo del componente `Kitchen Core`se implementaran via WebSocket.
5. El componente `Kitchen Core` recibe y procesa cada peticion proveniente del tab `Kitchen`.
6. El componente `Kitchen Core` pasa la peticion al backend `c:\HellenCommerce\fastapi_service\` (si esta disponible, de no estar diponible hace reintentos de conexion hasta lograr disponibilidad) en el formato establecido segun lo requiere el endpoint `c:\HellenCommerce\fastapi_service\`.
7. Despacha en paralelo multiples peticiones (fan-out).
8. El componente `Kitchen Core` retorna respuesta recibida desde el backend `c:\HellenCommerce\fastapi_service\` y se la pasa a la interfaz del tab `Kitchen`.
9. El componente `Kitchen Core` tiene encuenta si recibe peticiones con valores nulos o erroneos.
10. Si el componente `Kitchen Core` recibe valores errores o nulos los maneja y le comunica una respuesta coherente a la interfaz del tab `Kitchen`.
11. La libreria `Kitchen Core` estara ubicada en `/core`.
12. La interfaz web `Kitchen` estara ubicada en `/components/tab`.

## Estructura del Componente `Kitchen Core`
- `/core`: Librería interna que enruta las operaciones de los WebSockets y llamadas HTTP al Orquestador (FastAPI). No es un microservicio autónomo, corre dentro del propio binario de `Room`.
- `/controllers`: Lógica de actualización HTTP → WS y autenticación.
- `/components/tab`: Renderización de Vistas, inyección segura de configuraciones.
- `/static`: CSS y Vanilla JS agrupados por dominio de responsabilidad (ws.js, auth.js, kitchen.js, app.js, share.js).
- `/templates`: Archivos HTML base, separando el Layout de los paneles (Kitchen, Youroom, Hallway).

# OBJETIVOS
Necesito implementar EXCLUSIVAMENTE los módulos `Kitchen Core` y, de la interfaz web, el componente `Kitchen`. La interfaz debe tener disponible 3 tab adicionales que quedaran pendientes a desarrollo en una proxima ETAPA. Esos tab adicionales seran `youroom`, `hallway` y `tracking`.

# REQUERIMIENTOS ESTRICTOS DE IMPLEMENTACION
Analiza y procesa las siguientes directrices delimitadas en etiquetas XML para construir tu respuesta:

<requerimiento_1_panel_deslizante>
El tab `Kitchen` sera un panel deslizante con una barra de scroll minima en el lateral derecho tal y como lo implementa `X`. Para la vista movil no tendra barra de scroll. Se mostrara las publicaciones que haces a medida que se desliza verticalmente.
</requerimiento_1_panel_deslizante>

<requerimiento_2_publicaciones>
Las publicaciones seran del tipo `X` o similares, se mostrara en el panel del tab `Kitchen` cada publicacion estara encabezada con un titulo que contiene un autor o nombre de negocio, con fecha de publicacion seguido en caracteres de menor tamano. Al menos se veran, minimo 3 publicaciones en vista vertical. Cada publicacion sera de similar espacio en el area del tab verticalmente. 
Cada publicacion contendra imagenes publicadas de productos, u otro contenido asociados a un negocio. El texto descriptivo se mostrara debajo de las imagenes en forma de parrajo justificado. Debe estar divido el area de las imagenes del texto horizontalmente, por solo un espacio minimo y las imagenes ocuparan al menos algo mas de la mitad del espacio vertical superior dejando el resto para el texto o parte del texto. 
Cada espacio de imagenes dejara un pequeo espacio vacio cuadrado con un signo de adicion `+` adentro para insertar nuevas imagenes. Para ver estas imagenes podra desplazarlas como cinta horizontalmente.
Si el texto no cabe en la publicacion debera dar la opcion de `mostrar` para desplegar el resto del contenido.
Debajo de cada publicacion, en especifico debajo del texto, un icono con la funcion de `editar` la publicacion, a su lado un icono para ver los `comentarios` recibidos, a continuacion un icono de `compartir` publicacion y por ultimo un icono de `eliminar` la publicacion.
</requerimiento_2_publicaciones>

<requerimiento_3_funcionalidades_de_los_iconos_en_las_publicaciones>
Cada Icono sera disenado de manera simplista, tal y como se visualiza en aplicaciones como whatsapp o twitter, no contendran colores brillantes, alterados o efectos de algun tipo. Seran con un fondo oscuro y delineados en blanco, al dar click sobre estos cambiaran la tonalidad inviertiendo los colores mientras estan seleccionados dejando con claridad y de manera instuitiva la opcion sobre la que se acciona.

- **Icono `edit`**: la opcion de editar cuando se da un click sobre este debe permitir alteral el texto y/o las imagenes. Ademas debe dar la opcion de `save change`, `dismiss`o `publish` en su parte inferior. Sobre el cuadro o icono del signo adicionar `+` dentro de las imagenes debera permitir las mismas opciones.
En el caso de la opcion `save change` esta guardara los cambios en el `Kitchen` que es tu muro, manteniendo activo la opcion de `publish` para publicar el post en `hallway` si selecciona la opcion. 
En el caso de la opcion `publish` su funcion sera agregar la publicacion al tab `hallway` para que sea visible (compartida) para el resto de los usuarios de `Room`.
_ **Icono `comments`**: Similar a `X`, ver los comentarios que han escrito otras personas sobre la publicacion. Debe permitir desplegarlas y desplazarce en sentido vertical para verlas todas ha medida que se hace scroll. Tendra la opcion de retornar marcada por un icono de flecha hacia atras, en la parte superior izquierda, la cual cumple la funcion de retornar a las publicaciones originales en el ultimo lugar o posicion de publicacion a la que accediste al desplegar los comentarios.
- **Icono `share`**: da la opcion de compartir la publicacion via los diferentes metodos que tenga el medio para publicar, digase whatsapp, facebook, telegram, mensajeria u otro.
- **Icono `delete`**: Este icono da la opcion de eliminar esa publicacion en especifico. Debe pedir la confirmacion de la accion de eliminar la publicacion.
</requerimiento_3_funcionalidades_de_los_iconos_en_las_publicaciones>

<requerimiento_4_funcionalidades_del_panel_deslizante>
Tendra en su parte inferior en forma de cinta un icono de adicionar publicacion `add`, al lado un icono de eliminar publicacion `delete`, y al final dejando espacio un icono para un asistente `IA`. Cumpliran igualmente con los requerimientos funcionales <requerimiento_3_funcionalidades_de_los_iconos_en_las_publicaciones>
</requerimiento_4_funcionalidades_del_panel_deslizante>

<requerimiento_5_funcionalidades_de_los_iconos_del_panel_deslizante>
- **Icono `add`**: el icono de adicionar permitara crear y agregar una nueva publicacion en el tab `Kitchen` de manera que sea visible para ti y para todo aquel que reciba la app con sus las publicaciones del dia y de la semana o del mes. LAS ESPCIFICACIONES PARA CREAR CADA PUBLICACION COINCIDEN CON LOS REQUERIMIENTOS: <requerimiento_2_publicaciones> y <requerimiento_3_funcionalidades_de_los_iconos_en_las_publicaciones>.
- **Icono `delete`**: Permite eliminar la publicacion del `Kitchen` y/o el `hallway` segun se seleccione. La eliminacion de una publicacion lleva confirmacion de la accion. Al eliminar una publicacion especificamente del `hallway` dejara de mostrarce para todos los usuarios que esten usando la app web.
- **Icono `IA`**: el icono de IA permitira establecer una conversacion con el sistema donde pueda realizar todas las consultas o querys sobre la totalidad del sistema, filtrados, publicaciones, busquedas, notificaciones y otro tipo de acciones. Esta especificacion sera determinada en otra etapa. 
</requerimiento_5_funcionalidades_de_los_iconos_del_panel_deslizante>

<requerimiento_6_funcionalidades_de_notificaciones>
El icono de notificaciones sera similar al de Twitter, una campanita que cuando lea una notificacion desde el endpoint ponga un numero concecutivo.
Estara trabajando en segundo plano escuchando cualquier notificacion que envie el endpoint del backend `fastapi_service` y acumulando las notificaciones. Cuando el usuario abra las notificaciones deberan mostrarce en un panel de lectura. Automaticamente quedara limpio el avizo en forma numerica dando como leida las notificaiones pendientes del panel de notificaciones. El panel de notificaciones tendra un icono del tipo `del`,  esta opcion de borrado permitira la eliminacion de todas las notificaciones a la misma vez habilitando un circulo al lado de cada notificacion cuando la clickea permitiendo seleccionar las que desee eliminar de una en una y tambien mostrara un cuadradito superior de seleccion `all` para marcar todas las notificaciones a la misma vez que seran eliminadas al presionar el icono `acept` que se activara luego que se activen las selecciones. Siempre pedira confirmacion de la eliminacion. 

Si presionas encima de un cuadro de texto de una notificacion mostrara una opcion con icono `del` de eliminar notificacion. Permitira el marcado o seleccion de varias notificaciones al mismo tiempo mostrando similarmente la opcion de borrado. 
</requerimiento_6_funcionalidades_de_notificaciones>

<requerimiento_7_generales>
Cada accion determinada por un icono estara directamente vinculada al endpoint `Kitchen Core`. Se creara un endpoint para cada operacion via Websocket, comunicandole al backend `c:\HellenCommerce\fastapi_service\` cada accion a tomar. Cada accion estara determinada por el codigo que ya esta desplegado en `c:\HellenCommerce\fastapi_service\` que es el que se encarga de atender cada peticion o solicitud. Deberas ser extricta y revisar cuidadosamente cada implementacion en el `Kitchen Core` asociada a cualquier peticion a `c:\HellenCommerce\fastapi_service\`. De no existir o tener dudas de su implementacion deberas ofrecerme una solucion profesional y de alto nivel resolutivo, con manejo de errores y desconexion para desarrollarlo en el backend `c:\HellenCommerce\fastapi_service\`.
</requerimiento_7_generales>

Las opciones de delete de cada requerimiento ejecutaran el borrado exclusivamente de la aplicacion `Room` dejando de mostrarlas en el muro personal `Kitchen` y en las publicaciones que hacen diariamente los usuarios que se muestran en `hallway`, incluyendo en las que sigues y etiquetas como siguiendo en `youroom` manteniendolas en la base de datos `hellecommerce` para futuro analisis estadistico. La base de datos `hellencommerce.db` debera contener en la tabla `marketplace` un campo `showthis` que marque en 0 si la publicacion fue marcada como eliminada y en 1 si aun se mantiene visible para la aplicacion. Bajo ningun concepto se borraran las publicaciones de la base de datos.

# CONTINUIDAD
Esta es la segunda etapa que define arquitectura del sistema, componentes, reglas, tecnologias, modelo de datos, requisitos funcionales y de implementacion para dar paso a la siguiente etapa.

# Etapa 3: Implementacion.
## Implementacion: requerimientos de codigo, logica de negocio, estructura de carpetas, modelos, endpoints, base de datos y validaciones.

# REQUERIMIENTOS ESTRICTOS DE CÓDIGO
<requerimiento_1_generales>
Se implementara en lenguaje Go en su totalidad. Utilizaras POO para cada solucion. Manejaras separacion de funciones, clases y el uso de MVC para una solucion totalmente escalable, refactorizable y modular. Cada nueva funcionalidad debera agregarse con una solucion simple para el crecimiento , depuracion y mantenibilidad, adicionando un endpoint a `Kitchen Core`, un pluggin o componente y una solucion para el endpoint `c:\HellenCommerce\fastapi_service\`.
</requerimiento_1_generales>

<requerimiento_2_interfaz_de_autenticacion>
La interfaz de autenticacion sera con firebird de google, una interfaz simple que permita mediate google entrar al sistema y ser registrado en la base de datos del backend `c:\HellenCommerce\fastapi_service\`. Tu usario de google sera tu usuario del sistema y sera el que le pases al backend `c:\HellenCommerce\fastapi_service\` como `user`.
</requerimiento_2__interfaz_de_autenticacion>

<requerimiento_3_Api_y_endpoint_de_fastapi>
El `fastapi_service` de HellenCommerce cuenta con los siguientes endpoints operativos. Cada funciionalidad esta descrita en los comentarios del codigo de la funcion `main.py` pero su logica infiere su funcionalidad:
- `@app.websocket("/ws/{user_id}")`
- `@app.post("/user/{user_id}/chat")`
- `@app.post("/user/{user_id}/notificacion/{notif_id}/leida")`
- `@app.get("/user/{user_id}/conversations/last5")`
- `@app.get("/user/{user_id}/conversations/{conversation_id}")`
- `@app.post("/user/{user_id}/conversations")`
- `@app.post("/user/{user_id}/conversations/{conversation_id}/messages")`
- `@app.get("/business/{business_id}/products")`
- `@app.post("/business/{business_id}/products")`
- `@app.post("/user/{user_id}/business/by_bounds")`
- `@app.get("/user/{user_id}/business/nearby")`
- `@app.post("/user/{user_id}/location")`
- `@app.post("/user/{user_id}/comm/status")`
- `@app.get("/user/{user_id}/comm/info")`
- `@app.post("/api/auth/google")`
- `@app.get("/health")`

`c:\HellenCommerce\app\adapters\db\SQLiteAdapter.py` es el fichero que contiene el codigo para la creacion de la base de datos inicial (ya existe en el backend). Cada metodo asociado al endpoint `Kitchen Core` debera tener una contra parte en `c:\HellenCommerce\fastapi_service\main.py` que lo resuelva. Cada metodo en el endpoint `Kitchen Core` se correspondera con los REQUERIMIENTOS ESTRICTOS DE IMPLEMENTACION descritos. <requerimiento_5_funcionalidades_de_los_iconos_del_panel_deslizante>

La base de datos `hellencommerce.db` del backend `fastapi_service` esta alojada en `c:\HellenData\sqlite_store\hellencommerce.db` y esta formada por las siguientes tablas y campos descritos en `c:\HellenCommerce\app\adapters\db\SQLiteAdapter.py`:

usuarios (
                user_id TEXT PRIMARY KEY,
                tipo TEXT,
                mercancia TEXT,
                estado TEXT,
                current_product_query TEXT,
                product_state TEXT,
                last_vendor TEXT,
                contexto TEXT,
                lat REAL,
                lon REAL, 
                comm_status TEXT DEFAULT 'online',
                social_links TEXT,
                timestamp TEXT
            )
marketplace (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                tipo TEXT,
                nombre TEXT,
                mercancia TEXT,
                categoria_negocio TEXT,
                servicio TEXT,
                tags TEXT,
                tamaños TEXT,
                precio REAL,
                ubicacion TEXT,
                lat REAL,
                lon REAL,
                telefono TEXT,
                correo TEXT,
                contacto TEXT,
                domicilio INTEGER,
                estado TEXT,
                contexto TEXT,
                timestamp TEXT,
                acepta_notificaciones INTEGER,
                canal TEXT,
                preferencias TEXT,
                current_product_query TEXT,
                product_state TEXT,
                last_vendor TEXT,
                comm_status TEXT DEFAULT 'online',
                social_links TEXT
            )
alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                tipo TEXT,
                item TEXT,
                estado TEXT DEFAULT 'activo',
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
notificaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                tipo TEXT,
                mensaje TEXT,
                estado TEXT DEFAULT 'pendiente',
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                fecha_envio TIMESTAMP,
                fecha_lectura TIMESTAMP
            )

Consultaras cada tabla y cada campo involucrado en la creacion de cada nueva funcionalidad del `Kitchen Core`. Luego de crear la funcionalidad o endpoint deberas testearla en tiempo de diseno para verificar que sean correctos los resultados esperados.

Verifica que al crear los metodos de consulta en el endpoind de `Kitchen Core` al endpoint del backend `fastaapi_service` asocies correctamente la consulta a los campos existentes en las tablas de `hellencommerce.db`. Para ello se te facilita arriba las tablas de la base datos `hellencommerce.db`.

No crearas nuevas tablas. SI necesitas crear un campo nuevo o tabla nueva deberas justificarlo. Lo haras modificando o adicionando el codigo de creacion/insercion de las tablas en `c:\HellenCommerce\app\adapters\db\SQLiteAdapter.py` a la base de datos `hellencommerce.db`. Toda la logica de la consultas a las tablas sera delegada al adaptador de Sql `c:\HellenCommerce\app\adapters\db\SQLiteAdapter.py` que es el que maneja la logica de bases de datos.
</requerimiento_3_Api_y_endpoint_de_fastapi>

# CONTINUIDAD
Esta es la tercera etapa que define Implementacion, requerimientos de codigo, logica de negocio, estructura de carpetas, modelos, endpoints, base de datos y validaciones.

# ULTIMA ETAPA: Requisitos de Bases de datos y despliegue. 
## Instalación y Despliegue de webserver, requisitos de consultas a la base de datos y requerimientos de IA. Integracion con las etapas anteriores y ejecucion de la solucion. Resultado final. 

### Requisitos
- **Go 1.22+** + **Go Web Server**
- **Python 3.11+** (Para el backend de HellenCommerce)

### Codigo para despliegue del Web Server (.\start.ps1)
    $ErrorActionPreference = 'Stop'

    Write-Host '==========================================' -ForegroundColor Cyan
    Write-Host ' Iniciando Room v1.0.0 (Go Web Server) ' -ForegroundColor Cyan
    Write-Host '==========================================' -ForegroundColor Cyan

    if (-not (Get-Command 'go' -ErrorAction SilentlyContinue)) {
        Write-Host 'Error: go no esta instalado o no se encuentra en el PATH.' -ForegroundColor Red
        exit 1
    }

    if (-not (Test-Path '.env')) {
        Write-Host 'No se encontro el archivo .env. Creando uno a partir de .env.example...' -ForegroundColor Yellow
        if (Test-Path '.env.example') {
            Copy-Item '.env.example' '.env'
            Write-Host 'Archivo .env creado.' -ForegroundColor Green
        }
    }

    Write-Host 'Verificando dependencias...'
    go mod tidy

    Write-Host 'Levantando servidor...' -ForegroundColor Green
    Write-Host 'Presiona Ctrl+C para detener el servidor.' -ForegroundColor Gray
    go run main.go

# REQUERIMIENTOS ESTRICTOS DE BASE DE DATOS
Para ello consultaras todos y cada uno de los `REQUERIMIENTOS ESTRICTOS DE CODIGO`, especificamente las tablas de la base de datos `hellencommerce.db`del backend `fastapi_service`. 

## Cada inserccion en la base de datos estara formada por: 
- **un user_id**, **tipo**, **nombre**, **mercancia**, **tamaños**, **precio**, **ubicacion**, **telefono**, **correo**, **contacto**, 
**domicilio**, **estado**, **contexto**
ej: nuevos = [
        ("60000011", "vendedor", "Raúl Medina", "Arroz brasileño", "saco de 25kg", 22.0,
         "La Habana", "60000011", "raul.medina@ejemplo.com", "Raúl Medina", 1, "activo",
         "USUARIO: Tengo arroz brasileño en sacos de 25kg, buena calidad.\nIA: Entendido, lo registro.")

## Tambien tenemos como ejemplo en la misma tabla `usuarios` otra inserccion en otros campos:
 INSERT INTO usuarios (
        user_id, tipo, nombre, mercancia, precio, ubicacion,
        telefono, correo, domicilio, estado
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "60000031", "vendedor", "Juan Pérez",
        "detergente líquido marca brillo",
        5.5, "Santiago de Cuba",
        "5551234", None, 0, "activo"

## Este ejemplo es para proporcionar la ubicacion actual:

"SELECT id, ubicacion FROM marketplace")
 UPDATE marketplace
            SET lat = ?, lon = ?
            WHERE id = ?
        """, (lat, lon, negocio_id))

## ej: COORDENADAS_PROVINCIAS = 
 "Pinar del Río": (22.4173, -83.6987),

## Este es un ejemplo para poblar un negocio:
  ("Corte Clásico", "barberia", "corte de pelo", ["barberia", "clasico"], "Avenida 10 #234, Playa", 15, "535-234-5678"),

 INSERT INTO usuarios (user_id, tipo, nombre, mercancia, estado, contexto)
        VALUES (?, 'vendedor', ?, ?, 'activo', '')
    """, (user_id, nombre, categoria))

 INSERT INTO marketplace (
            user_id, tipo, nombre, mercancia, categoria_negocio, servicio, tags,
           precio, ubicacion, telefono, estado, timestamp
        )
        VALUES (?, 'vendedor', ?, ?, ?, ?, ?, ?, ?, ?, 'activo', ?)
    """, (
        user_id, nombre, categoria, categoria, servicio,
        json.dumps(tags), precio, ubicacion, telefono,
        datetime.now().isoformat()

Todos los elementos son recogidos de la interfaz de `Room` y enviado al backend `fastapi_service`. El `user_id` es un valor automatico numerico.
El resto de los elementos se recojen de cada publicacion o de la interaccion con el agente de IA.

# REQUERIMIENTOS ESTRICTOS DE IA
El icono de IA sera visible desde cualquier parte de la app. Estara en la barra inferior junto a `add`, `del` al final a la derecha.
Cuando se clickea sobre el icono se abre un panel de IA al estilo de `Grok` o `Copilot` con un boton habilitado de enviar `send` con una flechita como indicador. El panel de conversacion debera mostrar toda la conversacion actual. Debera tener un panel lateral recogido para mostrar el historial de las conversaciones. Cada nueva conversacion quue se crea la maneja el endpoint `fastapi_service` `@app.post("/user/{user_id}/conversations")`.
Tendra la opcion de eliminar `del` historial o parte del historial o una conversacion en especifico similar a las descrita anteriormente. 
El agente de IA envia la solicitud al endpoint `Kitchen Core` y este la procesa para el envio o recepcion de la respuesta directamente con el backend `fastapi_service` al endpoint  `@app.websocket("/ws/{user_id}")`

# Continuidad
## Esta es la culminacion de la ultima etapa

# RESULTADO ESPERADO
Entrégame el código limpio, optimizado y puramente en Go correspondiente a la primera etapa, listo para el despliegue o deploy. El cual guardaras en el directorio local `c:\Klinee_Solutions\Room\`). Usa los SDKs oficiales ligeros, CSS para lograr vistas totalmente profesionales, y garantiza que los archivo esten completamente libre de dependencias pesadas locales o remotas.
