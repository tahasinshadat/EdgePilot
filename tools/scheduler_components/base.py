"""Abstract scheduler base class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List


class BaseScheduler(ABC):
    """Abstract scheduler interface for app listing/search/launch."""

    @abstractmethod
    def list_applications(self, filter_term: str = "") -> List[str]:
        ...

    @abstractmethod
    def search(self, app_name: str) -> List[str]:
        ...

    @abstractmethod
    def launch(self, app_name: str) -> bool:
        ...
