from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class LLMProvider(ABC):
    @abstractmethod
    async def complete(self, model: Optional[str], messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def validate_config(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def get_available_models(self) -> List[str]:
        raise NotImplementedError
