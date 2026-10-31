from fastapi import APIRouter

from app.api.v1 import analysis, resumes, session, transitions

router = APIRouter()
for module in (session, transitions, resumes, analysis):
    router.include_router(module.router)
