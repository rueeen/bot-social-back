import requests
from . import config

class Cliente:
    def __init__(self):
        self.sesion = requests.Session()
        self.refresco = None

    def autenticar(self):
        datos = self._enviar('POST', '/token/', json={
            'username': config.exigir('PRESENTADOR_USER'),
            'password': config.exigir('PRESENTADOR_PASS'),
        })
        self.refresco = datos['refresh']
        self.sesion.headers['Authorization'] = 'Bearer ' + datos['access']

    def _enviar(self, metodo, ruta, **opciones):
        respuesta = self.sesion.request(metodo, config.API_URL + ruta, timeout=30, **opciones)
        if respuesta.status_code == 401 and self.refresco and ruta != '/token/refresh/':
            nueva = self._enviar('POST', '/token/refresh/', json={'refresh': self.refresco})
            self.sesion.headers['Authorization'] = 'Bearer ' + nueva['access']
            respuesta = self.sesion.request(metodo, config.API_URL + ruta, timeout=30, **opciones)
        if not respuesta.ok:
            try:
                error = respuesta.json().get('error', 'Solicitud rechazada')
            except ValueError:
                error = 'Respuesta no JSON del servidor'
            raise RuntimeError(f'API {respuesta.status_code}: {error}')
        return respuesta.json()

    def get(self, ruta, **parametros):
        return self._enviar('GET', ruta, params=parametros)

    def post(self, ruta, datos=None):
        return self._enviar('POST', ruta, json=datos or {})

    def patch(self, ruta, datos):
        return self._enviar('PATCH', ruta, json=datos)

    def comentarios(self, hilo, corrida, desde_id):
        # Consumir todas las páginas incrementales; el backend limita cada lote a 100.
        comentarios = []
        while True:
            lote = self.get(f'/hilos/{hilo}/comentarios/', corrida=corrida, desde_id=desde_id)
            comentarios.extend(lote['comentarios'])
            if len(lote['comentarios']) < 100:
                return comentarios
            desde_id = lote['ultimo_id']
