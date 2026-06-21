from fastapi import FastAPI
from api.agent import router as agent_router

app = FastAPI(title="Soteria API")
app.include_router(agent_router)