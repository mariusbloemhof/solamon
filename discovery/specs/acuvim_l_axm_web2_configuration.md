# AccuEnergy AXM-WEB2 — Cloud Push Configuration Guide

**Module:** AXM-WEB2 Expansion Module for Acuvim-L Series  
**Source:** AXM-WEB2 Series Users Manual V2.1.4 (September 2024)  
**Supported push methods:** MQTT, HTTP/HTTPS, FTP, SFTP  
**Local data cache:** Up to 3GB — queued and auto-uploaded on reconnect

---

## 1. Default Network Settings (Commissioning Reference)

| Interface | IP / Setting | Notes |
|-----------|-------------|-------|
| Ethernet 1 | 192.168.1.254 (static) | Subnet 255.255.255.0, GW 192.168.1.1 |
| Ethernet 2 | DHCP | Check meter display N12 for assigned IP |
| Wi-Fi AP | 192.168.100.1 | SSID: `AXM-WEB2-WIFI-[serial]` / Password: `accuenergy` |
| Web UI | HTTP port 80, HTTPS port 443 | Login: `admin` / `admin` |
| Modbus TCP | Port 502 | Standard range; configurable 2000–5999 |

---

## 2. MQTT Push Configuration (Web UI → Section 6.16)

### 2.1 General Settings

| Parameter | Description |
|-----------|-------------|
| Enable MQTT | Toggle on/off |
| Broker Address | IP address or FQDN (e.g. `mqtt.yourdomain.com`) |
| Broker Port | 1883 (plain TCP) or 8883 (TLS/SSL) |
| Client ID | Unique string per device |
| Keep Alive | Seconds between pings (prevent broker disconnect) |
| Clean Session | Yes = discard queued messages on reconnect; No = retain offline queue |

After configuring: click **Save MQTT**, then **Test MQTT** to verify broker connectivity.

### 2.2 Authentication

| Parameter | Description |
|-----------|-------------|
| Username | MQTT broker username |
| Password | MQTT broker password |

### 2.3 TLS/SSL (SSL/TLS tab)

| Parameter | Description |
|-----------|-------------|
| Enable SSL | Toggle |
| CA File | Upload Certificate Authority public key (.pem/.crt) |
| Cert File | Upload client certificate (.pem/.crt) |
| Key File | Upload client private key (.key) |

### 2.4 Last Will and Testament (LWT)

| Parameter | Values |
|-----------|--------|
| Enable LWT | Toggle |
| Topic | MQTT topic path for LWT message |
| QoS | 0 = at-most-once, 1 = at-least-once, 2 = exactly-once |
| Retained | Yes / No |

### 2.5 Publish Configuration

| Parameter | Description |
|-----------|-------------|
| Topic | MQTT topic path (e.g. `solar/site1/grid-meter`) |
| QoS | 0, 1, or 2 |
| Retained | Yes / No |
| Interval | 10–600 seconds |
| Parameter Type | Real-Time, Energy, or Demand |
| Parameter Selection | Multi-select from available measurement list |

### 2.6 MQTT Payload Format (JSON)

```json
{
  "timestamp": "2025-09-15T10:30:00Z",
  "gateway": {
    "name": "AXM-WEB2",
    "model": "AXM-WEB2",
    "serial": "AND00123456"
  },
  "device": {
    "name": "",
    "model": "Acuvim-L"
  },
  "readings": [
    {"param": "V1",      "value": "230.5",  "unit": "V"},
    {"param": "V2",      "value": "231.2",  "unit": "V"},
    {"param": "V3",      "value": "230.8",  "unit": "V"},
    {"param": "I1",      "value": "15.3",   "unit": "A"},
    {"param": "I2",      "value": "14.9",   "unit": "A"},
    {"param": "I3",      "value": "15.1",   "unit": "A"},
    {"param": "Psum",    "value": "10530",  "unit": "W"},
    {"param": "Qsum",    "value": "1250",   "unit": "var"},
    {"param": "Ssum",    "value": "10604",  "unit": "VA"},
    {"param": "PF",      "value": "0.993",  "unit": ""},
    {"param": "Freq_Hz", "value": "50.01",  "unit": "Hz"},
    {"param": "Ep_imp",  "value": "12530.5","unit": "kWh"},
    {"param": "Ep_exp",  "value": "0.0",    "unit": "kWh"},
    {"param": "LoadType","value": "L",      "unit": ""}
  ]
}
```

> **Note:** The `param` field names map directly to the meter's internal parameter names. The set of params published depends on configuration in the Publish Configuration screen.

---

## 3. HTTP/HTTPS Push Configuration (Web UI → Section 6.8)

