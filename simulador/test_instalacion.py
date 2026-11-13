"""Pruebas sin red ni gasto: reloj, presupuesto y ciclo de vida del navegador."""
from datetime import datetime
import io
import unittest
from unittest.mock import MagicMock, patch

from playwright.sync_api import Error as ErrorPlaywright
from rich.console import Console
from . import instalacion as modulo
from .argumentos import mezcla
from .bots_comentarios import BotsComentarios


class Reloj:
    def __init__(self):
        self.segundos = 0
        self.pausas = []

    def monotonic(self):
        return self.segundos

    def sleep(self, segundos):
        self.pausas.append(segundos)
        self.segundos += segundos


class ClienteFalso:
    def __init__(self):
        self.corridas = []
        self.cerradas = []

    def autenticar(self):
        pass

    def get(self, ruta):
        return {'id': 1, 'estado': 'abierto'}

    def post(self, ruta, datos):
        if ruta.endswith('/corridas/'):
            corrida = dict(datos, id=len(self.corridas) + 1)
            self.corridas.append(corrida)
            return corrida
        return {'ronda': 0, 'promedio': 0}

    def patch(self, ruta, datos):
        self.cerradas.append(int(ruta.rstrip('/').split('/')[-1]))


class PruebasInstalacion(unittest.TestCase):
    def setUp(self):
        self.reloj = Reloj()
        self.cliente = ClienteFalso()
        self.salida = io.StringIO()
        self.parches = [
            patch.object(modulo.time, 'monotonic', self.reloj.monotonic),
            patch.object(modulo.time, 'sleep', self.reloj.sleep),
            patch.object(modulo, 'Cliente', return_value=self.cliente),
            patch.object(modulo, 'consola', Console(file=self.salida, width=200)),
            patch.object(modulo.config, 'obtener', return_value=''),
            patch.object(modulo.config, 'exigir', return_value='token-de-prueba'),
        ]
        for parche in self.parches:
            parche.start()
            self.addCleanup(parche.stop)

    def args(self, *extra):
        return modulo.crear_parser().parse_args(['--hilo', '1', '--duracion', '2', '--poblacion', '8',
            '--rondas-por-corrida', '3', '--pausa', '5', '--mezcla', 'contra=3,favor=1,neutral=0', *extra])

    def avanzar(self, *args):
        self.reloj.segundos += 1
        return {'ronda': 1, 'promedio': -10, 'n_comentarios_bot': 4}

    def test_duracion_multiples_corridas_y_un_navegador(self):
        navegador = MagicMock()
        with patch.object(modulo, 'BotsComentarios') as clase, patch.object(modulo, 'avanzar_ronda', side_effect=self.avanzar):
            clase.return_value.__enter__.return_value = navegador
            args = self.args()
            resumen = modulo.ejecutar(args, modulo.calcular_plazo(args, modulo.crear_parser()))
        self.assertGreater(resumen['corridas'], 1)
        self.assertEqual(clase.call_count, 1)
        self.assertEqual(navegador.cambiar_corrida.call_count, resumen['corridas'] - 1)
        navegador.__exit__.assert_called_once()
        self.assertEqual(self.cliente.cerradas, list(range(1, resumen['corridas'] + 1)))
        self.assertEqual([c['semilla'] for c in self.cliente.corridas], list(range(101, 101 + resumen['corridas'])))
        self.assertEqual([c['etiqueta'] for c in self.cliente.corridas], [f'charla {n}' for n in range(1, resumen['corridas'] + 1)])
        self.assertGreaterEqual(self.reloj.segundos, 120)
        self.assertLessEqual(max(self.reloj.pausas), 2)
        self.assertIn('costo real de IA: USD 0', self.salida.getvalue())

    def test_tope_reservado_antes_de_ronda_y_errores_cuentan(self):
        args = self.args('--mezcla', 'favor=0', '--tope-llamadas', '17', '--pausa', '0')
        with patch.object(modulo, 'avanzar_ronda', side_effect=[RuntimeError('hipo de red'), self.avanzar()]):
            resumen = modulo.ejecutar(args, 120)
        self.assertEqual(resumen['llamadas'], 16)
        self.assertEqual(resumen['rondas'], 2)
        self.assertEqual(resumen['fallidas'], 1)
        self.assertEqual(resumen['completadas'], 1)
        self.assertIn('hipo de red', self.salida.getvalue())
        self.assertEqual(self.cliente.cerradas, [1])
        self.assertLess(self.reloj.segundos, 120)

    def test_tope_menor_a_una_ronda_no_crea_corrida(self):
        resumen = modulo.ejecutar(self.args('--tope-llamadas', '11'), 120)
        self.assertEqual(resumen['corridas'], 0)
        self.assertEqual(resumen['llamadas'], 0)

    def test_keyboard_interrupt_cierra_recursos(self):
        navegador = MagicMock()
        with patch.object(modulo, 'BotsComentarios') as clase, patch.object(modulo, 'avanzar_ronda', side_effect=KeyboardInterrupt):
            clase.return_value.__enter__.return_value = navegador
            resumen = modulo.ejecutar(self.args(), 120)
        self.assertIn('Ctrl-C', resumen['motivo'])
        self.assertEqual(self.cliente.cerradas, [1])
        navegador.__exit__.assert_called_once()

    def test_reabre_una_vez_y_continua(self):
        primero, segundo = MagicMock(), MagicMock()
        primero.publicar_ronda.side_effect = ErrorPlaywright('Navegador cerrado')
        with patch.object(modulo, 'BotsComentarios') as clase, patch.object(modulo, 'avanzar_ronda', side_effect=self.avanzar):
            clase.return_value.__enter__.side_effect = [primero, segundo]
            resumen = modulo.ejecutar(self.args('--tope-llamadas', '36', '--pausa', '0'), 120)
        self.assertEqual(clase.call_count, 2)
        self.assertEqual(resumen['completadas'], 2)
        self.assertEqual(resumen['fallidas'], 1)
        primero.__exit__.assert_called_once()
        segundo.__exit__.assert_called_once()

    def test_segunda_falla_de_navegador_detiene(self):
        primero, segundo = MagicMock(), MagicMock()
        for navegador in [primero, segundo]:
            navegador.publicar_ronda.side_effect = ErrorPlaywright('Navegador cerrado')
        with patch.object(modulo, 'BotsComentarios') as clase:
            clase.return_value.__enter__.side_effect = [primero, segundo]
            resumen = modulo.ejecutar(self.args('--pausa', '0'), 120)
        self.assertEqual(clase.call_count, 2)
        self.assertIn('volvió a fallar', resumen['motivo'])
        self.assertEqual(self.cliente.cerradas, [1])

    def test_fallo_inicial_del_navegador_tambien_reabre(self):
        navegador = MagicMock()
        with patch.object(modulo, 'BotsComentarios') as clase, patch.object(modulo, 'avanzar_ronda', side_effect=self.avanzar):
            clase.return_value.__enter__.side_effect = [ErrorPlaywright('Inicio fallido'), navegador]
            resumen = modulo.ejecutar(self.args('--tope-llamadas', '12'), 120)
        self.assertEqual(clase.call_count, 2)
        self.assertEqual(resumen['completadas'], 1)

    def test_cambiar_corrida_actualiza_antes_de_navegar(self):
        bots = BotsComentarios({'id': 1}, {'id': 2}, self.cliente)
        bots.pagina = MagicMock()
        bots.destino = 'https://foro.example/h/1'
        bots.cambiar_corrida({'id': 3})
        self.assertEqual(bots.corrida['id'], 3)
        self.assertEqual([llamada[0] for llamada in bots.pagina.method_calls], ['evaluate', 'goto'])
        self.assertEqual(bots.pagina.evaluate.call_args.args[1], 3)

    def test_interrupcion_al_abrir_libera_motor(self):
        with patch('simulador.bots_comentarios.sync_playwright') as iniciar:
            motor = iniciar.return_value.start.return_value
            motor.chromium.launch.side_effect = KeyboardInterrupt
            with self.assertRaises(KeyboardInterrupt):
                BotsComentarios({'id': 1}, {'id': 2}, self.cliente).__enter__()
            motor.stop.assert_called_once()

    def test_hasta_hoy_santiago_pasado_e_invalido(self):
        parser = modulo.crear_parser()
        ahora = datetime(2026, 11, 13, 10, 0, tzinfo=modulo.ZONA)
        args = parser.parse_args(['--hilo', '1', '--hasta', '12:00'])
        self.assertEqual(modulo.calcular_plazo(args, parser, ahora), 7200)
        for valor in ['09:59', '10:00', '25:00', 'ayer', '']:
            args.hasta = valor
            with self.subTest(valor=valor), patch('sys.stderr', new_callable=io.StringIO) as salida, self.assertRaises(SystemExit):
                modulo.calcular_plazo(args, parser, ahora)
        args.hasta = '09:00'
        with patch('sys.stderr', new_callable=io.StringIO) as salida, self.assertRaises(SystemExit):
            modulo.calcular_plazo(args, parser, ahora)
        self.assertIn('ya pasó', salida.getvalue())

    def test_validacion_argumentos_y_parser_compartido(self):
        parser = modulo.crear_parser()
        for argumentos in [[], ['--hasta', '12:00', '--duracion', '1']]:
            with patch('sys.stderr', new_callable=io.StringIO), self.assertRaises(SystemExit):
                parser.parse_args(['--hilo', '1', *argumentos])
        for opciones in [('--duracion', 'nan'), ('--duracion', '-1'), ('--pausa', '-1'), ('--poblacion', '0'), ('--rondas-por-corrida', '0'), ('--tope-llamadas', '-1')]:
            with patch('sys.stderr', new_callable=io.StringIO), self.assertRaises(SystemExit):
                modulo.calcular_plazo(self.args(*opciones), parser)
        from .orquestador import mezcla as mezcla_orquestador
        self.assertIs(mezcla_orquestador, mezcla)
        self.assertEqual(mezcla('contra=3,favor=1,neutral=0'), {'favor': 1, 'contra': 3, 'neutral': 0})

    def test_costo_referencia_con_clave_sin_llamadas_reales(self):
        args = self.args('--mezcla', 'favor=0', '--tope-llamadas', '8', '--pausa', '0')
        with patch.object(modulo.config, 'obtener', return_value='clave-falsa'), patch.object(modulo, 'avanzar_ronda', side_effect=self.avanzar):
            modulo.ejecutar(args, 120)
        self.assertIn('USD 0.000800', self.salida.getvalue())
        self.assertNotIn('costo real de IA: USD 0', self.salida.getvalue())


if __name__ == '__main__':
    unittest.main()
