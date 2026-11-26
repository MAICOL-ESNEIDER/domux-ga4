import os
import secrets


os.environ.setdefault("JWT_SECRET", secrets.token_urlsafe(48))
