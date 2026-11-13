import os
from pathlib import Path
from dotenv import dotenv_values

# No cargar el .env del backend ni sobrescribir sus variables en este proceso.
_ARCHIVO = dotenv_values(Path(__file__).with_name('.env'))

def obtener(nombre, defecto=''):
    return os.environ.get(nombre, _ARCHIVO.get(nombre) or defecto)

API_URL = obtener('API_URL', 'http://127.0.0.1:8000/api').rstrip('/')
FRONT_URL = obtener('FRONT_URL', 'http://localhost:5173').rstrip('/')
MODELO_IA = obtener('MODELO_IA', 'claude-haiku-5-5')

def exigir(nombre):
    valor = obtener(nombre)
    if not valor:
        raise RuntimeError(f'Configura {nombre} en simulador/.env')
    return valor
