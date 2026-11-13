from django.http import Http404, JsonResponse
from rest_framework.views import exception_handler

def primer_mensaje(datos):
    if isinstance(datos, dict):
        return primer_mensaje(next(iter(datos.values()))) if datos else 'Solicitud inválida'
    if isinstance(datos, list):
        return primer_mensaje(datos[0]) if datos else 'Solicitud inválida'
    return str(datos)

def manejar_error(exc, contexto):
    respuesta = exception_handler(exc, contexto)
    if respuesta is not None:
        mensaje = 'No se encontró el recurso' if isinstance(exc, Http404) else primer_mensaje(respuesta.data)
        respuesta.data = {'error': mensaje}
    return respuesta

def no_encontrado(request, exception):
    return JsonResponse({'error': 'No se encontró el recurso'}, status=404)

def error_servidor(request):
    return JsonResponse({'error': 'Error interno del servidor'}, status=500)
