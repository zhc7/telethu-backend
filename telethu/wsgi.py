"""
WSGI config for telethu project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/wsgi/
"""

import os
import threading

from django.core.wsgi import get_wsgi_application

from utils.storage import start_storage

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'telethu.settings')

application = get_wsgi_application()

threading.Thread(target=start_storage).start()
