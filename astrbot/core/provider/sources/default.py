from tenacity import (
    AsyncRetrying,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

MODEL_REQUEST_RETRY_ATTEMPTS = 5
MODEL_REQUEST_RETRY_WAIT_MAX_SECONDS = 15
MODEL_REQUEST_RETRY_WAIT_MIN_SECONDS = 1
MODEL_REQUEST_RETRY_WAIT_MULTIPLIER = 1


def with_model_request_retry():
    return retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(MODEL_REQUEST_RETRY_ATTEMPTS),
        wait=wait_exponential(
            multiplier=MODEL_REQUEST_RETRY_WAIT_MULTIPLIER,
            min=MODEL_REQUEST_RETRY_WAIT_MIN_SECONDS,
            max=MODEL_REQUEST_RETRY_WAIT_MAX_SECONDS,
        ),
        reraise=True,
    )


def get_model_request_async_retrying() -> AsyncRetrying:
    return AsyncRetrying(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(MODEL_REQUEST_RETRY_ATTEMPTS),
        wait=wait_exponential(
            multiplier=MODEL_REQUEST_RETRY_WAIT_MULTIPLIER,
            min=MODEL_REQUEST_RETRY_WAIT_MIN_SECONDS,
            max=MODEL_REQUEST_RETRY_WAIT_MAX_SECONDS,
        ),
        reraise=True,
    )
