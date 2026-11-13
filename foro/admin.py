from django.contrib import admin
from django.db import transaction
from .models import Hilo, Corrida, Comentario, AgenteLector, Snapshot

@admin.action(description='Reiniciar simulación')
@transaction.atomic
def reiniciar_simulacion(modeladmin, request, queryset):
    for hilo in queryset:
        hilo.comentarios.filter(es_bot=True).delete()
        AgenteLector.objects.filter(hilo=hilo).delete()
        Snapshot.objects.filter(hilo=hilo).delete()
        hilo.corridas.all().delete()
    modeladmin.message_user(request, 'Simulación reiniciada; comentarios humanos conservados.')

@admin.register(Hilo)
class HiloAdmin(admin.ModelAdmin):
    list_display = ['id', 'titulo', 'estado', 'creado']
    list_filter = ['estado', 'id']
    actions = [reiniciar_simulacion]

@admin.register(Corrida)
class CorridaAdmin(admin.ModelAdmin):
    list_display = ['id', 'hilo', 'etiqueta', 'creada', 'cerrada_en']
    list_filter = ['hilo', 'etiqueta']

@admin.register(Comentario)
class ComentarioAdmin(admin.ModelAdmin):
    list_display = ['id', 'hilo', 'corrida', 'autor_nombre', 'es_bot', 'postura_bot']
    list_filter = ['hilo', 'corrida', 'es_bot', 'postura_bot']

@admin.register(AgenteLector)
class AgenteAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'hilo', 'corrida', 'postura_actual', 'apertura']
    list_filter = ['hilo', 'corrida']

@admin.register(Snapshot)
class SnapshotAdmin(admin.ModelAdmin):
    list_display = ['hilo', 'corrida', 'ronda', 'promedio', 'n_comentarios_bot']
    list_filter = ['hilo', 'corrida']
