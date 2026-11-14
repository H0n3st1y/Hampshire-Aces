"""Run from project root: python -m uvicorn backend.main:app --port 8000."""
import logging
import os

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from .contracts import EvaluateRequest, Evaluation, ScenarioList
from .fixtures import load_scenarios, public_scenarios
from .service import evaluate_scenario

logger = logging.getLogger(__name__)
DEFAULT_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000"


def error_response(status, code, message):
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def create_app() -> FastAPI:
    app = FastAPI(title="Synthetic Investing Simulator", version="1.0.0")
    origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", DEFAULT_ORIGINS).split(",") if o.strip()]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False,
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
    app.state.scenarios = load_scenarios()

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        return error_response(400, "INVALID_REQUEST", "Expected schema_version '1', a scenario_id, and action strategy, hold, increase, or reduce.")

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return error_response(exc.status_code, "HTTP_ERROR", "The requested resource or method is unavailable.")

    @app.exception_handler(Exception)
    async def server_error(request: Request, exc: Exception):
        logger.error("Evaluation failed (%s)", type(exc).__name__)
        return error_response(500, "INTERNAL_ERROR", "The simulator could not complete this request.")

    @app.get("/api/scenarios", response_model=ScenarioList)
    def get_scenarios():
        return public_scenarios(app.state.scenarios)

    @app.post("/api/evaluate", response_model=Evaluation)
    def evaluate(body: EvaluateRequest):
        fixture = app.state.scenarios.get(body.scenario_id)
        if fixture is None:
            return error_response(400, "INVALID_REQUEST", "Unknown synthetic scenario_id.")
        return evaluate_scenario(fixture.model_copy(deep=True), body.action)

    return app


app = create_app()
