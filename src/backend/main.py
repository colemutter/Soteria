import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.agent import poller_report_router, router as agent_router
from api.operations import router as operations_router

app = FastAPI(title="Soteria API")

frontend_origin = os.getenv("FRONTEND_ORIGIN")

if frontend_origin:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[frontend_origin],
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