Three independent post channels are available. Each can target a different endpoint.

### 3.1 Channel Settings

| Parameter | Description |
|-----------|-------------|
| Post Channel Enable | Toggle per channel |
| Post Method | HTTP, HTTPS, FTP, or SFTP |
| Post Name Fixed | Use fixed filename instead of timestamp-based |
| Post File Name | Custom filename when Post Name Fixed is enabled |

### 3.2 HTTP/HTTPS Parameters

| Parameter | Description |
|-----------|-------------|
| Need Authorization | Toggle |
| Authorization type | **Default** (token/bearer) or **Basic** (username + password) |
| HTTP/HTTPS URL | Full URL: `https://api.yourdomain.com/ingest/meter` |
| HTTP/HTTPS Port | Server port |
| HTTP/HTTPS Meter ID | Identifier string sent with each post (use for multi-meter identification) |

### 3.3 HTTP POST Encoding

The module sends a **multipart/form-data** POST:

```
POST /ingest/meter HTTP/1.1
Content-Type: multipart/form-data; boundary=----Boundary

------Boundary
Content-Disposition: form-data; name="action"

upload
------Boundary
Content-Disposition: form-data; name="datasource"

[serial_number]/[model_name]
------Boundary
Content-Disposition: form-data; name="file"; filename="[timestamp].json"
Content-Type: text/json

[JSON file contents — same structure as MQTT payload when JSON format selected]
------Boundary--
```

The JSON body structure (when Log File Format = JSON) matches the MQTT payload format shown above.

---

## 4. Data Log Configuration (linked to Post Channels)

| Parameter | Description |
|-----------|-------------|
| Logger Enable | Toggle per logger (3 loggers available) |
| Post Channel | Which post channel (1, 2, or 3) |
| Log Param Type | Real-Time, Demand, Energy, THD, IO, etc. |
| Log Param Detail | Instantaneous / Min / Max / Average |
| Log File Format | **CSV** or **JSON** (JSON required for HTTP/FTP post) |
| Timestamp Format | Local Time, UTC Seconds, or ISO8601 |
| Log Interval | 1s (RT/IO), 15s (Energy), 1min (Demand/PQ) minimum |
| Post File Length | How often to upload: 1 min to 1 month |
| Log File Name Prefix | Custom prefix on filenames |
| Local Log File Length | 1 hour / 1 day / 7 days / 1 month |

**Offline cache:** Up to 3GB cached locally when server is unreachable. Auto-uploads on reconnect — critical for cellular-backup sites where connectivity is intermittent.

---

## 5. FTP / SFTP Push Configuration

| Parameter | Description |
|-----------|-------------|
| FTP/SFTP Server | Hostname or IP |
| Port | Default 21 (FTP) or 22 (SFTP) |
| Username / Password | Server credentials |
| Remote Directory | Target directory on server |
| Post File Name | Same naming options as HTTP channel |

---

## 6. Integration Architecture Recommendations

### For the Solar Monitor Platform

**Recommended approach: MQTT push (primary) + local Acuvim log (backup)**

1. Configure AXM-WEB2 to push to your cloud MQTT broker every 30–60 seconds (real-time channel)
2. Enable a second logger for energy data (15s or 1min interval) to a separate MQTT topic or HTTP endpoint
3. Enable offline caching — the 3GB local cache handles multi-day cellular outages
4. Use TLS/SSL with certificate authentication for the MQTT connection
5. Set LWT topic to detect meter offline events on the broker

**Topic structure suggestion:**
```
solar/{site_id}/meters/{meter_id}/realtime     ← V, I, P, Q, PF, Freq
solar/{site_id}/meters/{meter_id}/energy       ← Ep_imp, Ep_exp, TOU registers
solar/{site_id}/meters/{meter_id}/status       ← LWT / online indicator
```

**For billing:** Trust the Acuvim L's local TOU energy registers (0x0200–0x0231) as the source of truth, not the MQTT stream. The Modbus TCP registers hold the accumulated TOU energy even across connectivity gaps. Poll these via the edge agent or use the HTTP post channel to deliver a daily/monthly energy report.

### Modbus vs Push — When to Use Each

| Use Case | Recommended |
|----------|-------------|
| Real-time monitoring (live dashboard) | MQTT push (lower latency, no polling overhead) |
| Billing data collection | Modbus TCP poll of TOU registers OR HTTP post energy log |
| Alarm/event detection | MQTT push with event-triggered publish |
| Historical backfill after outage | HTTP/FTP post with offline cache delivery |
| Control (none — meter is read-only) | N/A |
