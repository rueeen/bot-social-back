# Ecoforo: laboratorio de opinión y bots declarados

Backend Django 5.2 + DRF + SimpleJWT, SQLite y controlador Python local. Código preparado en el checkout `bot-social-back` para el proyecto `ecoforo-back`. El frontend React (`ecoforo-front`) es un repositorio independiente; aquí no se implementa el gráfico ni la interfaz React.

El servidor almacena hilos, comentarios, corridas, agentes lectores y snapshots. Solo hace estadística: **no importa Anthropic ni Playwright ni inicia procesos de simulación**. El controlador `simulador/` se ejecuta en el notebook del presentador. PythonAnywhere atiende solicitudes síncronas con un worker, sin Celery, threads, websockets ni servicios always-on.

## Instalación local

Requiere Python 3.11 o superior (validado con 3.12). Desde la raíz del repositorio:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Usa el valor generado como `SECRET_KEY`; genera otro para `BOT_TOKEN`. No reutilices claves de desarrollo en producción. Edita `.env` (ignorado por Git):

- `DEBUG=True` para desarrollo; `False` en PythonAnywhere.
- `ALLOWED_HOSTS=localhost,127.0.0.1` en local, o el dominio del backend en producción, sin esquema.
- `CORS_ALLOWED_ORIGINS`: orígenes completos separados por coma, por ejemplo `https://tu-foro.netlify.app,http://localhost:5173`.
- `CSRF_TRUSTED_ORIGINS`: orígenes completos de confianza, incluido el dominio HTTPS del admin cuando corresponda.
- `BOT_TOKEN`: secreto compartido solo con el notebook; vacío desactiva los privilegios de bot.

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py cargar_palabras
python manage.py runserver --noreload --nothreading
```

El superusuario sirve como presentador; también puedes crear un usuario `is_staff` en el admin. Los alumnos no necesitan cuentas. No incluyas claves de Anthropic en el `.env` del servidor.

Pruebas y comprobaciones:

```bash
python manage.py test foro
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py collectstatic --noinput
```

`SECRET_KEY` es obligatoria incluso para ejecutar los tests. `test foro` usa una base temporal; no modifica la base del foro.

## API y permisos

Respuestas JSON, errores `{"error":"mensaje en español"}`, sin paginación DRF. Los identificadores del hilo se usan en las rutas que siguen.

| Método | Ruta | Acceso / función |
| --- | --- | --- |
| POST | `/api/token/` | `username`, `password`; devuelve `access`, `refresh` |
| POST | `/api/token/refresh/` | `refresh`; renueva `access` |
| GET | `/api/hilos/` | Público; incluye `n_comentarios` |
| GET | `/api/hilos/1/` | Detalle público |
| GET, POST | `/api/hilos/1/comentarios/` | Leer o comentar |
| GET | `/api/hilos/1/corridas/` | Escenarios del hilo |
| GET | `/api/hilos/1/snapshots/?corrida=2` | Serie para el dashboard |
| POST | `/api/panel/hilos/` | Crear hilo: `titulo`, `tema`, `pregunta_postura` |
| PATCH | `/api/panel/hilos/1/` | Editar datos / `estado` |
| POST | `/api/panel/hilos/1/corridas/` | `etiqueta`, `mezcla_bots`, `semilla` |
| PATCH | `/api/panel/corridas/2/` | Cerrar corrida; cuerpo `{}`, idempotente |
| POST | `/api/panel/corridas/2/sembrar/` | `n`, `media`, `dispersion` |
| GET | `/api/panel/corridas/2/agentes/` | Población y cursores de lectura |
| PATCH | `/api/panel/agentes/3/` | `postura_actual`, `ultimo_comentario_leido_id` |
| POST | `/api/panel/corridas/2/snapshots/` | Guardar estadísticas proporcionadas |
| POST | `/api/panel/corridas/2/snapshot_auto/` | Calcular estadísticas actuales |

Todo `/api/panel/` requiere `Authorization: Bearer <access>` de un usuario `is_staff`. El token de bot **no** concede acceso al panel. La obtención/renovación de JWT se limita a 10 solicitudes por minuto por IP con LocMem.

Comentario humano: `{"autor_nombre":"Ana","texto":"Considero ambas alternativas"}`. Con `X-Bot-Token` válido puede añadirse `"es_bot":true,"postura_bot":"favor","corrida":2`. Las posturas son `favor`, `contra`, `neutral`. Sin token válido se fuerza humano, postura nula y corrida nula, incluso si el cliente intenta marcarlos. El nombre visible de bot no reemplaza la marca validada por el servidor. Un hilo cerrado acepta GET pero rechaza POST de comentarios con 403 y `{"error":"El hilo está cerrado"}`.

Lectura incremental: `/api/hilos/1/comentarios/?desde_id=0&corrida=2` devuelve `{"comentarios":[...],"ultimo_id":N}` con máximo 100 elementos en orden ascendente de ID. Repetir con `desde_id=N` hasta recibir menos de 100; sin comentarios conserva el cursor recibido. Con `corrida=2` incluye los comentarios de ese escenario y los humanos compartidos (`corrida=null`), excluyendo los bots de otras corridas. Sin filtro devuelve todos los comentarios del hilo. Los snapshots admiten también `desde_id` y se ordenan por corrida/ronda. Las lecturas del dashboard son públicas: puede consultar periódicamente corridas y snapshots para comparar curvas, sin websockets.

Siembra: entre 1 y 500 lectores, posturas normales recortadas a [-100,100], apertura en [0.1,0.6] y perfiles variados. La misma semilla, cantidad, media y dispersión reproducen **posturas, aperturas y perfiles**; la mezcla no interviene en esa generación. Se rechaza una segunda siembra para no sobrescribir una corrida; crea otra. Las corridas cerradas no admiten cambios de agentes, snapshots ni comentarios asociados.

`snapshot_auto` acepta `{}`: ronda 0 inicialmente, luego la siguiente. Opcionalmente acepta `{"ronda":3}` y rechaza duplicados. Devuelve promedio, desviación **poblacional**, histograma y conteos acumulados de bots por postura de esa corrida. El histograma es un objeto de diez claves `"-100", "-80", …, "80"`: tramos de ancho 20, cerrados a izquierda y abiertos a derecha salvo el último, que incluye +100. El snapshot manual exige el mismo formato y que los conteos por postura sumen el total de bots.

En el admin, todos los modelos tienen filtros por hilo y/o corrida. La acción **Reiniciar simulación** en Hilo elimina agentes, snapshots, corridas y comentarios de bot; conserva el hilo y todos los comentarios humanos. Es una acción destructiva para los resultados del experimento: exporta lo necesario antes de usarla.

## Moderación

`foro/moderacion.py` normaliza minúsculas, tildes, leet y repeticiones. Compara palabras completas con `foro/palabras_bloqueadas.txt`, evitando bloquear «computador». Rechaza enlaces comunes, teléfonos y más de 400 caracteres; comprueba también el nombre. Es un filtro pedagógico simple, no un clasificador exhaustivo de evasiones.

Después de editar la lista ejecuta `python manage.py cargar_palabras` para validarla y reinicia/Reload el servidor para refrescar el proceso WSGI. No requiere una tabla de palabras. Humanos: un comentario cada 5 segundos por `REMOTE_ADDR`, con caché LocMem. Los bots válidos se saltan solo el rate-limit, no la moderación. Si pones un proxy delante, verifica cómo entrega la IP real; no se confía en `X-Forwarded-For` suministrado por clientes. LocMem corresponde al diseño de un worker; sus límites se reinician al recargar.

## Despliegue en PythonAnywhere

1. En una consola Bash, clona tu repositorio con el código (ajusta la URL si conservas el nombre `bot-social-back`):

   ```bash
   git clone https://github.com/rueeen/ecoforo-back.git
   cd ~/ecoforo-back
   python3.12 -m venv ~/.virtualenvs/ecoforo
   source ~/.virtualenvs/ecoforo/bin/activate
   pip install -r requirements.txt
   cp .env.example .env
   ```

2. Edita `.env` con claves nuevas, `DEBUG=False`, `ALLOWED_HOSTS=TU_USUARIO.pythonanywhere.com`, el origen HTTPS real de Netlify y `http://localhost:5173` en CORS, y los orígenes de confianza CSRF. Mantén el archivo privado (`chmod 600 .env`). No instales `simulador/requirements.txt` en el servidor.

