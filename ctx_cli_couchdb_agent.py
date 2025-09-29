#!/usr/bin/env python3
import os, asyncio, argparse, json
from dotenv import load_dotenv

from agents import Agent, Runner
from agents.model_settings import ModelSettings
from agents.mcp import MCPServerStdio

AGENT_SYS_PROMPT = """
You are a CouchDB read-only assistant. You may ONLY use the provided CouchDB MCP tools.
Never write or modify data. When the user asks for data, call the appropriate tool(s) and
return concise JSON results. If the user asks for something that would require writes,
explain that you are read-only.
"""

async def run(prompt: str, json_only: bool):
    # Connect to the local stdio MCP server
    server = MCPServerStdio(
        name="couchdb",
        params={
            "command": "python",
            "args": ["couchdb_mcp_server.py"],
        },
    )
    srv = await server.__aenter__()

    agent = Agent(
        name="CouchDB Reader",
        instructions=AGENT_SYS_PROMPT,
        model=os.getenv("OPENAI_MODEL", "gpt-4.1"),
        mcp_servers=[srv],
        tools=[],  # all tools come from the MCP server
        model_settings=ModelSettings(tool_choice="auto"),  # allow the model to pick tools
        # No structured output here; we let the agent return readable JSON
    )

    result = await Runner.run(agent, prompt, max_turns=8)

    out = result.final_output or "(no output)"
    if json_only:
        print(out)
    else:
        print("\n--- Agent Output ---\n" + out)

    await server.__aexit__(None, None, None)

def main():
    load_dotenv()
    ap = argparse.ArgumentParser(description="Query CouchDB via MCP agent (read-only).")
    ap.add_argument("prompt", nargs="+", help="Ask for docs/databases, e.g. 'get doc users user:alice'")
    ap.add_argument("--json", action="store_true", help="Print agent JSON only")
    args = ap.parse_args()
    asyncio.run(run(" ".join(args.prompt), args.json))

if __name__ == "__main__":
    main()
