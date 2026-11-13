from django.core.management.base import BaseCommand
from foro.moderacion import palabras

class Command(BaseCommand):
    help = 'Valida y carga la lista local de palabras bloqueadas'

    def handle(self, *args, **options):
        palabras.cache_clear()
        self.stdout.write(self.style.SUCCESS(f'{len(palabras())} palabras cargadas. Reinicia el servidor si editaste la lista.'))
