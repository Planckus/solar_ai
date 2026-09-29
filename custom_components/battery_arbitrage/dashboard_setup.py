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

import json
import logging
import re
from pathlib import Path
from typing import Any

import yaml
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er, issue_registry as ir

from .const import (
    CONF_BATTERY_CHARGE_ENTITY,
    CONF_BATTERY_DISCHARGE_ENTITY,
    CONF_BATTERY_SOC_ENTITY,
    CONF_FOXESS_GRID_EXPORT_ENTITY,
    CONF_FOXESS_GRID_IMPORT_ENTITY,
    CONF_FOXESS_LOAD_POWER_ENTITY,
    CONF_FOXESS_PV_POWER_ENTITY,
    CONF_FOXESS_WORK_MODE_ENTITY,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

DASHBOARD_URL_PATH = "solar-ai"
DASHBOARD_TITLE = "Solar AI"
DASHBOARD_ICON = "mdi:solar-power"
_DASHBOARDS_DIR = Path(__file__).parent / "dashboards"

_MISSING_CARDS_ISSUE = "missing_dashboard_cards"
_MISSING_ENTITIES_ISSUE = "missing_dashboard_entities"

# v1.20.0 — the bundled YAML is written against one install's entity ids, and
# those ids are not portable. Three things move them: the device was renamed
# from "Battery Arbitrage" to "Solar AI", and Home Assistant never rewrites an
# existing entity id, so an install created before the rename keeps the old
# prefix while a fresh one gets `solar_ai_`; the id is slugged from the
# entity's translated name at creation time, so a Danish and an English
# install disagree on the suffix; and the FoxESS entities carry whatever
# device name that user chose. `entity_map.json` maps every id the YAML uses
# to its translation key, which is stable across all three, and the ids are
# resolved against this install's registry when the dashboard is written.
_ENTITY_MAP_FILE = _DASHBOARDS_DIR / "entity_map.json"

_ENTITY_ID_RE = re.compile(
    r"\b(?:sensor|binary_sensor|switch|select|number|time|date|text|button)"
    r"\.[a-z0-9_]+\b"
)

# v1.20.2 — the bundled YAML also hardcodes the dashboard's OWN url_path in
# every navigation target (`/battery-arbitrage/priser` and the nav card). The
# integration creates the dashboard at DASHBOARD_URL_PATH, so on any install
# but the author's those links pointed at a dashboard that does not exist and
# Home Assistant fell back to the default one. Reported as issue #4. Only the
# leading dashboard path is rewritten; `/config/integrations/integration/
# battery_arbitrage` is the integration's own settings page, spelled with an
# underscore, and is left alone.
_YAML_DASHBOARD_PATH = "/battery-arbitrage/"

# v1.20.2 — one notification switch exists per discovered mobile app, named
# after that device, so its entity id differs on every install. The YAML can
# only carry placeholders; these rows are rebuilt from the install's own
# switches. Matched on unique_id, which the per-device switch builds as
# `{entry_id}_target_notify_mobile_app_<device>`.
_NOTIFY_TARGET_UNIQUE_ID_MARK = "_target_notify_mobile_app_"
_NOTIFY_PLACEHOLDER_ENTITIES = (
    "switch.solar_ai_notifikation_iphone",
    "switch.solar_ai_notifikation_ipad_air",
)

# FoxESS entities the YAML references, and the config key holding the user's
# real entity for each. Anything not configured is left untouched and reported.
_FOREIGN_ENTITY_KEYS: dict[str, str] = {
    "sensor.foxessmodbus_battery_soc_1": CONF_BATTERY_SOC_ENTITY,
    "sensor.foxessmodbus_battery_charge": CONF_BATTERY_CHARGE_ENTITY,
    "sensor.foxessmodbus_battery_discharge": CONF_BATTERY_DISCHARGE_ENTITY,
    "sensor.foxessmodbus_grid_consumption": CONF_FOXESS_GRID_IMPORT_ENTITY,
    "sensor.foxessmodbus_feed_in": CONF_FOXESS_GRID_EXPORT_ENTITY,
    "sensor.foxessmodbus_load_power": CONF_FOXESS_LOAD_POWER_ENTITY,
    "sensor.pv_power_foxessmodbus": CONF_FOXESS_PV_POWER_ENTITY,
    "select.foxessmodbus_work_mode": CONF_FOXESS_WORK_MODE_ENTITY,
}

# v0.74.0 — the bundled dashboard now ships its own cards (registered
# automatically by frontend.py, no HACS install needed), so this list is
# empty. Kept as a list (not deleted) since async_check_dashboard_cards below
# is still useful infrastructure if a future card is ever added that isn't
# self-hosted.
REQUIRED_CARDS: list[tuple[str, str, str]] = []


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


def _load_entity_map() -> dict[str, str]:
    """Bundled map of YAML entity id → translation key (blocking — executor)."""
    try:
        with open(_ENTITY_MAP_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except (OSError, ValueError) as err:
        _LOGGER.warning("Could not read the dashboard entity map: %s", err)
        return {}


def _build_substitutions(
    hass: HomeAssistant, entity_map: dict[str, str], url_path: str,
) -> tuple[dict[str, str], list[str]]:
    """Return (yaml id → this install's id, ids that could not be resolved).

    Our own entities are matched on translation key, which survives the device
    rename and the language the install was first set up in. FoxESS entities
    are taken from what the user picked in the config flow. An id that resolves
    to itself is dropped — nothing to rewrite.
    """
    registry = er.async_get(hass)
    by_key: dict[tuple[str, str], str] = {}
    for entry in registry.entities.values():
        if entry.platform != DOMAIN or not entry.translation_key:
            continue
        by_key[(entry.domain, entry.translation_key)] = entry.entity_id

    subs: dict[str, str] = {}
    unresolved: list[str] = []
    for yaml_id, translation_key in entity_map.items():
        domain = yaml_id.split(".", 1)[0]
        live = by_key.get((domain, translation_key))
        if live is None:
            unresolved.append(yaml_id)
        elif live != yaml_id:
            subs[yaml_id] = live

    # The dashboard's own navigation targets, pointed at wherever this copy is
    # being written — which is not always this integration's own dashboard.
    if _YAML_DASHBOARD_PATH != f"/{url_path}/":
        subs[_YAML_DASHBOARD_PATH] = f"/{url_path}/"

    # FoxESS and other third-party entities: whatever the config flow stored.
    for cfg_entry in hass.config_entries.async_entries(DOMAIN):
        data = {**cfg_entry.data, **cfg_entry.options}
        for yaml_id, conf_key in _FOREIGN_ENTITY_KEYS.items():
            live = data.get(conf_key)
            if isinstance(live, str) and live and live != yaml_id:
                subs[yaml_id] = live
        break

    return subs, unresolved


def _apply_substitutions(node: Any, subs: dict[str, str]) -> Any:
    """Rewrite every entity id in a loaded dashboard, in place where possible."""
    if isinstance(node, dict):
        return {k: _apply_substitutions(v, subs) for k, v in node.items()}
    if isinstance(node, list):
        return [_apply_substitutions(v, subs) for v in node]
    if isinstance(node, str):
        if node in subs:
            return subs[node]
        # Templates and markdown embed ids inside longer strings.
        out = node
        for old, new in subs.items():
            if old in out:
                out = out.replace(old, new)
        return out
    return node


def _notify_target_rows(hass: HomeAssistant) -> list[dict[str, str]]:
    """One dashboard row per mobile app this install can notify.

    v1.20.2 — the bundled YAML carries two placeholder rows named after the
    author's phone and tablet. Each install has its own devices, so the rows
    are rebuilt here from the switches that actually exist.
    """
    registry = er.async_get(hass)
    rows: list[dict[str, str]] = []
    for entry in registry.entities.values():
        if entry.platform != DOMAIN or entry.domain != "switch":
            continue
        if _NOTIFY_TARGET_UNIQUE_ID_MARK not in (entry.unique_id or ""):
            continue
        # v1.20.2 — only devices that are actually there. A companion app that
        # was removed, or reinstalled under a new service name, leaves its
        # registry entry behind; switch.py recreates switches only for notify
        # services that exist now. Writing the leftovers onto the dashboard
        # would make the integration's own missing-entity check complain about
        # rows the integration had just added.
        if entry.disabled_by is not None or hass.states.get(entry.entity_id) is None:
            continue
        label = (entry.name or entry.original_name or "").strip()
        # The entity is named "Notifikation: <device>"; the card has its own
        # heading, so show the device alone.
        if ":" in label:
            label = label.split(":", 1)[1].strip()
        rows.append({"entity": entry.entity_id, "name": f"📱 {label}" if label else entry.entity_id})
    rows.sort(key=lambda r: r["entity"])
    return rows


def _apply_notify_rows(node: Any, rows: list[dict[str, str]]) -> Any:
    """Swap the placeholder notification rows for this install's own.

    With no mobile app configured the rows disappear, and the divider that
    introduces them goes with them rather than trailing the card.
    """
    if isinstance(node, dict):
        return {k: _apply_notify_rows(v, rows) for k, v in node.items()}
    if not isinstance(node, list):
        return node

    out: list[Any] = []
    replaced = False
    for item in node:
        is_placeholder = (
            isinstance(item, dict)
            and item.get("entity") in _NOTIFY_PLACEHOLDER_ENTITIES
        )
        if not is_placeholder:
            out.append(_apply_notify_rows(item, rows))
            continue
        if replaced:
            continue                      # further placeholders collapse into the first
        replaced = True
        if rows:
            out.extend(dict(r) for r in rows)
        elif out and out[-1] == {"type": "divider"}:
            out.pop()                     # nothing to introduce
    return out


def _referenced_entities(node: Any, found: set[str] | None = None) -> set[str]:
    """Every entity id a dashboard config refers to, for the existence check."""
    found = set() if found is None else found
    if isinstance(node, dict):
        for value in node.values():
            _referenced_entities(value, found)
    elif isinstance(node, list):
        for value in node:
            _referenced_entities(value, found)
    elif isinstance(node, str):
        found.update(_ENTITY_ID_RE.findall(node))
    return found


async def async_create_dashboard(
    hass: HomeAssistant, *, force: bool = False, url_path: str | None = None,
) -> str | None:
    """Create (or, with force, overwrite) the Solar AI storage dashboard.

    v1.21.0 — `url_path` writes the resolved dashboard into an EXISTING
    dashboard instead of creating this integration's own. It is for the user
    who imported the YAML by hand before auto-creation existed: their
    dashboard keeps its URL, its sidebar entry and its place in the sidebar,
    and gains the entity ids, navigation targets and notification rows of this
    install. The target must already exist — this never creates a dashboard at
    an arbitrary path — and because writing to it replaces whatever is there,
    `force` must be set as well.

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

        target_path = url_path or DASHBOARD_URL_PATH
        writing_to_existing = url_path is not None and url_path != DASHBOARD_URL_PATH
        if writing_to_existing:
            if target_path not in dashboards_map:
                _LOGGER.warning(
                    "Solar AI dashboard: no dashboard at '%s' — refusing to create "
                    "one there. Check Settings → Dashboards for the exact url_path.",
                    target_path,
                )
                return None
            if not force:
                _LOGGER.warning(
                    "Solar AI dashboard: writing to '%s' replaces its current "
                    "contents, so it needs force: true.", target_path,
                )
                return None
        elif target_path in dashboards_map and not force:
            return target_path  # leave the existing one alone

        config = await hass.async_add_executor_job(_load_dashboard_yaml, hass.config.language)
        if not config:
            return None

        # v1.20.0 — rewrite the bundled ids to this install's before writing.
        # v1.20.2 — the navigation paths and the notification rows are resolved
        # whether or not the entity map loads. They do not depend on it, and
        # gating them behind it meant a missing or malformed map silently
        # reinstated both bugs from issue #4.
        entity_map = await hass.async_add_executor_job(_load_entity_map)
        subs, unresolved = _build_substitutions(hass, entity_map, target_path)
        if subs:
            config = _apply_substitutions(config, subs)
            _LOGGER.info(
                "Solar AI dashboard: resolved %d id(s)/path(s) to this install",
                len(subs),
            )
        notify_rows = _notify_target_rows(hass)
        config = _apply_notify_rows(config, notify_rows)
        _LOGGER.info(
            "Solar AI dashboard: %d mobile notification row(s)", len(notify_rows),
        )
        if unresolved:
            _LOGGER.debug(
                "Solar AI dashboard: %d id(s) had no match in the registry: %s",
                len(unresolved), ", ".join(sorted(unresolved)[:10]),
            )

        # Persist (or fetch) the dashboard metadata via the storage collection.
        collection = DashboardsCollection(hass)
        await collection.async_load()
        items = {it["url_path"]: it for it in collection.async_items()}
        item = items.get(target_path)
        newly_created = item is None and not writing_to_existing
        if newly_created:
            item = await collection.async_create_item({
                "url_path": target_path,
                "title": DASHBOARD_TITLE,
                "icon": DASHBOARD_ICON,
                "show_in_sidebar": True,
                "require_admin": False,
            })

        # Live config store + sidebar panel, so it shows without a restart.
        store = dashboards_map.get(target_path)
        if store is None:
            store = LovelaceStorage(hass, item)
            dashboards_map[target_path] = store
            try:
                _register_panel(hass, target_path, MODE_STORAGE, item, False)
            except Exception:  # noqa: BLE001
                _LOGGER.debug(
                    "Live panel registration failed; dashboard will appear after a restart",
                    exc_info=True,
                )

        await store.async_save(config)
        _LOGGER.info("Solar AI dashboard %s at /%s",
                     "created" if newly_created else "updated", target_path)

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

        return target_path
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


async def async_check_dashboard_entities(hass: HomeAssistant) -> None:
    """Raise/clear a Repairs issue listing dashboard entities that do not exist.

    v1.20.0 — the resolver rewrites what it can match; anything left over would
    otherwise render as an empty card with no explanation. Entities the user
    has simply not configured (no EV charger, no Strømligning) show up here
    too, which is why this is a warning rather than an error.
    """
    try:
        data = hass.data.get("lovelace")
        dashboards_map = getattr(data, "dashboards", None) if data is not None else None
        store = (dashboards_map or {}).get(DASHBOARD_URL_PATH)
        if store is None:
            return
        config = await store.async_load(False)
        if not config:
            return
        missing = sorted(
            eid for eid in _referenced_entities(config)
            if hass.states.get(eid) is None
        )
        if missing:
            shown = ", ".join(missing[:12]) + (f" (+{len(missing) - 12} more)" if len(missing) > 12 else "")
            ir.async_create_issue(
                hass, DOMAIN, _MISSING_ENTITIES_ISSUE,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=_MISSING_ENTITIES_ISSUE,
                translation_placeholders={"count": str(len(missing)), "entities": shown},
                learn_more_url="https://github.com/Planckus/solar_ai#dashboard-entity-ids",
            )
        else:
            ir.async_delete_issue(hass, DOMAIN, _MISSING_ENTITIES_ISSUE)
    except Exception:  # noqa: BLE001
        _LOGGER.debug("Dashboard entity check skipped (error)", exc_info=True)


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
