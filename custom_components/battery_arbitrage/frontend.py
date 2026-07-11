"""Auto-register the bundled Solar AI Lovelace cards (v0.74.0).

Ships its own frontend so the dashboard needs no third-party HACS cards
(mushroom, apexcharts-card, power-flow-card-plus, card-mod). The JS lives in
`www/solar-ai-cards.js` inside this integration's own folder — HACS copies it
along with everything else, no separate frontend-repo install step.

Serving is done with `async_register_static_paths` (the only supported API on
any HA version still receiving updates; the old synchronous
`register_static_path` was removed some time ago). The resource is then added
to the Lovelace *resources storage collection* — the exact mechanism every
HACS frontend card (mushroom, apexcharts-card, etc.) already relies on, and
confirmed working on live hardware. (`frontend.add_extra_js_url` looks like
the more "native-integration" way to do this and was tried first, but it
silently failed to make the custom elements available in time for Lovelace's
card-creation pass — the resources collection is the proven path.) Either
way, the user needs no manual "Settings > Dashboards > Resources" step, unlike
every third-party card this replaces.

Wrapped in try/except throughout: a frontend-registration failure must never
prevent the integration's entities and EV/arbitrage logic from loading.
"""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

_URL_BASE = f"/{DOMAIN}_static"
_JS_FILENAME = "solar-ai-cards.js"
_RESOURCE_PATH = f"{_URL_BASE}/{_JS_FILENAME}"


async def async_register_frontend(hass: HomeAssistant, version: str) -> None:
    """Serve the bundled card JS and register it as a Lovelace resource.

    Safe to call on every setup: idempotent (updates the existing resource
    entry in place rather than duplicating it) and never raises.
    """
    try:
        from homeassistant.components.http import StaticPathConfig

        www_dir = str(Path(__file__).parent / "www")
        await hass.http.async_register_static_paths([
            StaticPathConfig(_URL_BASE, www_dir, cache_headers=True),
        ])

        # Version-tagged query string busts the browser cache on every
        # integration update, so a stale bundle never lingers after an
        # upgrade the way an un-tagged URL would.
        target_url = f"{_RESOURCE_PATH}?v={version}"

        data = hass.data.get("lovelace")
        resources = getattr(data, "resources", None) if data is not None else None
        if resources is None:
            _LOGGER.warning(
                "Lovelace resources storage not available — cannot "
                "auto-register the Solar AI cards. Add %s as a module "
                "resource manually (Settings > Dashboards > Resources).",
                target_url,
            )
            return

        # async_items() can raise before the collection has loaded on a very
        # early call; that's fine, we just register fresh in that case.
        try:
            existing = resources.async_items()
        except Exception:  # noqa: BLE001
            existing = []
        ours = next(
            (it for it in existing if str(it.get("url", "")).startswith(_RESOURCE_PATH)),
            None,
        )
        if ours is None:
            await resources.async_create_item({"res_type": "module", "url": target_url})
            _LOGGER.debug("Solar AI frontend cards registered (v%s)", version)
        elif ours.get("url") != target_url:
            await resources.async_update_item(ours["id"], {"res_type": "module", "url": target_url})
            _LOGGER.debug("Solar AI frontend cards updated to v%s", version)
    except Exception:  # noqa: BLE001 — must never break entry setup
        _LOGGER.exception(
            "Could not register the bundled Solar AI dashboard cards — "
            "the dashboard will fall back to needing the third-party cards"
        )
