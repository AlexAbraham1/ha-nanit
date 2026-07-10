# Nanit — Home Assistant Integration

<p align="center">
  <img src="custom_components/nanit/brand/icon@2x.png" alt="Nanit" width="128" />
</p>

<a href="https://github.com/wealthystudent/ha-nanit">
  <img src="docs/star-banner.svg" alt="Star this repo to help us get an official Nanit API" width="100%" />
</a>

---

> **Monitor your baby — right from Home Assistant.**
>
> Live streams, nursery sensors, night light control, and automations — all from your HA dashboard. Works with all Nanit cameras and the Sound & Light Machine.

<p align="center">
  <img src="docs/images/nanit-card.png" alt="Nanit dashboard card" width="420" />
</p>

## Requirements

- Home Assistant **2025.12** or newer
- A Nanit account with email/password
- [HACS](https://hacs.xyz/) (recommended)

## Installation

### HACS (recommended)

1. Open **HACS → Integrations → ⋮ → Custom repositories**.
2. Add `https://github.com/wealthystudent/ha-nanit` as **Integration**.
3. Install **Nanit**, then restart Home Assistant.

### Manual

Copy `custom_components/nanit/` into your HA `config/custom_components/` directory and restart.

## Setup

1. Go to **Settings → Devices & Services → Add Integration → Nanit**.
2. Enter your Nanit email and password.
3. Enter the MFA code sent to your device (use the latest code — they expire quickly).
4. Done — all cameras on your account are discovered automatically.

> [!TIP]
> Enable **Store credentials** during setup so re-authentication can happen without re-entering your password.

## What you get

**Per camera:**
- 📷 Live camera stream (RTMPS)
- 🌡️ Temperature & humidity sensors
- 👁️ Motion & sound detection
- 🫁 Breaths-per-minute & breathing alert (with Nanit Breathing Wear; available while tracking is active)
- 🫁 `button.<baby>_start_breathing_tracking` — one-shot button that starts a Breathing Motion Monitoring session, mirroring the **Start** action in the Nanit app
- 🫁 `binary_sensor.<baby>_breathing_tracking` (device class `running`) — on while a session is actively pushing breathing readings
- 💡 Night light switch
- 🔌 Camera power switch

> [!IMPORTANT]
> **Safety.** The breathing entities (`breaths_per_minute`, `breathing_alert`, `breathing_tracking`, and the start button) are a **display/convenience mirror** of the Nanit app's Breathing Motion Monitoring feature — they are **not** a safety device. **The Nanit app remains the safety-critical breathing-alarm path.** Never rely on these Home Assistant entities for apnea/breathing safety alerting.
>
> Pressing `button.<baby>_start_breathing_tracking` mirrors the app's "start" action; there is no stop button because the camera stops tracking on its own when the baby leaves the crib (same as the app). **It is not yet verified whether starting a session from Home Assistant also engages the Nanit app's phone-alert pipeline.** Until this is confirmed, if you rely on phone alerts, start breathing tracking from the Nanit app itself rather than from this button.

**Sound & Light Machine** (if linked):
- Power, sound, and light switches
- Sound track selector, volume & brightness controls
- Temperature & humidity sensors

Some entities are disabled by default. Enable them in **Settings → Devices & Services → Nanit → Entities**.

## Dashboard Card

A companion Lovelace card is **bundled with the integration** — no HACS frontend dependencies or manual JS installation required. After setup, the card appears in your card picker automatically.

**To add it:** Open any dashboard → **Add Card** → search for **Nanit** → select your camera.

The card provides:
- Live camera stream with loading indicator
- Temperature & humidity overlays, with optional semantic entity overrides for the displayed sensors
- Breaths-per-minute overlay pill (auto-detected, or overridden via `breathing_entity_id`), turning red and pulsing when the breathing-alert entity is on
- Motion & sound activity indicators
- Optional baby name and connectivity status display
- Header power button (can be hidden in card settings)
- Night light slider (drag to adjust brightness, 0% = off; can be hidden in card settings)
- Sound machine controls with icon-based track selection (can be hidden in card settings)
- Volume slider
- Network info popup (WiFi name, frequency, signal strength)

Optional sensor overrides can be set in the visual editor or YAML when you want the overlay to display another Home Assistant sensor instead of the Nanit-discovered sensor:

```yaml
type: custom:nanit-card
camera_entity_id: camera.nursery
temperature_entity_id: sensor.nursery_temperature
humidity_entity_id: sensor.nursery_humidity
breathing_entity_id: sensor.nursery_breaths_per_minute
breathing_alert_entity_id: binary_sensor.nursery_breathing_alert
```

> [!NOTE]
> If your Lovelace is in **YAML mode**, add the resource manually:
> ```yaml
> resources:
>   - url: /nanit-card/nanit-card.js
>     type: module
> ```

## Local connection (optional)

For faster response times, you can connect directly to your camera over LAN:

**Settings → Devices & Services → Nanit → Configure** → select camera → enter its local IP address.

The integration will use your local network for sensors and controls, falling back to cloud for auth and events.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| MFA code rejected | Codes expire fast — use the latest one. |
| Stream not playing | Verify HA can reach `rtmps://media-secured.nanit.com` and the Stream integration is enabled. |
| Sensors unavailable | WebSocket reconnects automatically. Try reloading the integration if it persists. |
| Local connection failing | Confirm the camera IP is correct and port 442 is reachable from HA. |
| Re-authentication required | Session expired — click the notification to re-enter credentials. |
| Other issues | Check **Settings → System → Logs** (filter for `nanit`) or download diagnostics from the integration page. |

## Known limitations

- Authentication, motion/sound events, and streaming always require the Nanit cloud — no fully offline mode.
- Motion and sound detection is polled every 30 seconds (up to ~30s delay).
- Live video requires your HA instance to reach `rtmps://media-secured.nanit.com`.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup and PR workflow.

## License

[MIT](LICENSE)
