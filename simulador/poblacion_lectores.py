import random
from .cliente import Cliente
from .ia import nueva_postura

def avanzar_ronda(corrida_id, cliente=None, azar=None):
    cliente = cliente or Cliente()
    if not cliente.refresco:
        cliente.autenticar()
    agentes = cliente.get(f'/panel/corridas/{corrida_id}/agentes/')
    if not agentes:
        raise RuntimeError('La corrida no tiene agentes')
    hilo = cliente.get(f'/hilos/{agentes[0]["hilo"]}/')
    # Una sola descarga; cada agente recibe lo que todavía no ha leído.
    desde = min(a['ultimo_comentario_leido_id'] for a in agentes)
    comentarios = cliente.comentarios(hilo['id'], corrida_id, desde)
    for agente in agentes:
        nuevos = [c for c in comentarios if c['id'] > agente['ultimo_comentario_leido_id']]
        if nuevos:
            resultado = nueva_postura(agente, hilo['pregunta_postura'], nuevos, azar)
            cliente.patch(f'/panel/agentes/{agente["id"]}/', {
                'postura_actual': resultado['postura'], 'ultimo_comentario_leido_id': nuevos[-1]['id'],
            })
    return cliente.post(f'/panel/corridas/{corrida_id}/snapshot_auto/')
