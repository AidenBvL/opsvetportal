# OPS/VET Portaal

Intern portaal voor het OPS/VET-team van Cory Brothers: rooster en agenda, dagelijkse overleggen,
acties en escalaties met extra kosten, en een overzicht van inkomende zeecontainers en wegtransporten.
Het is gebouwd met Django 5.2 en draait op SQLite (lokaal) of PostgreSQL (productie).

## Onderdelen

| Onderdeel | Wat het doet |
|---|---|
| **Agenda & rooster** | Maakt automatisch het thuiswerkschema en de avond- en zaterdagdiensten per maand (spelregels hieronder). Je kunt het rooster als concept bekijken en daarna vaststellen. Diensten en thuiswerkdagen zijn handmatig aan te passen, met een waarschuwing als een spelregel wordt overtreden. Je exporteert het rooster naar Excel (zelfde opzet als het oude bestand) en elke medewerker heeft een persoonlijke ICS-agendafeed voor Outlook, Google of iPhone. |
| **Overleggen** | Per dag drie blokken: ochtend, middag en einde dag. Een vraag of onderwerp koppel je aan collega's, een klant, een container of een wegtransport. Elk punt kun je beantwoorden, doorschuiven naar het volgende overleg of in één klik omzetten naar een actie of escalatie. |
| **Acties & escalaties** | Kanban-dashboard met escalatieniveaus 1 t/m 4, deadlines, eigenaren en filters op klant en eigenaar. Elke actie kan extra kosten krijgen, met als verantwoordelijke **klant / wij (Cory Brothers) / vervoerder / overmacht** en een status (door te belasten, geclaimd, afgeboekt…). |
| **Extra kosten** | Totalen per verantwoordelijke en per klant, filters op periode, export naar CSV. |
| **Zeevracht** | Per container: klantreferentie, Cory-referentie, containernummer (gecontroleerd volgens ISO 6346), rederij, B/L, schip en reis, ETA/ATA, keurpunt, CHED-nummer, keuringsstatus, vrije dagen (demurrage), temperatuur, enz. Je kunt meerdere containers tegelijk aanmaken. |
| **Tracking** | Haalt automatisch de nieuwste ETA en het zeeschip op. Als een container naar een ander schip is overgezet, krijg je een rode melding met het oorspronkelijke schip, en wordt er automatisch een actie aangemaakt. De volledige trackinghistorie wordt per container bewaard. |
| **Wegtransport** | Vervoerder, kentekens, chauffeur, CMR, laad- en losmomenten en keuring. Te koppelen aan een zeecontainer: de gegevens worden dan alvast ingevuld. |
| **Documenten** | Upload een B/L, arrival notice of CHED. Het portaal leest de tekst uit (tekstlaag van de PDF, of OCR met Tesseract) en herkent containers, zegels, het containertype, B/L, booking, schip en reis, ETA, POL/POD, CHED, klantreferentie, temperatuur en goederen. Daarna controleer je de gegevens en maak je de dossiers aan; bestaande dossiers worden aangevuld in plaats van dubbel aangemaakt. |
| **Stamgegevens** | Klanten (naam, nationaliteit, adres, btw, EORI, contactpersoon, accountmanager, werkinstructies), rederijen (SCAC en API-instellingen), vervoerders en keurpunten (TRACES/BCP-code, openingstijden). |
| **Accounts & rechten** | Accounts aanmaken, rollen toewijzen (Beheerder, Planner, Operations, Alleen lezen) en per account extra rechten aanvinken in een rechtenmatrix (bekijken / toevoegen / wijzigen / verwijderen per onderdeel). Een account koppel je aan een medewerker. |
| **Zoeken** | De zoekbalk bovenin zoekt op container, referentie, B/L, CHED, schip, kenteken of klant. |

## Spelregels van de roostergenerator

De regels komen uit het oude Excel-rooster en zijn per medewerker in te stellen onder *Medewerkers*:

1. Elke medewerker werkt het ingestelde aantal dagen per week thuis (standaard 1, Jarno 2, Aiden 0).
2. Collega's uit dezelfde afdelingsgroep werken nooit op dezelfde dag thuis, en ook nooit op de dag direct na de thuiswerkdag van een groepsgenoot.
3. Een vaste vrije dag (Desley: woensdag) wordt nooit een thuiswerkdag of dienstdag.
4. Op elke avond- en zaterdagdienst staat 1 persoon, en niemand heeft twee dagen achter elkaar dienst.
5. Wie op zaterdag dienst heeft, heeft in die werkweek geen avonddienst. Dit geldt ook over de maandgrens heen.
6. **Aiden heeft nooit dienst op maandag** (instelling "geen dienst op: maandag", vanwege zijn schooldag).
7. Afwezigheid en feestdagen worden overgeslagen. De Nederlandse feestdagen staan er al in.
8. Wie thuiswerkt, krijgt waar mogelijk die dag ook de avonddienst.
9. Diensten worden eerlijk verdeeld (ook zaterdagen) en rouleren over de weekdagen.
10. Handmatige wijzigingen (gemarkeerd met `*`) blijven staan als je opnieuw genereert. Een rooster dat is *vastgesteld* wordt niet meer overschreven.

Genereren kan via de knop in de agenda, of automatisch in de laatste week van de maand:
`python manage.py generate_roster` (zonder argumenten maakt dit het rooster voor volgende maand).

## Lokaal starten

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_portal --demo     # rollen, team, rederijen, feestdagen (+ voorbeelddata)
python manage.py createsuperuser
python manage.py generate_roster --jaar 2026 --maand 11
python manage.py runserver
```

Tests draaien: `python manage.py test`

Voor OCR van gescande documenten installeer je Tesseract: `apt install tesseract-ocr tesseract-ocr-nld`.
Tekst-PDF's werken ook zonder Tesseract.

## Productie (Docker)

```bash
cp .env.example .env   # vul DJANGO_SECRET_KEY, hosts en wachtwoorden in
docker compose up -d --build
docker compose exec web python manage.py seed_portal
docker compose exec web python manage.py createsuperuser
```

De `tracking`-service ververst elke 30 minuten de ETA's. Plan ook een maandelijkse cronjob voor
`generate_roster`.

## ETA en zeeschip via API

Per rederij stel je onder *Stamgegevens → Rederijen* een tracking provider in:

- **`mock`**: demodata met kleine ETA-verschuivingen en af en toe een schipwissel, om het portaal te testen zonder API-sleutels.
- **`dcsa`**: de [DCSA Track & Trace](https://dcsa.org/standards/track-and-trace/) REST-standaard (v2.2 en v3). Die wordt ondersteund door onder andere Maersk, Hapag-Lloyd, CMA CGM, ONE, Evergreen en ZIM. Vul de API base URL in, en de naam van de omgevingsvariabele waarin de API-sleutel staat (de sleutel zelf komt niet in de database).
- **`none`**: geen automatische tracking voor deze rederij.

Wil je een andere bron toevoegen, zoals Portbase, Vizion, Terminal49 of ShipsGo? Schrijf dan een klasse
in `shipments/tracking/` die `track(shipment)` implementeert, en registreer die in `PROVIDERS`.

## Projectstructuur

```
config/      settings en URL's
core/        stamgegevens, accounts/rechten, dashboard, generieke CRUD
planning/    medewerkers, afwezigheid, roostergenerator (generator.py), agenda, ICS, Excel
meetings/    dagelijkse overleggen (ochtend / middag / einde dag)
actions/     acties, escalaties, extra kosten
shipments/   zeevracht, wegtransport, tracking providers
documents/   upload + tekstherkenning (parser.py)
```