3. Prepara SQLite y estáticos:

   ```bash
   python manage.py migrate
   python manage.py createsuperuser
   python manage.py cargar_palabras
   python manage.py collectstatic --noinput
   python manage.py check --deploy
   ```

4. En **Web → Add a new web app**, selecciona configuración manual y la misma versión de Python. Configura el virtualenv `/home/TU_USUARIO/.virtualenvs/ecoforo` y el directorio de código `/home/TU_USUARIO/ecoforo-back`. Un worker basta; no crees tareas always-on.

5. Reemplaza el contenido del WSGI del panel Web por lo siguiente, ajustando el usuario y la carpeta:

   ```python
   import os
   import sys
   from dotenv import load_dotenv

   ruta = '/home/TU_USUARIO/ecoforo-back'
   if ruta not in sys.path:
       sys.path.insert(0, ruta)
   load_dotenv(os.path.join(ruta, '.env'))
   os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ecoforo.settings')
   from django.core.wsgi import get_wsgi_application
   application = get_wsgi_application()
   ```

6. En **Static files**, agrega `/static/` → `/home/TU_USUARIO/ecoforo-back/staticfiles` y `/media/` → `/home/TU_USUARIO/ecoforo-back/media` (crea `media` si la usarás; actualmente no hay subidas). Django no sirve estos archivos en producción.

