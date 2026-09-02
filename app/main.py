"""FastAPI entrypoint for the local, single-user MVP."""

from __future__ import annotations

from contextlib import asynccontextmanager
import os
from typing import AsyncIterator

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.db import PROJECT_ROOT, STATIC_DIR, initialize_database
from app.schemas import ErrorResponse, Project, ProjectCreate, ProjectUpdate
from app.services import repositories
from app.routes.upstream import router as upstream_router
from app.routes.downstream import router as downstream_router


def error_response(status_code: int, code: str, message: str, details: dict | None = None) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": {"code": code, "message": message, "details": details or {}}})


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Keep credentials in the local project .env; do not log its values.
    load_dotenv(PROJECT_ROOT / ".env")
    # Keep all declared DeepSeek settings loaded for this local MVP. The vision
    # setting is not invoked by the text-only upstream route.
    app.state.deepseek_settings = {
        "has_api_key": bool(os.getenv("DEEPSEEK_API_KEY")),
        "base_url": os.getenv("DEEPSEEK_BASE_URL"),
        "text_model": os.getenv("DEEPSEEK_TEXT_MODEL"),
        "vision_model": os.getenv("DEEPSEEK_VISION_MODEL"),
    }
    initialize_database()
    yield


app = FastAPI(title="筑析 AI MVP", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR, check_dir=False), name="static")
app.include_router(upstream_router)
app.include_router(downstream_router)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return error_response(422, "VALIDATION_ERROR", "请求数据不符合要求。", {"issues": exc.errors()})


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict) and {"code", "message"}.issubset(exc.detail):
        return error_response(exc.status_code, exc.detail["code"], exc.detail["message"], exc.detail.get("details"))
    if exc.status_code == 404:
        return error_response(404, "NOT_FOUND", "请求的资源不存在。")
    return error_response(exc.status_code, "VALIDATION_ERROR", str(exc.detail))


@app.exception_handler(Exception)
async def internal_error_handler(_: Request, __: Exception) -> JSONResponse:
    return error_response(500, "INTERNAL_ERROR", "服务内部错误，请查看本地服务日志。")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def index() -> Response:
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return Response("筑析 AI MVP 基础服务已启动；前端页面待挂载。", media_type="text/plain; charset=utf-8")


@app.post("/api/projects", response_model=Project, status_code=201, responses={422: {"model": ErrorResponse}})
def create_project(payload: ProjectCreate) -> dict:
    return repositories.create_project(**payload.model_dump())


@app.get("/api/projects/{project_id}", response_model=Project, responses={404: {"model": ErrorResponse}})
def read_project(project_id: str) -> dict:
    project = repositories.get_project(project_id)
    if project is None:
        raise StarletteHTTPException(status_code=404, detail="项目不存在。")
    return project


@app.patch("/api/projects/{project_id}", response_model=Project, responses={404: {"model": ErrorResponse}})
def update_project(project_id: str, payload: ProjectUpdate) -> dict:
    project = repositories.update_project(project_id, **payload.model_dump(exclude_unset=True))
    if project is None:
        raise StarletteHTTPException(status_code=404, detail="项目不存在。")
    return project


# Upload, card-generation, review, strategy, and export routes are intentionally
# attached by their dedicated MVP modules. Repositories above are their stable API.
