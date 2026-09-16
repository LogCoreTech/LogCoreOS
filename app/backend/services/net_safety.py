"""net_safety.py — shared SSRF guard for any place the server makes an
outbound request to a host supplied by an admin/user rather than one this
codebase hardcoded itself: push subscription endpoints (push_service.py) and
admin-configured "custom"/not-yet-docs_verified AI provider base_urls
(routers/ai_settings.py) today. Pure, no I/O beyond the DNS lookup itself.

Validated by resolved IP, not a hostname allowlist — see
push_service._validate_push_endpoint's docstring for the full reasoning:
legitimate provider hostnames change/multiply over time and a stale allowlist
would just break real integrations, while "every resolved address must be
public" generalizes without maintenance.

Deliberately does NOT defend against DNS rebinding (a TOCTOU gap between this
check and the real request later) — the hosts this guards (push providers,
cloud AI APIs) are stable, high-reputation domains with no realistic path to
resolving privately, so full IP-pinning on every call isn't worth the
complexity it would add here. Same tradeoff push_service already made.
"""

import ipaddress
import socket


def assert_resolves_publicly(hostname: str) -> None:
    """Raise ValueError if `hostname` can't be resolved, or if ANY address it
    resolves to is private/loopback/link-local/reserved/multicast/unspecified
    (covers RFC1918, loopback, link-local incl. the 169.254.169.254 cloud
    metadata address, and friends). Callers that need a scheme requirement
    (push endpoints must be https) or a caller-specific message should check
    that separately — this only ever validates the hostname's resolved IPs.
    """
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        raise ValueError(f"{hostname!r} could not be resolved.") from None
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise ValueError(f"{hostname!r} resolves to a non-public address and was rejected.")