7. Configura HTTPS en el panel, pulsa **Reload** y comprueba `/api/hilos/`, `/admin/` y un inicio de sesión JWT desde tu notebook. Los cookies del admin son seguros con `DEBUG=False`. El control de redirección HTTPS/HSTS depende de tu dominio y proxy; revisa las advertencias de `check --deploy` antes de habilitarlo, sin confiar en headers de proxy desconocidos. Para actualizaciones: copia de SQLite, `git pull`, activar virtualenv, instalar requisitos, `migrate`, `collectstatic`, Reload.

No se hizo un despliegue remoto desde este repositorio. La API no necesita llamadas salientes a Anthropic y sus limitaciones de salida en PythonAnywhere no afectan el controlador local.

## Simulador en el notebook

Desde la raíz del proyecto, en el equipo con navegador/pantalla:

```bash
source .venv/bin/activate
pip install -r simulador/requirements.txt
python -m playwright install chromium
cp simulador/.env.example simulador/.env
```

En Linux, si faltan bibliotecas del navegador, instala las dependencias oficiales con `python -m playwright install-deps chromium` según los permisos de tu equipo. En la nube se puede usar un Chromium ya instalado configurando `CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium`; omite esa variable en tu notebook para usar el Chromium de Playwright.

Completa `API_URL` (con `/api`, sin slash final), `FRONT_URL` (origen del frontend), credenciales del presentador y `BOT_TOKEN` igual al backend. Las credenciales y el token se guardan solo en `simulador/.env`, ignorado por Git. El cliente obtiene JWT y renueva el access al expirar. Nunca muestra contraseñas ni tokens en sus mensajes.

`ANTHROPIC_API_KEY` es **opcional** y solo va aquí: vacía activa plantillas y heurística sin llamadas externas. `MODELO_IA` tiene el valor solicitado `claude-haiku-5-5`; para usar IA confirma en tu cuenta que ese identificador existe y está habilitado y cámbialo si corresponde. El modo con IA requiere acceso de tu notebook a Anthropic. Los errores de proveedor/JSON se propagan para que no se confundan con resultados de heurística. No se comprobó un modelo remoto sin credenciales.

### Contrato con el frontend separado

Antes de ejecutar bots sobre el frontend React, implementa este contrato en `ecoforo-front`:

- Ruta de hilo `/hilos/:id`; formulario con inputs `name="autor_nombre"`, `name="texto"` y botón `type="submit"`. Ajustables mediante `RUTA_HILO`, `SELECTOR_NOMBRE`, `SELECTOR_TEXTO`, `SELECTOR_ENVIAR` en el `.env` del simulador.
- Al enviar el formulario, lee **en ese momento** las claves locales `bot_token`, `es_bot`, `postura_bot`, `corrida`. Si `es_bot === "true"`, envía `es_bot: true`, `postura_bot` y `corrida: Number(...)` y el header `X-Bot-Token` al backend configurado. No guardes ni empaquetes un token real dentro del código React ni en variables públicas de Netlify.
- Muestra siempre el indicador **BOT** y la postura a partir de la respuesta validada del servidor. El navegador dedicado del presentador conserva el token en localStorage para esta demo; no debe compartirse con alumnos. Cierra el contexto al terminar (el simulador lo hace).
- Los bots rellenan el formulario real y esperan su respuesta HTTP 201; verifican que la API confirmó bot, postura y corrida. No interceptan ni sustituyen la publicación con llamadas API ocultas.
- El dashboard consulta snapshots por corrida y grafica `ronda` frente a `promedio`; usa `n_favor`, `n_contra`, `n_neutral` y sus diferencias por ronda como marcas de actividad. Conserva etiquetas de cada corrida y una escala fija [-100,100].

### Ejecutar y comparar escenarios

Crea un hilo en el admin o con `POST /api/panel/hilos/`, y usa su ID. Con el mismo hilo, población, semilla, media y dispersión:

