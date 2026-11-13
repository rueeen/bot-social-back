import functools
import http.server
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time
import urllib.request

raiz = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(raiz))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ecoforo.settings')
import django
django.setup()
from django.conf import settings
from django.contrib.auth import get_user_model
from foro.models import Hilo, Corrida

# Solo datos temporales: se eliminan en finally, sin mostrar credenciales.
usuario = 'smoke_' + secrets.token_hex(4)
clave = secrets.token_urlsafe(24)
presentador = get_user_model().objects.create_user(usuario, password=clave, is_staff=True)
hilo = Hilo.objects.create(titulo='Prueba temporal', tema='Celulares en clases', pregunta_postura='¿Prohibir celulares?', creado_por=presentador)
procesos = []
try:
    with tempfile.TemporaryDirectory(prefix='ecoforo-smoke-') as temporal:
        carpeta = Path(temporal)
        pagina = '''<!doctype html><meta charset="utf-8"><form><input name="autor_nombre"><textarea name="texto"></textarea><button type="submit">Publicar</button></form><ul id="comentarios"></ul><script>
        document.querySelector('form').onsubmit=async e=>{
          e.preventDefault();
          const datos={autor_nombre:document.querySelector('[name=autor_nombre]').value,texto:document.querySelector('[name=texto]').value,
            es_bot:localStorage.getItem('es_bot')==='true',postura_bot:localStorage.getItem('postura_bot'),corrida:Number(localStorage.getItem('corrida'))};
          const respuesta=await fetch('http://127.0.0.1:8000/api/hilos/HILO/comentarios/',{method:'POST',headers:{'Content-Type':'application/json','X-Bot-Token':localStorage.getItem('bot_token')},body:JSON.stringify(datos)});
          const comentario=await respuesta.json();
          const item=document.createElement('li');item.textContent=(comentario.es_bot?'BOT '+comentario.postura_bot+': ':'')+comentario.texto;document.querySelector('ul').append(item);
        };</script>'''.replace('HILO', str(hilo.id))
        destino = carpeta / 'hilos' / str(hilo.id)
        destino.mkdir(parents=True)
        (destino / 'index.html').write_text(pagina)
        registros = open(carpeta / 'servidores.log', 'w')
        procesos.append(subprocess.Popen([sys.executable,'manage.py','runserver','127.0.0.1:8000','--noreload','--nothreading'],cwd=raiz,stdout=registros,stderr=registros))
        procesos.append(subprocess.Popen([sys.executable,'-m','http.server','5173','--bind','127.0.0.1','--directory',str(carpeta)],stdout=registros,stderr=registros))
        for intento in range(50):
            try:
                with urllib.request.urlopen('http://127.0.0.1:8000/api/hilos/', timeout=2) as respuesta:
                    assert respuesta.status == 200
                with urllib.request.urlopen('http://127.0.0.1:5173/', timeout=2) as respuesta:
                    assert respuesta.status == 200
                break
            except OSError:
                time.sleep(.2)
        else:
            raise RuntimeError('Los servidores de prueba no iniciaron')
        entorno = dict(os.environ, API_URL='http://127.0.0.1:8000/api',FRONT_URL='http://127.0.0.1:5173',
            PRESENTADOR_USER=usuario,PRESENTADOR_PASS=clave,BOT_TOKEN=settings.BOT_TOKEN,ANTHROPIC_API_KEY='',CHROMIUM_EXECUTABLE_PATH=os.environ.get('CHROMIUM_EXECUTABLE_PATH', '/usr/bin/chromium' if Path('/usr/bin/chromium').exists() else ''))
        for etiqueta, mezcla in [('sin bots','favor=0,contra=0,neutral=0'),('solo favor','favor=2,contra=0,neutral=0'),('equilibrio','favor=1,contra=1,neutral=0'),('neutrales','favor=0,contra=0,neutral=2')]:
            salida = subprocess.run([sys.executable,'-m','simulador.orquestador','--hilo',str(hilo.id),'--etiqueta',etiqueta,'--mezcla',mezcla,'--poblacion','6','--media','-20','--dispersion','40','--semilla','42','--rondas','2','--headless'],cwd=raiz,env=entorno,capture_output=True,text=True,timeout=120)
            print(salida.stdout)
            if salida.returncode:
                print(salida.stderr)
                raise RuntimeError('Falló el escenario ' + etiqueta)
        corridas = list(Corrida.objects.filter(hilo=hilo).order_by('id'))
        iniciales = [list(c.agentes.order_by('id').values_list('postura_inicial',flat=True)) for c in corridas]
        assert all(p == iniciales[0] for p in iniciales)
        assert all(c.cerrada_en and c.snapshots.count() == 3 for c in corridas)
        finales = {c.etiqueta:c.snapshots.get(ronda=2).promedio for c in corridas}
        assert finales['solo favor'] > finales['sin bots']
        assert all(c.comentarios.filter(es_bot=False).count() == 0 for c in corridas)
        print('SMOKE OK: cuatro escenarios, semillas idénticas, 12 snapshots, bots publicados con formulario Chromium y aislamiento entre corridas.')
finally:
    for proceso in procesos:
        proceso.terminate()
        proceso.wait(timeout=10)
    hilo.delete()
    presentador.delete()
