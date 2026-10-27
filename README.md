# PIA — Investment Research Assistant

Rechercheassistent für langfristigen Vermögensaufbau im eigenen GmbH-Vermögen. Originalquellen, Gegenthese, Watchlist, nachvollziehbare Bewertungsrechnungen und Entscheidungsjournal. Keine Handelsrechte und keine Broker-Zugangsdaten.

## Status

Version 0.4 unterstützt lokalen Betrieb und einen privaten Vercel-Workspace mit PostgreSQL. Im Browser erfolgt die Anmeldung über eine eigene Login-Seite. Die automatisierten Cloud-Tests verwenden einen Speicher-Testdouble; Datenbank, Deployment und Anbieterzugänge müssen zusätzlich in der jeweiligen Umgebung geprüft werden.

## Privat oder lokal starten

```sh
bash START_MAC.command
```

Alternativ Python 3.11+ verwenden, eine virtuelle Umgebung anlegen, `pip install -r requirements.txt` und `python start.py` ausführen. Der lokale Server bindet ausschließlich an 127.0.0.1:8765 und verwendet SQLite. Ohne Zugänge funktionieren Watchlist, Journal, Bewertungsrechner und das klar markierte synthetische Bedienbeispiel.

## Auf Vercel bereitstellen

1. Dieses Repository in Vercel als neues Projekt importieren. Repository-Branch: **flux**. Root Directory: Repository-Wurzel. Die Konfiguration liegt in `vercel.json`; der ASGI-Einstieg ist `api/index.py`. Kein separates Frontend-Build erforderlich.
2. Eine dauerhafte PostgreSQL-Datenbank verbinden, zum Beispiel über eine vom Nutzer gewählte Vercel-Marketplace-Integration. Die Verbindungszeichenfolge als **DATABASE_URL** hinterlegen. Für Produktion und Vorschau getrennte Datenbanken und Zugangsschlüssel verwenden. Der Code legt seine `pia_`-Tabellen an; Tabellen anderer Anwendungen werden nicht verändert.
3. **PIA_ACCESS_KEY** mit mindestens 32 zufälligen Zeichen hinterlegen. Erzeugen beispielsweise mit `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Benutzername: **pia**, optional über `PIA_USERNAME` ändern. Die App zeigt ein eigenes Anmeldeformular und setzt nach erfolgreicher Anmeldung ein sicheres, für zwölf Stunden gültiges Sitzungscookie. Über „Abmelden“ wird die Sitzung auf diesem Gerät beendet. Explizite API-Clients können weiterhin HTTP Basic Authentication verwenden. Nur über HTTPS betreiben. Keine Zugangsdaten in URLs einbauen.
4. Für Live-Recherche **PIA_PROVIDER**, **PIA_MODEL_ID** und **BRAVE_API_KEY** setzen. Bei `PIA_PROVIDER=anthropic` zusätzlich **ANTHROPIC_API_KEY**. Für `bedrock` zusätzlich eine passende **PIA_AWS_REGION** und sichere AWS-Zugangsdaten mit minimal erforderlichen Bedrock-Rechten. Die konkrete Modell-ID muss im eigenen Konto verfügbar sein. Keine Schlüssel im Chat oder im Repository hinterlegen.
5. Deploy ausführen. Nach Änderungen der Umgebungsvariablen erneut deployen. Zuerst Anmeldung, Demo, Export und Wiederaufruf gespeicherter Einträge prüfen, dann den Verbindungstest und eine kleine Live-Recherche.

Fehlen Passwort oder Datenbank, bleibt die App mit HTTP 503 gesperrt. Es gibt im Onlinebetrieb **keinen unsicheren Rückfall auf eine temporäre Datenbank**. Die Oberfläche und alle API-Routen sind nach Einrichtung geschützt. Online-Zugänge werden ausschließlich über die Deployment-Umgebung verwaltet; die App bietet online keine Speicherung von Schlüsseln an.

## Speicherung und Laufzeit

Die direkte Claude-Anbindung verwendet strukturierte JSON-Ausgaben über `output_config.format`. Die vollständigen Pydantic-Regeln und Quellenprüfungen bleiben anschließend aktiv. Von der API nicht unterstützte Längen- und Zahlenlimits werden zusätzlich als Format-Hinweise übertragen und weiterhin lokal geprüft. Nur eindeutige Unterschiede in der Groß-/Kleinschreibung vorgegebener Kategorien werden vereinheitlicht. Ungültige Antworten werden nicht durch automatische kostenpflichtige Wiederholungsaufrufe repariert. Bei Schemafehlern speichert der betroffene Lauf lediglich Feldpfad und Fehlercode für die Diagnose, keine ungeprüfte Rohantwort. Siehe [Anthropic Structured Outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs).

Online werden Mandat, Watchlist, Berichte und Journal in PostgreSQL gespeichert. Im lokalen Betrieb bleiben sie in `data/pia.sqlite3`. Ein bestehender lokaler Datenbestand wird nicht automatisch hochgeladen. Regelmäßig das Archiv exportieren; ein Import früherer SQLite-Daten ist noch nicht implementiert.

Im Onlinebetrieb legt der erste Request einen Rechercheauftrag an. Der Browser startet einen zweiten, langen Request für dessen Ausführung und fragt den Fortschritt separat ab. Es läuft **kein Hintergrund-Thread nach einer Serverless-Antwort**. Die Ausführung hat ein kooperatives Zeitbudget von 240 Sekunden; Vercel ist für maximal 300 Sekunden konfiguriert. Große Recherchen können trotzdem abbrechen. Ein abgebrochener Auftrag wird nach sechs Minuten als unterbrochen markiert und niemals automatisch kostenpflichtig wiederholt. Die endgültige Funktionsdauer muss zum gewählten Vercel-Tarif passen.

## Öffentliches Repository, private Daten

Das Repository ist öffentlich. Persönliche Kapitalstände und Einzahlungsbeträge sind entfernt; die Vorlage beginnt mit neutralen Werten. Tatsächliche Werte erst nach Anmeldung im Anlagemandat eintragen. `.env`, Datenbanken, Schlüsseldateien und private Exporte nicht committen. Dieses Repository enthält keine tatsächlichen Depotpositionen.

Eine lokale Hash-Kette ist keine vollständige Unveränderbarkeitsgarantie und kein vertrauenswürdiger externer Zeitstempel. Für zusätzliche Kontrolle den Kopf-Hash außerhalb der Anwendung sichern. Research ist ein prüfbedürftiger Entwurf: kein Live-Kursfeed, keine verifizierte Trade-Republic-Handelbarkeit, keine automatische Steuerberatung, keine Orders.

## Tests

```sh
pip install -r requirements-dev.txt
python -m pytest -q
```

Siehe `DEPLOYMENT.md` für den verbleibenden Live-Abnahmetest. Ein grüner lokaler Testlauf ersetzt weder den echten Datenbank- noch den Plattformtest.
