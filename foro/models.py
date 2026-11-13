from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.db.models import Q

POSTURAS = [('neutral', 'Neutral'), ('favor', 'A favor'), ('contra', 'En contra')]
LIMITES_POSTURA = [MinValueValidator(-100), MaxValueValidator(100)]

class Hilo(models.Model):
    titulo = models.CharField(max_length=200)
    tema = models.TextField()
    pregunta_postura = models.TextField()
    estado = models.CharField(max_length=10, choices=[('abierto', 'Abierto'), ('cerrado', 'Cerrado')], default='abierto')
    creado = models.DateTimeField(auto_now_add=True)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    def __str__(self):
        return self.titulo

class Corrida(models.Model):
    hilo = models.ForeignKey(Hilo, on_delete=models.CASCADE, related_name='corridas')
    etiqueta = models.CharField(max_length=100)
    mezcla_bots = models.JSONField(default=dict)
    semilla = models.IntegerField(default=42)
    creada = models.DateTimeField(auto_now_add=True)
    cerrada_en = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.etiqueta

class Comentario(models.Model):
    hilo = models.ForeignKey(Hilo, on_delete=models.CASCADE, related_name='comentarios')
    autor_nombre = models.CharField(max_length=30)
    es_bot = models.BooleanField(default=False)
    postura_bot = models.CharField(max_length=7, choices=POSTURAS, null=True, blank=True)
    texto = models.CharField(max_length=400)
    corrida = models.ForeignKey(Corrida, on_delete=models.SET_NULL, null=True, blank=True, related_name='comentarios')
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['hilo', 'corrida', 'id'])]
        constraints = [models.CheckConstraint(condition=(Q(es_bot=False, postura_bot__isnull=True) | Q(es_bot=True, postura_bot__in=['neutral', 'favor', 'contra'])), name='marca_bot_coherente')]

class AgenteLector(models.Model):
    hilo = models.ForeignKey(Hilo, on_delete=models.CASCADE)
    corrida = models.ForeignKey(Corrida, on_delete=models.CASCADE, related_name='agentes')
    nombre = models.CharField(max_length=50)
    perfil = models.CharField(max_length=200)
    postura_inicial = models.FloatField(validators=LIMITES_POSTURA)
    postura_actual = models.FloatField(validators=LIMITES_POSTURA)
    apertura = models.FloatField(validators=[MinValueValidator(0), MaxValueValidator(1)])
    ultimo_comentario_leido_id = models.PositiveBigIntegerField(default=0)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(postura_inicial__gte=-100, postura_inicial__lte=100, postura_actual__gte=-100, postura_actual__lte=100), name='posturas_acotadas'),
            models.CheckConstraint(condition=Q(apertura__gte=0, apertura__lte=1), name='apertura_acotada'),
        ]

class Snapshot(models.Model):
    hilo = models.ForeignKey(Hilo, on_delete=models.CASCADE)
    corrida = models.ForeignKey(Corrida, on_delete=models.CASCADE, related_name='snapshots')
    ronda = models.PositiveIntegerField()
    promedio = models.FloatField(validators=LIMITES_POSTURA)
    desviacion = models.FloatField(validators=[MinValueValidator(0)])
    histograma = models.JSONField()
    n_comentarios_bot = models.PositiveIntegerField(default=0)
    n_favor = models.PositiveIntegerField(default=0)
    n_contra = models.PositiveIntegerField(default=0)
    n_neutral = models.PositiveIntegerField(default=0)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['corrida', 'ronda'], name='ronda_unica_por_corrida')]
