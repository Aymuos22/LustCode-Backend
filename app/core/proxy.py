"""Resolve forwarded addresses only through explicitly configured trusted networks."""

from ipaddress import IPv4Network, IPv6Network, ip_address

from starlette.types import Scope


def client_address(
    scope: Scope,
    networks: tuple[IPv4Network | IPv6Network, ...],
    header_name: str = "x-forwarded-for",
) -> str:
    peer = (scope.get("client") or ("unknown", 0))[0]
    try:
        address = ip_address(peer)
    except ValueError:
        return peer
    if not any(address in network for network in networks):
        return peer
    if header_name == "cf-connecting-ip":
        values = [
            v.decode("latin1")
            for k, v in scope.get("headers", [])
            if k.lower() == b"cf-connecting-ip"
        ]
        if len(values) != 1:
            return peer
        try:
            return str(ip_address(values[0].strip()))
        except ValueError:
            return peer
    fields = [
        value.decode("latin1")
        for name, value in scope.get("headers", [])
        if name.lower() == b"x-forwarded-for"
    ]
    combined = ",".join(fields)
    if not combined or len(combined) > 4096:
        return peer
    parts = [value.strip() for value in combined.split(",")]
    if len(parts) > 32:
        return peer
    try:
        chain = [ip_address(value) for value in parts]
    except ValueError:
        return peer
    # Attacker-supplied leftmost entries cannot override the first untrusted peer.
    for address in reversed(chain):
        if not any(address in network for network in networks):
            return str(address)
    return str(chain[0])


def forwarded_scheme(scope: Scope, networks: tuple[IPv4Network | IPv6Network, ...]) -> str:
    try:
        peer = ip_address((scope.get("client") or ("unknown", 0))[0])
    except ValueError:
        return scope.get("scheme", "http")
    if any(peer in network for network in networks):
        values = [v for k, v in scope.get("headers", []) if k.lower() == b"x-forwarded-proto"]
        if len(values) == 1 and values[0] in (b"http", b"https"):
            return values[0].decode()
    return scope.get("scheme", "http")
