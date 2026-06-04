"""Auto-create the Solar AI Lovelace dashboard from the bundled YAML (v0.51.0).

HACS only copies the integration's own folder, so the dashboard YAML ships
inside `dashboards/` here. At setup (opt-in) the integration registers a
storage-mode Lovelace dashboard and writes the bundled config into it — the
same two steps the WebSocket commands `lovelace/dashboards/create` and
`lovelace/config/save` perform, done in-process.

Everything is wrapped so a failure can never stop the config entry from
loading; the user can always fall back to the manual import documented in the
README.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

DASHBOARD_URL_PATH = "solar-ai"
DASHBOARD_TITLE = "Solar AI"
DASHBOARD_ICON = "mdi:solar-power"
_DASHBOARDS_DIR = Path(__file__).parent / "dashboards"

_MISSING_CARDS_ISSUE = "missing_dashboard_cards"

# Custom Lovelace cards the bundled dashboard needs. Each: (display name,
# substring expected in the registered resource URL, install link).
REQUIRED_CARDS: list[tuple[str, str, str]] = [
    ("Mushroom", "mushroom", "https://github.com/piitaya/lovelace-mushroom"),
    ("ApexCharts Card", "apexcharts-card", "https://github.com/RomRider/apexcharts-card"),
    ("Power Flow Card Plus", "power-flow-card-plus", "https://github.com/flixlix/power-flow-card-plus"),
    ("card-mod", "card-mod", "https://github.com/thomasloven/lovelace-card-mod"),
    ("button-card", "button-card", "https://github.com/custom-cards/button-card"),
]


def _load_dashboard_yaml(language: str) -> dict[str, Any] | None:
    """Load the Danish or English bundled dashboard (blocking — run in executor)."""
    fname = "dashboard_da.yaml" if str(language or "").lower().startswith("da") else "dashboard_en.yaml"
    path = _DASHBOARDS_DIR / fname
    try:
        with open(path, encoding="utf-8") as fh:
            return yaml.safe_load(fh)
    except (OSError, yaml.YAMLError) as err:
        _LOGGER.error("Could not read bundled dashboard %s: %s", path, err)
        return None


async def async_create_dashboard(hass: HomeAssistant, *, force: bool = False) -> str | None:
    """Create (or, with force, overwrite) the Solar AI storage dashboard.

    HA's LovelaceData does not expose the *live* dashboards collection (it is a
    local in async_setup; only its change-listener writes back to
    `data.dashboards`). So we persist the dashboard's metadata through our own
    DashboardsCollection (writes the same `.storage/lovelace_dashboards` file),
    add a LovelaceStorage config to the live `data.dashboards` map, and register
    the sidebar panel — the dashboard appears immediately and survives a
    restart. The one consequence is that until the next HA restart the live
    collection doesn't yet track it, so it can't be edited/removed from
    Settings → Dashboards (and a manual dashboard reorganisation could drop it).
    On a newly-created dashboard we therefore raise a persistent notification
    recommending a one-time restart to finalise it; after that it is fully
    managed like any other dashboard.

    Idempotent: if the dashboard already exists and force is False, it is left
    untouched. Returns the url_path on success, None on any failure (the user
    can always import the bundled YAML manually — see the README).
    """
    try:
        from homeassistant.components.lovelace import MODE_STORAGE, _register_panel
        from homeassistant.components.lovelace.dashboard import (
            DashboardsCollection,
            LovelaceStorage,
        )

        data = hass.data.get("lovelace")
        dashboards_map = getattr(data, "dashboards", None)
        if dashboards_map is None:
            _LOGGER.warning(
                "Lovelace storage not available — cannot auto-create the dashboard. "
                "Import the bundled YAML manually instead (see the README)."
            )
            return None

        if DASHBOARD_URL_PATH in dashboards_map and not force:
            return DASHBOARD_URL_PATH  # leave the existing one alone

        config = await hass.async_add_executor_job(_load_dashboard_yaml, hass.config.language)
        if not config:
            return None

        # Persist (or fetch) the dashboard metadata via the storage collection.
        collection = DashboardsCollection(hass)
        await collection.async_load()
        items = {it["url_path"]: it for it in collection.async_items()}
        item = items.get(DASHBOARD_URL_PATH)
        newly_created = item is None
        if newly_created:
            item = await collection.async_create_item({
                "url_path": DASHBOARD_URL_PATH,
                "title": DASHBOARD_TITLE,
                "icon": DASHBOARD_ICON,
                "show_in_sidebar": True,
                "require_admin": False,
            })

        # Live config store + sidebar panel, so it shows without a restart.
        store = dashboards_map.get(DASHBOARD_URL_PATH)
        if store is None:
            store = LovelaceStorage(hass, item)
            dashboards_map[DASHBOARD_URL_PATH] = store
            try:
                _register_panel(hass, DASHBOARD_URL_PATH, MODE_STORAGE, item, False)
            except Exception:  # noqa: BLE001
                _LOGGER.debug(
                    "Live panel registration failed; dashboard will appear after a restart",
                    exc_info=True,
                )

        await store.async_save(config)
        _LOGGER.info("Solar AI dashboard %s at /%s",
                     "created" if newly_created else "updated", DASHBOARD_URL_PATH)

        if newly_created:
            # The live dashboards collection won't track it until the next
            # restart, so prompt the user to do one to finalise management.
            try:
                from homeassistant.components.persistent_notification import (
                    async_create as _pn_create,
                )
                _pn_create(
                    hass,
                    "The Solar AI dashboard was created at **/solar-ai** and is ready to "
                    "use now.\n\nRestart Home Assistant once when convenient to finalise it "
                    "— after a restart it appears in **Settings → Dashboards**, where it can "
                    "be edited or removed like any other dashboard. (It also needs the custom "
                    "Lovelace cards from HACS to render fully — see Settings → Repairs if any "
                    "are missing.)",
                    title="Solar AI dashboard created",
                    notification_id="solar_ai_dashboard_created",
                )
            except Exception:  # noqa: BLE001
                _LOGGER.debug("Could not raise dashboard-created notification", exc_info=True)

        return DASHBOARD_URL_PATH
    except Exception:  # noqa: BLE001 — must never break config-entry setup
        _LOGGER.exception("Auto-create of the Solar AI dashboard failed")
        return None


def _registered_resource_urls(hass: HomeAssistant) -> list[str] | None:
    """Return registered Lovelace resource URLs, or None if undetectable.

    None means we can't tell (resources not loaded, or YAML-mode where they
    live in configuration.yaml) — callers should NOT warn in that case to
    avoid false positives.
    """
    data = hass.data.get("lovelace")
    resources = getattr(data, "resources", None) if data is not None else None
    if resources is None:
        return None
    try:
        items = resources.async_items()
    except Exception:  # noqa: BLE001
        return None
    urls = [str(it.get("url", "")) for it in items if isinstance(it, dict)]
    return urls or None


async def async_check_dashboard_cards(hass: HomeAssistant) -> None:
    """Raise/clear a Repairs issue listing custom cards the dashboard needs.

    HACS does not chain-install frontend plugins when an integration is
    downloaded, so the bundled dashboard's cards must be installed once by the
    user. This surfaces exactly which are missing instead of leaving cryptic
    "Custom element doesn't exist" errors on the dashboard. The issue clears
    automatically once all cards are present (re-checked each setup).
    """
    try:
        urls = _registered_resource_urls(hass)
        if urls is None:
            return  # can't detect reliably — stay silent
        missing = [name for name, substr, _ in REQUIRED_CARDS
                   if not any(substr in u for u in urls)]
        if missing:
            ir.async_create_issue(
                hass, DOMAIN, _MISSING_CARDS_ISSUE,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=_MISSING_CARDS_ISSUE,
                translation_placeholders={"cards": ", ".join(missing)},
                learn_more_url="https://github.com/Planckus/solar_ai#dashboard-dependencies-hacs",
            )
        else:
            ir.async_delete_issue(hass, DOMAIN, _MISSING_CARDS_ISSUE)
    except Exception:  # noqa: BLE001
        _LOGGER.debug("Dashboard card check skipped (error)", exc_info=True)
