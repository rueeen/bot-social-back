"""Corridas breves encadenadas para una charla, con reloj y presupuesto locales."""
import argparse
from datetime import datetime
import math
import random
import time
from zoneinfo import ZoneInfo

from playwright.sync_api import Error as ErrorPlaywright
from rich.console import Console
from . import config
from .argumentos import mezcla
from .bots_comentarios import BotsComentarios
from .cliente import Cliente
from .poblacion_lectores import avanzar_ronda

consola = Console()
ZONA = ZoneInfo('America/Santiago')


def crear_parser():
    parser = argparse.ArgumentParser(description='Modo instalación: corridas sucesivas hasta una hora o un tope aproximado de IA')
    parser.add_argument('--hilo', type=int, required=True)
    parser.add_argument('--mezcla', type=mezcla, default=mezcla('favor=0,contra=0,neutral=0'))
    parser.add_argument('--poblacion', type=int, default=25)
    parser.add_argument('--media', type=float, default=0)
    parser.add_argument('--dispersion', type=float, default=30)
    termino = parser.add_mutually_exclusive_group(required=True)
    termino.add_argument('--hasta', help='Hora de hoy en America/Santiago, HH:MM')
    termino.add_argument('--duracion', type=float, help='Minutos a partir de ahora')
    parser.add_argument('--rondas-por-corrida', type=int, default=15)
    parser.add_argument('--pausa', type=float, default=20, help='Segundos entre rondas')
    parser.add_argument('--tope-llamadas', type=int, default=4000)
    parser.add_argument('--etiqueta-base', default='charla')
    parser.add_argument('--semilla', type=int, default=100)
    parser.add_argument('--lento', action='store_true')
    parser.add_argument('--headless', action='store_true')
    return parser


def calcular_plazo(args, parser, ahora=None):
    ahora = ahora or datetime.now(ZONA)
    if args.hasta is not None:
        try:
            hora = datetime.strptime(args.hasta, '%H:%M').time()
        except ValueError:
            parser.error('--hasta debe tener formato HH:MM, por ejemplo 12:00')
        fin = datetime.combine(ahora.date(), hora, tzinfo=ZONA)
        segundos = fin.timestamp() - ahora.timestamp()
        if segundos <= 0:
            parser.error('--hasta ya pasó: indica una hora posterior de hoy en America/Santiago')
    else:
        if not math.isfinite(args.duracion) or args.duracion <= 0:
            parser.error('--duracion debe ser un número positivo de minutos')
        segundos = args.duracion * 60
    if not math.isfinite(segundos):
        parser.error('La duración está fuera de rango')
    if not 1 <= args.poblacion <= 500 or args.rondas_por_corrida < 1:
        parser.error('--poblacion debe estar entre 1 y 500 y --rondas-por-corrida debe ser positivo')
    if not math.isfinite(args.pausa) or args.pausa < 0 or args.tope_llamadas < 0:
        parser.error('--pausa y --tope-llamadas deben ser no negativos y finitos')
    if not math.isfinite(args.media) or not -100 <= args.media <= 100:
        parser.error('--media debe estar entre -100 y 100')
    if not math.isfinite(args.dispersion) or not 0 <= args.dispersion <= 200:
        parser.error('--dispersion debe estar entre 0 y 200')
    if not args.etiqueta_base.strip():
        parser.error('--etiqueta-base no puede estar vacía')
    return time.monotonic() + segundos


def esperar(segundos, plazo):
    fin = min(time.monotonic() + segundos, plazo)
    while True:
        restante = fin - time.monotonic()
        if restante <= 0:
            return
        time.sleep(min(2, restante))


