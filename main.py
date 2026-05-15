import os
import uvicorn
from fastapi import FastAPI
from api.supplier import router as supplier_router
from api.dashboard.routes import router as dashboard_router

# Swagger visível apenas em desenvolvimento
_dev_mode = os.getenv("DEV", "false").lower() == "true"

app = FastAPI(
    title="OTPBridge Supplier API",
    docs_url="/docs" if _dev_mode else None,
    redoc_url="/redoc" if _dev_mode else None,
    openapi_url="/openapi.json" if _dev_mode else None,
)

# Endpoint público — HeroSMS chama este
app.include_router(supplier_router)

# Endpoints internos — ocultos do Swagger
app.include_router(dashboard_router, include_in_schema=False)

from modems.goip.webhook import goip_router
from modems.openvox.webhook import openvox_router
app.include_router(goip_router, include_in_schema=False)
app.include_router(openvox_router, include_in_schema=False)

pool = None

@app.on_event("startup")
async def startup():
    global pool
    if os.getenv("SIMULATE", "false").lower() == "true":
        from tests.simulator import SimulatedModemPool
        pool = SimulatedModemPool()
        print("[OTPBridge] modo SIMULAÇÃO ativo")
    else:
        from modems.pool import ModemPool
        pool = ModemPool()
    pool.start()
    app.state.modem_pool = pool

@app.on_event("shutdown")
async def shutdown():
    if pool:
        pool.stop()

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
