"""Tool package. Importing it registers every tool into TOOL_REGISTRY.

Import order matters only in that these modules must be imported before any
agent manifest is validated or any agent is constructed.
"""

from hq.tools import (  # noqa: F401
    board_tools,
    brightdata,
    browser_tools,
    content_tools,
    factory_tools,
    facts_tools,
    job_tools,
    learning_tools,
    policy_tools,
    request_tools,
    review_tools,
    vault_tools,
    web_tools,
)
from hq.tools.registry import TOOL_REGISTRY, HQDeps, hq_tool

__all__ = ["TOOL_REGISTRY", "HQDeps", "hq_tool"]
