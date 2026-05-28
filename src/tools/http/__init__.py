"""HTTP tool implementing ToolProtocol.

Outbound HTTP requests with host-level network policy enforcement.
Every request is validated by ``NetworkEnforcer`` before transmission.
"""

from __future__ import annotations

from typing import Any

from core.tool_protocol import (
    BaseTool,
    ParamSchema,
    ReturnSchema,
    RiskLevel,
    ToolContext,
    ToolResult,
    ToolSchema,
)
from tools.network import NetworkEnforcer, NetworkPolicy, NetworkViolation


class HttpTool(BaseTool):
    """Outbound HTTP requests with host-level network policy enforcement.

    Every request passes through ``NetworkEnforcer`` which validates:
    - Whether network access is allowed at all
    - URL scheme (default: https only)
    - Host allow/deny lists (glob patterns)
    - Private IP ranges (RFC 1918, loopback)
    - Link-local addresses
    - DNS-level protection
    """

    def __init__(self, network_policy: NetworkPolicy | None = None) -> None:
        self._enforcer = NetworkEnforcer(network_policy or NetworkPolicy(allowed=True))
        schema = ToolSchema(
            description="Make outbound HTTP requests with host-level network policy.",
            parameters={
                "method": ParamSchema(
                    type="string",
                    description="HTTP method",
                    enum=["GET", "POST", "PUT", "DELETE", "PATCH"],
                    required=True,
                ),
                "url": ParamSchema(type="string", description="Request URL", required=True),
                "headers": ParamSchema(
                    type="object", description="Request headers", required=False
                ),
                "body": ParamSchema(type="string", description="Request body", required=False),
                "timeout": ParamSchema(
                    type="integer", description="Timeout in seconds", default=30, required=False
                ),
            },
            returns=ReturnSchema(type="object", description="{status, headers, body}"),
        )
        super().__init__("http.request", schema, RiskLevel.HIGH)

    def invoke(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        valid, err = self.validate_params(params)
        if not valid:
            return ToolResult(success=False, error=err)

        url = params.get("url", "")
        method = params.get("method", "GET")
        headers = params.get("headers", {})
        body = params.get("body")
        timeout = params.get("timeout", 30)

        # Network policy check (ToolContext level)
        if not context.network_allowed:
            return ToolResult(success=False, error="Network access is not allowed by policy.")

        # Host-level network enforcement (cannot be bypassed by ToolContext)
        try:
            self._enforcer.validate(url)
        except NetworkViolation as exc:
            return ToolResult(success=False, error=f"Network policy violation: {exc}")

        try:
            import urllib.request

            req = urllib.request.Request(url, method=method, headers=headers)
            if body is not None:
                req.data = body.encode("utf-8") if isinstance(body, str) else body

            with urllib.request.urlopen(req, timeout=timeout) as response:
                response_body = response.read().decode("utf-8", errors="ignore")
                return ToolResult(
                    success=True,
                    data={
                        "status": response.status,
                        "headers": dict(response.headers),
                        "body": response_body,
                    },
                )
        except Exception as exc:
            return ToolResult(success=False, error=f"HTTP request failed: {exc}")