def ejecutar(args, plazo):
    cliente = Cliente()
    bots = None
    corrida = None
    reapertura_usada = False
    por_ronda = args.poblacion + sum(args.mezcla.values())
    resumen = {'corridas': 0, 'rondas': 0, 'completadas': 0, 'fallidas': 0, 'llamadas': 0, 'motivo': ''}
    usa_ia = bool(config.obtener('ANTHROPIC_API_KEY'))

    def motivo_parada():
        if time.monotonic() >= plazo:
            return 'hora de término alcanzada'
        # Reserva la cota completa antes de comenzar, incluyendo rondas que fallen.
        if resumen['llamadas'] + por_ronda > args.tope_llamadas:
            return 'tope de llamadas: no alcanza el presupuesto para otra ronda'
        return ''

    def cerrar_corrida():
        nonlocal corrida
        if corrida is not None:
            cliente.patch(f'/panel/corridas/{corrida["id"]}/', {})
            corrida = None

    def cerrar_navegador():
        nonlocal bots
        if bots is not None:
            anterior, bots = bots, None
            try:
                anterior.__exit__(None, None, None)
            except Exception as error:
                consola.print(f'No se pudo completar el cierre del navegador: {error}', markup=False)

    def abrir_navegador():
        nonlocal bots
        candidato = BotsComentarios(hilo, corrida, cliente, args.lento, args.headless,
                                    random.Random(corrida['semilla']))
        bots = candidato.__enter__()

    def recuperar_navegador(error):
        nonlocal reapertura_usada
        consola.print(f'Error de Playwright: {error}', markup=False)
        if reapertura_usada:
            raise RuntimeError('El navegador volvió a fallar; se detiene la instalación') from error
        reapertura_usada = True
        cerrar_navegador()
        consola.print('Reabriendo el navegador; hace falta una ronda exitosa para permitir otra recuperación…')
        abrir_navegador()

    try:
        if motivo_parada():
            resumen['motivo'] = motivo_parada()
            return resumen
        if sum(args.mezcla.values()):
            config.exigir('BOT_TOKEN')
        cliente.autenticar()
        hilo = cliente.get(f'/hilos/{args.hilo}/')
        if hilo['estado'] != 'abierto':
            raise RuntimeError('El hilo está cerrado')
        while not motivo_parada():
            indice = resumen['corridas'] + 1
            corrida = cliente.post(f'/panel/hilos/{args.hilo}/corridas/', {
                'etiqueta': f'{args.etiqueta_base} {indice}', 'mezcla_bots': args.mezcla,
                'semilla': args.semilla + indice,
            })
            resumen['corridas'] += 1
            cliente.post(f'/panel/corridas/{corrida["id"]}/sembrar/', {
                'n': args.poblacion, 'media': args.media, 'dispersion': args.dispersion,
            })
            foto = cliente.post(f'/panel/corridas/{corrida["id"]}/snapshot_auto/', {'ronda': 0})
            consola.print(f'{corrida["etiqueta"]} · ronda 0 · promedio {foto["promedio"]:.2f}', markup=False)
            azar_lectores = random.Random(args.semilla + indice)
            if sum(args.mezcla.values()) and not motivo_parada():
                try:
                    if bots is None:
                        abrir_navegador()
                    else:
                        bots.azar = random.Random(args.semilla + indice)
                        bots.cambiar_corrida(corrida)
                except ErrorPlaywright as error:
                    recuperar_navegador(error)
            for intento in range(1, args.rondas_por_corrida + 1):
                if motivo_parada():
                    break
                resumen['llamadas'] += por_ronda
                resumen['rondas'] += 1
                try:
                    if bots is not None:
                        bots.publicar_ronda()
                    foto = avanzar_ronda(corrida['id'], cliente, azar_lectores)
                    resumen['completadas'] += 1
                    reapertura_usada = False
                    consola.print(f'{corrida["etiqueta"]} · ronda {foto["ronda"]} · promedio {foto["promedio"]:.2f} · bots {foto["n_comentarios_bot"]}', markup=False)
                except ErrorPlaywright as error:
                    resumen['fallidas'] += 1
                    recuperar_navegador(error)
                except Exception as error:
                    resumen['fallidas'] += 1
                    consola.print(f'{corrida["etiqueta"]} · intento {intento} fallido: {error}. Se continúa con el siguiente.', markup=False)
                if not motivo_parada():
                    esperar(args.pausa, plazo)
            cerrar_corrida()
        resumen['motivo'] = motivo_parada()
    except KeyboardInterrupt:
        resumen['motivo'] = 'interrupción del presentador (Ctrl-C)'
    except Exception as error:
        resumen['motivo'] = f'error que impide continuar: {error}'
    finally:
        try:
            cerrar_corrida()
        except Exception as error:
            resumen['motivo'] += f'; no se pudo confirmar el cierre de la corrida: {error}'
        finally:
            cerrar_navegador()
            # Tarifas y tokens pedidos para la demo; no son una cotización del proveedor.
            costo = resumen['llamadas'] * (500 * 0.10 + 100 * 0.50) / 1_000_000 if usa_ia else 0
            consola.print('\nResumen de instalación', style='bold')
            consola.print(f'Corridas creadas: {resumen["corridas"]}; rondas intentadas: {resumen["rondas"]}; completadas: {resumen["completadas"]}; fallidas: {resumen["fallidas"]}')
            consola.print(f'Llamadas de IA aproximadas (reserva por ronda): {resumen["llamadas"]}')
            consola.print(f'Costo estimado de referencia: USD {costo:.6f} (estimación, no facturación)')
            if not usa_ia:
                consola.print('Sin ANTHROPIC_API_KEY: heurística/plantillas; llamadas reales de IA: 0; costo real de IA: USD 0.')
            consola.print(f'Término: {resumen["motivo"]}', markup=False)
    return resumen


def main():
    parser = crear_parser()
    args = parser.parse_args()
    plazo = calcular_plazo(args, parser)
    resumen = ejecutar(args, plazo)
    return 1 if 'error que impide' in resumen['motivo'] or 'no se pudo confirmar' in resumen['motivo'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
