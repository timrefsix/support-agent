#!/usr/bin/env python3
import os, asyncio, argparse, json
from dotenv import load_dotenv

from agents import Agent, Runner
from agents.model_settings import ModelSettings
from agents.mcp import MCPServerStdio

AGENT_SYS_PROMPT = """
You are a read-only assistant with access to CouchDB and Stripe MCP tools.
Use these tools to retrieve data from either source as needed, never attempt writes.
When responding, return concise JSON results or explanations, and make it clear when
an action is impossible because you cannot modify data.
"""

async def run(prompt: str, json_only: bool):
    # Connect to the local stdio MCP server
    couchdb_server = MCPServerStdio(
        name="couchdb",
        params={
            "command": "python",
            "args": ["couchdb_mcp_server.py"],
        },
    )
    stripe_api_key = os.environ["STRIPE_API_KEY"]
    stripe_server = MCPServerStdio(
        name="stripe",
        params={
            "command": "stripe-mcp",
            "args": [],
            "env": {**os.environ, "STRIPE_API_KEY": stripe_api_key},
        },
    )

    couch_srv, stripe_srv = await asyncio.gather(
        couchdb_server.__aenter__(), stripe_server.__aenter__()
    )

    agent = Agent(
        name="CouchDB Reader",
        instructions=AGENT_SYS_PROMPT,
        model=os.getenv("OPENAI_MODEL", "gpt-4.1"),
        mcp_servers=[couch_srv],
        tools=[],  # all tools come from the MCP server
        model_settings=ModelSettings(tool_choice="auto"),  # allow the model to pick tools
        # No structured output here; we let the agent return readable JSON
    )
    agent.mcp_servers.append(stripe_srv)

    result = await Runner.run(agent, prompt, max_turns=8)

    out = result.final_output or "(no output)"
    if json_only:
        print(out)
    else:
        print("\n--- Agent Output ---\n" + out)

    await asyncio.gather(
        couchdb_server.__aexit__(None, None, None),
        stripe_server.__aexit__(None, None, None),
    )

def main():
    load_dotenv()
    ap = argparse.ArgumentParser(description="Query CouchDB via MCP agent (read-only).")
    ap.add_argument("prompt", nargs="+", help="Ask for docs/databases, e.g. 'get doc users user:alice'")
    ap.add_argument("--json", action="store_true", help="Print agent JSON only")
    args = ap.parse_args()
    asyncio.run(run(" ".join(args.prompt), args.json))

if __name__ == "__main__":
    main()
