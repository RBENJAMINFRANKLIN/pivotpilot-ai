from fastapi import APIRouter

from app.api.v1 import analysis, assessments, commands, dashboard, plans, resumes, session, tracking, transitions

router = APIRouter()
for module in (session, transitions, resumes, analysis, assessments, plans, tracking, commands, dashboard):
    router.include_router(module.router)
