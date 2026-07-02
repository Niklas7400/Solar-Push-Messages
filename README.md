# Solar-Push-Messages

Schickt Push-Benachrichtigungen aufs Handy, wenn gerade ein Stromüberschuss
eingespeist wird ("Verbraucher jetzt einschalten") oder viel Strom aus dem
Netz bezogen wird ("Verbrauch reduzieren") — auf Basis der Live-Werte eines
Huawei SUN2000 Wechselrichters.

## Funktionsweise

- Das Skript fragt den Wechselrichter **lokal per Modbus TCP** ab (kein
  Cloud-Zugang zu FusionSolar nötig, keine Installateur-Zugangsdaten
  erforderlich). Das ist derselbe Weg, den z.B. die `huawei-solar`
  Home-Assistant-Integration nutzt.
- Ausgewertet wird der Netz-Leistungsmesswert (vom "Smart Power Sensor" /
  Stromzähler, falls an deiner Anlage verbaut): positiv = Einspeisung
  (Überschuss), negativ = Bezug.
- Bei Über-/Unterschreiten konfigurierbarer Schwellwerte wird eine
  Push-Nachricht über [ntfy.sh](https://ntfy.sh) verschickt.

**Voraussetzung:** An deinem Wechselrichter muss ein Leistungsmesser
("Smart Power Sensor", z.B. DTSU666) installiert sein, der Netzbezug/
-einspeisung misst. Ohne ihn liefert der Wechselrichter nur die reine
PV-Erzeugung, aber keinen Netzwert — dann funktioniert die Kernlogik
dieses Projekts nicht.

### Alternative: FusionSolar-Cloud statt lokalem Modbus

Falls der Wechselrichter im LAN nicht erreichbar ist (z.B. eigenes
Solar-/IoT-VLAN ohne Routing zum restlichen Netz), kann `DATA_SOURCE=cloud`
gesetzt werden. Das nutzt die inoffizielle, reverse-engineered
[fusion-solar-py](https://pypi.org/project/fusion-solar-py/)-Bibliothek
gegen dieselbe API, die auch die FusionSolar-Web-Oberfläche verwendet —
kein LAN-Zugriff nötig, dafür:

- dein FusionSolar-Account-Passwort liegt in der `.env` auf dem Pi
- Daten sind mit einer gewissen Verzögerung aktuell (bei häufigem Login-Retry
  kann die API laut Projekt-Doku ein Captcha verlangen)
- inoffizielle API, kann sich jederzeit ändern oder abgeschaltet werden

PV-Leistung, Netzbezug/-einspeisung und Batterie-Ladestand
(`solar_push/cloud_inverter.py`) wurden gegen einen echten FusionSolar-Account
end-to-end getestet (Login, Werte lesen, Push-Zustellung). Die Netzwerte
kommen direkt vom "Power Sensor"-Gerät (`get_real_time_data`, Signal "Active
power") — dieselbe physische Smart-Power-Sensor-Quelle wie beim lokalen
Modbus-Weg, mit demselben Vorzeichen (positiv = Einspeisung). Zum
Nachvollziehen/Debuggen der rohen API-Antworten:
`python scripts/dump_fusion_solar_flow.py` (liest die Zugangsdaten aus
`.env`, gibt sie nie aus).

## 1. Modbus TCP am Wechselrichter aktivieren

*(Nur relevant für `DATA_SOURCE=modbus`, siehe oben für die Cloud-Alternative.)*

Standardmäßig ist der externe Modbus-TCP-Zugriff auf SUN2000-Geräten
deaktiviert. Üblicher Weg (kann je nach Firmware/App-Version leicht
abweichen):

1. Mit dem Handy per WLAN mit dem Hotspot des Wechselrichters verbinden
   (SSID beginnt mit `SUN2000-...`, Passwort meist auf dem Typenschild bzw.
   initial `Changeme`).
2. Im Browser `https://192.168.200.1` öffnen und mit dem **Installateur**-
   Konto einloggen (nicht das normale Nutzerkonto — falls du nur Zugriff als
   Endkunde hast, frag deinen Installateur nach dem Installer-Login oder
   danach, Modbus TCP einmalig für dich freizuschalten).
3. Unter *Einstellungen → Kommunikationskonfiguration → Modbus TCP*
   aktivieren und den Port (Standard `502`) sowie **ohne** Passwortschutz
   für "External" bestätigen.
4. **Wichtig:** Bei manchen Firmwareständen deaktiviert sich Modbus TCP nach
   ca. 1 Stunde automatisch wieder, wenn kein Gerät verbunden ist/bleibt.
   Sobald dieses Skript regelmäßig (z.B. jede Minute) abfragt, bleibt die
   Verbindung normalerweise aktiv. Falls es dennoch abbricht: erneut
   aktivieren und Abfrageintervall (`POLL_INTERVAL_SECONDS`) verkleinern.
5. IP-Adresse des Wechselrichters im normalen Heim-WLAN (nicht der Hotspot)
   über die Router-Oberfläche ermitteln — die brauchst du für
   `INVERTER_HOST` im Dauerbetrieb.

## 2. ntfy einrichten (Push-Benachrichtigungen)

1. App **ntfy** aus dem Play Store / App Store installieren.
2. Ein frei erfundenes, schwer zu erratendes Topic ausdenken (z.B.
   `mueller-solar-h3x9k`) — ntfy.sh ist standardmäßig öffentlich, jeder der
   das Topic kennt, kann mitlesen/Nachrichten senden. Kein Leerzeichen, kein
   Sonderzeichen.
3. In der App dieses Topic abonnieren ("+" → Topic-Name eingeben).
4. Denselben Namen in `.env` bei `NTFY_TOPIC` eintragen (siehe unten).

## 3. Installation

```bash
git clone <dieses-repo>
cd Solar-Push-Messages
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# .env editieren: INVERTER_HOST, NTFY_TOPIC, Schwellwerte anpassen
```

## 4. Kalibrieren (Debug-Modus)

Bevor du dich auf die Benachrichtigungen verlässt, das Vorzeichen des
Netzwerts prüfen: mit `--debug` werden nur Messwerte geloggt, es wird
nichts verschickt.

```bash
python -m solar_push --debug
```

Beobachte den geloggten `Grid=`-Wert zu einer Zeit, in der du sicher weißt,
ob gerade eingespeist oder bezogen wird (z.B. abends ohne Sonne = Bezug).
Falls das Vorzeichen andersherum ist als erwartet, `GRID_EXPORT_POSITIVE`
in `.env` umdrehen.

## 5. Testlauf auf dem Handy (Termux, Android)

Zum schnellen Testen, ohne extra Hardware — läuft nur solange Termux im
Vordergrund/nicht von Android beendet wird, **nicht** für Dauerbetrieb
gedacht:

```bash
pkg update && pkg install python git
git clone <dieses-repo>
cd Solar-Push-Messages
pip install -r requirements.txt
cp .env.example .env
# .env anpassen
termux-wake-lock          # verhindert, dass Android den Prozess sofort killt
python -m solar_push --debug
```

Handy muss im selben WLAN wie der Wechselrichter sein. Für dauerhaften
Betrieb Android-Akkuoptimierung für Termux deaktivieren — trotzdem nicht so
zuverlässig wie ein dediziertes Gerät, siehe nächster Schritt.

## 6. Dauerbetrieb auf einem Raspberry Pi

```bash
git clone <dieses-repo> ~/Solar-Push-Messages
cd ~/Solar-Push-Messages
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
# .env anpassen

sudo cp deploy/solar-push.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now solar-push.service
journalctl -u solar-push.service -f   # Logs ansehen
```

`deploy/solar-push.service` geht von Benutzer `pi` und Pfad
`/home/pi/Solar-Push-Messages` aus — bei Bedarf anpassen.

## Konfiguration (`.env`)

| Variable | Bedeutung |
|---|---|
| `DATA_SOURCE` | `modbus` (Standard) oder `cloud` |
| `INVERTER_HOST` / `INVERTER_PORT` | Adresse des Wechselrichters im lokalen Netz (nur `modbus`) |
| `FUSIONSOLAR_USERNAME` / `FUSIONSOLAR_PASSWORD` / `FUSIONSOLAR_SUBDOMAIN` / `FUSIONSOLAR_PLANT_ID` | FusionSolar-Account-Zugang (nur `cloud`) |
| `NTFY_URL` / `NTFY_TOPIC` | ntfy-Server und Topic für Push-Nachrichten |
| `POLL_INTERVAL_SECONDS` | Abfrageintervall |
| `INCREASE_THRESHOLD_W` | Ab wie viel Watt **Netz-Überschuss** "jetzt einschalten" gemeldet wird |
| `DECREASE_THRESHOLD_W` | Ab wie viel Watt **Speicher-Entladeleistung** "Verbrauch senken" gemeldet wird (nicht Netzbezug) |
| `BATTERY_LOW_SOC_PCT` / `BATTERY_LOW_HYSTERESIS_PCT` | Ab welchem Ladestand (%) der Speicher als "niedrig" gemeldet wird, plus Puffer |
| `HYSTERESIS_W` | Puffer gegen Flattern nahe den Watt-Schwellen |
| `COOLDOWN_MINUTES` | Mindestabstand zwischen zwei Benachrichtigungen |
| `RENOTIFY_MINUTES` | Erinnerung, falls Zustand länger anhält |
| `GRID_EXPORT_POSITIVE` | Vorzeichen-Kalibrierung Netzleistung, siehe Schritt 4 |
| `BATTERY_CHARGE_POSITIVE` | Vorzeichen-Kalibrierung Speicher-Lade-/Entladeleistung (noch nicht real verifiziert, siehe Hinweis unten) |

**Speicher-Vorzeichen noch nicht verifiziert:** Anders als bei `GRID_EXPORT_POSITIVE`
(gegen echte Daten bestätigt) beruht `BATTERY_CHARGE_POSITIVE=true` bisher nur auf
der in der Community üblichen Huawei-Konvention (positiv = Laden). Am
Testaccount war der Speicher während der Entwicklung durchgehend voll und
im Leerlauf, ein echter Lade-/Entladevorgang wurde nicht beobachtet. Einmal
mit `--debug` prüfen, während der Speicher sichtbar lädt oder entlädt
(z.B. abends beim Entladen), und bei Bedarf auf `false` umstellen.

## Tests

Die Entscheidungslogik (`solar_push/logic.py`) ist ohne echte Hardware
testbar:

```bash
pip install -r requirements-dev.txt
pytest
```

## Hinweis

Dieses Projekt wurde ohne Zugriff auf einen echten SUN2000 entwickelt und
getestet. Register-Namen/API der `huawei-solar`-Bibliothek können sich
zwischen Versionen leicht unterscheiden — falls beim Start Fehler zu
Register-Namen auftreten, in der [huawei-solar
Dokumentation](https://pypi.org/project/huawei-solar/) die aktuell gültigen
Namen prüfen und in `solar_push/inverter.py` entsprechend anpassen.
