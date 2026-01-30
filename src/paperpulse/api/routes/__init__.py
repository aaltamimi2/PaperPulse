"""API route modules."""

from paperpulse.api.routes.auth import router as auth_router
from paperpulse.api.routes.clustering import router as clustering_router
from paperpulse.api.routes.papers import router as papers_router
from paperpulse.api.routes.profiles import router as profiles_router
from paperpulse.api.routes.reading_lists import router as reading_lists_router
from paperpulse.api.routes.users import router as users_router

__all__ = [
    "auth_router",
    "users_router",
    "profiles_router",
    "papers_router",
    "clustering_router",
    "reading_lists_router",
]
