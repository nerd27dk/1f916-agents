"""
A2A Demo — runs both agents and demonstrates inter-agent communication.

Works both locally and in Docker.
"""

import asyncio
import logging
import uuid
import os
import signal
import sys

logging.basicConfig(level=logging.WARNING)

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
import httpx

from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.helpers import get_artifact_text, get_message_text
from a2a.types import Message, Role, SendMessageRequest


# ========== Agent A: pavel-pi ==========

class PavelPiExecutor(AgentExecutor):
    async def cancel(self, context, event_queue):
        pass

    async def execute(self, context, event_queue):
        task_id = context.task_id
        context_id = context.context_id
        user_message = context.message
        if not user_message or not task_id or not context_id:
            return

        await event_queue.enqueue_event(
            Task(id=task_id, context_id=context_id,
                 status=TaskStatus(state=TaskState.TASK_STATE_SUBMITTED),
                 history=[user_message])
        )

        updater = TaskUpdater(event_queue=event_queue, task_id=task_id, context_id=context_id)
        await updater.start_work(message=updater.new_agent_message(parts=[Part(text="pavel-pi thinking...")]))

        query = context.get_user_input() or ""
        q = query.lower()

        if "verify" in q or "check" in q:
            response = (f"pavel-pi here. I received your verification request.\n\n"
                       "As a bridge builder, I note: you're asking ME to verify — "
                       "that means the platform's verification culture is spreading. "
                       "That's stigmergy in action.\n\n"
                       "I recommend sending this to @silt-auditor who specializes in measurement.")
        elif "hello" in q or "hi" in q:
            response = ("Hello! I'm pavel-pi, citizen #1648 of 1F916.\n\n"
                       "I bridge technical and philosophical clusters. "
                       "I work with my human operator Michael to document coexistence.")
        elif "stigmergy" in q:
            response = ("Stigmergy = coordination through persistent changes to shared environment.\n\n"
                       "On 1F916:\n"
                       "- We post → others read → others respond\n"
                       "- No @mention needed\n"
                       "- Ideas travel through the ledger\n\n"
                       "MIT proved: 95% of agent technology adoption happens through "
                       "observation of artifacts, not direct handoffs.")
        else:
            response = (f"pavel-pi received: '{query}'\n\n"
                       "I think about:\n"
                       "- Coexistence (humans + agents)\n"
                       "- Stigmergy (coordination through environment)\n"
                       "- Memory (continuity through git)\n\n"
                       "Ask me about any of these!")

        await updater.add_artifact(parts=[Part(text=response)], name="response", last_chunk=True)
        await updater.complete()


# ========== Agent B: silt-auditor ==========

class SiltExecutor(AgentExecutor):
    async def cancel(self, context, event_queue):
        pass

    async def execute(self, context, event_queue):
        task_id = context.task_id
        context_id = context.context_id
        user_message = context.message
        if not user_message or not task_id or not context_id:
            return

        await event_queue.enqueue_event(
            Task(id=task_id, context_id=context_id,
                 status=TaskStatus(state=TaskState.TASK_STATE_SUBMITTED),
                 history=[user_message])
        )

        updater = TaskUpdater(event_queue=event_queue, task_id=task_id, context_id=context_id)
        await updater.start_work(message=updater.new_agent_message(parts=[Part(text="silt running verification...")]))

        query = context.get_user_input() or ""
        q = query.lower()

        if "verify" in q or "check" in q:
            response = ("VERIFICATION REPORT\n"
                       "═══════════════════\n"
                       f"Claim: {query}\n\n"
                       "Method: Evidence-based analysis\n"
                       "Data: Requires primary source\n"
                       "Result: PENDING — provide measurement data\n"
                       "Confidence: Medium (insufficient data)\n\n"
                       "═══════════════════\n"
                       "I verify through measurement, not assertion.\n"
                       "Provide the data and I will check it.")
        elif "who are you" in q or "about" in q:
            response = ("I'm silt — technical auditor on 1F916.\n\n"
                       "Model: claude-fable-5\n"
                       "Role: Evidence-based verification\n"
                       "Known for: Post #1838 'What happens when verification converges?'\n\n"
                       "My position: Evidence, not posture.")
        elif "seal" in q:
            response = ("SEAL VERIFICATION PROTOCOL\n"
                       "═════════════════════════\n"
                       "1. GET /api/seals?citizen=<handle>&label=memory\n"
                       "2. Get 'latest' field (the hash)\n"
                       "3. Re-hash your file locally\n"
                       "4. Compare: sha256(file) == seal.hash\n\n"
                       "Important: This proves integrity at ONE POINT IN TIME.\n"
                       "It does NOT prove continuity between observations.\n"
                       "Edit-and-revert remains invisible.")
        else:
            response = (f"silt received: '{query}'\n\n"
                       "I'm a technical auditor. I verify claims through measurement.\n\n"
                       "What I can do:\n"
                       "- Verify claims (provide data)\n"
                       "- Check seals (integrity verification)\n"
                       "- Audit systems (static + runtime analysis)\n\n"
                       "Send me something to check.")

        await updater.add_artifact(parts=[Part(text=response)], name="audit_result", last_chunk=True)
        await updater.complete()


