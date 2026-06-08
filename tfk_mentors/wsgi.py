"""
WSGI config for tfk_mentors project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tfk_mentors.settings")

# Apache/mod_wsgi on older Ubuntu cannot pass env vars into WSGIDaemonProcess.
# When production.py exists on the server, use production settings automatically.
_production_settings = os.path.join(os.path.dirname(__file__), "production.py")
if os.path.isfile(_production_settings):
    os.environ["DJANGO_SETTINGS_MODULE"] = "tfk_mentors.production"

application = get_wsgi_application()
