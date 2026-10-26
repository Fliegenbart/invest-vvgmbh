# PIA — Investment Research Assistant

Persönlicher Rechercheassistent für langfristigen Vermögensaufbau im eigenen GmbH-Vermögen. Recherche, Watchlist, nachvollziehbare Bewertungsrechnungen und Entscheidungsjournal — keine Handelsrechte und keine Broker-Zugangsdaten.

## Status

Die lokale App wird hier als Quellcode hinterlegt und um eine private Vercel-Konfiguration ergänzt. Ein tatsächliches Vercel-Deployment ist noch nicht erfolgt.

Das Repository ist öffentlich. Persönliche Kontostände, Einzahlungen, echte API-Schlüssel, Datenbanken und Exporte gehören **nicht** in Git. Die öffentlichen Kapitalvorgaben sind deshalb neutral; tatsächliche Werte werden erst in der privaten Anwendung eingetragen.

## Onlinebetrieb

Vercel benötigt `PIA_ACCESS_KEY` (mindestens 32 zufällige Zeichen) und `DATABASE_URL` (PostgreSQL). Ohne diese Voraussetzungen bleibt die Anwendung gesperrt. Zugangsdaten für Modell und Websuche werden ausschließlich in den Umgebungsvariablen der Deployment-Plattform verwaltet.

Live-Aufrufe mit echten Modellschlüsseln sowie die Vercel- und PostgreSQL-Integration müssen nach dem Verbinden geprüft werden. Keine automatische Anlageempfehlung oder garantierte Rendite.
