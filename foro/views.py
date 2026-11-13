import random
import secrets
import statistics
from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import Count, Max, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, serializers, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .models import Hilo, Comentario, Corrida, AgenteLector, Snapshot
from .serializers import (HiloSerializer, ComentarioSerializer, CorridaSerializer,
                          SiembraSerializer, AgenteSerializer, SnapshotSerializer)
from .moderacion import moderar

class TokenPresentador(TokenObtainPairView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'token'

class RefrescarToken(TokenRefreshView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'token'

class Hilos(generics.ListAPIView):
    queryset = Hilo.objects.annotate(n_comentarios=Count('comentarios')).order_by('id')
    serializer_class = HiloSerializer

class DetalleHilo(generics.RetrieveAPIView):
    queryset = Hilo.objects.annotate(n_comentarios=Count('comentarios'))
    serializer_class = HiloSerializer

def entero_parametro(peticion, nombre, defecto=None):
    valor = peticion.query_params.get(nombre, defecto)
    if valor is None:
        return None
    try:
        valor = int(valor)
        if valor < 0:
            raise ValueError
        return valor
    except (ValueError, TypeError):
        raise ValidationError(f'{nombre} debe ser un entero no negativo')

def corrida_consulta(peticion, hilo):
    identificador = entero_parametro(peticion, 'corrida')
    return get_object_or_404(Corrida, pk=identificador, hilo=hilo) if identificador is not None else None

def exigir_abierta(corrida):
    if corrida.cerrada_en:
        raise ValidationError('La corrida está cerrada')

def guardar_snapshot(datos, corrida):
    try:
        with transaction.atomic():
            return Snapshot.objects.create(hilo=corrida.hilo, corrida=corrida, **datos)
    except IntegrityError:
        raise ValidationError('Ya existe un snapshot para esta ronda')

class Comentarios(APIView):
    def get(self, request, pk):
        hilo = get_object_or_404(Hilo, pk=pk)
        desde = entero_parametro(request, 'desde_id', 0)
        corrida = corrida_consulta(request, hilo)
        consulta = Comentario.objects.filter(hilo=hilo, id__gt=desde)
        if corrida:
            consulta = consulta.filter(Q(corrida=corrida) | Q(corrida__isnull=True))
        comentarios = list(consulta.order_by('id')[:100])
        return Response({'comentarios': ComentarioSerializer(comentarios, many=True).data,
                         'ultimo_id': comentarios[-1].id if comentarios else desde})

    def post(self, request, pk):
        hilo = get_object_or_404(Hilo, pk=pk)
        if hilo.estado == 'cerrado':
            raise PermissionDenied('El hilo está cerrado')
        token = request.headers.get('X-Bot-Token', '')
        autorizado = bool(settings.BOT_TOKEN) and secrets.compare_digest(token.encode(), settings.BOT_TOKEN.encode())
        if not isinstance(request.data, dict):
            raise ValidationError('El comentario debe ser un objeto JSON')
        datos = request.data.copy()
        if not autorizado:
            datos.update(es_bot=False, postura_bot=None, corrida=None)
        serializador = ComentarioSerializer(data=datos)
        serializador.is_valid(raise_exception=True)
        valores = serializador.validated_data
        if valores.get('es_bot') and not valores.get('postura_bot'):
            raise ValidationError('Los bots deben declarar su postura')
        if not valores.get('es_bot'):
            valores['postura_bot'] = None
            valores['corrida'] = None
        corrida = valores.get('corrida')
        if corrida:
            if corrida.hilo_id != hilo.id:
                raise ValidationError('La corrida no pertenece a este hilo')
            exigir_abierta(corrida)
        moderar(valores['texto'])
        moderar(valores['autor_nombre'])
        if not valores.get('es_bot'):
            # REMOTE_ADDR: configurar correctamente el proxy de confianza; no confiar en X-Forwarded-For del cliente.
            clave = 'comentario:' + request.META.get('REMOTE_ADDR', 'desconocida')
            if not cache.add(clave, True, timeout=5):
                return Response({'error': 'Espera 5 segundos entre comentarios'}, status=429)
        comentario = serializador.save(hilo=hilo)
        return Response(ComentarioSerializer(comentario).data, status=201)

class Snapshots(APIView):
    def get(self, request, pk):
        hilo = get_object_or_404(Hilo, pk=pk)
        corrida = corrida_consulta(request, hilo)
        consulta = Snapshot.objects.filter(hilo=hilo, id__gt=entero_parametro(request, 'desde_id', 0))
        if corrida:
            consulta = consulta.filter(corrida=corrida)
        return Response(SnapshotSerializer(consulta.order_by('corrida_id', 'ronda'), many=True).data)

class Corridas(APIView):
    def get(self, request, pk):
        hilo = get_object_or_404(Hilo, pk=pk)
        return Response(CorridaSerializer(hilo.corridas.order_by('id'), many=True).data)

class PanelCrearHilo(generics.CreateAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = HiloSerializer
    def perform_create(self, serializer):
        serializer.save(creado_por=self.request.user)

class SoloPatch:
    http_method_names = ['patch', 'options']

class PanelHilo(SoloPatch, generics.UpdateAPIView):
    permission_classes = [IsAdminUser]
    queryset = Hilo.objects.all()
    serializer_class = HiloSerializer

class PanelCorridas(generics.CreateAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = CorridaSerializer
    def perform_create(self, serializer):
        serializer.save(hilo=get_object_or_404(Hilo, pk=self.kwargs['pk']))

class PanelCerrarCorrida(APIView):
    permission_classes = [IsAdminUser]
    def patch(self, request, pk):
        corrida = get_object_or_404(Corrida, pk=pk)
        if corrida.cerrada_en is None:
            corrida.cerrada_en = timezone.now()
            corrida.save(update_fields=['cerrada_en'])
        return Response(CorridaSerializer(corrida).data)

PERFILES = ['Pragmático, valora la evidencia', 'Escéptico, compara argumentos',
            'Empático, considera el bienestar colectivo', 'Cauteloso, prefiere cambios graduales',
            'Curioso, abierto a perspectivas nuevas', 'Analítico, busca datos concretos']

class Sembrar(APIView):
    permission_classes = [IsAdminUser]
    @transaction.atomic
    def post(self, request, pk):
        corrida = get_object_or_404(Corrida.objects.select_for_update(), pk=pk)
        exigir_abierta(corrida)
        if corrida.agentes.exists() or corrida.snapshots.exists():
            raise ValidationError('La corrida ya tiene población o snapshots; crea otra para repetir el experimento')
        entrada = SiembraSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        datos = entrada.validated_data
        azar = random.Random(corrida.semilla)
        agentes = []
        for i in range(datos['n']):
            postura = max(-100, min(100, azar.gauss(datos['media'], datos['dispersion'])))
            agentes.append(AgenteLector(hilo_id=corrida.hilo_id, corrida=corrida, nombre=f'Lector_{i+1:03}',
                perfil=azar.choice(PERFILES), postura_inicial=postura, postura_actual=postura,
                apertura=azar.uniform(0.1, 0.6)))
        AgenteLector.objects.bulk_create(agentes)
        return Response(AgenteSerializer(agentes, many=True).data, status=201)

class Agentes(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = AgenteSerializer
    def get_queryset(self):
        corrida = get_object_or_404(Corrida, pk=self.kwargs['pk'])
        return corrida.agentes.order_by('id')

class PanelAgente(SoloPatch, generics.UpdateAPIView):
    permission_classes = [IsAdminUser]
    queryset = AgenteLector.objects.select_related('corrida')
    serializer_class = AgenteSerializer
    def perform_update(self, serializer):
        exigir_abierta(serializer.instance.corrida)
        serializer.save()

class PanelSnapshot(APIView):
    permission_classes = [IsAdminUser]
    @transaction.atomic
    def post(self, request, pk):
        corrida = get_object_or_404(Corrida.objects.select_for_update(), pk=pk)
        exigir_abierta(corrida)
        entrada = SnapshotSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        foto = guardar_snapshot(entrada.validated_data, corrida)
        return Response(SnapshotSerializer(foto).data, status=201)

class SnapshotAuto(APIView):
    permission_classes = [IsAdminUser]
    @transaction.atomic
    def post(self, request, pk):
        corrida = get_object_or_404(Corrida.objects.select_for_update(), pk=pk)
        exigir_abierta(corrida)
        posturas = list(corrida.agentes.values_list('postura_actual', flat=True))
        if not posturas:
            raise ValidationError('Primero siembra la población')
        if 'ronda' in request.data:
            campo = serializers.IntegerField(min_value=0)
            ronda = campo.run_validation(request.data['ronda'])
        else:
            ultima = corrida.snapshots.aggregate(ultima=Max('ronda'))['ultima']
            ronda = 0 if ultima is None else ultima + 1
        histograma = {str(n): 0 for n in range(-100, 100, 20)}
        for postura in posturas:
            tramo = min(9, int((postura + 100) // 20))
            histograma[str(-100 + 20 * tramo)] += 1
        conteos = dict(corrida.comentarios.filter(es_bot=True).values('postura_bot').annotate(n=Count('id')).values_list('postura_bot', 'n'))
        datos = {'ronda': ronda, 'promedio': statistics.mean(posturas), 'desviacion': statistics.pstdev(posturas),
                 'histograma': histograma, 'n_comentarios_bot': sum(conteos.values()),
                 **{'n_' + p: conteos.get(p, 0) for p in ['favor', 'contra', 'neutral']}}
        return Response(SnapshotSerializer(guardar_snapshot(datos, corrida)).data, status=201)
