"""Panel UI -- connections list/connect form for Alibaba Cloud Connector.

SIDEBAR CONTENT -- NO CARDS ANYWHERE, per ~/UI_INTERFACE_STANDARD.md's
"left sidebar, no decorated cards" rule (same convention as AWS/Azure/
GCP/OCI/DigitalOcean Connector's panels.py).

Every section (connections, connect form) is a plain ui.Stack, content
stacked vertically and left-aligned, sections separated by ui.Divider() --
no Card border/background/shadow anywhere in this slot. Disconnect lives
only in the "App settings" screen (panels_settings.py). The one secondary
"App settings" button is always the LAST element at the bottom of the
sidebar.

Per Vlad's standing rule: every input carries its own label (as a
ui.Text(variant="caption") directly above it -- ui.Input itself has no
`label` prop, only `param_name`/`placeholder`/`value`/`on_submit`),
placeholders are contextually specific, secret fields use ui.Password
(NOT ui.Input(input_type=...) -- that keyword does not exist and is
rejected by the deploy validator, confirmed on DigitalOcean Connector),
and section stacks use align="stretch" so inputs fill the left sidebar's
width. The sidebar carries NO instructions that duplicate the "How do I
set this up?" modal.
"""
from __future__ import annotations

from imperal_sdk import ui

from app import ext
import handlers as h


def _settings_button() -> ui.UINode:
    """The one required secondary entry point into the settings screen --
    always the last element at the bottom of the sidebar."""
    return ui.Button(
        "App settings", variant="secondary", size="sm", icon="settings", on_click=ui.Call("__panel__alibaba_cloud_settings"),
    )


def _field(label: str, node: ui.UINode) -> ui.UINode:
    return ui.Stack(direction="v", gap=1, align="stretch", children=[
        ui.Text(label, variant="caption"),
        node,
    ])


def _connection_row(c: dict) -> ui.UINode:
    label = c.get("title") or c.get("label") or "Alibaba Cloud account"
    return ui.Stack(direction="v", gap=1, align="start", children=[
        ui.Text(label, variant="body"),
        ui.Text(f"Region: {c.get('region_id', '')}", variant="caption"),
        ui.Button(
            "Open cloud overview", variant="primary", size="sm",
            on_click=ui.Call("get_cloud_overview", {"connection_id": c.get("id")}),
        ),
    ])


def _connections_section(connections: list[dict]) -> ui.UINode:
    if not connections:
        return ui.Text("No Alibaba Cloud accounts connected yet.", variant="caption")
    children: list[ui.UINode] = []
    for i, c in enumerate(connections):
        if i > 0:
            children.append(ui.Divider())
        children.append(_connection_row(c))
    return ui.Stack(direction="v", gap=2, children=children)


def _connect_section() -> ui.UINode:
    return ui.Stack(direction="v", gap=3, align="stretch", children=[
        ui.Text("Connect an Alibaba Cloud account", variant="heading"),
        ui.Form(
            action="connect_alibaba_cloud",
            submit_label="Verify and connect",
            children=[
                _field("AccessKey ID", ui.Input(
                    param_name="access_key_id",
                    placeholder="e.g. LTAI5t...",
                )),
                _field("AccessKey Secret", ui.Password(
                    param_name="access_key_secret",
                    placeholder="Paste the secret shown once by the RAM console",
                )),
                _field("Default region (optional)", ui.Input(
                    param_name="region_id", placeholder="e.g. cn-hangzhou",
                )),
                _field("Label (optional)", ui.Input(
                    param_name="label", placeholder="e.g. Production account",
                )),
            ],
        ),
    ])


@ext.panel("alibaba_cloud_sidebar", slot="left", title="Alibaba Cloud")
async def alibaba_cloud_sidebar_panel(ctx, **kwargs) -> object:
    connections = await h._load_connections(ctx)
    content = ui.Stack(direction="v", gap=4, align="stretch", children=[
        _connections_section(connections),
        ui.Divider(),
        _connect_section(),
        ui.Divider(),
        _settings_button(),
    ])
    return content


@ext.panel("alibaba_cloud_center", slot="center", title="Alibaba Cloud", center_overlay=True)
async def alibaba_cloud_center_panel(ctx, **kwargs) -> object:
    return ui.Stack(direction="v", align="center", justify="center", children=[
        ui.Text("Nothing to show here", variant="body"),
    ])


@ext.panel("alibaba_cloud_connect_help", slot="center", title="How do I set this up?", center_overlay=True)
async def alibaba_cloud_connect_help(ctx, **kwargs) -> object:
    content = ui.Stack(direction="v", gap=3, children=[
        ui.Text("1. Sign in to the Alibaba Cloud console and open RAM "
                "(Resource Access Management) > Users."),
        ui.Text("2. Create a new RAM user (or use an existing one), and "
                "attach the built-in \"AliyunReadOnlyAccess\" policy -- "
                "this is enough to start exploring your account safely."),
        ui.Text("3. Open that user's \"Create AccessKey\" action and copy "
                "the AccessKey ID and AccessKey Secret immediately -- "
                "Alibaba Cloud only shows the secret once."),
        ui.Text("4. Paste both values into the fields on the left."),
        ui.Text("5. Set your default region (e.g. cn-hangzhou or "
                "ap-southeast-1) -- most operations need one, and this "
                "saves you from typing it every time."),
        ui.Text("6. If you later want me to start/stop ECS instances, "
                "attach \"AliyunECSFullAccess\" (or a narrower custom "
                "policy) to the same RAM user."),
    ])
    return content
