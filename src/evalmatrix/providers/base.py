"""Base interfaces and protocols for LLM providers in EvalMatrix."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Protocol, runtime_checkable
from evalmatrix.models import ProviderResponse


@runtime_checkable
class ProviderProtocol(Protocol):
    """Protocol defining the interface for all evaluation providers."""

    def generate(
        self,
        prompt: str,
        case_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        """Generate a response for the given prompt."""
        ...


class BaseProvider(ABC):
    """Abstract base class for evaluation provider implementations."""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        case_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        """Generate a response for the provided prompt string.

        Args:
            prompt: The formatted prompt string sent to the model/provider.
            case_id: Optional test case identifier for targeted fixture resolution.
            metadata: Optional contextual metadata from the test case.
            **kwargs: Extra runtime parameters.

        Returns:
            ProviderResponse containing the generated content and metrics.
        """
        raise NotImplementedError("Subclasses must implement generate()")
