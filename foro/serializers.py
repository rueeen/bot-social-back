import math
from rest_framework import serializers
from .models import Hilo, Comentario, Corrida, AgenteLector, Snapshot

class NumeroFinito(serializers.FloatField):
    def to_internal_value(self, data):
        valor = super().to_internal_value(data)
        if not math.isfinite(valor):
            raise serializers.ValidationError('El número debe ser finito')
        return valor

class HiloSerializer(serializers.ModelSerializer):
    n_comentarios = serializers.IntegerField(read_only=True)
    class Meta:
        model = Hilo
        fields = ['id', 'titulo', 'tema', 'pregunta_postura', 'estado', 'creado', 'creado_por', 'n_comentarios']
        read_only_fields = ['creado_por']

class ComentarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Comentario
        fields = ['id', 'hilo', 'autor_nombre', 'es_bot', 'postura_bot', 'texto', 'corrida', 'creado']
        read_only_fields = ['hilo']

class CorridaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Corrida
        fields = ['id', 'hilo', 'etiqueta', 'mezcla_bots', 'semilla', 'creada', 'cerrada_en']
        read_only_fields = ['hilo', 'cerrada_en']

    def validate_mezcla_bots(self, valor):
        if not isinstance(valor, dict) or set(valor) - {'favor', 'contra', 'neutral'}:
            raise serializers.ValidationError('La mezcla admite favor, contra y neutral')
        if any(type(n) is not int or not 0 <= n <= 50 for n in valor.values()):
            raise serializers.ValidationError('Cada cantidad de bots debe ser un entero entre 0 y 50')
        return {postura: valor.get(postura, 0) for postura in ['favor', 'contra', 'neutral']}

class SiembraSerializer(serializers.Serializer):
    n = serializers.IntegerField(min_value=1, max_value=500, default=30)
    media = NumeroFinito(min_value=-100, max_value=100, default=0)
    dispersion = NumeroFinito(min_value=0, max_value=200, default=40)

class AgenteSerializer(serializers.ModelSerializer):
    postura_actual = NumeroFinito(min_value=-100, max_value=100)
    class Meta:
        model = AgenteLector
        fields = ['id', 'hilo', 'corrida', 'nombre', 'perfil', 'postura_inicial', 'postura_actual', 'apertura', 'ultimo_comentario_leido_id']
        read_only_fields = ['hilo', 'corrida', 'nombre', 'perfil', 'postura_inicial', 'apertura']

    def validate_ultimo_comentario_leido_id(self, valor):
        if self.instance and valor < self.instance.ultimo_comentario_leido_id:
            raise serializers.ValidationError('El cursor de lectura no puede retroceder')
        if valor and self.instance:
            from django.db.models import Q
            existe = Comentario.objects.filter(id=valor, hilo_id=self.instance.hilo_id).filter(Q(corrida_id=self.instance.corrida_id) | Q(corrida__isnull=True)).exists()
            if not existe:
                raise serializers.ValidationError('El comentario no pertenece a este escenario')
        return valor

class SnapshotSerializer(serializers.ModelSerializer):
    promedio = NumeroFinito(min_value=-100, max_value=100)
    desviacion = NumeroFinito(min_value=0, max_value=100)
    class Meta:
        model = Snapshot
        fields = ['id', 'hilo', 'corrida', 'ronda', 'promedio', 'desviacion', 'histograma', 'n_comentarios_bot', 'n_favor', 'n_contra', 'n_neutral', 'creado']
        read_only_fields = ['hilo', 'corrida']
        validators = []

    def validate_histograma(self, valor):
        claves = {str(n) for n in range(-100, 100, 20)}
        if not isinstance(valor, dict) or set(valor) != claves or any(type(n) is not int or n < 0 for n in valor.values()):
            raise serializers.ValidationError('El histograma debe contener los diez tramos -100, -80, …, 80 con conteos enteros no negativos')
        return valor

    def validate(self, datos):
        if datos.get('n_comentarios_bot', 0) != sum(datos.get('n_' + p, 0) for p in ['favor', 'contra', 'neutral']):
            raise serializers.ValidationError('Los conteos por postura deben sumar el total de bots')
        return datos
