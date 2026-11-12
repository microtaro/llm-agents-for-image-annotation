"""The one operation that starts the plan's draft again from a place (definition 16.2): blank, an
earlier version of this dataset or another dataset's version (drafts.start_plan). The workers and
the outside start a plan here; the plan's screen asks its worker (definition 26.7).
"""

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import Field

from . import drafts
from .actors import who_of
from .errors import Model
from .run_routes import db_of, no_worker

router = APIRouter(prefix="/v1")


class StartInput(Model):
    kind: Literal["blank", "version", "other"]
    dataset_id: str | None = Field(
        None, description="For other: the dataset whose version to start from."
    )
    revision: int | None = Field(
        None, description="For version and other: the version to start from."
    )


@router.post("/datasets/{dataset_id}/plan/start")
def post_start(request: Request, dataset_id: str, body: StartInput):
    """The draft started again from a place (definition 16.2)."""
    no_worker(request)
    return drafts.start_plan(
        db_of(request), dataset_id, body.model_dump(), who_of(request)
    )
