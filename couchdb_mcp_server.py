#!/usr/bin/env python3
import os, json, asyncio
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlencode

import aiohttp
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP, Context

load_dotenv()

COUCHDB_URL = os.environ["COUCHDB_URL"].rstrip("/")
COUCHDB_USER = os.environ.get("COUCHDB_USER")
COUCHDB_PASS = os.environ.get("COUCHDB_PASS")

app = FastMCP("couchdb")

def auth() -> Optional[aiohttp.BasicAuth]:
    if COUCHDB_USER and COUCHDB_PASS:
        return aiohttp.BasicAuth(COUCHDB_USER, COUCHDB_PASS)
    return None

async def _get(session: aiohttp.ClientSession, path: str, params: Dict[str, Any] = None):
    url = f"{COUCHDB_URL}{path}"
    async with session.get(url, params=params or {}, auth=auth(), ssl=True, timeout=aiohttp.ClientTimeout(total=20)) as r:
        r.raise_for_status()
        return await r.json()

async def _post_json(session: aiohttp.ClientSession, path: str, payload: Dict[str, Any]):
    # Only used for _find (read). No writes are implemented anywhere.
    url = f"{COUCHDB_URL}{path}"
    async with session.post(url, json=payload, auth=auth(), ssl=True, timeout=aiohttp.ClientTimeout(total=30)) as r:
        r.raise_for_status()
        return await r.json()

@app.tool(description="List all databases (/_all_dbs).")
async def list_databases(ctx: Context) -> List[str]:
    async with aiohttp.ClientSession() as s:
        data = await _get(s, "/_all_dbs")
        return data  # list[str]

@app.tool(description="Database info (GET /{db}).")
async def db_info(ctx: Context, db: str) -> Dict[str, Any]:
    async with aiohttp.ClientSession() as s:
        return await _get(s, f"/{quote(db, safe='')}")

@app.tool(description="Get a document by id (GET /{db}/{doc_id}). Set include_attachments/revs if needed.")
async def get_document(
    ctx: Context,
    db: str,
    doc_id: str,
    include_attachments: bool = False,
    include_revs: bool = False,
) -> Dict[str, Any]:
    params = {}
    if include_attachments:
        params["attachments"] = "true"
    if include_revs:
        params["revs"] = "true"
    async with aiohttp.ClientSession() as s:
        return await _get(s, f"/{quote(db, safe='')}/{quote(doc_id, safe='')}", params=params)

@app.tool(description="List documents (/_all_docs). Optionally include_docs and pagination.")
async def list_documents(
    ctx: Context,
    db: str,
    include_docs: bool = True,
    limit: int = 100,
    skip: int = 0,
    startkey: Optional[str] = None,
    endkey: Optional[str] = None,
) -> Dict[str, Any]:
    params: Dict[str, Any] = {"limit": limit, "skip": skip, "include_docs": "true" if include_docs else "false"}
    if startkey is not None:
        params["startkey"] = json.dumps(startkey)
    if endkey is not None:
        params["endkey"] = json.dumps(endkey)
    async with aiohttp.ClientSession() as s:
        return await _get(s, f"/{quote(db, safe='')}/_all_docs", params=params)

@app.tool(description="Run a Mango query (POST /{db}/_find). Provide a JSON selector; optional fields/limit/sort/skip/use_index.")
async def mango_find(
    ctx: Context,
    db: str,
    selector: Dict[str, Any],
    fields: Optional[List[str]] = None,
    limit: int = 100,
    sort: Optional[List[Dict[str, str]]] = None,
    skip: int = 0,
    use_index: Optional[Any] = None,
) -> Dict[str, Any]:
    body: Dict[str, Any] = {"selector": selector, "limit": limit, "skip": skip}
    if fields is not None:
        body["fields"] = fields
    if sort is not None:
        body["sort"] = sort
    if use_index is not None:
        body["use_index"] = use_index
    async with aiohttp.ClientSession() as s:
        return await _post_json(s, f"/{quote(db, safe='')}/_find", body)

# No write tools are implemented. Keep it that way to enforce read-only.

if __name__ == "__main__":
    # Run as an MCP stdio server
    app.run()
