"""Respuestas imperfectas del proveedor, sin red ni credenciales reales."""
import math
import random
import unittest
from unittest.mock import MagicMock, patch

from .ia import PLANTILLAS, comentario_bot, nueva_postura


class PruebasIA(unittest.TestCase):
    def setUp(self):
        self.agente = {'postura_actual': -20, 'apertura': .3, 'perfil': 'Curioso'}
        self.comentarios = [{'postura_bot': 'favor', 'texto': 'Apoyo la propuesta'}]
        parche = patch('simulador.config.obtener', return_value='clave-simulada')
        parche.start()
        self.addCleanup(parche.stop)

    def comentar(self):
        return comentario_bot('favor', 'Tema', 'Pregunta', [], random.Random(42))

    def actualizar(self):
        return nueva_postura(self.agente, 'Pregunta', self.comentarios, random.Random(42))

    def test_comentario_vacio_reintenta_y_usa_plantilla(self):
        with patch('simulador.ia._consultar', return_value='') as consultar:
            self.assertIn(self.comentar(), PLANTILLAS['favor'])
        self.assertEqual(consultar.call_count, 2)
        self.assertEqual(consultar.call_args.kwargs['max_tokens'], 256)

    def test_segundo_intento_recupera_comentario(self):
        with patch('simulador.ia._consultar', side_effect=['   ', 'Un argumento breve.']) as consultar:
            self.assertEqual(self.comentar(), 'Un argumento breve.')
        self.assertEqual(consultar.call_count, 2)

    def test_comentario_largo_siempre_valido(self):
        for texto in ['a' * 450, 'palabra ' * 60, 'Primera frase. ' + 'palabra ' * 60]:
            with self.subTest(texto=texto[:20]), patch('simulador.ia._consultar', return_value=texto) as consultar:
                resultado = self.comentar()
                self.assertTrue(resultado)
                self.assertLessEqual(len(resultado), 400)
                self.assertTrue(resultado in PLANTILLAS['favor'] or texto.startswith(resultado))
                if texto.startswith('palabra'):
                    self.assertTrue(resultado.endswith('palabra'))
                if texto.startswith('Primera'):
                    self.assertEqual(resultado, 'Primera frase.')
                consultar.assert_called_once()

    def test_limpia_comillas_cercos_y_saltos(self):
        for texto in [' "Una opinión." ', '```\n"Una opinión."\n```', '```text\n“Una opinión.”\n```', '"```Una opinión.```"', 'Una\n  opinión.']:
            with self.subTest(texto=texto), patch('simulador.ia._consultar', return_value=texto):
                self.assertEqual(self.comentar(), 'Una opinión.')

    def test_respuestas_de_tipo_invalido_y_fallos_del_proveedor(self):
        for respuesta in [None, [], {'texto': 'Opinión'}]:
            with self.subTest(respuesta=respuesta), patch('simulador.ia._consultar', return_value=respuesta):
                self.assertIn(self.comentar(), PLANTILLAS['favor'])
                self.assertIn('Respaldo heurístico', self.actualizar()['motivo'])
        with patch('simulador.ia._consultar', side_effect=RuntimeError('Fallo del proveedor')):
            self.assertIn(self.comentar(), PLANTILLAS['favor'])
            self.assertIn('Respaldo heurístico', self.actualizar()['motivo'])

    def test_postura_valida_aplica_apertura_y_limites(self):
        for respuesta, esperada in [('{"postura":100,"motivo_breve":"Evidencia"}', 16), ('{"postura":999}', 16), ('{"postura":-999}', -44)]:
            with self.subTest(respuesta=respuesta), patch('simulador.ia._consultar', return_value=respuesta):
                self.assertEqual(self.actualizar()['postura'], esperada)

    def test_json_entre_texto_y_cercos(self):
        respuesta = 'Resultado:\n```json\n{"postura": 100, "motivo_breve": "Revisé {evidencia}"}\n```\nFin.'
        with patch('simulador.ia._consultar', return_value=respuesta):
            resultado = self.actualizar()
        self.assertEqual(resultado['postura'], 16)
        self.assertEqual(resultado['motivo'], 'Revisé {evidencia}')

    def test_json_completo_con_cercos_usa_ia_y_presupuesto_de_400(self):
        respuesta = '```json\n{"postura": 80, "motivo_breve": "La evidencia aporta una perspectiva útil"}\n```'
        with patch('simulador.ia._consultar', return_value=respuesta) as consultar, self.assertNoLogs('simulador.ia', level='WARNING'):
            resultado = self.actualizar()
        self.assertEqual(resultado['postura'], 10)
        self.assertEqual(resultado['motivo'], 'La evidencia aporta una perspectiva útil')
        self.assertNotIn('Respaldo', resultado['motivo'])
        self.assertEqual(consultar.call_args.kwargs['max_tokens'], 400)
        sistema = consultar.call_args.args[0]
        for regla in ['una sola línea', 'solo el objeto JSON', 'sin cercos de código', 'número entre -100 y 100', 'máximo 12 palabras']:
            self.assertIn(regla, sistema)

    def test_json_truncado_conserva_respaldo_heuristico(self):
        respuesta = '{"postura":80,"motivo_breve":"La evidencia presentada sugiere que'
        with patch('simulador.config.obtener', return_value=''):
            esperado = self.actualizar()['postura']
        with patch('simulador.ia._consultar', return_value=respuesta), self.assertLogs('simulador.ia', level='WARNING'):
            resultado = self.actualizar()
        self.assertEqual(resultado['postura'], esperado)
        self.assertTrue(math.isfinite(resultado['postura']))
        self.assertTrue(-100 <= resultado['postura'] <= 100)
        self.assertIn('Respaldo heurístico', resultado['motivo'])

    def test_postura_invalida_usa_misma_heuristica_sin_clave(self):
        respuestas = ['sin JSON', '{mal formado}', '{}', '{"motivo_breve":"Sin postura"}',
                      '{"postura":NaN}', '{"postura":Infinity}', '{"postura":-Infinity}',
                      '{"postura":"NaN"}', '{"postura":null}', '{"postura":true}',
                      '{"postura":{}}', '{"postura":"texto"}']
        with patch('simulador.config.obtener', return_value=''):
            esperado = self.actualizar()['postura']
        for respuesta in respuestas:
            with self.subTest(respuesta=respuesta), patch('simulador.ia._consultar', return_value=respuesta):
                resultado = self.actualizar()
                self.assertTrue(math.isfinite(resultado['postura']))
                self.assertTrue(-100 <= resultado['postura'] <= 100)
                self.assertEqual(resultado['postura'], esperado)
                self.assertGreater(resultado['postura'], self.agente['postura_actual'])
                self.assertIn('Respaldo heurístico', resultado['motivo'])

    def test_sin_clave_conserva_plantilla_y_heuristica(self):
        with patch('simulador.config.obtener', return_value=''), patch('simulador.ia._consultar') as consultar:
            self.assertIn(self.comentar(), PLANTILLAS['favor'])
            esperado = -20 + .3 * 24 + random.Random(42).uniform(-1, 1)
            resultado = self.actualizar()
            self.assertEqual(resultado['postura'], esperado)
            self.assertNotIn('Respaldo', resultado['motivo'])
            consultar.assert_not_called()

    def test_sin_comentarios_no_consulta_ni_mueve_postura(self):
        with patch('simulador.ia._consultar') as consultar:
            self.assertEqual(nueva_postura(self.agente, 'Pregunta', [])['postura'], -20)
            consultar.assert_not_called()


