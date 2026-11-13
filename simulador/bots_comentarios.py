import json
import random
import time
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright
from . import config
from .ia import comentario_bot
from .personas import PERSONAS

class BotsComentarios:
    def __init__(self, hilo, corrida, cliente, lento=False, headless=False, azar=None):
        self.hilo, self.corrida, self.cliente = hilo, corrida, cliente
        self.lento, self.headless = lento, headless
        self.azar = azar or random.Random()

    def asignar_personas(self):
        # Barajar una vez por corrida; el cupo conserva su estilo entre rondas.
        catalogo = list(PERSONAS)
        self.azar.shuffle(catalogo)
        cantidad = sum(self.corrida.get('mezcla_bots', {}).values())
        self.personas_por_cupo = [catalogo[i % len(catalogo)] for i in range(cantidad)]

    @staticmethod
    def nombre_bot(persona, numero):
        return f'Bot_{persona["etiqueta"]}_{numero:02}'[:30]

    def __enter__(self):
        self.asignar_personas()
        self.token = config.exigir('BOT_TOKEN')
        self.motor = sync_playwright().start()
        try:
            self.navegador = self.motor.chromium.launch(headless=self.headless, executable_path=config.obtener('CHROMIUM_EXECUTABLE_PATH') or None)
            self.contexto = self.navegador.new_context()
            self.pagina = self.contexto.new_page()
            self.destino = config.FRONT_URL + config.obtener('RUTA_HILO', '/h/{hilo}').format(hilo=self.hilo['id'])
            # El front lee estas claves y envía el token únicamente a su API configurada.
            valores = {'bot_token': self.token, 'es_bot': 'true'}
            self.contexto.add_init_script('if (location.origin === ' + json.dumps(config.FRONT_URL) + ') {' +
                ''.join('localStorage.setItem(' + json.dumps(k) + ',' + json.dumps(v) + ');' for k, v in valores.items()) +
                'if (localStorage.getItem("corrida") === null) localStorage.setItem("corrida",' + json.dumps(str(self.corrida['id'])) + ');}')
            self.pagina.goto(self.destino)
            self.pagina.evaluate('(id) => localStorage.setItem("corrida", String(id))', self.corrida['id'])
            return self
        except BaseException:
            # También liberar Playwright si Ctrl-C llega durante el inicio.
            self.motor.stop()
            raise

    def cambiar_corrida(self, corrida):
        # El script de inicio no fija la corrida: no debe restaurar un ID antiguo al navegar.
        self.corrida = corrida
        self.asignar_personas()
        self.pagina.evaluate('(id) => localStorage.setItem("corrida", String(id))', corrida['id'])
        self.pagina.goto(self.destino)

    def publicar_ronda(self):
        previos = self.cliente.comentarios(self.hilo['id'], self.corrida['id'], 0)
        numero = 0
        for postura, cantidad in self.corrida['mezcla_bots'].items():
            for _ in range(cantidad):
                numero += 1
                persona = self.personas_por_cupo[numero - 1]
                texto = comentario_bot(postura, self.hilo['tema'], self.hilo['pregunta_postura'], previos, self.azar, persona=persona)
                self.pagina.evaluate('(p) => localStorage.setItem("postura_bot", p)', postura)
                self.pagina.locator(config.obtener('SELECTOR_NOMBRE', '[name="autor_nombre"]')).fill(self.nombre_bot(persona, numero))
                self.pagina.locator(config.obtener('SELECTOR_TEXTO', '[name="texto"]')).fill(texto)
                ruta_api = urlsplit(config.API_URL).path.rstrip('/') + f'/hilos/{self.hilo["id"]}/comentarios/'
                with self.pagina.expect_response(lambda r: r.request.method == 'POST' and urlsplit(r.url).path == ruta_api) as pendiente:
                    self.pagina.locator(config.obtener('SELECTOR_ENVIAR', 'button[type="submit"]')).click()
                respuesta = pendiente.value
                if respuesta.status != 201:
                    raise RuntimeError(f'El formulario rechazó el comentario (HTTP {respuesta.status})')
                guardado = respuesta.json()
                if not guardado.get('es_bot') or guardado.get('postura_bot') != postura or guardado.get('corrida') != self.corrida['id']:
                    raise RuntimeError('El frontend no respetó el contrato de bot_token, postura_bot y corrida')
                previos.append(guardado)
                time.sleep(self.azar.uniform(2, 5) if self.lento else self.azar.uniform(0.2, 0.7))

    def __exit__(self, *args):
        try:
            self.navegador.close()
        finally:
            self.motor.stop()
