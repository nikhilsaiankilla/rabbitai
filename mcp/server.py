"""
mcp/server.py
RabbitAI MCP server — trigger PR reviews directly from Claude or Cursor.

Usage:
    python mcp/server.py

Then add to Claude/Cursor MCP config:
    {
      "mcpServers": {
        "rabbitai": {
          "command": "python",
          "args": ["path/to/rabbitai/mcp/server.py"]
        }
      }
    }

Inside Claude/Cursor, type:
    "Review PR #12 in nikhilsaiankilla/myrepo"
"""

from __future__ import annotations

import asyncio
import sys
import os

# Make sure imports resolve from project root regardless of where server.py is called from
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

from agent import run
from utils.config import load_config


server = Server("rabbitai")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="review_pr",
            description=(
                "Review a GitHub pull request using RabbitAI. "
                "Fetches the PR diff, analyzes blast radius, classifies the change type, "
                "retrieves relevant context, and posts a structured AI review comment on the PR. "
                "Returns the review text and the URL of the posted comment."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_name": {
                        "type": "string",
                        "description": 'GitHub repo in owner/repo format. Example: "nikhilsaiankilla/rabbitai"',
                    },
                    "pr_number": {
                        "type": "integer",
                        "description": "Pull request number to review. Example: 12",
                    },
                },
                "required": ["repo_name", "pr_number"],
            },
        ),
        types.Tool(
            name="review_status",
            description=(
                "Check what RabbitAI knows about a repo — "
                "shows current config (language, focus areas, score threshold) "
                "and whether memory is enabled."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:

    if name == "review_pr":
        repo_name: str = arguments.get("repo_name", "").strip()
        pr_number: int = int(arguments.get("pr_number", 0))

        if not repo_name or "/" not in repo_name:
            return [types.TextContent(
                type="text",
                text=' Invalid repo_name. Use "owner/repo" format, e.g. "nikhilsaiankilla/rabbitai"',
            )]

        if pr_number <= 0:
            return [types.TextContent(
                type="text",
                text=" Invalid pr_number. Must be a positive integer.",
            )]

        try:
            result = run(repo_name=repo_name, pr_number=pr_number)
        except Exception as e:
            return [types.TextContent(
                type="text",
                text=f" RabbitAI error: {str(e)}",
            )]

        if result.posted:
            return [types.TextContent(
                type="text",
                text=(
                    f"Review posted on PR #{pr_number} in {repo_name}\n\n"
                    f"{result.comment_url}"
                ),
            )]
        else:
            return [types.TextContent(
                type="text",
                text=f"Review skipped: {result.reason}",
            )]

    if name == "review_status":
        try:
            config = load_config()
            review_cfg = config.get("review", {})
            memory_cfg = config.get("memory", {})
            vs_cfg = config.get("vector_store", {})

            status = (
                f"🐇 RabbitAI is configured and ready.\n\n"
                f"Language:       {review_cfg.get('language', 'not set')}\n"
                f"Focus areas:    {', '.join(review_cfg.get('focus', []))}\n"
                f"Min risk score: {review_cfg.get('min_risk_score', 0)}\n"
                f"Post score:     {review_cfg.get('post_score', True)}\n"
                f"Memory:         {'enabled' if memory_cfg.get('enabled', True) else 'disabled'}\n"
                f"Vector store:   {vs_cfg.get('provider', 'chromadb')}\n"
            )
        except Exception as e:
            status = f"Could not load config: {str(e)}"

        return [types.TextContent(type="text", text=status)]

    return [types.TextContent(
        type="text",
        text=f" Unknown tool: {name}",
    )]


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())