class PruebasPersonas(unittest.TestCase):
    def setUp(self):
        from .personas import PERSONAS
        self.personas = PERSONAS

    def test_catalogo_variado_con_etiquetas_cortas(self):
        self.assertGreaterEqual(len(self.personas), 6)
        self.assertEqual(len({p['etiqueta'] for p in self.personas}), len(self.personas))
        self.assertTrue(all(0 < len(p['etiqueta']) <= 12 and p['estilo'] for p in self.personas))

    def test_persona_en_prompt_conserva_reglas_y_robustez(self):
        for persona in self.personas:
            for respuesta in ['Una opinión breve.', '', 'palabra ' * 70]:
                with self.subTest(persona=persona['etiqueta'], respuesta=respuesta[:20]), patch('simulador.config.obtener', return_value='clave-simulada'), patch('simulador.ia._consultar', return_value=respuesta) as consultar:
                    texto = comentario_bot('contra', 'Tema', 'Pregunta', [], random.Random(42), persona=persona)
                    self.assertTrue(texto)
                    self.assertLessEqual(len(texto), 400)
                    sistema = consultar.call_args.args[0]
                    self.assertIn(persona['estilo'], sistema)
                    for regla in ['bot declarado', 'contra', '300 caracteres', 'una o dos frases', 'una sola línea', 'sin comillas', 'sin insultos', 'enlaces ni teléfonos', 'no cambia tu postura']:
                        self.assertIn(regla, sistema)
                    self.assertEqual(consultar.call_count, 2 if respuesta == '' else 1)
                    if respuesta == '':
                        self.assertIn(texto, PLANTILLAS['contra'])

    def test_sin_persona_conserva_prompt_y_resultado(self):
        with patch('simulador.config.obtener', return_value='clave-simulada'), patch('simulador.ia._consultar', return_value='Una opinión breve.') as consultar:
            a = comentario_bot('favor', 'Tema', 'Pregunta', [], random.Random(42))
            primera = consultar.call_args
            b = comentario_bot('favor', 'Tema', 'Pregunta', [], random.Random(42), persona=None)
            self.assertEqual(a, b)
            self.assertEqual(primera, consultar.call_args)
            self.assertNotIn('Estilo de argumentación', primera.args[0])

    def test_sin_clave_persona_no_cambia_plantilla(self):
        with patch('simulador.config.obtener', return_value=''), patch('simulador.ia._consultar') as consultar:
            for postura in PLANTILLAS:
                a = comentario_bot(postura, 'Tema', 'Pregunta', [], random.Random(42))
                for persona in self.personas:
                    b = comentario_bot(postura, 'Tema', 'Pregunta', [], random.Random(42), persona=persona)
                    self.assertEqual(a, b)
            consultar.assert_not_called()

    def bots(self, cantidad, semilla=42):
        from .bots_comentarios import BotsComentarios
        return BotsComentarios({'id': 1, 'tema': 'Tema', 'pregunta_postura': 'Pregunta'},
                              {'id': 2, 'mezcla_bots': {'contra': cantidad}}, MagicMock(), azar=random.Random(semilla))

    def test_asignacion_reproducible_repite_catalogo_sin_perder_variedad(self):
        cantidad = len(self.personas) * 2 + 3
        a, b = self.bots(cantidad), self.bots(cantidad)
        for bots in [a, b]:
            bots.asignar_personas()
        self.assertEqual(a.personas_por_cupo, b.personas_por_cupo)
        self.assertEqual(len(a.personas_por_cupo), cantidad)
        etiquetas = [p['etiqueta'] for p in a.personas_por_cupo]
        n = len(self.personas)
        self.assertEqual(len(set(etiquetas[:n])), n)
        self.assertEqual(etiquetas[:n], etiquetas[n:2*n])

    def test_enter_y_cambiar_corrida_asignan_usando_semilla(self):
        a, b = self.bots(4), self.bots(4)
        with patch('simulador.bots_comentarios.sync_playwright'), patch('simulador.config.exigir', return_value='token'), patch('simulador.config.obtener', side_effect=lambda nombre, defecto='': defecto):
            with a:
                inicial = list(a.personas_por_cupo)
                b.pagina = MagicMock()
                b.destino = 'https://foro.example/h/1'
                b.cambiar_corrida(b.corrida)
                self.assertEqual(inicial, b.personas_por_cupo)
                a.azar = random.Random(101)
                nueva = {'id': 3, 'mezcla_bots': {'contra': 10}}
                a.cambiar_corrida(nueva)
                b.azar = random.Random(101)
                b.cambiar_corrida(nueva)
                self.assertEqual(a.personas_por_cupo, b.personas_por_cupo)
                self.assertEqual(len(a.personas_por_cupo), 10)

    def test_publicar_mantiene_personas_entre_rondas_y_nombre_visible(self):
        bots = self.bots(4)
        bots.asignar_personas()
        asignacion = list(bots.personas_por_cupo)
        bots.pagina = MagicMock()
        campos = {}
        bots.pagina.locator.side_effect = lambda selector: campos.setdefault(selector, MagicMock())
        bots.cliente.comentarios.return_value = []
        respuesta = bots.pagina.expect_response.return_value.__enter__.return_value.value
        respuesta.status = 201
        respuesta.json.return_value = {'es_bot': True, 'postura_bot': 'contra', 'corrida': 2}
        with patch('simulador.bots_comentarios.comentario_bot', return_value='Opinión de bot.') as comentar, patch('simulador.bots_comentarios.time.sleep'), patch('simulador.config.obtener', side_effect=lambda nombre, defecto='': defecto):
            bots.publicar_ronda()
            bots.publicar_ronda()
        self.assertEqual([llamada.kwargs['persona'] for llamada in comentar.call_args_list], asignacion * 2)
        self.assertEqual(bots.personas_por_cupo, asignacion)
        nombres = [llamada.args[0] for llamada in bots.pagina.locator('[name="autor_nombre"]').fill.call_args_list]
        self.assertEqual(nombres, [bots.nombre_bot(p, n) for n, p in enumerate(asignacion, 1)] * 2)
        for nombre, persona in zip(nombres, asignacion * 2):
            self.assertTrue(nombre.startswith('Bot_'))
            self.assertIn(persona['etiqueta'], nombre)
            self.assertLessEqual(len(nombre), 30)

    def test_nombre_no_supera_limite_incluso_con_etiqueta_editada(self):
        from .bots_comentarios import BotsComentarios
        for persona in [*self.personas, {'etiqueta': 'etiqueta-extremadamente-larga' * 3}]:
            self.assertLessEqual(len(BotsComentarios.nombre_bot(persona, 150)), 30)


if __name__ == '__main__':
    unittest.main()
