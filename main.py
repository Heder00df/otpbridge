import os
import uvicorn
from fastapi import FastAPI
from api.supplier import router as supplier_router

app = FastAPI(title="OTPBridge Supplier API")
app.include_router(supplier_router)

# Webhooks de hardware
from modems.goip.webhook import goip_router
from modems.openvox.webhook import openvox_router
from modems.e303.webhook import e303_router
app.include_router(goip_router)
app.include_router(openvox_router)
app.include_router(e303_router)

# Endpoint interno usado pelo AGI do Asterisk
from api.internal import router as internal_router
app.include_router(internal_router)

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
