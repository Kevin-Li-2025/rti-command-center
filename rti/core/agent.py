from __future__ import annotations

from typing import Protocol, runtime_checkable
from rti.models.schemas import PipelineState


@runtime_checkable
class Agent(Protocol):
    """state in, state out. that's it."""
    name: str

    async def run(self, state: PipelineState) -> PipelineState: ...
