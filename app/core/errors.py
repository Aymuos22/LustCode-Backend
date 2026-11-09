class AppError(Exception):
    def __init__(
        self, code: str, message: str, status: int = 400, *, current_revision: int | None = None
    ) -> None:
        self.code = code
        self.message = message
        self.status = status
        self.current_revision = current_revision
        super().__init__(message)


class ProviderError(AppError):
    def __init__(
        self,
        message: str = "Execution provider is temporarily unavailable",
        *,
        retryable: bool = True,
        retry_after: int | None = None,
    ) -> None:
        self.retryable = retryable
        self.retry_after = retry_after
        super().__init__("provider_unavailable", message, 503)


class LeaseLost(Exception):
    pass
