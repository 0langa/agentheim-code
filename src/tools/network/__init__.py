"""Network access enforcement — host-level filtering and policy evaluation.

Provides the ``NetworkEnforcer`` that validates all outbound connections
against configured host allow/deny lists, URL scheme constraints, and
DNS-level protection.  This is consumed by ``HttpTool`` and the policy
engine to ensure network policies are enforced at runtime, not merely
advisory at the tool level.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from fnmatch import fnmatch
from typing import Literal
from urllib.parse import urlparse


class NetworkViolation(Exception):
    """Raised when a network request violates policy."""


@dataclass(frozen=True)
class NetworkPolicy:
    """Network access policy with host-level filtering.

    Attributes:
        allowed: Whether outbound network access is permitted at all.
        allowed_hosts: Glob/fnmatch patterns for permitted hosts.
        denied_hosts: Glob/fnmatch patterns for blocked hosts.
        allowed_schemes: Permitted URL schemes (default: https only).
        deny_private_ranges: Block RFC 1918 / private / loopback ranges.
        deny_link_local: Block link-local addresses (169.254.x.x).
        policy_mode: "strict" blocks violations, "advisory" warns only.
    """

    allowed: bool = False
    allowed_hosts: tuple[str, ...] = ()
    denied_hosts: tuple[str, ...] = (
        "169.254.*",  # link-local
        "metadata.google.internal",
        "metadata*",  # cloud metadata services
    )
    allowed_schemes: tuple[str, ...] = ("https",)
    deny_private_ranges: bool = True
    deny_link_local: bool = True
    policy_mode: Literal["strict", "advisory"] = "strict"


class NetworkEnforcer:
    """Validates outbound network requests against a ``NetworkPolicy``.

    Usage::

        enforcer = NetworkEnforcer()
        enforcer.validate("https://example.com/api")  # raises on violation
    """

    # RFC 1918 and other private/loopback CIDR ranges
    _PRIVATE_RANGES = [
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("127.0.0.0/8"),  # loopback
        ipaddress.ip_network("::1/128"),  # IPv6 loopback
        ipaddress.ip_network("fc00::/7"),  # IPv6 unique-local
    ]

    _LINK_LOCAL_RANGES = [
        ipaddress.ip_network("169.254.0.0/16"),  # IPv4 link-local
        ipaddress.ip_network("fe80::/10"),  # IPv6 link-local
    ]

    def __init__(self, policy: NetworkPolicy | None = None) -> None:
        self.policy = policy or NetworkPolicy()

    def validate(self, url: str) -> None:
        """Validate *url* against the network policy.

        Args:
            url: The full URL to validate.

        Raises:
            NetworkViolation: If the URL violates any policy rule.
        """
        parsed = urlparse(url)
        host = parsed.hostname or ""
        scheme = parsed.scheme.lower() if parsed.scheme else ""

        # 1. Check if network access is allowed at all
        if not self.policy.allowed:
            raise NetworkViolation("Outbound network access is disabled by policy.")

        # 2. Check scheme
        if self.policy.allowed_schemes and scheme not in self.policy.allowed_schemes:
            raise NetworkViolation(
                f"URL scheme '{scheme}' is not in allowed schemes: "
                f"{', '.join(self.policy.allowed_schemes)}"
            )

        # 3. Check denied hosts (glob patterns)
        for denied in self.policy.denied_hosts:
            if fnmatch(host.lower(), denied.lower()):
                raise NetworkViolation(f"Host '{host}' matches denied pattern '{denied}'")

        # 4. Check allowed hosts (if specified)
        if self.policy.allowed_hosts and not any(
            fnmatch(host.lower(), allowed.lower()) for allowed in self.policy.allowed_hosts
        ):
            raise NetworkViolation(
                f"Host '{host}' is not in the allowed hosts list. "
                f"Allowed: {', '.join(self.policy.allowed_hosts)}"
            )

        # 5. Resolve IP and check private/link-local ranges
        if self.policy.deny_private_ranges or self.policy.deny_link_local:
            self._check_ip_ranges(host)

    def _check_ip_ranges(self, host: str) -> None:
        """Resolve *host* to IP address(es) and check against forbidden ranges."""
        try:
            addr = ipaddress.ip_address(host)
            self._check_single_ip(addr)
            return
        except ValueError:
            pass  # not a raw IP, need to resolve

        # For hostnames, we attempt resolution to catch DNS rebinding risks
        import socket

        try:
            addrs = socket.getaddrinfo(host, None)
            seen: set[str] = set()
            for _family, _type, _proto, _canonname, sockaddr in addrs:
                ip_str = sockaddr[0]
                if not isinstance(ip_str, str):
                    continue
                if ip_str in seen:
                    continue
                seen.add(ip_str)
                try:
                    addr = ipaddress.ip_address(ip_str)
                    self._check_single_ip(addr)
                except ValueError:
                    pass
        except (socket.gaierror, OSError) as exc:
            # DNS resolution failure — in strict mode this is a violation
            if self.policy.policy_mode == "strict":
                raise NetworkViolation(
                    f"DNS resolution failed for host '{host}' in strict mode"
                ) from exc

    def _check_single_ip(self, addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
        """Check a single IP address against forbidden ranges."""
        if self.policy.deny_private_ranges:
            for private_net in self._PRIVATE_RANGES:
                if addr in private_net:
                    raise NetworkViolation(
                        f"IP '{addr}' is in a private/loopback range ({private_net}) and "
                        f"private ranges are denied by policy."
                    )

        if self.policy.deny_link_local:
            for ll_net in self._LINK_LOCAL_RANGES:
                if addr in ll_net:
                    raise NetworkViolation(
                        f"IP '{addr}' is in a link-local range ({ll_net}) and "
                        f"link-local ranges are denied by policy."
                    )
