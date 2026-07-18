/*
 * Solar AI — first-party Lovelace cards.
 *
 * Plain web components, zero framework/CDN dependency (not even HA's bundled
 * lit — this file is entirely self-contained, matching the integration's own
 * local-polling, no-external-calls design). Ships inside the integration's
 * own `www/` folder and is auto-registered by `frontend.py`; no manual
 * "Settings > Dashboards > Resources" step, unlike the third-party cards it
 * replaces (mushroom, apexcharts-card, power-flow-card-plus, card-mod).
 *
 * Four element types:
 *   solar-ai-status-card       energy flow + mode + price/savings hero
 *   solar-ai-mode-picker-card  EV charge-mode button row
 *   solar-ai-chart-card        declarative line/bar chart (hand-rolled SVG)
 *   solar-ai-grid-card         24-cell hour grid: toggle / heatmap / timeline
 */
(function () {
  'use strict';

  console.info('%c SOLAR AI CARDS %c v1.10.0 loading… ', 'color:white;background:#BA7517;font-weight:bold;', 'color:#BA7517;background:white;font-weight:bold;');

  // ---------------------------------------------------------------- helpers

  function fireEvent(el, type, detail) {
    el.dispatchEvent(new CustomEvent(type, {
      detail, bubbles: true, composed: true,
    }));
  }

  function moreInfo(el, entityId) {
    if (!entityId) return;
    fireEvent(el, 'hass-more-info', { entityId });
  }

  // Setting-explainer popup (v0.75.14, fixed v0.75.16). A fresh <ha-dialog>
  // is created and appended to the document body on every open, then removed
  // on close — ha-dialog (HA's bundled mwc-dialog wrapper) is already a
  // registered custom element once the HA frontend has loaded, so this needs
  // no import or extra registration step, matching the file's zero-dependency
  // design. v0.75.14 originally reused one dialog instance across opens; that
  // left it unable to reopen after the first close (reported live: only the
  // first "?" worked, every subsequent one needed a full page reload).
  // Create-fresh/remove-on-close sidesteps whatever internal open/close state
  // the shared instance was getting stuck in.
  function showHelpDialog(hass, title, text) {
    const closeLabel = hass && hass.language && hass.language.slice(0, 2) === 'da' ? 'Luk' : 'Close';
    const dlg = document.createElement('ha-dialog');
    dlg.heading = title;
    dlg.innerHTML = `
      <div style="min-width:240px;max-width:420px;font-size:14px;line-height:1.6;color:var(--primary-text-color);padding:4px 2px 8px;white-space:pre-line;">${escapeHtml(text)}</div>
      <mwc-button slot="primaryAction" data-sa-help-close>${escapeHtml(closeLabel)}</mwc-button>
    `;
    const remove = () => dlg.remove();
    dlg.addEventListener('closed', remove);
    dlg.addEventListener('click', (e) => {
      if (e.target && e.target.closest && e.target.closest('[data-sa-help-close]')) {
        if (typeof dlg.close === 'function') dlg.close();
        else dlg.open = false;
      }
    });
    document.body.appendChild(dlg);
    dlg.open = true;
  }

  function navigate(path) {
    if (!path) return;
    history.pushState(null, '', path);
    fireEvent(window, 'location-changed', { replace: false });
  }

  function callService(hass, domain, service, data) {
    hass.callService(domain, service, data || {});
  }

  function state(hass, entityId) {
    const st = hass && entityId ? hass.states[entityId] : undefined;
    return st ? st.state : undefined;
  }

  function num(hass, entityId, fallback) {
    const s = state(hass, entityId);
    const n = parseFloat(s);
    return Number.isFinite(n) ? n : (fallback === undefined ? 0 : fallback);
  }

  function attr(hass, entityId, key, fallback) {
    const st = hass && entityId ? hass.states[entityId] : undefined;
    if (!st || !st.attributes || !(key in st.attributes)) return fallback;
    return st.attributes[key];
  }

  function fmt(n, decimals) {
    if (!Number.isFinite(n)) return '–';
    return n.toFixed(decimals === undefined ? 1 : decimals);
  }

  function sig(hass, entityIds) {
    let s = '';
    for (const id of entityIds) {
      if (!id) continue;
      const st = hass.states[id];
      s += id + ':' + (st ? st.state + JSON.stringify(st.attributes) : '_') + '|';
    }
    return s;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
  }

  // ---------------------------------------------------------- localization
  //
  // The dashboard YAML is language-forked (dashboard_en.yaml / dashboard_da.yaml,
  // picked at load time by hass.config.language), but this JS bundle is shared
  // by both — so UI chrome strings the elements draw themselves (not passed in
  // via config) need their own small translation table, keyed off hass.language,
  // to avoid silently forcing English inside an otherwise-Danish dashboard.
  const L10N = {
    en: {
      house_load: 'House load', solar: 'Solar', battery: 'Battery', grid: 'Grid', ev: 'EV',
      selling: 'Selling', buying: 'Buying', buy_now: 'Buy now', sell_now: 'Sell now',
      saved_today: 'Saved today', solar_today: 'Solar today', tomorrow: 'Tomorrow',
      floor: 'floor', starting_in: (s) => `Starting in ${s}s`,
      ev_stops_in: (s) => `EV stops in ${s}s — low sun`, charge_mode: 'Charge mode',
    },
    da: {
      house_load: 'Husforbrug', solar: 'Sol', battery: 'Batteri', grid: 'Elnet', ev: 'EV',
      selling: 'Sælger', buying: 'Køber', buy_now: 'Køb nu', sell_now: 'Salg nu',
      saved_today: 'Sparet i dag', solar_today: 'Sol i dag', tomorrow: 'I morgen',
      floor: 'gulv', starting_in: (s) => `Starter om ${s}s`,
      ev_stops_in: (s) => `EV stopper om ${s}s — lav sol`, charge_mode: 'Opladningstilstand',
    },
  };

  function t(hass, key, ...args) {
    const lang = (hass && hass.language && L10N[hass.language.slice(0, 2)]) ? hass.language.slice(0, 2) : 'en';
    const table = L10N[lang] || L10N.en;
    const entry = key in table ? table[key] : (L10N.en[key] || key);
    return typeof entry === 'function' ? entry(...args) : entry;
  }

  const BASE_CSS = `
    :host { display: block; width: 100%; box-sizing: border-box; }
    ha-card { width: 100%; box-sizing: border-box; padding: 16px; }
    .sa-inner { max-width: 900px; margin: 0 auto; }
    .row { display: flex; align-items: center; justify-content: space-between; }
    .muted { color: var(--secondary-text-color); }
    .tile {
      background: var(--secondary-background-color, rgba(127,127,127,0.08));
      border-radius: var(--ha-card-border-radius, 12px);
      padding: 12px 8px;
      text-align: center;
    }
    /* Labels on top of .tile's own background tint compound with a dimmed
       text color and become hard to read — use full-strength text there,
       distinguished from the value below it by size/weight only, not color. */
    .tile-label { color: var(--primary-text-color); font-weight: 400; }
    .grid4 { display: grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: 8px; }
    .grid3 { display: grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: 10px; }
    .badge {
      font-size: 15px; padding: 4px 12px; border-radius: 12px;
      background: var(--success-color); color: white;
    }
    button.sa-btn {
      background: none; cursor: pointer; padding: 10px 4px; font-size: 14px;
      border: 1px solid var(--divider-color); border-radius: var(--ha-card-border-radius, 12px);
      color: var(--primary-text-color); display: flex; flex-direction: column;
      align-items: center; gap: 4px;
    }
    button.sa-btn.active { border-color: var(--primary-color); color: var(--primary-color); }
    button.sa-btn ha-icon { --mdc-icon-size: 20px; }
    ha-icon.lg { --mdc-icon-size: 24px; }
    button.sa-help-btn {
      all: unset; cursor: pointer; box-sizing: border-box;
      width: 16px; height: 16px; min-width: 16px; border-radius: 50%;
      border: 1px solid var(--secondary-text-color);
      color: var(--secondary-text-color); font-size: 11px; font-weight: 600;
      line-height: 14px; text-align: center; display: inline-flex;
      align-items: center; justify-content: center; opacity: 0.6; flex-shrink: 0;
    }
    button.sa-help-btn:hover { opacity: 1; border-color: var(--primary-color); color: var(--primary-color); }
  `;

  // -------------------------------------------------------------- base card

  class SolarAiBaseCard extends HTMLElement {
    constructor() {
      super();
      this._root = this.attachShadow({ mode: 'open' });
      this._lastSig = null;
    }

    setConfig(config) {
      if (!config) throw new Error('Invalid configuration');
      this._config = config;
    }

    set hass(hass) {
      this._hass = hass;
      try {
        const s = this._signature(hass);
        if (s === this._lastSig) return;
        this._lastSig = s;
        this._render();
      } catch (err) {
        console.error('Solar AI card render error (' + this.tagName + '):', err);
        this._root.innerHTML = `<ha-card style="padding:16px;color:var(--error-color);">
          <div style="font-weight:500;margin-bottom:4px;">${escapeHtml(this.tagName.toLowerCase())} render error</div>
          <div style="font-size:15px;font-family:monospace;white-space:pre-wrap;">${escapeHtml(err && err.stack ? err.stack : String(err))}</div>
        </ha-card>`;
      }
    }

    _watchedEntities() { return []; }
    _signature(hass) { return sig(hass, this._watchedEntities()); }
    getCardSize() { return 3; }
  }

  // --------------------------------------------------------- status (hero)

  class SolarAiStatusCard extends SolarAiBaseCard {
    _watchedEntities() {
      const c = this._config;
      return [
        c.mode_entity, c.mode_reason_entity, c.enabled_entity,
        c.house_load_entity, c.solar_entity,
        c.battery_charge_entity, c.battery_discharge_entity,
        c.battery_soc_entity, c.battery_floor_entity,
        c.grid_import_entity, c.grid_export_entity,
        c.ev_power_entity, c.ev_status_entity,
        c.buy_price_entity, c.sell_price_entity, c.savings_today_entity,
        c.solar_forecast_entity, c.solar_actual_today_entity,
      ];
    }

    getCardSize() { return 7; }

    _render() {
      const c = this._config;
      const hass = this._hass;
      if (!hass) return;

      const mode = state(hass, c.mode_entity) || '–';
      const modeReason = state(hass, c.mode_reason_entity) || '';
      const enabled = state(hass, c.enabled_entity) === 'on';

      const evPower = num(hass, c.ev_power_entity);
      const houseLoadRaw = num(hass, c.house_load_entity);
      const houseLoad = Math.max(houseLoadRaw - evPower, 0);

      const solar = num(hass, c.solar_entity);
      const batC = num(hass, c.battery_charge_entity);
      const batD = num(hass, c.battery_discharge_entity);
      const soc = num(hass, c.battery_soc_entity);
      const floor = num(hass, c.battery_floor_entity);
      const gridImp = num(hass, c.grid_import_entity);
      const gridExp = num(hass, c.grid_export_entity);

      const livePhases = attr(hass, c.ev_power_entity, 'live_phases', null);
      const targetPhases = attr(hass, c.ev_power_entity, 'target_phases', null);
      const phase = livePhases || targetPhases;

      const armingS = attr(hass, c.ev_status_entity, 'arming_seconds_left', 0) || 0;
      const coolingS = attr(hass, c.ev_status_entity, 'cooling_seconds_left', 0) || 0;
      const evReason = attr(hass, c.ev_status_entity, 'reason', '');

      const buyPrice = num(hass, c.buy_price_entity);
      const sellPrice = num(hass, c.sell_price_entity);
      const savedToday = num(hass, c.savings_today_entity);

      const todayRest = attr(hass, c.solar_forecast_entity, 'today_remaining_kwh', null);
      const tomorrow = attr(hass, c.solar_forecast_entity, 'tomorrow_kwh', null);
      const actualToday = num(hass, c.solar_actual_today_entity);

      let banner = '';
      if (armingS > 0) {
        banner = `<div class="row" style="background:var(--warning-color);opacity:.85;border-radius:12px;padding:6px 12px;margin-bottom:12px;">
          <span style="font-size:15px;color:#000;">${t(hass, 'starting_in', Math.round(armingS))}</span></div>`;
      } else if (coolingS > 0) {
        banner = `<div class="row" style="background:var(--warning-color);opacity:.85;border-radius:12px;padding:6px 12px;margin-bottom:12px;">
          <span style="font-size:15px;color:#000;">${t(hass, 'ev_stops_in', Math.round(coolingS))}</span></div>`;
      }

      const gridColor = gridExp > gridImp ? 'var(--success-color)' : (gridImp > 0.05 ? 'var(--error-color)' : 'var(--secondary-text-color)');
      const gridLabel = gridExp > gridImp ? t(hass, 'selling') : (gridImp > 0.05 ? t(hass, 'buying') : '');
      const gridVal = gridExp > gridImp ? gridExp : gridImp;

      let forecastRow = '';
      if (todayRest !== null || tomorrow !== null) {
        forecastRow = `<div class="row tile" style="margin-bottom:12px;">
          <div>
            <div class="tile-label" style="font-size:15px;">${t(hass, 'solar_today')}</div>
            <div style="font-size:17px;font-weight:500;">${fmt(actualToday, 1)} + ${fmt(todayRest, 1)} = ${fmt(actualToday + (todayRest || 0), 1)} kWh</div>
          </div>
          <div style="text-align:right;">
            <div class="tile-label" style="font-size:15px;">${t(hass, 'tomorrow')}</div>
            <div style="font-size:17px;font-weight:500;">${fmt(tomorrow, 1)} kWh</div>
          </div>
        </div>`;
      }

      this._root.innerHTML = `
        <style>${BASE_CSS}</style>
        <ha-card>
        <div class="sa-inner">
          <div class="row" style="margin-bottom:12px;" data-action="mode-info">
            <div class="row" style="gap:8px;">
              <ha-icon icon="mdi:solar-power-variant" class="lg" style="color:var(--warning-color);"></ha-icon>
              <span style="font-size:19px;font-weight:500;">Solar AI</span>
            </div>
            <span class="badge" data-action="toggle-enabled" style="cursor:pointer;background:${enabled ? 'var(--success-color)' : 'var(--disabled-text-color)'};">${escapeHtml(mode)}</span>
          </div>

          ${banner}

          <div style="text-align:center;margin-bottom:12px;">
            <div class="tile-label" style="font-size:16px;">${t(hass, 'house_load')}</div>
            <div style="font-size:32px;font-weight:500;">${fmt(houseLoad, 1)} kW</div>
          </div>

          <div class="grid4" style="margin-bottom:12px;">
            <div class="tile" data-action="more-info" data-entity="${c.solar_entity || ''}">
              <ha-icon icon="mdi:weather-sunny" style="color:var(--warning-color);"></ha-icon>
              <div class="tile-label" style="font-size:14px;margin-top:4px;">${t(hass, 'solar')}</div>
              <div style="font-size:19px;font-weight:500;">${fmt(solar, 1)} kW</div>
            </div>
            <div class="tile" data-action="more-info" data-entity="${c.battery_soc_entity || ''}">
              <ha-icon icon="mdi:battery-high" style="color:var(--primary-color);"></ha-icon>
              <div class="tile-label" style="font-size:14px;margin-top:4px;">${t(hass, 'battery')}</div>
              <div style="font-size:19px;font-weight:500;">${fmt(batC > 0.05 ? batC : batD, 1)} kW</div>
              <div style="position:relative;height:5px;background:var(--divider-color);border-radius:3px;margin-top:6px;">
                <div style="position:absolute;left:0;top:0;height:100%;width:${Math.min(100, Math.max(0, soc))}%;background:var(--primary-color);border-radius:3px;"></div>
                <div style="position:absolute;left:${Math.min(100, Math.max(0, floor))}%;top:-2px;width:1.5px;height:9px;background:var(--secondary-text-color);"></div>
              </div>
              <div class="tile-label" style="font-size:13px;margin-top:3px;">${Math.round(soc)}% &middot; ${t(hass, 'floor')} ${Math.round(floor)}%</div>
            </div>
            <div class="tile" data-action="more-info" data-entity="${c.grid_import_entity || ''}">
              <ha-icon icon="mdi:transmission-tower" style="color:var(--info-color, #039be5);"></ha-icon>
              <div class="tile-label" style="font-size:14px;margin-top:4px;">${t(hass, 'grid')}</div>
              <div style="font-size:19px;font-weight:500;color:${gridColor};">${fmt(gridVal, 1)} kW</div>
              <div style="font-size:13px;margin-top:3px;color:${gridColor};">${gridLabel}</div>
            </div>
            <div class="tile" data-action="more-info" data-entity="${c.ev_power_entity || ''}">
              <ha-icon icon="mdi:car-electric" style="color:var(--error-color);"></ha-icon>
              <div class="tile-label" style="font-size:14px;margin-top:4px;">${t(hass, 'ev')}</div>
              <div style="font-size:19px;font-weight:500;">${fmt(evPower, 1)} kW</div>
              ${phase ? `<span style="font-size:13px;border:1px solid var(--divider-color);border-radius:8px;padding:0 5px;margin-top:3px;display:inline-block;">${phase}&phi;</span>` : ''}
            </div>
          </div>

          <div class="grid3" style="margin-bottom:12px;">
            <div class="tile" data-action="navigate" data-path="${c.prices_navigate_path || ''}">
              <div class="tile-label" style="font-size:15px;">${t(hass, 'buy_now')}</div>
              <div style="font-size:22px;font-weight:500;">${fmt(buyPrice, 2)} kr</div>
            </div>
            <div class="tile" data-action="navigate" data-path="${c.prices_navigate_path || ''}">
              <div class="tile-label" style="font-size:15px;">${t(hass, 'sell_now')}</div>
              <div style="font-size:22px;font-weight:500;">${fmt(sellPrice, 2)} kr</div>
            </div>
            <div class="tile" data-action="more-info" data-entity="${c.savings_today_entity || ''}">
              <div class="tile-label" style="font-size:15px;">${t(hass, 'saved_today')}</div>
              <div style="font-size:22px;font-weight:500;color:var(--success-color);">${fmt(savedToday, 0)} kr</div>
            </div>
          </div>

          ${forecastRow}

          <div style="border-top:1px solid var(--divider-color);padding-top:8px;">
            ${modeReason ? `<div class="muted" style="font-size:15px;">${escapeHtml(modeReason)}</div>` : ''}
            ${evReason ? `<div class="muted" style="font-size:15px;">EV: ${escapeHtml(evReason)}</div>` : ''}
          </div>
        </div>
        </ha-card>
      `;

      this._bindClicks(c);
    }

    _bindClicks(c) {
      if (this._bound) return;
      this._bound = true;
      this._root.addEventListener('click', (ev) => {
        const target = ev.composedPath().find((n) => n && n.dataset && n.dataset.action);
        if (!target) return;
        const action = target.dataset.action;
        if (action === 'toggle-enabled' && c.enabled_entity) {
          const domain = c.enabled_entity.split('.')[0];
          callService(this._hass, domain, 'toggle', { entity_id: c.enabled_entity });
        } else if (action === 'mode-info' && c.mode_entity) {
          moreInfo(this, c.mode_entity);
        } else if (action === 'more-info' && target.dataset.entity) {
          moreInfo(this, target.dataset.entity);
        } else if (action === 'navigate' && target.dataset.path) {
          navigate(target.dataset.path);
        }
      });
    }
  }
  try {
    customElements.define('solar-ai-status-card', SolarAiStatusCard);
    console.info('Solar AI: registered <solar-ai-status-card>');
  } catch (err) {
    console.error('Solar AI: failed to register <solar-ai-status-card>', err);
  }

  // ------------------------------------------------------------ mode picker

  const MODE_ICONS = {
    locked: 'mdi:lock', pv: 'mdi:weather-sunny', pv_battery: 'mdi:weather-sunny-alert',
    full: 'mdi:rocket-launch', scheduled: 'mdi:calendar-clock',
  };
  const MODE_ICON_COLORS = {
    locked: 'var(--secondary-text-color)', pv: 'var(--warning-color)',
    pv_battery: 'var(--primary-color)', full: 'var(--error-color)',
    scheduled: '#9c27b0',
  };
  const MODE_LABELS = {
    en: { locked: 'Locked', pv: 'Solar', pv_battery: 'Solar+Bat', full: 'Fast', scheduled: 'Scheduled' },
    da: { locked: 'Fra', pv: 'Sol', pv_battery: 'Sol+Bat', full: 'Hurtig', scheduled: 'Planlagt' },
  };

  class SolarAiModePickerCard extends SolarAiBaseCard {
    _watchedEntities() { return [this._config.entity]; }
    getCardSize() { return 2; }

    _render() {
      const c = this._config;
      const hass = this._hass;
      if (!hass || !c.entity) return;
      const st = hass.states[c.entity];
      const options = (st && st.attributes && st.attributes.options) || [];
      const current = st ? st.state : null;
      const lang = (hass.language || 'en').slice(0, 2);
      const labels = MODE_LABELS[lang] || MODE_LABELS.en;

      const buttons = options.map((opt) => {
        const icon = MODE_ICONS[opt] || 'mdi:radiobox-blank';
        const iconColor = MODE_ICON_COLORS[opt] || 'var(--primary-text-color)';
        const label = labels[opt] || (opt.charAt(0).toUpperCase() + opt.slice(1));
        const active = opt === current;
        return `<button class="sa-btn${active ? ' active' : ''}" data-option="${escapeHtml(opt)}">
          <ha-icon icon="${icon}" style="color:${iconColor};"></ha-icon><span>${escapeHtml(label)}</span></button>`;
      }).join('');

      this._root.innerHTML = `
        <style>${BASE_CSS}
          .picker { display: grid; grid-template-columns: repeat(${Math.max(options.length, 1)}, minmax(0,1fr)); gap: 6px; }
        </style>
        <ha-card>
        <div class="sa-inner">
          ${c.title ? `<div style="font-size:16px;color:var(--secondary-text-color);margin-bottom:8px;">${escapeHtml(c.title)}</div>` : ''}
          <div class="picker">${buttons}</div>
        </div>
        </ha-card>
      `;

      this._root.querySelectorAll('button[data-option]').forEach((btn) => {
        btn.addEventListener('click', () => {
          callService(hass, 'select', 'select_option', {
            entity_id: c.entity, option: btn.dataset.option,
          });
        });
      });
    }
  }
  try {
    customElements.define('solar-ai-mode-picker-card', SolarAiModePickerCard);
    console.info('Solar AI: registered <solar-ai-mode-picker-card>');
  } catch (err) {
    console.error('Solar AI: failed to register <solar-ai-mode-picker-card>', err);
  }

  // -------------------------------------------------------------- nav card

  const NAMED_COLORS = {
    red: '#e51c23', pink: '#e91e63', purple: '#9c27b0', 'deep-purple': '#673ab7',
    blue: '#2196f3', 'light-blue': '#03a9f4', cyan: '#00bcd4', teal: '#009688',
    green: 'var(--success-color)', amber: 'var(--warning-color)', orange: '#ff9800',
    'blue-grey': '#607d8b', grey: 'var(--secondary-text-color)', brown: '#795548',
  };

  class SolarAiNavCard extends SolarAiBaseCard {
    _watchedEntities() { return []; }
    getCardSize() { return 1; }

    _render() {
      const c = this._config;
      const items = c.items || [];
      const buttons = items.map((item) => {
        const color = NAMED_COLORS[item.icon_color] || item.icon_color || 'var(--primary-text-color)';
        return `
        <button class="sa-btn" data-path="${escapeHtml(item.path || '')}">
          <ha-icon icon="${escapeHtml(item.icon || 'mdi:link')}" style="color:${color};"></ha-icon>
          <span>${escapeHtml(item.label || '')}</span>
        </button>`;
      }).join('');

      this._root.innerHTML = `
        <style>${BASE_CSS}
          .nav { display: grid; grid-template-columns: repeat(${Math.max(items.length, 1)}, minmax(0,1fr)); gap: 6px; }
        </style>
        <ha-card>
        <div class="sa-inner">
          <div class="nav">${buttons}</div>
        </div>
        </ha-card>
      `;

      this._root.querySelectorAll('button[data-path]').forEach((btn) => {
        btn.addEventListener('click', () => navigate(btn.dataset.path));
      });
    }
  }
  try {
    customElements.define('solar-ai-nav-card', SolarAiNavCard);
    console.info('Solar AI: registered <solar-ai-nav-card>');
  } catch (err) {
    console.error('Solar AI: failed to register <solar-ai-nav-card>', err);
  }

  // ---------------------------------------------------------- chart engine

  const TIER_COLORS = ['var(--success-color)', 'var(--warning-color)', 'var(--warning-color)', 'var(--error-color)'];
  const TIER_TEXT_COLORS = ['white', 'black', 'black', 'white'];

  function seriesPoints(hass, s) {
    const raw = attr(hass, s.entity, s.path || 'slots', []) || [];
    return raw.map((item) => {
      let x;
      if (s.x === 'h') {
        x = (item.h || 0) + (item.m || 0) / 60;
      } else if (item[s.x] && typeof item[s.x] === 'string' && item[s.x].length > 10 && item[s.x].indexOf('T') > -1) {
        x = new Date(item[s.x]).getTime();
      } else {
        x = item[s.x];
      }
      return { x, y: item[s.y], raw: item };
    }).filter((p) => p.y !== null && p.y !== undefined && Number.isFinite(p.y));
  }

  function renderChartSvg(cfg, allSeries, width, height) {
    const padL = 40, padR = 8, padT = 8, padB = 22;
    const plotW = Math.max(10, width - padL - padR);
    const plotH = Math.max(10, height - padT - padB);

    const isCategory = cfg.x_type === 'category';
    let allX = [];
    allSeries.forEach((s) => s.points.forEach((p) => allX.push(p.x)));
    let xMin, xMax, catList = [];
    if (cfg.x_type === 'hour_offset') {
      xMin = 0; xMax = 24;
    } else if (isCategory) {
      catList = Array.from(new Set(allX)).sort();
      xMin = 0; xMax = Math.max(1, catList.length - 1);
    } else {
      xMin = Math.min(...allX); xMax = Math.max(...allX);
      if (!Number.isFinite(xMin) || !Number.isFinite(xMax) || xMin === xMax) { xMin = 0; xMax = 1; }
    }

    let yMin = 0, yMax = 1;
    const allY = [];
    allSeries.forEach((s) => s.points.forEach((p) => allY.push(p.y)));
    if (allY.length) {
      yMin = Math.min(0, ...allY);
      yMax = Math.max(...allY) * 1.15 || 1;
    }
    if (yMax === yMin) yMax = yMin + 1;

    function xPos(x) {
      const xi = isCategory ? catList.indexOf(x) : x;
      return padL + ((xi - xMin) / (xMax - xMin)) * plotW;
    }
    function yPos(y) {
      return padT + plotH - ((y - yMin) / (yMax - yMin)) * plotH;
    }

    let svg = '';
    const gridN = 4;
    for (let i = 0; i <= gridN; i++) {
      const yVal = yMin + (yMax - yMin) * (i / gridN);
      const yy = yPos(yVal);
      svg += `<line x1="${padL}" y1="${yy}" x2="${padL + plotW}" y2="${yy}" stroke="var(--divider-color)" stroke-width="0.5"/>`;
      svg += `<text x="${padL - 6}" y="${yy + 3}" text-anchor="end" font-size="12" fill="var(--secondary-text-color)">${yVal.toFixed(cfg.unit === 'kW' ? 1 : (Math.abs(yVal) < 10 ? 2 : 0))}</text>`;
    }

    const barSeries = allSeries.filter((s) => s.type === 'bar');
    const nBars = Math.max(1, barSeries.length);
    barSeries.forEach((s, si) => {
      const n = s.points.length || 1;
      const stepPx = plotW / (isCategory ? Math.max(catList.length, 1) : (cfg.x_type === 'hour_offset' ? 24 : n));
      const barW = Math.max(1, (stepPx * 0.7) / nBars);
      s.points.forEach((p) => {
        const cx = xPos(p.x);
        const bx = cx - (stepPx * 0.35) + si * barW;
        const by = yPos(Math.max(p.y, 0));
        const h2 = Math.abs(yPos(p.y) - yPos(0));
        const color = s.tierThresholds ? tierColor(p.y, s.tierThresholds, s.invert) : s.color;
        svg += `<rect x="${bx}" y="${Math.min(by, yPos(0))}" width="${barW}" height="${Math.max(1, h2)}" fill="${color}" rx="1.5">
          <title>${escapeHtml(s.name)}: ${fmt(p.y, 2)}</title></rect>`;
      });
    });

    allSeries.filter((s) => s.type === 'line').forEach((s) => {
      if (!s.points.length) return;
      const pts = s.points.slice().sort((a, b) => (isCategory ? catList.indexOf(a.x) - catList.indexOf(b.x) : a.x - b.x));
      let d = '';
      pts.forEach((p, i) => {
        const px = xPos(p.x), py = yPos(p.y);
        if (i === 0) { d += `M ${px},${py}`; return; }
        if (s.curve === 'step') {
          const prev = pts[i - 1];
          const prevX = xPos(prev.x);
          d += ` L ${prevX},${py} L ${px},${py}`;
        } else {
          d += ` L ${px},${py}`;
        }
      });
      svg += `<path d="${d}" fill="none" stroke="${s.color}" stroke-width="2"/>`;
      pts.forEach((p) => {
        svg += `<circle cx="${xPos(p.x)}" cy="${yPos(p.y)}" r="1.6" fill="${s.color}"><title>${escapeHtml(s.name)}: ${fmt(p.y, 2)}</title></circle>`;
      });
    });

    if (cfg.now_marker && cfg.x_type !== 'category') {
      const nowX = cfg.x_type === 'hour_offset'
        ? (new Date().getHours() + new Date().getMinutes() / 60)
        : Date.now();
      if (nowX >= xMin && nowX <= xMax) {
        const nx = xPos(nowX);
        svg += `<line x1="${nx}" y1="${padT}" x2="${nx}" y2="${padT + plotH}" stroke="var(--secondary-text-color)" stroke-width="1" stroke-dasharray="3,2"/>`;
      }
    }

    const xTickCount = Math.min(8, isCategory ? catList.length : 8);
    for (let i = 0; i <= xTickCount; i++) {
      const frac = i / xTickCount;
      const xv = isCategory ? catList[Math.round(frac * (catList.length - 1))] : xMin + (xMax - xMin) * frac;
      if (xv === undefined) continue;
      const xx = xPos(xv);
      let label;
      if (cfg.x_type === 'hour_offset') label = String(Math.round(xv)).padStart(2, '0');
      else if (isCategory) label = String(xv).slice(5);
      else label = new Date(xv).toLocaleTimeString([], { hour: '2-digit' });
      svg += `<text x="${xx}" y="${height - 6}" text-anchor="middle" font-size="12" fill="var(--secondary-text-color)">${label}</text>`;
    }

    return `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet" style="display:block;width:100%;height:${height}px;">${svg}</svg>`;
  }

  function tierIndex(v, thresholds, invert) {
    let tier = thresholds.length;
    for (let i = 0; i < thresholds.length; i++) {
      if (v < thresholds[i]) { tier = i; break; }
    }
    if (invert) tier = thresholds.length - tier;
    return Math.min(tier, TIER_COLORS.length - 1);
  }
  function tierColor(v, thresholds, invert) {
    return TIER_COLORS[tierIndex(v, thresholds, invert)];
  }
  function tierTextColor(v, thresholds, invert) {
    return TIER_TEXT_COLORS[tierIndex(v, thresholds, invert)];
  }

  class SolarAiChartCard extends SolarAiBaseCard {
    _watchedEntities() { return (this._config.series || []).map((s) => s.entity); }
    getCardSize() { return 4; }

    _render() {
      const c = this._config;
      const hass = this._hass;
      if (!hass) return;
      const height = c.height || 220;

      const allSeries = (c.series || []).map((s) => ({
        ...s,
        points: seriesPoints(hass, { ...s, x: c.x_type === 'category' ? s.x : (c.x_type === 'hour_offset' ? 'h' : s.x) }),
      }));

      const svg = renderChartSvg(c, allSeries, 640, height);
      const legend = allSeries.map((s) => `
        <span style="font-size:14px;color:var(--secondary-text-color);display:inline-flex;align-items:center;gap:4px;margin-right:14px;">
          <span style="width:8px;height:8px;border-radius:2px;background:${s.color};display:inline-block;"></span>${escapeHtml(s.name || s.entity)}
        </span>`).join('');

      this._root.innerHTML = `
        <style>${BASE_CSS}</style>
        <ha-card>
        <div class="sa-inner">
          ${c.title ? `<div style="font-size:17px;font-weight:500;margin-bottom:8px;display:flex;align-items:center;gap:8px;">${c.icon ? `<ha-icon icon="${escapeHtml(c.icon)}" style="color:${NAMED_COLORS[c.icon_color] || c.icon_color || 'var(--primary-text-color)'};"></ha-icon>` : ''}${escapeHtml(c.title)}</div>` : ''}
          <div style="position:relative;">${svg}</div>
          <div style="text-align:center;margin-top:6px;">${legend}</div>
        </div>
        </ha-card>
      `;
    }
  }
  try {
    customElements.define('solar-ai-chart-card', SolarAiChartCard);
    console.info('Solar AI: registered <solar-ai-chart-card>');
  } catch (err) {
    console.error('Solar AI: failed to register <solar-ai-chart-card>', err);
  }

  // ------------------------------------------------------------- hour grid

  class SolarAiGridCard extends SolarAiBaseCard {
    _watchedEntities() {
      const c = this._config;
      return [c.entity, c.charge_entity, c.export_entity].filter(Boolean);
    }
    getCardSize() { return 3; }

    _render() {
      const c = this._config;
      const hass = this._hass;
      if (!hass) return;
      const mode = c.mode || 'toggle';
      const nowHour = new Date().getHours();

      let cells = [];
      if (mode === 'toggle') {
        const blocked = (state(hass, c.entity) || '').split(',').map((s) => s.trim()).filter(Boolean);
        cells = Array.from({ length: 24 }, (_, h) => {
          const isBlocked = blocked.includes(String(h));
          return {
            label: String(h).padStart(2, '0'),
            bg: isBlocked ? 'var(--error-color)' : 'var(--secondary-background-color, rgba(127,127,127,0.08))',
            color: isBlocked ? 'white' : 'var(--secondary-text-color)',
            action: 'toggle', hour: h, blocked: isBlocked,
          };
        });
      } else if (mode === 'heatmap') {
        const raw = attr(hass, c.entity, c.path || 'slots', []) || [];
        const today = new Date(); today.setHours(0, 0, 0, 0);
        const tomorrow = new Date(today.getTime() + 86400000);
        const dayKey = (d) => d.toISOString().slice(0, 10);
        const byDay = { [dayKey(today)]: {}, [dayKey(tomorrow)]: {} };
        raw.forEach((item) => {
          const d = new Date(item[c.x_field || 'iso']);
          const key = dayKey(new Date(d.getFullYear(), d.getMonth(), d.getDate()));
          if (byDay[key]) byDay[key][d.getHours()] = item[c.value_field];
        });
        const thresholds = c.thresholds || [1.0, 1.5, 2.0];
        // Header row of hour labels — without this there's no way to tell
        // which column is which hour; the original markdown table had this
        // as its header row, the grid dropped it entirely.
        for (let h = 0; h < 24; h++) {
          cells.push({
            label: String(h).padStart(2, '0'), bg: 'transparent',
            color: 'var(--secondary-text-color)', outline: h === nowHour,
          });
        }
        [dayKey(today), dayKey(tomorrow)].forEach((key, rowIdx) => {
          for (let h = 0; h < 24; h++) {
            const v = byDay[key][h];
            const isNow = rowIdx === 0 && h === nowHour;
            cells.push({
              label: v === undefined ? '·' : v.toFixed(2),
              bg: v === undefined ? 'transparent' : tierColor(v, thresholds, c.invert),
              color: v === undefined ? 'var(--secondary-text-color)' : tierTextColor(v, thresholds, c.invert),
              outline: isNow,
            });
          }
        });
      } else if (mode === 'timeline') {
        const chargeHrs = attr(hass, c.entity, c.charge_field || 'charge_hours_today', []) || [];
        const exportHrs = attr(hass, c.entity, c.export_field || 'export_hours_today', []) || [];
        cells = Array.from({ length: 24 }, (_, h) => {
          const isNow = h === nowHour;
          if (chargeHrs.includes(h)) return { label: '⚡', bg: 'var(--warning-color)', color: '#000', outline: isNow };
          if (exportHrs.includes(h)) return { label: '$', bg: 'var(--success-color)', color: 'white', outline: isNow };
          return { label: String(h).padStart(2, '0'), bg: 'transparent', color: 'var(--secondary-text-color)', outline: isNow };
        });
      }

      const cols = mode === 'toggle' ? 12 : 24;
      const cellMin = mode === 'toggle' ? 40 : 46;
      const cellsHtml = cells.map((cell) => `
        <div class="sa-cell" data-hour="${cell.hour !== undefined ? cell.hour : ''}"
             data-blocked="${cell.blocked ? '1' : '0'}"
             title="${escapeHtml(cell.label)}"
             style="aspect-ratio:1;border-radius:4px;background:${cell.bg};color:${cell.color};
                    display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:500;cursor:${mode === 'toggle' ? 'pointer' : 'default'};
                    ${cell.outline ? 'outline:2px solid var(--primary-color);outline-offset:-1px;' : ''}">${cell.label}</div>
      `).join('');

      this._root.innerHTML = `
        <style>${BASE_CSS}
          .sa-grid-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; padding-bottom: 4px; }
          .sa-grid { display: grid; grid-template-columns: repeat(${cols}, minmax(${cellMin}px, 1fr)); gap: 4px; }
        </style>
        <ha-card>
        <div class="sa-inner">
          ${c.title ? `<div style="font-size:17px;font-weight:500;margin-bottom:2px;display:flex;align-items:center;gap:8px;">${c.icon ? `<ha-icon icon="${escapeHtml(c.icon)}" style="color:${NAMED_COLORS[c.icon_color] || c.icon_color || 'var(--primary-text-color)'};"></ha-icon>` : ''}${escapeHtml(c.title)}</div>` : ''}
          ${c.subtitle ? `<div class="muted" style="font-size:15px;margin-bottom:8px;">${escapeHtml(c.subtitle)}</div>` : ''}
          <div class="sa-grid-wrap"><div class="sa-grid">${cellsHtml}</div></div>
        </div>
        </ha-card>
      `;

      if (mode === 'toggle') {
        this._root.querySelectorAll('.sa-cell').forEach((cell) => {
          cell.addEventListener('click', () => {
            // Toggling calls a service and waits for the round-trip (service
            // call -> coordinator -> new hass -> re-render) before the cell's
            // color actually updates. With no immediate feedback, a second
            // tap during that gap silently un-does the first one — it looks
            // "random" but was really just two real toggles. Flip the cell's
            // own look right away (optimistic update) and briefly ignore
            // further clicks on it so a fast double-tap can't cancel itself.
            if (cell.dataset.pending === '1') return;
            cell.dataset.pending = '1';
            cell.style.pointerEvents = 'none';
            const nowBlocked = cell.dataset.blocked !== '1';
            cell.dataset.blocked = nowBlocked ? '1' : '0';
            cell.style.background = nowBlocked ? 'var(--error-color)' : 'var(--secondary-background-color, rgba(127,127,127,0.08))';
            cell.style.color = nowBlocked ? 'white' : 'var(--secondary-text-color)';
            const [domain, service] = (c.toggle_service || 'battery_arbitrage.toggle_blocked_sell_hour').split('.');
            callService(hass, domain, service, { hour: parseInt(cell.dataset.hour, 10) });
            setTimeout(() => { cell.style.pointerEvents = ''; delete cell.dataset.pending; }, 1200);
          });
        });
      }
    }
  }
  try {
    customElements.define('solar-ai-grid-card', SolarAiGridCard);
    console.info('Solar AI: registered <solar-ai-grid-card>');
  } catch (err) {
    console.error('Solar AI: failed to register <solar-ai-grid-card>', err);
  }

  // ---------------------------------------------------------- entities card

  const DOMAIN_ICONS = {
    number: 'mdi:numeric', switch: 'mdi:toggle-switch-outline', sensor: 'mdi:information-outline',
    binary_sensor: 'mdi:checkbox-blank-circle-outline', select: 'mdi:format-list-bulleted',
    text: 'mdi:form-textbox', date: 'mdi:calendar', time: 'mdi:clock-outline',
  };

  class SolarAiEntitiesCard extends SolarAiBaseCard {
    _watchedEntities() {
      return (this._config.entities || [])
        .filter((row) => typeof row === 'object' && row.entity)
        .map((row) => row.entity);
    }
    getCardSize() { return Math.max(1, (this._config.entities || []).length / 2); }

    _rowValue(hass, entityId) {
      const st = hass.states[entityId];
      if (!st) return { text: '–', pill: null };
      if (entityId.startsWith('binary_sensor.') || entityId.startsWith('switch.')) {
        const on = st.state === 'on';
        return { text: '', pill: { on, label: on ? 'On' : 'Off' } };
      }
      const unit = (st.attributes && st.attributes.unit_of_measurement) || '';
      return { text: unit ? `${st.state} ${unit}` : st.state, pill: null };
    }

    _render() {
      const c = this._config;
      const hass = this._hass;
      if (!hass) return;
      const cardColorRaw = NAMED_COLORS[c.icon_color] || c.icon_color || 'var(--primary-color)';

      // Help texts are kept in a side array and referenced by index (not
      // embedded in a data-* attribute) so arbitrary punctuation/length in
      // the explainer text can't break HTML attribute quoting.
      const helpTexts = [];
      const rowsHtml = (c.entities || []).map((row) => {
        if (typeof row === 'string') row = { entity: row };
        if (row.type === 'divider') return '<div style="border-top:1px solid var(--divider-color);margin:6px 0;"></div>';
        if (row.type === 'section') {
          return `<div style="font-size:12px;color:var(--secondary-text-color);text-transform:uppercase;letter-spacing:.04em;margin:10px 0 2px;">${escapeHtml(row.label || '')}</div>`;
        }
        const st = hass.states[row.entity];
        const name = row.name || (st && st.attributes && st.attributes.friendly_name) || row.entity;
        const domain = (row.entity || '').split('.')[0];
        const icon = row.icon || (st && st.attributes && st.attributes.icon) || DOMAIN_ICONS[domain] || 'mdi:help-circle-outline';
        const rowColor = NAMED_COLORS[row.icon_color] || row.icon_color || cardColorRaw;
        const { text, pill } = this._rowValue(hass, row.entity);
        const valueHtml = pill
          ? `<span style="font-size:13px;padding:2px 10px;border-radius:10px;background:${pill.on ? 'var(--success-color)' : 'var(--secondary-background-color, rgba(127,127,127,0.15))'};color:${pill.on ? 'white' : 'var(--secondary-text-color)'};">${pill.label}</span>`
          : `<span style="font-size:15px;">${escapeHtml(text)}</span>`;
        let helpBtnHtml = '';
        if (row.help) {
          const idx = helpTexts.length;
          helpTexts.push({ title: name, text: row.help });
          helpBtnHtml = `<button class="sa-help-btn" type="button" data-help-idx="${idx}" aria-label="Help">?</button>`;
        }
        return `
          <div class="sa-erow" data-entity="${escapeHtml(row.entity || '')}" style="display:flex;align-items:center;gap:12px;padding:8px 0;cursor:pointer;">
            <div style="width:34px;height:34px;min-width:34px;border-radius:50%;background:color-mix(in srgb, ${rowColor} 18%, transparent);display:flex;align-items:center;justify-content:center;">
              <ha-icon icon="${escapeHtml(icon)}" style="color:${rowColor};--mdc-icon-size:19px;"></ha-icon>
            </div>
            <div style="flex:1;min-width:0;display:flex;align-items:center;gap:7px;">
              <span style="font-size:15px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escapeHtml(name)}</span>
              ${helpBtnHtml}
            </div>
            <div style="text-align:right;">${valueHtml}</div>
          </div>`;
      }).join('');

      this._root.innerHTML = `
        <style>${BASE_CSS}</style>
        <ha-card>
        <div class="sa-inner">
          ${c.title ? `<div style="font-size:17px;font-weight:500;margin-bottom:6px;display:flex;align-items:center;gap:8px;">${c.icon ? `<ha-icon icon="${escapeHtml(c.icon)}" style="color:${cardColorRaw};"></ha-icon>` : ''}${escapeHtml(c.title)}</div>` : ''}
          ${c.subtitle ? `<div class="muted" style="font-size:14px;margin-bottom:6px;">${escapeHtml(c.subtitle)}</div>` : ''}
          <div>${rowsHtml}</div>
        </div>
        </ha-card>
      `;

      this._root.querySelectorAll('.sa-erow[data-entity]').forEach((row) => {
        row.addEventListener('click', () => moreInfo(this, row.dataset.entity));
      });
      this._root.querySelectorAll('.sa-help-btn[data-help-idx]').forEach((btn) => {
        btn.addEventListener('click', (e) => {
          e.stopPropagation();  // don't also trigger the row's moreInfo
          const item = helpTexts[Number(btn.dataset.helpIdx)];
          if (item) showHelpDialog(hass, item.title, item.text);
        });
      });
    }
  }
  try {
    customElements.define('solar-ai-entities-card', SolarAiEntitiesCard);
    console.info('Solar AI: registered <solar-ai-entities-card>');
  } catch (err) {
    console.error('Solar AI: failed to register <solar-ai-entities-card>', err);
  }

  // ----------------------------------------------------------- view wrapper
  //
  // Hosts an arbitrary list of child cards — native HA cards (entities,
  // markdown, history-graph, …) and our own alike — and caps + centers the
  // WHOLE stack at a single consistent width. This is what card-mod's
  // `:host { max-width: 1000px; margin: 0 auto; }` trick did in the original
  // dashboard: a native card has no way to size itself, so the cap has to be
  // applied once, at the wrapper, not per-card — putting a max-width only on
  // our OWN element types left every native card (e.g. a plain `entities`
  // list) flush against the screen edge while ours floated centered next to
  // it, which is what looked broken. Built with `loadCardHelpers()`, HA's
  // own public, documented API for a custom card to host other cards — the
  // same mechanism third-party layout cards use, so this isn't a private-API
  // hack.
  class SolarAiViewCard extends HTMLElement {
    constructor() {
      super();
      this._root = this.attachShadow({ mode: 'open' });
      this._cardEls = [];
    }

    async setConfig(config) {
      if (!config || !Array.isArray(config.cards)) {
        throw new Error('solar-ai-view-card requires a "cards" list');
      }
      this._config = config;
      if (!this._helpers && window.loadCardHelpers) {
        this._helpers = await window.loadCardHelpers();
      }
      this._cardEls = config.cards.map((cardConfig) => {
        let el;
        try {
          el = this._helpers
            ? this._helpers.createCardElement(cardConfig)
            : document.createElement('hui-error-card');
          if (!this._helpers) el.setConfig({ type: 'error', error: 'Card helpers unavailable' });
        } catch (err) {
          el = document.createElement('hui-error-card');
          el.setConfig({ type: 'error', error: String(err) });
        }
        if (this._hass) el.hass = this._hass;
        return el;
      });
      this._renderShell();
    }

    set hass(hass) {
      this._hass = hass;
      this._cardEls.forEach((el) => { el.hass = hass; });
    }

    _renderShell() {
      this._root.innerHTML = `
        <style>
          :host { display: block; }
          .sa-view { max-width: 1000px; margin: 0 auto; display: flex; flex-direction: column; gap: 12px; padding: 8px 0; }
        </style>
        <div class="sa-view"></div>
      `;
      const container = this._root.querySelector('.sa-view');
      this._cardEls.forEach((el) => container.appendChild(el));
    }

    getCardSize() {
      return this._cardEls.reduce(
        (sum, el) => sum + (typeof el.getCardSize === 'function' ? (el.getCardSize() || 1) : 1),
        0,
      );
    }
  }
  try {
    customElements.define('solar-ai-view-card', SolarAiViewCard);
    console.info('Solar AI: registered <solar-ai-view-card>');
  } catch (err) {
    console.error('Solar AI: failed to register <solar-ai-view-card>', err);
  }

  // ---------------------------------------------------------- card picker

  window.customCards = window.customCards || [];
  window.customCards.push(
    { type: 'solar-ai-status-card', name: 'Solar AI Status', description: 'Energy flow, mode, and price hero card.' },
    { type: 'solar-ai-mode-picker-card', name: 'Solar AI Mode Picker', description: 'EV charge-mode selector.' },
    { type: 'solar-ai-chart-card', name: 'Solar AI Chart', description: 'Self-contained price/solar/savings chart.' },
    { type: 'solar-ai-grid-card', name: 'Solar AI Hour Grid', description: '24-hour toggle/heatmap/timeline grid.' },
    { type: 'solar-ai-view-card', name: 'Solar AI View Stack', description: 'Width-capped, centered stack of any cards.' },
    { type: 'solar-ai-nav-card', name: 'Solar AI Nav', description: 'Button row that navigates between views.' },
    { type: 'solar-ai-entities-card', name: 'Solar AI Entities', description: 'Entity list with colored icon badges.' },
  );
})();