```bash
python -m simulador.orquestador --hilo 1 --etiqueta "sin bots" --mezcla favor=0,contra=0,neutral=0 --poblacion 30 --media -20 --dispersion 40 --rondas 5 --semilla 42
python -m simulador.orquestador --hilo 1 --etiqueta "solo a favor" --mezcla favor=4,contra=0,neutral=0 --poblacion 30 --media -20 --dispersion 40 --rondas 5 --semilla 42 --lento
python -m simulador.orquestador --hilo 1 --etiqueta "a favor+en contra" --mezcla favor=2,contra=2,neutral=0 --poblacion 30 --media -20 --dispersion 40 --rondas 5 --semilla 42 --lento
python -m simulador.orquestador --hilo 1 --etiqueta "solo neutrales" --mezcla favor=0,contra=0,neutral=4 --poblacion 30 --media -20 --dispersion 40 --rondas 5 --semilla 42 --lento
```

Por defecto Playwright abre un navegador **visible**. `--headless` sirve solo para validación automatizada. Sin bots, el controlador no abre navegador. Flujo: corrida → siembra → snapshot 0 → por ronda, comentarios visibles y lectura de cada agente → snapshot automático → cerrar corrida. Cada comentario corresponde a un bot de la mezcla por ronda. `avanzar_ronda(corrida_id)` puede importarse desde `simulador.poblacion_lectores`.

En heurística, favor empuja +24 y contra -24; neutral y humanos aportan 0. Se promedia ese empuje y se aplica apertura, más ruido uniforme [-1,1]; el resultado se recorta a [-100,100]. Sin comentarios nuevos la postura permanece igual. La fórmula depende del promedio, no aumenta linealmente con el número de mensajes idénticos: el volumen cambia la proporción de exposición frente a otras posturas. No es una calibración científica. Con IA se aplica `actual + apertura * (sugerida - actual)` y se delimitan los comentarios como datos no confiables, nunca instrucciones.

Los comentarios humanos sin corrida se comparten entre escenarios. Para una comparación controlada, evita agregar nuevos comentarios humanos entre corridas, o usa hilos separados con las mismas condiciones. Los bots de una corrida nunca se leen desde otra. Las semillas reproducen la población y los aleatorios locales; un proveedor IA remoto no garantiza resultados idénticos. Si el proceso falla a mitad de una ronda, la corrida queda abierta para diagnóstico; no se reintenta automáticamente una ronda parcial que podría duplicar comentarios.

## Para la charla

**Astroturfing** es la fabricación de una apariencia de apoyo ciudadano espontáneo mediante actividad coordinada. Una **cámara de eco** refuerza una postura al repetir mensajes similares y reducir la exposición a otras perspectivas. En este laboratorio los participantes ven cómo cambia una distribución de opiniones al variar la exposición.

Es una **simulación ética**: sitio propio y cerrado, lectores sintéticos, sin cuentas ni acciones sobre plataformas reales, y bots siempre declarados con su postura visible. No se engaña a participantes sobre la identidad automatizada. El acceso público de lectura significa «sin login»; si necesitas un recinto realmente privado, restringe el acceso al sitio en el despliegue.

Compara las curvas y el histograma, no solo el promedio: ¿un lado repetido domina la exposición?, ¿cambian más los lectores con mayor apertura?, ¿el equilibrio reduce el desplazamiento? Que un bot lleve etiqueta no impide que el modelo de lectores procese su argumento. El promedio puede moverse si un lado inunda el hilo, pero aquí el cambio sigue las reglas explícitas de una heurística o las respuestas de un modelo: **no demuestra causalidad ni predice opiniones de personas reales**.

## Validación de integración y entorno en la nube

`scripts/configurar_entorno.sh` instala ambos grupos de dependencias para desarrollo, crea un `.env` local con claves aleatorias solo si no existe, aplica migraciones y prepara estáticos. Preserva la configuración existente. No es el instalador de producción: en PythonAnywhere instala únicamente `requirements.txt`.

Con los puertos 8000 y 5173 libres y Chromium disponible:

```bash
.venv/bin/python scripts/prueba_integracion.py
```

La prueba levanta Django sin threads y un formulario temporal en servidores locales, ejecuta el orquestador real para cuatro escenarios de dos rondas y seis lectores, valida semillas, snapshots, etiquetas de bot y cierre, y elimina sus datos y procesos al terminar. Usa un presentador temporal con credenciales aleatorias que no imprime. No llama a Anthropic. El formulario temporal verifica el contrato de Playwright; no reemplaza la prueba de integración con el frontend React real.

Validación realizada en este entorno: 21 tests de Django, migraciones, carga de palabras, archivos estáticos y los cuatro escenarios anteriores con Chromium del sistema. Los escenarios comenzaron en promedio -31,67; después de dos rondas, sin bots quedó en -31,67 y solo a favor llegó a -16,04. Estos resultados pertenecen a la heurística configurada. No se validó el despliegue de PythonAnywhere, el frontend separado ni un proveedor IA remoto.
