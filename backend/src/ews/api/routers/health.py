"""Health endpoint for monitoring and container orchestration."""

import asyncio
import logging
from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ews.api.dependencies import LLMGatewayDep, SessionDep, SettingsDep
from ews.llm.gateway import LLMGateway

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


class CheckResult(BaseModel):
    """Outcome of one dependency check."""

    status: Literal["pass", "fail"]
    message: str


class HealthResponse(BaseModel):
    """Overall status plus the result of each check."""

    status: Literal["healthy", "unhealthy"]
    checks: dict[str, CheckResult]


async def check_database(session: AsyncSession, timeout_seconds: float) -> CheckResult:
    """Check that the database answers a trivial query within the timeout."""
    try:
        async with asyncio.timeout(timeout_seconds):
            await session.execute(text("SELECT 1"))
    except TimeoutError:
        logger.warning("Database health check timed out after %ss", timeout_seconds)
        return CheckResult(status="fail", message="timed out")
    except Exception:
        # Connection failures surface as driver, OS or SQLAlchemy errors; any of
        # them means the database is not usable, which is what this check reports.
        logger.warning("Database health check failed", exc_info=True)
        return CheckResult(status="fail", message="unreachable")
    return CheckResult(status="pass", message="reachable")


async def check_llm(gateway: LLMGateway, timeout_seconds: float) -> CheckResult:
    """Check that the configured model can serve a call within the timeout."""
    availability = await gateway.availability(timeout_seconds)
    if not availability.available:
        logger.warning("LLM health check failed: %s", availability.message)
    return CheckResult(
        status="pass" if availability.available else "fail",
        message=availability.message,
    )


@router.get(
    "/health",
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": HealthResponse}},
)
async def health(
    session: SessionDep,
    settings: SettingsDep,
    gateway: LLMGatewayDep,
    response: Response,
) -> HealthResponse:
    """Report whether the service and its dependencies are usable."""
    timeout = settings.health_check_timeout_seconds
    database, llm = await asyncio.gather(
        check_database(session, timeout), check_llm(gateway, timeout)
    )
    checks = {"database": database, "llm": llm}
    # Without a model, ingestion and screening still run, so only the database
    # decides the overall status; the container health check relies on this
    healthy = database.status == "pass"
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(status="healthy" if healthy else "unhealthy", checks=checks)
