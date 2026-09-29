from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.routes.auth import router as auth_router
from app.routes.links import router as links_router
from app.routes.redirects import router as redirects_router

app = FastAPI()
app.include_router(auth_router)
app.include_router(links_router)
app.include_router(redirects_router)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request, exc):
    # Validation errors must not echo passwords or other submitted values.
    errors = [
        {"loc": error["loc"], "msg": error["msg"], "type": error["type"]}
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": errors})

@app.get("/health")
def get_health():
    return {"status": "ok"}
