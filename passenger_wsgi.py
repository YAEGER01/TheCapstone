import os
import sys

# Make sure the app root is on the import path (Passenger sometimes
# doesn't set PYTHONPATH if the app was created manually).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "caufa_portal.settings")

# .env is loaded automatically by settings.py via load_dotenv(BASE_DIR / ".env"),
# so your .env must live next to manage.py.

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()