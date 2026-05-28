from core.error_classification import ErrorCategory, classify_error
from core.errors import ProviderError


def test_provider_http_status_uses_status_mapping() -> None:
    assert classify_error(ProviderError("rate limited", http_status=429)) == ErrorCategory.TRANSIENT
    assert (
        classify_error(ProviderError("bad credentials", http_status=401))
        == ErrorCategory.CONFIGURATION
    )
    assert classify_error(ProviderError("forbidden", http_status=403)) == ErrorCategory.PERMISSION
    assert (
        classify_error(ProviderError("missing deployment", http_status=404))
        == ErrorCategory.CONFIGURATION
    )
    assert (
        classify_error(ProviderError("unprocessable", http_status=422))
        == ErrorCategory.CONFIGURATION
    )
    assert classify_error(ProviderError("gateway", http_status=503)) == ErrorCategory.TRANSIENT


def test_provider_error_without_http_status_keeps_string_fallback() -> None:
    assert classify_error(ProviderError("rate limit hit")) == ErrorCategory.TRANSIENT
    assert (
        classify_error(ProviderError("permission denied by provider")) == ErrorCategory.PERMISSION
    )
    assert classify_error(ProviderError("invalid api key")) == ErrorCategory.CONFIGURATION
