# Guía Completa de Despliegue de Microservicios en Render

Esta guía contiene los pasos necesarios para configurar, desplegar y mantener tus microservicios activos utilizando la capa gratuita de **Render** conectada a **GitHub**.

---

## 📋 Requisitos Previos

1. Una cuenta de [Render](https://render.com).
2. Una cuenta de [GitHub](https://github.com) con el código de tus microservicios subido en repositorios (pueden ser públicos o privados).
3. Asegurarte de que tu código use la variable de entorno `PORT` dinámica (Render asigna un puerto aleatorio a cada servicio).
   - *Ejemplo en Node.js:* `const PORT = process.env.PORT || 3000;`
   - *Ejemplo en Python:* `port = int(os.environ.get("PORT", 5000))`

---

## 🛠️ Paso 1: Vincular GitHub con Render

1. Inicia sesión en el **Dashboard de Render**.
2. Ve a tu perfil (esquina superior derecha) y selecciona **Account Settings**.
3. En la sección **Connected Accounts**, busca **GitHub** y haz clic en **Connect**.
4. Autoriza el acceso. Se recomienda seleccionar *"All repositories"* o elegir específicamente los repositorios de tus microservicios.

---

## 🚀 Paso 2: Desplegar un Microservicio

Por cada microservicio que quieras levantar, repite el siguiente proceso:

1. En el panel principal de Render, haz clic en el botón azul **New +** y selecciona **Web Service**.
2. En la lista de repositorios de GitHub que aparecerá, busca el microservicio correspondiente y haz clic en **Connect**.
3. Configura el formulario con los siguientes datos:
   - **Name:** Nombre de tu servicio (ej. `microservicio-usuarios`).
   - **Region:** Selecciona la más cercana (ej. *Frankfurt* para Europa, *Ohio* o *Oregon* para América).
   - **Branch:** La rama principal (generalmente `main` o `master`).
   - **Runtime:** El lenguaje de tu app (Node, Python, Go, Docker, etc.).
   - **Build Command:** Comando para instalar dependencias.
     - *Node.js:* `npm install`
     - *Python:* `pip install -r requirements.txt`
   - **Start Command:** Comando para arrancar el servidor.
     - *Node.js:* `node server.js` (o tu archivo principal)
     - *Python:* `gunicorn app:app` o `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. **Selección de Plan:** Baja hasta la tabla de precios y marca la opción **Free ($0/mo)**.
5. Haz clic en **Create Web Service**.

---

## 🔐 Paso 3: Configurar Variables de Entorno (Conectar Microservicios)

Para que tus microservicios se comuniquen entre sí o con una Base de Datos:

1. Entra a la configuración de tu servicio en Render y ve a la pestaña **Environment**.
2. Haz clic en **Add Environment Variable**.
3. Añade las credenciales o las URLs de los otros microservicios que genera Render (ej. `AUTH_SERVICE_URL` = `https://onrender.com`).
4. Haz clic en **Save Changes**. El servicio se reiniciará automáticamente aplicando los cambios.

---

## 🔄 Paso 4: Flujo de Trabajo Diario (CI/CD Automático)

Render tiene Integración Continua nativa. Esto significa que ya no necesitas tocar el panel para actualizar tu código:

1. Realiza cambios en tu código local.
2. Sube los cambios a GitHub mediante tu terminal:
   ```bash
   git add .
   git commit -m "feat: actualización de microservicio"
   git push origin main
   ```
3. **¡Y listo!** Render detectará el *push* en GitHub de inmediato, compilará la nueva versión en segundo plano y reemplazará la vieja sin interrumpir el servicio (Zero- downtime deploy).

---

## ⏰ Paso 5: Evitar que los Microservicios se "Duerman"

> ⚠️ **Nota de la Capa Gratuita:** Si un servicio no recibe visitas en **15 minutos**, Render lo apaga temporalmente. La siguiente persona o servicio que intente consultarlo sufrirá un retraso de **50 segundos** mientras la máquina vuelve a encender.

Para solucionar esto y mantener tus microservicios despiertos 24/7 de forma gratuita:

1. Copia la URL pública que Render le dio a tu microservicio (ej. `https://onrender.com`).
2. Ve a [cron-job.org](https://cron-job.org) y crea una cuenta gratuita.
3. Haz clic en **Create Cronjob**.
4. Configura el Cron:
   - **Title:** Despertador Microservicio.
   - **Address (URL):** Pega la URL de tu servicio de Render.
   - **Schedule:** Selecciona "Every 12 minutes" (Cada 12 minutos).
5. Guarda el Cronjob. 

Al recibir una petición automática cada 12 minutos, Render asumirá que el servicio está activo y **nunca lo mandará a dormir**.
