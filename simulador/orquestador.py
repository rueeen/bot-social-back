import argparse
import random
from rich.console import Console

consola = Console()
from . import config
from .argumentos import mezcla
from .cliente import Cliente
from .bots_comentarios import BotsComentarios
from .poblacion_lectores import avanzar_ronda


def main():
    parser = argparse.ArgumentParser(description='Experimento educativo en un foro propio con bots declarados')
    parser.add_argument('--hilo', type=int, required=True)
    parser.add_argument('--etiqueta', required=True)
    parser.add_argument('--mezcla', type=mezcla, default=mezcla('favor=0,contra=0,neutral=0'))
    parser.add_argument('--poblacion', type=int, default=30)
    parser.add_argument('--media', type=float, default=0)
    parser.add_argument('--dispersion', type=float, default=40)
    parser.add_argument('--rondas', type=int, default=5)
    parser.add_argument('--semilla', type=int, default=42)
    parser.add_argument('--lento', action='store_true')
    parser.add_argument('--headless', action='store_true', help='Solo para validación automatizada; por defecto el navegador es visible')
    args = parser.parse_args()
    if args.rondas < 0:
        parser.error('--rondas debe ser no negativo')
    if sum(args.mezcla.values()):
        config.exigir('BOT_TOKEN')
    cliente = Cliente()
    cliente.autenticar()
    hilo = cliente.get(f'/hilos/{args.hilo}/')
    if hilo['estado'] != 'abierto':
        raise RuntimeError('El hilo está cerrado')
    corrida = cliente.post(f'/panel/hilos/{args.hilo}/corridas/', {
        'etiqueta': args.etiqueta, 'mezcla_bots': args.mezcla, 'semilla': args.semilla})
    consola.print(f'Corrida {corrida["id"]}: {args.etiqueta}', markup=False)
    cliente.post(f'/panel/corridas/{corrida["id"]}/sembrar/',
        {'n': args.poblacion, 'media': args.media, 'dispersion': args.dispersion})
    foto = cliente.post(f'/panel/corridas/{corrida["id"]}/snapshot_auto/', {'ronda': 0})
    consola.print(f'Ronda 0: promedio {foto["promedio"]:.2f}')
    # Flujos aleatorios separados: las pausas y plantillas no alteran el ruido de lectores.
    azar_lectores = random.Random(args.semilla)
    def rondas(bots=None):
        for _ in range(args.rondas):
            if bots:
                bots.publicar_ronda()
            foto = avanzar_ronda(corrida['id'], cliente, azar_lectores)
            consola.print(f'Ronda {foto["ronda"]}: promedio {foto["promedio"]:.2f}; bots {foto["n_comentarios_bot"]}')
    if sum(args.mezcla.values()):
        with BotsComentarios(hilo, corrida, cliente, args.lento, args.headless, random.Random(args.semilla)) as bots:
            rondas(bots)
    else:
        rondas()
    cliente.patch(f'/panel/corridas/{corrida["id"]}/', {})
    consola.print('Corrida cerrada')

if __name__ == '__main__':
    main()
