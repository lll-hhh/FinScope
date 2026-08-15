"""FinScope: a local, scope-bound privacy mediator for financial agents.

The package deliberately has no model or framework dependency.  An adapter can
sanitize messages/tool results before an external LLM call and restore/validate
the response locally before handing it to the trading system.
"""

from .core import (
    ActionValidationError,
    FinScopeError,
    FinScopeMediator,
    Scope,
    ScopeNotFoundError,
    ValidationResult,
)
from .recognizer import (
    CatalogEntityRecognizer,
    EntityRecognizer,
    EntitySpan,
    JsonModelEntityRecognizer,
    TransformersEntityRecognizer,
)
from .policy import (
    AdaptivePrivacyPolicy,
    PrivacyDecision,
    PrivacyLevel,
    ResidualScanDecision,
    ResidualScanPolicy,
)

__all__ = [
    "ActionValidationError",
    "FinScopeError",
    "FinScopeMediator",
    "Scope",
    "ScopeNotFoundError",
    "ValidationResult",
    "CatalogEntityRecognizer",
    "EntityRecognizer",
    "EntitySpan",
    "JsonModelEntityRecognizer",
    "TransformersEntityRecognizer",
    "AdaptivePrivacyPolicy",
    "PrivacyDecision",
    "PrivacyLevel",
    "ResidualScanDecision",
    "ResidualScanPolicy",
]
