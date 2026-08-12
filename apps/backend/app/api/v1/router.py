from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.groups import router as groups_router
from app.api.v1.hangouts import router as hangouts_router
from app.api.v1.health import router as health_router
from app.api.v1.proposals import router as proposals_router
from app.api.v1.time_options import router as time_options_router
from app.api.v1.users import router as users_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["system"])
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(groups_router)
api_router.include_router(hangouts_router)
api_router.include_router(proposals_router)
api_router.include_router(time_options_router)
