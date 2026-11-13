"""Respuestas imperfectas del proveedor, sin red ni credenciales reales."""
import math
import random
import unittest
from unittest.mock import patch

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
        self.assertEqual(consultar.call_args.kwargs['max_tokens'], 150)

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


if __name__ == '__main__':
    unittest.main()
