from django.contrib import admin
from django.urls import path
from foro import views as v

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/token/', v.TokenPresentador.as_view()),
    path('api/token/refresh/', v.RefrescarToken.as_view()),
    path('api/hilos/', v.Hilos.as_view()),
    path('api/hilos/<int:pk>/', v.DetalleHilo.as_view()),
    path('api/hilos/<int:pk>/comentarios/', v.Comentarios.as_view()),
    path('api/hilos/<int:pk>/snapshots/', v.Snapshots.as_view()),
    path('api/hilos/<int:pk>/corridas/', v.Corridas.as_view()),
    path('api/panel/hilos/', v.PanelCrearHilo.as_view()),
    path('api/panel/hilos/<int:pk>/', v.PanelHilo.as_view()),
    path('api/panel/hilos/<int:pk>/corridas/', v.PanelCorridas.as_view()),
    path('api/panel/corridas/<int:pk>/', v.PanelCerrarCorrida.as_view()),
    path('api/panel/corridas/<int:pk>/sembrar/', v.Sembrar.as_view()),
    path('api/panel/corridas/<int:pk>/agentes/', v.Agentes.as_view()),
    path('api/panel/agentes/<int:pk>/', v.PanelAgente.as_view()),
    path('api/panel/corridas/<int:pk>/snapshots/', v.PanelSnapshot.as_view()),
    path('api/panel/corridas/<int:pk>/snapshot_auto/', v.SnapshotAuto.as_view()),
]

handler404 = 'foro.errores.no_encontrado'
handler500 = 'foro.errores.error_servidor'
