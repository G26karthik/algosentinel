import asyncio
import hashlib
import hmac

import structlog
from fastapi import FastAPI, Header, HTTPException, Request

from algosentinel.agent.core import AgentLoop
from algosentinel.config import settings

app = FastAPI(title="AlgoSentinel", version="0.1.0")
logger = structlog.get_logger()


@app.post("/webhook/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: str = Header(None),
    x_github_event: str = Header(None),
):
    body = await request.body()

    if settings.github_webhook_secret:
        expected = "sha256=" + hmac.new(
            settings.github_webhook_secret.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, x_hub_signature_256 or ""):
            raise HTTPException(status_code=401, detail="Invalid HMAC signature")

    if x_github_event != "pull_request":
        return {"status": "ignored", "reason": f"event type is {x_github_event}"}

    payload = await request.json()
    action = payload.get("action")

    if action not in ("opened", "synchronize"):
        return {"status": "ignored", "reason": f"action is {action}"}

    repo = payload["repository"]["full_name"]
    pr_number = payload["pull_request"]["number"]

    logger.info("webhook_triggered", repo=repo, pr=pr_number, action=action)

    loop = asyncio.get_event_loop()
    loop.run_in_executor(
        None,
        lambda: AgentLoop().run(repo=repo, pr_numbers=[pr_number]),
    )

    return {"status": "accepted", "repo": repo, "pr": pr_number}


@app.get("/health")
def health():
    import algosentinel.tools.github  # noqa: F401
    import algosentinel.tools.sandbox  # noqa: F401
    import algosentinel.tools.complexity  # noqa: F401
    import algosentinel.tools.optimizer  # noqa: F401
    from algosentinel.tools.registry import ToolRegistry

    registry = ToolRegistry.get()
    return {
        "status": "ok",
        "tool_count": registry.tool_count(),
        "namespaces": registry.namespaces(),
        "tool_count_ok": registry.tool_count() >= 55,
    }
