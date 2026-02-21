"""
Base Tool interface.
Every tool inherits from Tool and implements run().
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any


class Tool(ABC):
    """Abstract base for all assistant tools."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool identifier (snake_case)."""

    @property
    @abstractmethod
    def description(self) -> str:
        """One-line human description shown to the planner."""

    @property
    @abstractmethod
    def input_schema(self) -> dict[str, Any]:
        """JSON-Schema-like dict describing accepted arguments."""

    @abstractmethod
    def run(self, **kwargs: Any) -> Any:
        """Execute the tool.  Must call policy checks internally."""

    def dry_run(self, **kwargs: Any) -> str:
        """Optional preview of what would happen.  Override in subclasses."""
        return f"[dry-run] {self.name} with {kwargs}"
