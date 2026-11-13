import random
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase
from .models import Hilo, Corrida, Comentario, AgenteLector, Snapshot
from .moderacion import moderar
from rest_framework.exceptions import ValidationError

@override_settings(BOT_TOKEN='token-docente-de-prueba')
class PruebasForo(APITestCase):
    def setUp(self):
        cache.clear()
        self.docente = get_user_model().objects.create_user('docente', password='clave-docente-segura', is_staff=True)
        self.alumno = get_user_model().objects.create_user('alumno', password='clave-alumno-segura')
        self.hilo = Hilo.objects.create(titulo='Celulares', tema='Uso en clases', pregunta_postura='¿Prohibir celulares?', creado_por=self.docente)
        self.corrida = Corrida.objects.create(hilo=self.hilo, etiqueta='favor', semilla=42, mezcla_bots={'favor': 1})
        self.ruta = f'/api/hilos/{self.hilo.id}/comentarios/'
        self.panel = f'/api/panel/corridas/{self.corrida.id}/'

    def autenticar(self):
        self.client.force_authenticate(self.docente)

    def comentar(self, token=None, **cambios):
        datos = {'autor_nombre': 'AutoOpina', 'texto': 'Apoyo esta medida', 'es_bot': True,
                 'postura_bot': 'favor', 'corrida': self.corrida.id}
        datos.update(cambios)
        headers = {'HTTP_X_BOT_TOKEN': token} if token else {}
        return self.client.post(self.ruta, datos, format='json', **headers)

    def test_sin_token_fuerza_humano(self):
        respuesta = self.comentar()
        self.assertEqual(respuesta.status_code, 201)
        self.assertFalse(respuesta.data['es_bot'])
        self.assertIsNone(respuesta.data['postura_bot'])
        self.assertIsNone(respuesta.data['corrida'])

    def test_token_invalido_fuerza_humano(self):
        respuesta = self.comentar(token='incorrecto')
        self.assertEqual(respuesta.status_code, 201)
        self.assertFalse(respuesta.data['es_bot'])

    @override_settings(BOT_TOKEN='')
    def test_token_no_configurado_no_autoriza(self):
        self.assertFalse(self.comentar().data['es_bot'])

    def test_token_valido_marca_y_exime_rate_limit(self):
        for _ in range(2):
            respuesta = self.comentar(token='token-docente-de-prueba')
            self.assertEqual(respuesta.status_code, 201)
            self.assertTrue(respuesta.data['es_bot'])
            self.assertEqual(respuesta.data['postura_bot'], 'favor')
            self.assertEqual(respuesta.data['corrida'], self.corrida.id)

    def test_humanos_rate_limit_por_ip(self):
        self.assertEqual(self.comentar().status_code, 201)
        self.assertEqual(self.comentar().status_code, 429)
        self.assertEqual(self.client.post(self.ruta, {'autor_nombre': 'Otra', 'texto': 'Estoy pensando'}, REMOTE_ADDR='127.0.0.2').status_code, 201)

    def test_moderacion_normaliza_sin_falso_positivo(self):
        moderar('Mi computador permite aprender programación')
        for texto in ['Qué MÍÉÉÉRDA', 'm13rd4', 'puuuutaaa', 'https://ejemplo.cl', 'www.ejemplo.cl', 'ejemplo.xyz', 'ftp://ejemplo.org', '+56 9 1234 5678', 'a' * 401]:
            with self.subTest(texto=texto), self.assertRaises(ValidationError):
                moderar(texto)

    def test_bot_tambien_pasa_moderacion(self):
        respuesta = self.comentar(token='token-docente-de-prueba', texto='m13rd4')
        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(set(respuesta.data), {'error'})

    def test_bot_necesita_postura(self):
        self.assertEqual(self.comentar(token='token-docente-de-prueba', postura_bot=None).status_code, 400)

    def test_hilo_cerrado(self):
        self.hilo.estado = 'cerrado'
        self.hilo.save()
        respuesta = self.comentar()
        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(respuesta.data, {'error': 'El hilo está cerrado'})
        self.assertEqual(self.client.get(self.ruta).status_code, 200)

    def test_panel_exige_staff_incluso_con_token_bot(self):
        for ruta in [self.panel + 'agentes/', '/api/panel/hilos/']:
            self.assertEqual(self.client.get(ruta, HTTP_X_BOT_TOKEN='token-docente-de-prueba').status_code, 401)
        self.client.force_authenticate(self.alumno)
        self.assertEqual(self.client.get(self.panel + 'agentes/').status_code, 403)

    def test_jwt_y_crear_hilo(self):
        token = self.client.post('/api/token/', {'username': 'docente', 'password': 'clave-docente-segura'})
        self.assertEqual(token.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + token.data['access'])
        nuevo = self.client.post('/api/panel/hilos/', {'titulo': 'Evidencia', 'tema': 'Debate', 'pregunta_postura': '¿Está de acuerdo?'})
        self.assertEqual(nuevo.status_code, 201)
        self.assertEqual(nuevo.data['creado_por'], self.docente.id)
        self.assertEqual(self.client.post('/api/token/refresh/', {'refresh': token.data['refresh']}).status_code, 200)

    def test_siembra_reproducible_y_no_duplica(self):
        self.autenticar()
        entrada = {'n': 30, 'media': -20, 'dispersion': 40}
        a = self.client.post(self.panel + 'sembrar/', entrada).data
        otra = Corrida.objects.create(hilo=self.hilo, etiqueta='contra', semilla=42)
        b = self.client.post(f'/api/panel/corridas/{otra.id}/sembrar/', entrada).data
        for campo in ['postura_inicial', 'apertura', 'perfil']:
            self.assertEqual([x[campo] for x in a], [x[campo] for x in b])
        self.assertTrue(all(-100 <= x['postura_inicial'] <= 100 for x in a))
        self.assertEqual(self.client.post(self.panel + 'sembrar/', entrada).status_code, 400)
        self.assertEqual(self.corrida.agentes.count(), 30)

    def test_snapshot_auto_estadistica_extremos_y_conteos(self):
        self.autenticar()
        for p in [-100, 0, 100]:
            AgenteLector.objects.create(hilo=self.hilo, corrida=self.corrida, nombre='Lector', perfil='Analítico', postura_inicial=p, postura_actual=p, apertura=.3)
        self.comentar(token='token-docente-de-prueba')
        respuesta = self.client.post(self.panel + 'snapshot_auto/', {})
        self.assertEqual(respuesta.status_code, 201)
        self.assertEqual(respuesta.data['ronda'], 0)
        self.assertEqual(respuesta.data['promedio'], 0)
        self.assertAlmostEqual(respuesta.data['desviacion'], (20000 / 3) ** .5)
        self.assertEqual(respuesta.data['histograma'], {str(n): int(n in [-100, 0, 80]) for n in range(-100, 100, 20)})
        self.assertEqual(respuesta.data['n_favor'], 1)
        self.assertEqual(respuesta.data['n_comentarios_bot'], 1)
        self.assertEqual(self.client.post(self.panel + 'snapshot_auto/', {}).data['ronda'], 1)
        self.assertEqual(self.client.post(self.panel + 'snapshot_auto/', {'ronda': 0}).status_code, 400)

    def test_snapshot_sin_poblacion_y_valores_invalidos(self):
        self.autenticar()
        self.assertEqual(self.client.post(self.panel + 'snapshot_auto/').status_code, 400)
        for datos in [{'n': 0}, {'media': 'NaN'}, {'dispersion': -1}]:
            self.assertEqual(self.client.post(self.panel + 'sembrar/', datos).status_code, 400)
        self.assertEqual(self.client.post(self.panel + 'snapshots/', {'ronda': 0, 'promedio': 'NaN'}, format='json').status_code, 400)

    def test_actualizacion_agente_y_cierre(self):
        self.autenticar()
        agente = self.client.post(self.panel + 'sembrar/', {'n': 1}).data[0]
        ruta = f'/api/panel/agentes/{agente["id"]}/'
        self.assertEqual(self.client.patch(ruta, {'postura_actual': 101}).status_code, 400)
        self.assertEqual(self.client.patch(ruta, {'postura_actual': 'NaN'}).status_code, 400)
        self.assertEqual(self.client.patch(ruta, {'ultimo_comentario_leido_id': 999}).status_code, 400)
        self.assertEqual(self.client.patch(ruta, {'postura_actual': 25}).status_code, 200)
        self.assertEqual(self.client.patch(self.panel, {}).status_code, 200)
        self.assertEqual(self.client.patch(ruta, {'postura_actual': 30}).status_code, 400)
        self.assertEqual(self.client.post(self.panel + 'snapshot_auto/').status_code, 400)
        self.assertEqual(self.comentar(token='token-docente-de-prueba').status_code, 400)

    def test_aislamiento_incremental_y_limite(self):
        otra = Corrida.objects.create(hilo=self.hilo, etiqueta='otra')
        ajeno = Comentario.objects.create(hilo=self.hilo, corrida=otra, autor_nombre='Otro', es_bot=True, postura_bot='contra', texto='Otra corrida')
        humano = Comentario.objects.create(hilo=self.hilo, autor_nombre='Persona', texto='Una opinión')
        Comentario.objects.bulk_create([Comentario(hilo=self.hilo, corrida=self.corrida, autor_nombre='Bot', es_bot=True, postura_bot='favor', texto='Apoyo') for _ in range(105)])
        ruta = self.ruta + f'?corrida={self.corrida.id}'
        respuesta = self.client.get(ruta)
        self.assertEqual(len(respuesta.data['comentarios']), 100)
        ids = [c['id'] for c in respuesta.data['comentarios']]
        self.assertIn(humano.id, ids)
        self.assertNotIn(ajeno.id, ids)
        resto = self.client.get(ruta + f'&desde_id={respuesta.data["ultimo_id"]}')
        self.assertEqual(len(resto.data['comentarios']), 6)
        self.assertEqual(self.client.get(self.ruta + '?desde_id=abc').status_code, 400)

    def test_rechaza_corrida_de_otro_hilo(self):
        otro = Hilo.objects.create(titulo='Otro', tema='Tema', pregunta_postura='Pregunta', creado_por=self.docente)
        corrida = Corrida.objects.create(hilo=otro, etiqueta='Otra')
        self.assertEqual(self.comentar(token='token-docente-de-prueba', corrida=corrida.id).status_code, 400)
        self.assertEqual(self.client.get(self.ruta + f'?corrida={corrida.id}').status_code, 404)

    def test_consultas_no_crecen_por_comentario(self):
        Comentario.objects.bulk_create([Comentario(hilo=self.hilo, autor_nombre='Persona', texto='Una opinión') for _ in range(20)])
        with self.assertNumQueries(2):
            self.client.get(self.ruta)
        with self.assertNumQueries(1):
            self.client.get('/api/hilos/')

    def test_reset_conserva_humanos(self):
        from .admin import reiniciar_simulacion
        humano = Comentario.objects.create(hilo=self.hilo, autor_nombre='Persona', texto='Opino')
        self.comentar(token='token-docente-de-prueba')
        with patch('foro.admin.HiloAdmin.message_user'):
            from .admin import HiloAdmin
            from django.contrib.admin import site
            reiniciar_simulacion(HiloAdmin(Hilo, site), None, Hilo.objects.filter(pk=self.hilo.id))
        self.assertTrue(Comentario.objects.filter(pk=humano.pk).exists())
        self.assertFalse(Corrida.objects.exists())
        self.assertEqual(Comentario.objects.count(), 1)

    def test_mezcla_valida_y_snapshot_manual(self):
        self.autenticar()
        ruta = f'/api/panel/hilos/{self.hilo.id}/corridas/'
        self.assertEqual(self.client.post(ruta, {'etiqueta': 'Mala', 'mezcla_bots': {'favor': -1}}, format='json').status_code, 400)
        foto = {'ronda': 0, 'promedio': 0, 'desviacion': 0,
                'histograma': {str(n): 0 for n in range(-100, 100, 20)}, 'n_comentarios_bot': 0}
        self.assertEqual(self.client.post(self.panel + 'snapshots/', foto, format='json').status_code, 201)
        self.assertEqual(self.client.post(self.panel + 'snapshots/', foto, format='json').status_code, 400)

    def test_heuristica_sin_clave_y_apertura_ia(self):
        from simulador.ia import nueva_postura, comentario_bot
        agente = {'postura_actual': -20, 'apertura': .3, 'perfil': 'Curioso'}
        with patch('simulador.config.obtener', return_value=''):
            favor = nueva_postura(agente, 'Pregunta', [{'postura_bot': 'favor'}], random.Random(42))
            contra = nueva_postura(agente, 'Pregunta', [{'postura_bot': 'contra'}], random.Random(42))
            self.assertGreater(favor['postura'], -20)
            self.assertLess(contra['postura'], -20)
            self.assertEqual(nueva_postura(agente, 'Pregunta', [])['postura'], -20)
            for postura in ['favor', 'contra', 'neutral']:
                moderar(comentario_bot(postura, 'Tema', 'Pregunta', []))
        with patch('simulador.config.obtener', return_value='presente'), patch('simulador.ia._consultar', return_value='{"postura": 100, "motivo_breve": "Ejemplo"}'):
            self.assertEqual(nueva_postura(agente, 'Pregunta', [{'texto': 'Opinión'}])['postura'], 16)
