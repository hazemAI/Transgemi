from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, Tuple


class TranslationService(ABC):
    @abstractmethod
    def get_or_translate(
        self,
        region: tuple,
        history: Optional[List[str]] = None,
        last_hash: Optional[Any] = None,
        cache: Optional[Dict] = None,
        screenshot_np: Optional[Any] = None,
        precomputed_ocr: Optional[Tuple[str, float, float]] = None,
    ) -> Tuple[str, Optional[Any]]:
        pass

    @abstractmethod
    def switch_service(self, service_name: str) -> bool:
        pass
