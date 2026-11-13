#!/usr/bin/env bash
# Preparación de desarrollo en la nube; no ejecutar en PythonAnywhere.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then
    python3 -m venv .venv
fi
export PIP_CACHE_DIR="$PWD/.venv/pip-cache"
.venv/bin/python -m pip install -r requirements.txt -r simulador/requirements.txt
.venv/bin/python - <<'PY'
from pathlib import Path
import secrets
ruta = Path('.env')
if not ruta.exists():
    # Claves locales nuevas; nunca sobrescribir configuración del usuario.
    contenido = (
        'SECRET_KEY=' + secrets.token_urlsafe(48) + '\n'
        'BOT_TOKEN=' + secrets.token_urlsafe(32) + '\n'
        'DEBUG=True\n'
        'ALLOWED_HOSTS=localhost,127.0.0.1\n'
        'CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173\n'
        'CSRF_TRUSTED_ORIGINS=http://localhost:5173\n'
    )
    with ruta.open('x') as archivo:
        archivo.write(contenido)
    ruta.chmod(0o600)
PY
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py cargar_palabras
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python manage.py check
