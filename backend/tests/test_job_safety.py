from services.job_safety import ProviderStopError, provider_stop_from_response


def test_rate_limit_is_a_global_job_stop_with_retry_window():
    error = provider_stop_from_response(429, '{"error":"rate limit reached"}', "45")
    assert isinstance(error, ProviderStopError)
    assert error.code == "provider_rate_limited"
    assert error.retry_after_seconds == 45


def test_credit_exhaustion_is_a_global_job_stop():
    error = provider_stop_from_response(402, '{"error":{"code":"insufficient_quota"}}')
    assert isinstance(error, ProviderStopError)
    assert error.code == "provider_credits_exhausted"
    assert error.retry_after_seconds is None


def test_unrelated_provider_error_is_not_misclassified_as_credit_or_rate_stop():
    assert provider_stop_from_response(500, "temporary upstream error") is None
