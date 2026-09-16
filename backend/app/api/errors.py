"""Small shared error envelope for application-level API failures."""

from collections.abc import Mapping

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict


class APIErrorDetail(BaseModel):
    """Safe machine-readable and human-readable error details."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    message: str


class APIErrorResponse(BaseModel):
    """Standard envelope for controlled application errors."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    error: APIErrorDetail


class APIError(Exception):
    """Controlled exception that can be rendered safely over HTTP."""

    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = dict(headers or {})
        super().__init__(message)


async def api_error_handler(_request: Request, exc: APIError) -> JSONResponse:
    """Render an APIError without exposing internal exception details."""

    response = APIErrorResponse(error=APIErrorDetail(code=exc.code, message=exc.message))
    return JSONResponse(
        status_code=exc.status_code,
        content=response.model_dump(),
        headers=exc.headers,
    )


async def request_validation_error_handler(
    _request: Request,
    _exc: RequestValidationError,
) -> JSONResponse:
    """Reject invalid input without reflecting raw user-controlled values."""

    response = APIErrorResponse(
        error=APIErrorDetail(
            code="invalid_request",
            message="The request payload is invalid.",
        )
    )
    return JSONResponse(status_code=422, content=response.model_dump())


def register_api_error_handlers(application: FastAPI) -> None:
    """Register controlled application-error handling on an app instance."""

    application.add_exception_handler(APIError, api_error_handler)
    application.add_exception_handler(RequestValidationError, request_validation_error_handler)
