class AlgoSentinelError(Exception):
    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


class RetryableError(AlgoSentinelError):
    def __init__(self, message: str):
        super().__init__(message, retryable=True)


class FatalError(AlgoSentinelError):
    def __init__(self, message: str):
        super().__init__(message, retryable=False)


class ToolError(AlgoSentinelError):
    pass


class GitHubToolError(ToolError):
    pass


class GitHubRateLimitError(GitHubToolError, RetryableError):
    pass


class GitHubNotFoundError(GitHubToolError, FatalError):
    pass


class SandboxError(ToolError):
    pass


class SandboxTimeoutError(SandboxError, RetryableError):
    pass


class SandboxStartError(SandboxError, FatalError):
    pass


class ComplexityInferenceError(ToolError):
    pass


class InsufficientDataError(ComplexityInferenceError, FatalError):
    pass


class SubagentError(AlgoSentinelError):
    pass


class SubagentTimeoutError(SubagentError, RetryableError):
    pass


class RateLimitError(RetryableError):
    pass
