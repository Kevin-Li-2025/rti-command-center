from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from rti.models.schemas import PipelineState

log = logging.getLogger("rti.graph")


@dataclass
class Node:
    name: str
    agent: object  # has async run(PipelineState) -> PipelineState
    deps: list[str] = field(default_factory=list)


class DAGRunner:
    """
    tiny DAG executor. nodes with satisfied deps run in parallel.
    failed nodes get logged but don't blow up the pipeline.
    """

    def __init__(self):
        self.nodes: dict[str, Node] = {}

    def add(self, name: str, agent: object, deps: list[str] | None = None):
        self.nodes[name] = Node(name=name, agent=agent, deps=deps or [])

    async def run(self, state: PipelineState) -> PipelineState:
        done: set[str] = set()

        while len(done) < len(self.nodes):
            ready = [
                n for n in self.nodes.values()
                if n.name not in done
                and all(d in done for d in n.deps)
            ]
            if not ready:
                stuck = set(self.nodes) - done
                raise RuntimeError(f"dag stuck, unresolved: {stuck}")

            names = [n.name for n in ready]
            log.info("running: %s", names)

            results = await asyncio.gather(
                *(n.agent.run(state) for n in ready),
                return_exceptions=True,
            )

            for node, result in zip(ready, results):
                if isinstance(result, Exception):
                    log.error("agent '%s' blew up: %s", node.name, result)
                else:
                    state = result
                done.add(node.name)

        return state
