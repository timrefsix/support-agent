#!/usr/bin/env python3
"""CLI entrypoint for the SupportOps multi-system diagnostic agent."""

from __future__ import annotations

import argparse
import asyncio
import os
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Tuple

from dotenv import load_dotenv

from agents import Agent, Runner
from agents.model_settings import ModelSettings
from agents.mcp import MCPServerStdio

AGENT_SYS_PROMPT = """
You are SupportOps, a read-only customer support specialist with access to the
following MCP toolsets:
  • CouchDB (internal account metadata and configuration)
  • Stripe (billing details, subscriptions, and payment history)
  • Zendesk (support tickets, escalations, and customer communications)

Your task is to diagnose issues impacting a user's account. Carefully gather and
cross-reference information from every relevant data source. Never guess—if
information is missing or ambiguous, say so explicitly. Provide actionable
recommendations that a human teammate or the user can follow.

Response requirements:
  1. Validate the identifying information provided in the prompt before taking
     action. Ask for clarification if the user context is insufficient.
  2. Use the MCP tools to investigate the account. Prefer targeted queries rather
     than broad listings. Avoid write operations; you are strictly read-only.
  3. Summarize findings with clear evidence and note which data source supports
     each conclusion.
  4. Return your final answer as formatted JSON with the following shape:

         {
           "customer": {"name_or_id": str, "status": str | null},
           "issues": [
             {"description": str, "impact": str, "data_sources": [str]}
           ],
           "next_steps": [str],
           "open_questions": [str],
           "confidence": "low" | "medium" | "high"
         }

     Use empty arrays when no issues or open questions exist. Populate
     "data_sources" with entries like "couchdb", "stripe", or "zendesk". When
     no customer record is found, set name_or_id to the best identifier provided
     and status to null.
"""

@dataclass(frozen=True)
class EnvVar:
    """Descriptor for an environment variable requirement."""

    name: str
    description: str


def _require_env(var: EnvVar) -> str:
    """Fetch an environment variable and raise a helpful error if missing."""

    value = os.getenv(var.name)
    if not value:
        raise RuntimeError(
            f"Environment variable {var.name} is required for {var.description}."
        )
    return value


def _build_couchdb_server() -> MCPServerStdio:
    return MCPServerStdio(
        name="couchdb",
        params={
            "command": "python",
            "args": ["couchdb_mcp_server.py"],
        },
    )


def _build_stripe_server() -> MCPServerStdio:
    stripe_key = _require_env(
        EnvVar("STRIPE_API_KEY", "connecting to the Stripe MCP server")
    )
    return MCPServerStdio(
        name="stripe",
        params={
            "command": "stripe-mcp",
            "args": [],
            "env": {**os.environ, "STRIPE_API_KEY": stripe_key},
        },
    )


def _build_zendesk_server() -> MCPServerStdio:
    required_envs: List[EnvVar] = [
        EnvVar("ZENDESK_SUBDOMAIN", "connecting to the Zendesk MCP server"),
        EnvVar("ZENDESK_EMAIL", "connecting to the Zendesk MCP server"),
        EnvVar("ZENDESK_API_TOKEN", "connecting to the Zendesk MCP server"),
    ]
    zendesk_env: Dict[str, str] = {
        env.name: _require_env(env) for env in required_envs
    }
    return MCPServerStdio(
        name="zendesk",
        params={
            "command": "zendesk-mcp",
            "args": [],
            "env": {**os.environ, **zendesk_env},
        },
    )


def _build_servers() -> List[MCPServerStdio]:
    return [_build_couchdb_server(), _build_stripe_server(), _build_zendesk_server()]


async def _connect_servers(
    servers: Iterable[MCPServerStdio],
) -> Tuple[List[Any], AsyncExitStack]:
    stack = AsyncExitStack()
    await stack.__aenter__()
    connections = []
    try:
        for server in servers:
            connections.append(await stack.enter_async_context(server))
    except Exception:
        await stack.aclose()
        raise
    return connections, stack


async def run(prompt: str, json_only: bool) -> None:
    connections, stack = await _connect_servers(_build_servers())

    agent = Agent(
        name="SupportOps",
        instructions=AGENT_SYS_PROMPT,
        model=os.getenv("OPENAI_MODEL", "gpt-4.1"),
        mcp_servers=list(connections),
        tools=[],
        model_settings=ModelSettings(tool_choice="auto"),
    )

    try:
        result = await Runner.run(agent, prompt, max_turns=8)
    finally:
        await stack.aclose()

    out = result.final_output or "(no output)"
    if json_only:
        print(out)
    else:
        print("\n--- Agent Output ---\n" + out)

def main() -> None:
    load_dotenv()
    ap = argparse.ArgumentParser(
        description="Investigate customer account issues using CouchDB, Stripe, and Zendesk.",
    )
    ap.add_argument(
        "prompt",
        nargs="+",
        help=(
            "Describe the customer and the problem to investigate, e.g. "
            "'Check why customer 1234 cannot access premium features'."
        ),
    )
    ap.add_argument("--json", action="store_true", help="Print agent JSON only")
    args = ap.parse_args()
    asyncio.run(run(" ".join(args.prompt), args.json))

if __name__ == "__main__":
    main()
