import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from rest_framework.exceptions import ValidationError

RUTA_PALABRAS = Path(__file__).with_name('palabras_bloqueadas.txt')

def normalizar(texto):
    texto = ''.join(c for c in unicodedata.normalize('NFD', texto.lower()) if unicodedata.category(c) != 'Mn')
    texto = texto.translate(str.maketrans({'0': 'o', '1': 'i', '3': 'e', '4': 'a', '5': 's', '7': 't', '@': 'a', '$': 's'}))
    return re.sub(r'(.)\1+', r'\1', texto)

@lru_cache(maxsize=1)
def palabras():
    return {normalizar(p.strip()) for p in RUTA_PALABRAS.read_text(encoding='utf-8').splitlines() if p.strip() and not p.startswith('#')}

def moderar(texto):
    if len(texto) > 400:
        raise ValidationError('El comentario no puede superar 400 caracteres')
    if re.search(r'(?:https?|ftp)://|www\.|\b(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}\b', texto, re.I):
        raise ValidationError('No se permiten enlaces')
    if re.search(r'(?<!\w)\+?\d[\d ()-]{6,}\d(?!\w)', texto):
        raise ValidationError('No se permiten teléfonos')
    # Palabras completas: evita falsos positivos como «computador».
    if set(re.findall(r'[a-z]+', normalizar(texto))) & palabras():
        raise ValidationError('El comentario contiene palabras no permitidas')
