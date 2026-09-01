"""Tool package. Importing it registers every tool into TOOL_REGISTRY.

Import order matters only in that these modules must be imported before any
agent manifest is validated or any agent is constructed.
"""

from hq.tools import board_tools, vault_tools, web_tools  # noqa: F401
from hq.tools.registry import TOOL_REGISTRY, HQDeps, hq_tool

__all__ = ["TOOL_REGISTRY", "HQDeps", "hq_tool"]
