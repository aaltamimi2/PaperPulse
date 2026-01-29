"""API route modules."""

from paperpulse.api.routes.auth import router as auth_router
from paperpulse.api.routes.profiles import router as profiles_router
from paperpulse.api.routes.users import router as users_router

__all__ = ["auth_router", "users_router", "profiles_router"]
