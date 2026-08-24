"""Alibaba Cloud RPC-style API client -- V2 Signature (HMAC-SHA1) over
ctx.http, no signing/token cache needed (see app.py).

WHY THIS IS THE ONLY *_client.py WITH ITS OWN SIGNATURE ALGORITHM
DISTINCT FROM AWS SigV4 / Azure OAuth / GCP JWT / OCI RSA-SHA256.

Every Alibaba Cloud RPC-style request is signed by:
1. Sort all params (common + operation-specific) alphabetically by key.
2. Percent-encode per RFC 3986 (with ~ NOT encoded, + and * fixed up
   manually after Python's urllib.parse.quote, which differs slightly).
3. Build a canonicalized query string, join with '&'.
4. stringToSign = f"{METHOD}&{encode('/')}&{encode(canonical_qs)}"
5. signature = base64(hmac_sha1(access_key_secret + "&", stringToSign))

See: alibabacloud.com/help/en/sdk/product-overview/rpc-mechanism
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import time
import urllib.parse
import uuid
from typing import Any

_COMMON_VERSION = {
    "ecs": "2014-05-26",
    "rds": "2014-08-15",
    "cs": "2015-12-15",       # ACK (Container Service for Kubernetes)
    "ram": "2015-05-01",
    "cms": "2019-01-01",      # CloudMonitor
    "bssopenapi": "2017-12-14",
}

_SERVICE_CODE = {
    "ecs": "ecs",
    "rds": "rds",
    "cs": "cs",
    "ram": "ram",
    "cms": "metrics.cn-hangzhou.aliyuncs.com",  # CloudMonitor endpoint quirk, overridden per-call
    "bssopenapi": "business.aliyuncs.com",
}


class ProviderError(Exception):
    """Raised for any Alibaba Cloud RPC API call that fails, carrying the
    Code/Message the API itself returned so handlers can distinguish
    auth failures from ordinary not-found/validation errors."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"Alibaba Cloud API error {code}: {message}")


def _percent_encode(s: str) -> str:
    """RFC 3986 percent-encoding per Alibaba Cloud's exact rules --
    tildes stay literal, spaces become %20, asterisks become %2A."""
    encoded = urllib.parse.quote(str(s), safe="~")
    return encoded.replace("+", "%20").replace("*", "%2A")


def _sign(access_key_secret: str, http_method: str, params: dict) -> str:
    sorted_items = sorted(params.items(), key=lambda kv: kv[0])
    canonical_qs = "&".join(f"{_percent_encode(k)}={_percent_encode(v)}" for k, v in sorted_items)
    string_to_sign = f"{http_method}&{_percent_encode('/')}&{_percent_encode(canonical_qs)}"
    key = (access_key_secret + "&").encode("utf-8")
    digest = hmac.new(key, string_to_sign.encode("utf-8"), hashlib.sha1).digest()
    return base64.b64encode(digest).decode("utf-8")


def _common_params(access_key_id: str, action: str, version: str) -> dict:
    return {
        "AccessKeyId": access_key_id,
        "Action": action,
        "Version": version,
        "Format": "JSON",
        "SignatureMethod": "HMAC-SHA1",
        "SignatureVersion": "1.0",
        "SignatureNonce": uuid.uuid4().hex,
        "Timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


async def call(ctx, service: str, region_id: str, action: str, access_key_id: str,
                access_key_secret: str, action_label: str, extra_params: dict | None = None,
                http_method: str = "GET") -> dict:
    """Call one Alibaba Cloud RPC-style action against a given service/region."""
    version = _COMMON_VERSION.get(service, "2014-05-26")
    host = f"{service}.{region_id}.aliyuncs.com" if region_id else f"{service}.aliyuncs.com"
    params = _common_params(access_key_id, action, version)
    if region_id:
        params["RegionId"] = region_id
    params.update(extra_params or {})
    params["Signature"] = _sign(access_key_secret, http_method, params)

    resp = await ctx.http.request(method=http_method, url=f"https://{host}/", params=params)
    try:
        body = resp.json()
    except Exception:
        body = {}
    if resp.status_code >= 400 or "Code" in body:
        code = body.get("Code", str(resp.status_code))
        message = body.get("Message", resp.text)
        raise ProviderError(code, f"Could not {action_label}: {message}")
    return body


# ──────────────────────────────────────────────────────────────────────────
# OSS (Object Storage Service) -- DIFFERENT signing scheme from RPC APIs
# ──────────────────────────────────────────────────────────────────────────
#
# OSS is NOT an RPC-style API -- it signs requests the way S3-compatible
# stores do: HMAC-SHA1 over a canonicalized string of (verb, headers,
# resource), sent as an `Authorization: OSS <AccessKeyId>:<signature>`
# header, not as signed query parameters. This is a second, separate
# signing algorithm within the same connector -- documented here rather
# than silently reused from the RPC `call()` above.


def _oss_string_to_sign(http_method: str, date: str, resource: str) -> str:
    return f"{http_method}\n\n\n{date}\n{resource}"


def _oss_sign(access_key_secret: str, string_to_sign: str) -> str:
    digest = hmac.new(access_key_secret.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha1).digest()
    return base64.b64encode(digest).decode("utf-8")


async def list_oss_buckets(ctx, access_key_id: str, access_key_secret: str, region_id: str) -> list[dict]:
    """List OSS buckets visible to this AccessKey pair (account-wide, not region-scoped)."""
    date = time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime())
    resource = "/"
    string_to_sign = _oss_string_to_sign("GET", date, resource)
    signature = _oss_sign(access_key_secret, string_to_sign)
    headers = {
        "Date": date,
        "Authorization": f"OSS {access_key_id}:{signature}",
    }
    host = f"oss-{region_id}.aliyuncs.com" if region_id else "oss.aliyuncs.com"
    resp = await ctx.http.request(method="GET", url=f"https://{host}/", headers=headers)
    if resp.status_code >= 400:
        raise ProviderError(str(resp.status_code), f"Could not list OSS buckets: {resp.text}")
    # OSS returns XML -- extract bucket names/regions/creation dates with a tiny parser
    import re
    text = resp.text
    names = re.findall(r"<Name>(.*?)</Name>", text)
    locations = re.findall(r"<Location>(.*?)</Location>", text)
    created = re.findall(r"<CreationDate>(.*?)</CreationDate>", text)
    out = []
    for i, name in enumerate(names):
        out.append({
            "name": name,
            "location": locations[i] if i < len(locations) else "",
            "creation_date": created[i] if i < len(created) else "",
        })
    return out
