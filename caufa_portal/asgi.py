import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "caufa_portal.settings")

asgi_app = get_asgi_application()

import core_system.routing  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": asgi_app,
        # Origin-validated handshake: a foreign page can no longer even open
        # a socket (bearer ?token= stays as defense in depth in consumers).
        "websocket": AllowedHostsOriginValidator(
            AuthMiddlewareStack(
                URLRouter(core_system.routing.websocket_urlpatterns)
            )
        ),
    }
)
