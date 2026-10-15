import pytest
from studio_ai_studio.limits import BucketPolicy, RateLimitExceeded, TokenBucketLimiter


def test_burst_and_refill_with_injected_clock():
    now = [0.0]
    limiter = TokenBucketLimiter(
        BucketPolicy(capacity=2, refill_per_second=1), clock=lambda: now[0]
    )
    limiter.allow("workspace:model")
    limiter.allow("workspace:model")
    with pytest.raises(RateLimitExceeded) as error:
        limiter.allow("workspace:model")
    assert error.value.retry_after_seconds == 1.0
    now[0] = 1.0
    limiter.allow("workspace:model")


def test_scopes_are_fair_and_cost_is_bounded():
    limiter = TokenBucketLimiter(BucketPolicy(capacity=2, refill_per_second=1), clock=lambda: 0.0)
    limiter.allow("workspace-a:model", cost=2)
    limiter.allow("workspace-b:model", cost=2)
    with pytest.raises(ValueError, match="invalid limiter"):
        limiter.allow("workspace-a:model", cost=3)
