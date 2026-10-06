"""
Tool nativi di Calliope.

Vedi docs/architettura-tool.md: i nativi sono la specificità di Calliope
(identità, voce, ascolto, casa, memoria), gli MCP ampliano verso il mondo.
"""

from .registry import ToolRegistry
from .spec import ToolSpec, ToolContext

__all__ = ["ToolRegistry", "ToolSpec", "ToolContext"]
