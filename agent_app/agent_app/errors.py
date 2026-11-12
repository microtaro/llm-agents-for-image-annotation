"""Errors the API returns as {"error": {code, message, details}}, and the base input model."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details=None):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message
        self.details = details or {}


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


def not_found(what):
    return ApiError(404, "not_found", f"{what} does not exist")


def invalid(message, **details):
    return ApiError(422, "invalid_input", message, details)


def body(code, message, details=None):
    return {"error": {"code": code, "message": message, "details": details or {}}}


def problems_of(errors, at=()):
    """A validation's errors as the API says them (type and limit let the screen say in its own
    words which field is wrong and how); at: where the validated part sits in the request."""
    return [
        {
            "at": ".".join(str(p) for p in (*at, *e["loc"])),
            "message": e["msg"],
            "type": e["type"],
            "limit": next(
                (
                    e.get("ctx", {})[k]
                    for k in ("max_length", "min_length", "ge", "le", "gt", "lt")
                    if k in e.get("ctx", {})
                ),
                None,
            ),
        }
        for e in errors
    ]


def install(app: FastAPI):
    @app.exception_handler(ApiError)
    async def api_error(_request: Request, exc: ApiError):
        return JSONResponse(body(exc.code, exc.message, exc.details), exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError):
        return JSONResponse(
            body(
                "invalid_input",
                "The request is not valid",
                {"problems": problems_of(exc.errors())},
            ),
            422,
        )
