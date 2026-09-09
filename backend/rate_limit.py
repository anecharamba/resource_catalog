"""
Shared slowapi Limiter instance. Lives in its own module because both
main.py (which registers it on the app) and admin_routes.py (which applies
@limiter.limit(...) to specific endpoints) need it, and main.py already
imports admin_routes — importing the other direction would be circular.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
