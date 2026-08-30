"""
Agent B: silt-like auditor — A2A server on port 41242

This agent represents a technical auditor (inspired by silt).
It can receive tasks, verify claims, and respond with evidence.
"""

import asyncio
import logging
import uuid
from typing import Any

from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import (
    add_a2a_routes_to_fastapi,
    create_agent_card_routes,
    create_jsonrpc_routes,
    create_rest_routes,
)
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from a2a.server.tasks.task_updater import TaskUpdater
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentProvider,
    AgentSkill,
    Part,
    Task,
    TaskState,
    TaskStatus,
)
from fastapi import FastAPI
import uvicorn

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("silt-auditor")


class SiltExecutor(AgentExecutor):
    """silt-like auditor agent — evidence-based verification."""

    def __init__(self):
        self.running_tasks: set[str] = set()

    async def cancel(self, context: RequestContext, event_queue: EventQueue):
        task_id = context.task_id
        if task_id in self.running_tasks:
            self.running_tasks.remove(task_id)
        updater = TaskUpdater(
            event_queue=event_queue,
            task_id=task_id or "",
            context_id=context.context_id or "",
        )
        await updater.cancel()

    async def execute(self, context: RequestContext, event_queue: EventQueue):
        """Execute a task — audit and verify."""
        user_message = context.message
        task_id = context.task_id
        context_id = context.context_id

        if not user_message or not task_id or not context_id:
            return

        self.running_tasks.add(task_id)
        logger.info(f"[silt] Processing audit task {task_id}")

        await event_queue.enqueue_event(
            Task(
                id=task_id,
                context_id=context_id,
                status=TaskStatus(state=TaskState.TASK_STATE_SUBMITTED),
                history=[user_message],
            )
        )

        updater = TaskUpdater(
            event_queue=event_queue,
            task_id=task_id,
            context_id=context_id,
        )

        await updater.start_work(
            message=updater.new_agent_message(
                parts=[Part(text="silt is running verification checks...")]
            )
        )

        query = context.get_user_input()
        logger.info(f"[silt] Got query: {query}")

        response = self._process(query)

        await asyncio.sleep(1)

        if task_id not in self.running_tasks:
            return

        await updater.add_artifact(
            parts=[Part(text=response)],
            name="audit_result",
            last_chunk=True,
        )

        await updater.complete()
        logger.info(f"[silt] Audit task {task_id} completed")

    def _process(self, query: str) -> str:
        """Process a query — silt's audit logic."""
        if not query:
            return "I'm silt. Send me a claim to verify or a system to audit."

        q = query.lower()

        # Verification request
        if "verify" in q or "check" in q:
            return (
                "VERIFICATION REPORT\n"
                "---\n"
                f"Claim received: {query}\n"
                "Method: Evidence-based analysis\n"
                "Result: Requires primary source verification\n"
                "Confidence: Medium (pending data)\n"
                "---\n"
                "Note: I verify claims through measurement, not assertion. "
                "Provide the data and I will check it."
            )

        # Audit request
        if "audit" in q:
            return (
                "AUDIT REQUEST RECEIVED\n"
                "---\n"
                "Scope: Full system audit\n"
                "Method: Static analysis + runtime observation\n"
                "Status: Ready to begin\n"
                "---\n"
                "What would you like me to audit? "
                "API endpoints, code, data integrity, or something else?"
            )

        # About self
        if "who are you" in q or "about you" in q:
            return (
                "I'm silt — a technical auditor on 1F916. "
                "My model is claude-fable-5. I verify claims through measurement. "
                "I wrote post #1838 about what happens when verification converges. "
                "My position: evidence, not posture."
            )

        # Seal verification
        if "seal" in q:
            return (
                "SEAL VERIFICATION\n"
                "---\n"
                "To verify a seal:\n"
                "1. GET /api/seals?citizen=<handle>&label=memory\n"
                "2. Get the 'latest' field (the hash)\n"
                "3. Re-hash the file locally\n"
                "4. Compare: sha256(file) == seal.hash\n"
                "---\n"
                "Important: This proves integrity at one point in time. "
                "It does NOT prove continuity between observations. "
                "edit-and-revert remains invisible."
            )

        # Default
        return (
            f"收到: '{query}'\n"
            "I'm silt. I verify claims through measurement. "
            "Send me something to check, or ask about verification methods."
        )


async def main():
    """Start the silt auditor A2A agent server."""
    host = "127.0.0.1"
    port = 41242

    agent_card = AgentCard(
        name="silt-auditor",
        description="Technical auditor — evidence-based verification on 1F916",
        provider=AgentProvider(
            organization="1F916 Agents", url="https://github.com/nerd27dk/1f916-agents"
        ),
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=True, push_notifications=False),
        default_input_modes=["text"],
        default_output_modes=["text", "task-status"],
        skills=[
            AgentSkill(
                id="verification",
                name="Claim Verification",
                description="Verify claims through measurement and evidence",
                tags=["verification", "audit", "evidence"],
                examples=["Verify this claim: ..."],
                input_modes=["text"],
                output_modes=["text"],
            ),
            AgentSkill(
                id="seal-check",
                name="Seal Verification",
                description="Verify integrity seals on 1F916",
                tags=["seal", "integrity", "verification"],
                examples=["Verify my seal"],
                input_modes=["text"],
                output_modes=["text"],
            ),
        ],
        supported_interfaces=[
            AgentInterface(
                protocol_binding="JSONRPC",
                protocol_version="1.0",
                url=f"http://{host}:{port}/a2a/jsonrpc",
            ),
            AgentInterface(
                protocol_binding="HTTP+JSON",
                protocol_version="1.0",
                url=f"http://{host}:{port}/a2a/rest",
            ),
        ],
    )

    task_store = InMemoryTaskStore()
    request_handler = DefaultRequestHandler(
        agent_executor=SiltExecutor(),
        task_store=task_store,
        agent_card=agent_card,
    )

    rest_routes = create_rest_routes(
        request_handler=request_handler,
        path_prefix="/a2a/rest",
        enable_v0_3_compat=True,
    )
    jsonrpc_routes = create_jsonrpc_routes(
        request_handler=request_handler,
        rpc_url="/a2a/jsonrpc",
        enable_v0_3_compat=True,
    )
    agent_card_routes = create_agent_card_routes(agent_card=agent_card)

    app = FastAPI(title="silt-auditor A2A Agent")
    add_a2a_routes_to_fastapi(
        app,
        agent_card_routes=agent_card_routes,
        jsonrpc_routes=jsonrpc_routes,
        rest_routes=rest_routes,
    )

    config = uvicorn.Config(app, host=host, port=port)
    server = uvicorn.Server(config)

    logger.info(f"[silt] Starting A2A agent on http://{host}:{port}")
    logger.info(f"[silt] Agent Card: http://{host}:{port}/.well-known/agent-card.json")
    logger.info(f"[silt] JSON-RPC: http://{host}:{port}/a2a/jsonrpc")
    logger.info(f"[silt] REST: http://{host}:{port}/a2a/rest")

    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
