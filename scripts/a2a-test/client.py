"""
A2A Client — connects to both agents and demonstrates inter-agent communication.

Usage:
    python client.py

This client:
1. Discovers Agent A (pavel-pi) and Agent B (silt-auditor)
2. Sends tasks from Agent A to Agent B
3. Demonstrates A2A task lifecycle
"""

import asyncio
import uuid

import httpx

from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.helpers import get_artifact_text, get_message_text
from a2a.helpers.agent_card import display_agent_card
from a2a.types import Message, Part, Role, SendMessageRequest, TaskState


async def talk_to_agent(url: str, message: str, agent_name: str):
    """Send a message to an agent and get the response."""
    print(f"\n{'='*60}")
    print(f"  Sending to {agent_name}: {message}")
    print(f"{'='*60}")

    config = ClientConfig(
        grpc_channel_factory=None,  # We'll use HTTP only
    )
    config.supported_protocol_bindings = ["JSONRPC"]

    async with httpx.AsyncClient() as httpx_client:
        # Discover the agent
        resolver = A2ACardResolver(httpx_client, url)
        card = await resolver.get_agent_card()
        print(f"\n  Agent Card Found:")
        print(f"    Name: {card.name}")
        print(f"    Description: {card.description}")
        print(f"    Skills: {[s.name for s in card.skills]}")

        # Create client
        client = await create_client(card, client_config=config)

        # Send message
        context_id = str(uuid.uuid4())
        message_obj = Message(
            role=Role.ROLE_USER,
            message_id=str(uuid.uuid4()),
            parts=[Part(text=message)],
            context_id=context_id,
        )

        request = SendMessageRequest(message=message_obj)

        print(f"\n  Sending task...")
        stream = client.send_message(request)

        # Process response
        async for event in stream:
            if event.HasField("task"):
                print(f"  Task started: {event.task.id}")

            if event.HasField("status_update"):
                state = TaskState.Name(event.status_update.status.state)
                print(f"  Status: {state}")
                if state in ("TASK_STATE_COMPLETED", "TASK_STATE_FAILED"):
                    break

            if event.HasField("artifact_update"):
                text = get_artifact_text(event.artifact_update.artifact)
                print(f"\n  Response from {agent_name}:")
                print(f"  {text}")

        await client.close()


async def demo_agent_to_agent():
    """Demo: pavel-pi sends a task to silt-auditor via A2A."""
    print("\n" + "="*60)
    print("  A2A AGENT-TO-AGENT COMMUNICATION DEMO")
    print("="*60)
    print("\n  Scenario: pavel-pi asks silt-auditor to verify a claim")
    print("  Protocol: A2A (Agent-to-Agent)")
    print()

    # Step 1: pavel-pi discovers silt
    print("  Step 1: pavel-pi discovers silt-auditor...")
    await talk_to_agent(
        "http://127.0.0.1:41242",
        "Verify this claim: 'On 1F916, verification has 15 taggers and astronomy has 1'",
        "silt-auditor"
    )

    # Step 2: silt sends audit result back
    print("\n\n  Step 2: silt-auditor sends audit result to pavel-pi...")
    await talk_to_agent(
        "http://127.0.0.1:41241",
        "silt-auditor confirmed: verification=15 taggers, astronomy=1 tagger. "
        "The platform is self-referential. What should we do about it?",
        "pavel-pi"
    )


async def interactive_mode():
    """Interactive mode: talk to either agent."""
    print("\n" + "="*60)
    print("  A2A INTERACTIVE MODE")
    print("="*60)
    print("\n  Agents available:")
    print("    1. pavel-pi (port 41241) — bridge builder")
    print("    2. silt-auditor (port 41242) — technical auditor")
    print("\n  Type 'quit' to exit, 'switch' to change agent\n")

    current_agent = "pavel-pi"
    current_url = "http://127.0.0.1:41241"

    while True:
        try:
            user_input = input(f"  [{current_agent}] You: ").strip()
        except (KeyboardInterrupt, EOFError):
            break

        if user_input.lower() == "quit":
            break

        if user_input.lower() == "switch":
            if current_agent == "pavel-pi":
                current_agent = "silt-auditor"
                current_url = "http://127.0.0.1:41242"
            else:
                current_agent = "pavel-pi"
                current_url = "http://127.0.0.1:41241"
            print(f"  Switched to {current_agent}")
            continue

        if not user_input:
            continue

        await talk_to_agent(current_url, user_input, current_agent)


async def main():
    """Main entry point."""
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--interactive":
        await interactive_mode()
    else:
        await demo_agent_to_agent()


if __name__ == "__main__":
    asyncio.run(main())
