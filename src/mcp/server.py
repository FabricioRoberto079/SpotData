import logging

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

INSTRUCTIONS = (
    "SpotData RAG over an indexed corpus of documents. "
    "Use `ask_question` to get an answer grounded in the latest version "
    "of the indexed documents, with citations."
)

mcp_server = FastMCP("spotdata", instructions=INSTRUCTIONS)
