import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.agent import poller_report_router, router as agent_router
from api.operations import router as operations_router


def split_env_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


app = FastAPI(title="Soteria API")

frontend_origins = [
    *split_env_list(os.getenv("FRONTEND_ORIGINS")),
    *split_env_list(os.getenv("FRONTEND_ORIGIN")),
]
frontend_origin_regex = os.getenv("FRONTEND_ORIGIN_REGEX")

if frontend_origins or frontend_origin_regex:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=frontend_origins,
        allow_origin_regex=frontend_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(agent_router)
app.include_router(poller_report_router)
app.include_router(operations_router)
