class AIProviderError(RuntimeError):
    pass


class AIRateLimitError(AIProviderError):
    pass


class AIResponseError(AIProviderError):
    pass


class AITimeoutError(AIProviderError):
    pass
