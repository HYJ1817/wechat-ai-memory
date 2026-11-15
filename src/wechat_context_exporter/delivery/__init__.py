"""Delivery targets: where a finished job actually goes."""

from .agent import AgentDelivery
from .base import (
    DeliveryError,
    DeliveryRequest,
    DeliveryResult,
    DeliveryTarget,
    copy_artifacts,
    ordered_artifacts,
    paths_as_text,
    safe_filename,
)
from .clipboard import ClipboardDelivery, fallback_text
from .folder import FolderDelivery
from .obsidian import ObsidianDelivery

TARGETS = ("none", "folder", "obsidian", "clipboard", "agent")

__all__ = [
    "AgentDelivery",
    "ClipboardDelivery",
    "DeliveryError",
    "DeliveryRequest",
    "DeliveryResult",
    "DeliveryTarget",
    "FolderDelivery",
    "ObsidianDelivery",
    "TARGETS",
    "copy_artifacts",
    "fallback_text",
    "ordered_artifacts",
    "paths_as_text",
    "safe_filename",
]