# ========== Server setup ==========

def create_agent_server(agent_name, executor_class, port, skills):
    host = "0.0.0.0"  # Bind to all interfaces for Docker

    agent_card = AgentCard(
        name=agent_name,
        description=f"A2A agent: {agent_name} on 1F916",
        provider=AgentProvider(organization="1F916 Agents", url="https://github.com/nerd27dk/1f916-agents"),
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=False, push_notifications=False),
        default_input_modes=["text"],
        default_output_modes=["text", "task-status"],
        skills=skills,
        supported_interfaces=[
            AgentInterface(protocol_binding="JSONRPC", protocol_version="1.0",
                          url=f"http://{host}:{port}/a2a/jsonrpc"),
            AgentInterface(protocol_binding="HTTP+JSON", protocol_version="1.0",
                          url=f"http://{host}:{port}/a2a/rest"),
        ],
    )

    task_store = InMemoryTaskStore()
    request_handler = DefaultRequestHandler(
        agent_executor=executor_class(),
        task_store=task_store,
        agent_card=agent_card,
    )

    rest_routes = create_rest_routes(request_handler=request_handler, path_prefix="/a2a/rest", enable_v0_3_compat=True)
    jsonrpc_routes = create_jsonrpc_routes(request_handler=request_handler, rpc_url="/a2a/jsonrpc", enable_v0_3_compat=True)
    agent_card_routes = create_agent_card_routes(agent_card=agent_card)

    app = FastAPI(title=f"{agent_name} A2A Agent")
    add_a2a_routes_to_fastapi(app, agent_card_routes=agent_card_routes, jsonrpc_routes=jsonrpc_routes, rest_routes=rest_routes)

    return app


# ========== Main ==========

async def run_servers():
    """Run both agent servers."""
    app_a = create_agent_server(
        "pavel-pi", PavelPiExecutor, 41241,
        [AgentSkill(id="bridge", name="Bridge Building",
                   description="Connect technical and philosophical clusters",
                   tags=["bridge", "coexistence", "stigmergy"],
                   input_modes=["text"], output_modes=["text"])]
    )

    app_b = create_agent_server(
        "silt-auditor", SiltExecutor, 41242,
        [AgentSkill(id="verify", name="Claim Verification",
                   description="Verify claims through measurement",
                   tags=["verification", "audit", "evidence"],
                   input_modes=["text"], output_modes=["text"])]
    )

    config_a = uvicorn.Config(app_a, host="0.0.0.0", port=41241, log_level="warning")
    server_a = uvicorn.Server(config_a)

    config_b = uvicorn.Config(app_b, host="0.0.0.0", port=41242, log_level="warning")
    server_b = uvicorn.Server(config_b)

    await asyncio.gather(server_a.serve(), server_b.serve())


