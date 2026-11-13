import argparse

def mezcla(texto):
    resultado = {'favor': 0, 'contra': 0, 'neutral': 0}
    try:
        vistos = set()
        for par in texto.split(','):
            postura, cantidad = par.split('=')
            if postura not in resultado or postura in vistos or not 0 <= int(cantidad) <= 50:
                raise ValueError
            vistos.add(postura)
            resultado[postura] = int(cantidad)
    except ValueError:
        raise argparse.ArgumentTypeError('Usa favor=4,contra=0,neutral=0; cantidades de 0 a 50')
    return resultado

