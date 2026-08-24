"""Extension declaration, secrets, lifecycle hooks.

WHY BYOK (bring-your-own-key), SAME REASONING AS AWS/Azure/GCP/OCI/
DigitalOcean Connector. Alibaba Cloud lives inside the USER'S OWN
account -- Imperal cannot and should not broker access centrally.

WHY RPC-STYLE SIGNATURE V2 (HMAC-SHA1), UNLIKE ANY OTHER HYPERSCALER
IN THE PORTFOLIO.

Alibaba Cloud signs every request with its own RPC-style algorithm:
sort all parameters alphabetically, build a canonicalized query
string, HMAC-SHA1 it with the AccessKey Secret. Different from AWS
SigV4 (HMAC-SHA256 canonical request with headers), Azure/GCP OAuth
client-credentials, and OCI's RSA-SHA256 request signing. See
CONNECTOR_DISCOVERY.md #2 for the exact algorithm and its URL-encoding
quirks (+, *, ~ need manual fixups after standard percent-encoding).

WHY THERE IS NO TOKEN CACHE HERE, SAME AS OCI/DigitalOcean CONNECTOR.

The AccessKey ID + Secret pair IS the credential -- every request is
signed fresh, nothing is exchanged or cached.

WHY THIS CONNECTOR IS SCOPED TO ECS/OSS/RDS/ACK(read)/CloudMonitor/BSS,
NOT "ALL OF ALIBABA CLOUD".

Mirrors AWS/Azure/GCP/OCI/DigitalOcean Connector's domain choice
(compute, storage, managed DB, k8s read-only, monitoring, cost) so all
five hyperscaler connectors read the same way. Serverless App Engine,
PAI (AI Platform) and China-specific products (WeChat integrations
etc.) are explicitly out of scope for v1.
"""
from __future__ import annotations

from imperal_sdk import Extension, ChatExtension

ext = Extension(
    "alibaba-cloud-connector",
    version="0.1.0",
    display_name="Alibaba Cloud",
    description=(
        "Connect your own Alibaba Cloud account (AccessKey ID + Secret) "
        "to see and manage ECS instances, OSS (Object Storage), ApsaraDB "
        "(managed databases), ACK (Kubernetes, read-only), CloudMonitor "
        "alerts, and Billing from Imperal. Your keys are verified against "
        "your account before they're saved. Scoped to the operational "
        "core -- Serverless App Engine, PAI (AI Platform) and China- "
        "specific products are out of scope."
    ),
    icon="icon.svg",
    actions_explicit=True,
    capabilities=["alibaba_cloud:read", "alibaba_cloud:write"],
)

chat = ChatExtension(
    ext,
    tool_name="alibaba-cloud-connector",
    description="View and manage Alibaba Cloud -- ECS, OSS, ApsaraDB, ACK, CloudMonitor, Billing",
)

ext.secret(
    "alibaba_cloud_connections",
    (
        "Your connected Alibaba Cloud accounts -- stored as a JSON "
        "array, one entry per account, each with its own AccessKey ID, "
        "AccessKey Secret, optional default region, and a friendly "
        "label. Managed through connect_alibaba_cloud / "
        "disconnect_alibaba_cloud -- you should not need to edit this "
        "directly."
    ),
    required=True,
    write_mode="both",
    max_bytes=65536,
    rotation_hint_days=90,
)(lambda: None)


@ext.health_check
async def health_check(ctx) -> dict:
    """Fast, no-network health check -- confirms the extension loaded and
    its secret slot is reachable, same pattern as AWS/Azure/GCP/OCI/
    DigitalOcean Connector."""
    return {"ok": True, "detail": "alibaba-cloud-connector loaded"}