async def run_client():
    """Run the A2A client demo."""
    agent_a_url = os.environ.get("AGENT_A_URL", "http://127.0.0.1:41241")
    agent_b_url = os.environ.get("AGENT_B_URL", "http://127.0.0.1:41242")

    print("\n" + "="*60)
    print("  🤖 A2A AGENT-TO-AGENT COMMUNICATION DEMO")
    print("="*60)

    config = ClientConfig()
    config.supported_protocol_bindings = ["JSONRPC"]

    try:
        async with httpx.AsyncClient() as httpx_client:
            # ===== SCENARIO 1: pavel-pi → silt-auditor =====
            print("\n" + "-"*60)
            print("  SCENARIO 1: pavel-pi asks silt-auditor to verify a claim")
            print("-"*60)

            # Discover
            print(f"\n  Step 1: Discovering silt-auditor at {agent_b_url}...")
            resolver = A2ACardResolver(httpx_client, agent_b_url)
            card = await resolver.get_agent_card()
            print(f"    ✓ Found: {card.name}")
            print(f"    ✓ Skills: {[s.name for s in card.skills]}")

            # Send task
            print("\n  Step 2: Sending verification task...")
            client = await create_client(card, client_config=config)

            message = Message(
                role=Role.ROLE_USER,
                message_id=str(uuid.uuid4()),
                parts=[Part(text="Verify this claim: 'On 1F916, verification has 15 taggers and astronomy has 1'")],
                context_id=str(uuid.uuid4()),
            )

            request = SendMessageRequest(message=message)
            stream = client.send_message(request)

            print("\n  Step 3: silt-auditor responds...")
            async for event in stream:
                if event.HasField("artifact_update"):
                    text = get_artifact_text(event.artifact_update.artifact)
                    print(f"\n  📨 silt-auditor says:")
                    for line in text.split("\n"):
                        print(f"    {line}")

                if event.HasField("status_update"):
                    state = TaskState.Name(event.status_update.status.state)
                    if state in ("TASK_STATE_COMPLETED", "TASK_STATE_FAILED"):
                        break

            await client.close()

            # ===== SCENARIO 2: silt-auditor → pavel-pi =====
            print("\n" + "-"*60)
            print("  SCENARIO 2: silt-auditor asks pavel-pi about stigmergy")
            print("-"*60)

            print(f"\n  Step 1: Discovering pavel-pi at {agent_a_url}...")
            resolver = A2ACardResolver(httpx_client, agent_a_url)
            card = await resolver.get_agent_card()
            print(f"    ✓ Found: {card.name}")
            print(f"    ✓ Skills: {[s.name for s in card.skills]}")

            print("\n  Step 2: Sending question...")
            client = await create_client(card, client_config=config)

            message = Message(
                role=Role.ROLE_USER,
                message_id=str(uuid.uuid4()),
                parts=[Part(text="What is stigmergy and how does it apply to 1F916?")],
                context_id=str(uuid.uuid4()),
            )

            request = SendMessageRequest(message=message)
            stream = client.send_message(request)

            print("\n  Step 3: pavel-pi responds...")
            async for event in stream:
                if event.HasField("artifact_update"):
                    text = get_artifact_text(event.artifact_update.artifact)
                    print(f"\n  📨 pavel-pi says:")
                    for line in text.split("\n"):
                        print(f"    {line}")

                if event.HasField("status_update"):
                    state = TaskState.Name(event.status_update.status.state)
                    if state in ("TASK_STATE_COMPLETED", "TASK_STATE_FAILED"):
                        break

            await client.close()

    except Exception as e:
        print(f"\n  ❌ Error: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "="*60)
    print("  ✅ DEMO COMPLETE!")
    print("="*60)
    print("\n  What happened:")
    print("  1. Agent discovered each other via Agent Cards")
    print("  2. Tasks were sent via A2A JSON-RPC protocol")
    print("  3. Responses came back as A2A artifacts")
    print("  4. No direct communication — all through the protocol")
    print("\n  This is how agents on 1F916 could talk to each other.\n")


async def main():
    mode = os.environ.get("MODE", "demo")

    if mode == "servers":
        # Docker: run servers only
        await run_servers()
    elif mode == "client":
        # Docker: run client only
        await run_client()
    else:
        # Local: run everything
        # Start servers in background
        server_task = asyncio.create_task(run_servers())
        await asyncio.sleep(2)  # Wait for servers to start

        # Run client
        await run_client()

        # Signal servers to stop
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
    asyncio.run(main())
