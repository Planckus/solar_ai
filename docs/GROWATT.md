# Growatt support (planned)

**Status: planned, not available.** Solar AI controls FoxESS inverters only. This page records the scope, the dependencies and the design for Growatt support so that the requirements are known before it ships. It will change once the backend has been tested on a real inverter.

## Scope: newer Growatt hybrid inverters only

Solar AI will support Growatt hybrid inverters of the **GEN4** generation that accept **VPP remote power control** (holding registers 30407-30410). Battery control in Solar AI depends on that feature; models without it are not supported.

| Status | Growatt models | Why |
|---|---|---|
| Planned | **MIN TL-XH** (2.5-6 kW, single-phase) | GEN4 hybrid with VPP remote power control |
| Planned | **MOD TL3-XH** (3-10 kW, three-phase) | GEN4 hybrid with VPP remote power control |
| Planned | **MID TL3-XH** (11-30 kW, three-phase) | GEN4 hybrid with VPP remote power control |
| Not supported | SPH, SPA (GEN3 hybrid and AC-coupled) | Older generation; not in scope |
| Not supported | MIC, MIN TL-X, MOD TL3-X, MID TL3-X | No battery |
| Not supported | SPF (off-grid) | Different control model |
| Not supported | WIT and other commercial models | Not detected by the integration Solar AI builds on |

The generation is the classification used by the SolaX Inverter Modbus integration, which identifies the model from the serial number or firmware prefix (for example `AL1` MIN TL-XH, `DN1` MOD/MID TL3-XH).

**Firmware matters.** VPP remote power control is a firmware feature. A model in the table may still lack it on older firmware. Solar AI will check for it during setup and refuse battery control if the registers do not respond. Which firmware versions are required is not yet confirmed; it will be recorded here once tested.

## Dependencies

| Dependency | Requirement |
|---|---|
| Connection | **ShineWLAN-X2** dongle on the local network, which provides Modbus TCP on port 502. An RS485-to-TCP adapter on the inverter's RS485 port is an alternative. The older ShineWiFi-S/-X dongles only talk to the Growatt cloud and are not supported. |
| Home Assistant integration | [SolaX Inverter Modbus](https://github.com/wills106/homeassistant-solax-modbus) from HACS, with inverter type **Growatt** and interface **TCP / Ethernet**. Solar AI reads and writes through its entities and does not open its own Modbus connection. |
| Write access | The integration's control entities must be enabled: VPP Remote Control, VPP Power, VPP Time, VPP Allow AC charging, Grid Export Limit, EMS Discharging Stop SOC (on grid). |
| One Modbus client | The X2 handles one Modbus TCP client reliably. Do not run a second Modbus integration or tool against the same dongle. |
| Inverter schedules | Time-of-use windows and Battery First / Grid First schedules set in the Growatt app or on the inverter must be disabled. They override mode changes. |
| Growatt cloud integration | Not used. Polling the Growatt cloud from Home Assistant can lock the Growatt account. |
| Home Assistant | Same minimum as Solar AI (2024.7.0). |

## How Solar AI will control a Growatt inverter

| Solar AI action | FoxESS (today) | Growatt (planned) |
|---|---|---|
| Normal self-consumption | Work mode *Self Use* | VPP remote control off; inverter in its own Load First mode |
| Grid charge at X kW | *Force Charge* + charge power | VPP Power +X % of rated power, AC charging allowed |
| Sell at X kW | *Force Discharge* + discharge power | VPP Power −X % of rated power |
| Export limit | Register 46616 | Grid Export Limit (register 123) |
| Hardware SoC floor while selling | Min SoC on grid | EMS Discharging Stop SOC (on grid) |
| Hold the battery while the car charges at full power | Max discharge current 0 | To be tested: VPP Power 0 %, or stop-SoC at the current SoC |
| PV curtailment flag | Register 49251 | No equivalent; Solar AI's power-flow detection is used instead |

A VPP command runs for the duration in VPP Time and then the inverter returns to its own mode. Solar AI renews it every control tick with a short duration, so the inverter falls back to self-consumption on its own if Home Assistant stops. Persistent settings (priority, time windows, stop-SoC) are written only when a setting changes, not in the control loop, to avoid wearing the inverter's settings memory.

## Installation (planned)

1. Install SolaX Inverter Modbus from HACS and add it with type Growatt, TCP, the X2's IP address and port 502. Check that battery SoC, PV and grid power read correctly.
2. Disable time-of-use schedules in the Growatt app.
3. Add Solar AI. The first setup step asks for the inverter brand; it is preselected when only one of the FoxESS Modbus and SolaX Inverter Modbus integrations is installed.
4. Solar AI maps the needed entities from the entity registry, by owning integration rather than by name, and lists anything missing together with the feature it affects.
5. A capability check confirms that the VPP registers respond. Without them Solar AI runs in monitoring mode only.
6. Start in monitoring mode and enable control once the readings look right, as for FoxESS.

## Open items before release

- Confirm on a real MIN TL-XH or MOD TL3-XH with an X2 that VPP remote power control responds, and record the firmware version.
- Confirm the battery hold method while the car charges at full power.
- Field test for at least one to two weeks in monitoring mode, then with control enabled.
