import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.core.exceptions import AppError

logger = logging.getLogger(__name__)

STATUS_ERROR_CODES = {
    HTTPStatus.BAD_REQUEST: 40000,
    HTTPStatus.UNAUTHORIZED: 40100,
    HTTPStatus.FORBIDDEN: 40300,
    HTTPStatus.NOT_FOUND: 40400,
    HTTPStatus.CONFLICT: 40900,
    HTTPStatus.UNPROCESSABLE_ENTITY: 40001,
}


def error_content(*, code: int, message: str) -> dict[str, int | str | None]:
    return {"code": code, "message": message, "data": None}


async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=error_content(code=exc.code, message=exc.message),
        headers=exc.headers,
    )


async def handle_validation_error(
    _request: Request,
    _exc: RequestValidationError,
) -> JSONResponse:
    return JSONResponse(
        status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        content=error_content(code=40001, message="Invalid request"),
    )


async def handle_http_error(_request: Request, exc: HTTPException) -> JSONResponse:
    try:
        default_message = HTTPStatus(exc.status_code).phrase
    except ValueError:
        default_message = "Request failed"
    message = exc.detail if isinstance(exc.detail, str) else default_message
    code = STATUS_ERROR_CODES.get(exc.status_code, exc.status_code * 100)
    return JSONResponse(
        status_code=exc.status_code,
        content=error_content(code=code, message=message),
        headers=exc.headers,
    )


async def handle_unexpected_error(request: Request, _exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error for %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        content=error_content(code=50000, message="Internal server error"),
    )


def register_exception_handlers(application: FastAPI) -> None:
    application.add_exception_handler(AppError, handle_app_error)
    application.add_exception_handler(RequestValidationError, handle_validation_error)
    application.add_exception_handler(HTTPException, handle_http_error)
    application.add_exception_handler(Exception, handle_unexpected_error)
