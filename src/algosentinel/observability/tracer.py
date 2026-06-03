import time

import structlog

logger = structlog.get_logger()


class ToolCallTracer:
    """Wraps tool calls with timing and structured JSON logging."""

    def trace(self, namespace: str, tool_name: str):
        return _TraceContext(namespace, tool_name)


class _TraceContext:
    def __init__(self, namespace: str, tool_name: str):
        self.namespace = namespace
        self.tool_name = tool_name
        self.start = time.time()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = (time.time() - self.start) * 1000
        success = exc_type is None
        logger.info(
            "tool_call_traced",
            namespace=self.namespace,
            tool_name=self.tool_name,
            duration_ms=round(duration_ms, 2),
            success=success,
        )
        return False
