# Deployment-Abnahme

## Lokal geprüft

- Automatisierte Tests: bestehende Logik plus Authentifizierung, Cross-Origin-Sperre, CSRF, neutrale öffentliche Kapitalvorgaben, Umgebungsvariablen-Verwaltung und explizite einmalige Request-Ausführung.
- Syntaxprüfung der JavaScript-Module.
- Cloud-Testdouble verwendet SQLite; keine Behauptung einer echten PostgreSQL-Prüfung.

## Noch nicht durchgeführt

- Import und Build im tatsächlichen Vercel-Konto.
- PostgreSQL-Verbindung, Tabellenanlage, gleichzeitige Requests und Persistenz über echte Neustarts hinweg.
- Live-Aufrufe bei Brave, Bedrock oder Anthropic mit echten Zugangsdaten.
- Tarifabhängiges Serverless-Laufzeitverhalten.

## Nach dem Deploy prüfen

1. Ohne Anmeldung muss eine Browser-Navigation zur Login-Seite führen. Nur Login-Formular und dessen Stylesheet sind öffentlich; App-Assets, APIs und Exporte bleiben geschützt. Falsche Zugangsdaten müssen einen Fehler im Formular zeigen. Danach Anmeldung, Seitenneuladen, Abmelden und erneute Anmeldung prüfen; es darf kein nativer Basic-Anmeldedialog erforderlich sein.
2. Nach Anmeldung Mandat ändern, Watchlist-Eintrag erstellen, Bedienbeispiel erzeugen und Entscheidung speichern.
3. Neu deployen; gespeicherte Einträge müssen erhalten bleiben.
4. Archiv exportieren und prüfen, dass keine Provider- oder Datenbank-Zugangsdaten enthalten sind.
5. Verbindungstest ausführen und dann mit einem Kandidaten recherchieren. Fortschritt, Bericht, Abbruch und fehlgeschlagene Quellen prüfen.
6. Einen unterbrochenen Auftrag nicht automatisch neu ausführen; vor einem manuellen Neustart Kosten und vorherige Ergebnisse prüfen.

Erst danach als produktiv abgenommen bezeichnen. Keine personenbezogenen Forschungsfragen oder unveröffentlichten Depotdaten an die Websuche senden.
