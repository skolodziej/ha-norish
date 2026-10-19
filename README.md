# Norish für Home Assistant

Custom Integration, die die Einkaufsliste (Groceries) einer selbst gehosteten
[Norish](https://norish.dev)-Instanz als native **Todo-Liste** in Home Assistant
bereitstellt, ähnlich wie die offizielle Cookidoo-Integration.

- Einträge anlegen, abhaken, zurücksetzen und löschen
- Menge, Einheit und optional der Laden stehen in der Beschreibung, z. B. `200 g · Rewe`
- Einheiten werden passend zur Systemsprache abgekürzt (`gram` → `g`,
  `tablespoon` → `EL` bzw. `tbsp`). Eigene Einheiten bleiben unverändert.
- Reihenfolge wie in Norish (`sortOrder`)
- Nach jedem Schreibzugriff ist der Zustand sofort aktuell. Ein
  `todo.get_items` direkt nach `todo.add_item` enthält den neuen Eintrag bereits.
- Keine zusätzlichen Python-Abhängigkeiten

Voraussetzung: Home Assistant 2026.10 oder neuer.

## Installation über HACS

1. HACS öffnen → Menü (⋮) → **Benutzerdefinierte Repositories**.
2. `https://github.com/skolodziej/ha-norish` eintragen, Typ **Integration**, hinzufügen.
3. „Norish“ in HACS suchen und herunterladen.
4. Home Assistant neu starten.

Manuell geht es auch: den Ordner `custom_components/norish` nach
`<config>/custom_components/norish` kopieren und neu starten.

## API-Key in Norish anlegen

1. In Norish anmelden.
2. **Einstellungen → Benutzer → API-Keys** öffnen.
3. Einen neuen Key erstellen, z. B. „Home Assistant“, und kopieren.
   Der Key gehört zu deinem Benutzer. Die Integration sieht deshalb genau die
   Einkaufsliste, die du in Norish siehst.

## Einrichtung

1. **Einstellungen → Geräte & Dienste → Integration hinzufügen → Norish**.
2. **URL** der Instanz eingeben, z. B. `https://rezepte.example.com`.
   Ein abschließender Slash oder `/api/v1` wird automatisch entfernt. Ohne
   Schema wird `https://` angenommen.
3. **API-Key** einfügen.

Die Integration prüft die Daten mit einem Abruf der Einkaufsliste. Jede
Instanz (normalisierte URL) lässt sich nur einmal einrichten. Wird der Key
später ungültig (HTTP 401/403), fordert Home Assistant zur erneuten Anmeldung
auf.

Danach gibt es die Entität `todo.norish_einkaufsliste` (bei englischer
Systemsprache `todo.norish_shopping_list`).

### Optionen

Unter **Konfigurieren** in der Integration:

| Option | Standard | Beschreibung |
| --- | --- | --- |
| Abfrageintervall | 60 s | Wie oft die Liste abgerufen wird, mindestens 15 s |
| Ladennamen in der Beschreibung anzeigen | an | Hängt den in Norish zugewiesenen Laden an, z. B. `200 g · Rewe` |

Läden werden zwischengespeichert und nur alle 15 Minuten neu geladen,
oder früher, wenn ein Eintrag auf einen unbekannten Laden verweist.

## Beispiel: Automation

```yaml
action: todo.add_item
target:
  entity_id: todo.norish_einkaufsliste
data:
  item: Milch
```

## Bekannte Einschränkungen

- **Umbenennen ist nicht möglich.** Die Norish-API bietet dafür keinen
  Endpunkt. Ein Umbenennungsversuch endet mit einer verständlichen
  Fehlermeldung. Lösung: Eintrag löschen und neu anlegen.
- **Beschreibung, Menge, Einheit und Laden** lassen sich nur in Norish ändern.
  Neue Einträge aus Home Assistant haben keine Menge und Einheit.
- **Fälligkeitsdatum und Umsortieren** werden nicht unterstützt.
- **Polling:** Norish hat keine Webhooks. Änderungen, die direkt in Norish
  gemacht werden, erscheinen erst nach dem nächsten Abruf, also spätestens
  nach dem eingestellten Intervall. Eigene Änderungen aus Home Assistant
  sind sofort sichtbar.
- **Gleichzeitige Änderungen:** Norish nutzt Optimistic Locking. Bei einem
  Versionskonflikt lädt die Integration die Liste neu und versucht es genau
  einmal erneut. Schlägt auch das fehl, gibt es eine Fehlermeldung.

## Diagnose

Die Diagnosedaten (Integration → ⋮ → **Diagnose herunterladen**) enthalten die
Einkaufsliste und die Läden. API-Key und URL sind geschwärzt. Der Key wird nie
geloggt.

## Entwicklung

```bash
uv venv -p 3.14 .venv
uv pip install -p .venv pytest-homeassistant-custom-component ruff
.venv/bin/python -m pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

Die Tests laufen gegen einen zustandsbehafteten Fake-Server, der Versionen
und `stale` simuliert. Echte Instanzen werden dabei nicht angesprochen.

## Lizenz

MIT, siehe [LICENSE](LICENSE).
