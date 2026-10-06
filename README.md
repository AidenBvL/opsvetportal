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
| **Ruilverzoeken** | Een medewerker vraagt een collega om een dienst over te nemen (of te ruilen tegen een dienst van die collega). De collega accepteert, een planner keurt goed, en daarna wordt het rooster automatisch aangepast. De planner ziet vooraf of de ruil een spelregel overtreedt. Bij elke stap gaat er een e-mail uit. |
| **E-mailmeldingen** | Elke gebruiker kiest zelf welke mails hij krijgt (*Mijn e-mailmeldingen*): schipwissel, ETA verschoven (vanaf X uur), actie toegewezen, escalaties, een dagoverzicht in de ochtend en een herinnering de dag vóór een dienst. Zendingmeldingen kunnen voor *eigen dossiers* of *alle dossiers*. |
| **Klantportaal** | Je maakt vanaf de klantpagina klantaccounts aan. De klant krijgt een link om zelf een wachtwoord in te stellen, en ziet alleen eigen containers, ETA's, schipwissels, keuringsstatus en transporten. Kosten, acties, notities en de rest van het portaal blijven afgeschermd. |
| **Wijzigingslog** | Van elke wijziging wordt vastgelegd wie wat wanneer heeft aangepast (oude → nieuwe waarde). Dit is per dossier te zien (klant, container, transport, actie) en in een totaaloverzicht met filters. Automatische wijzigingen, zoals tracking, staan erin als "systeem". |
| **Zoeken** | De zoekbalk bovenin zoekt op container, referentie, B/L, CHED, schip, kenteken of klant. |

## Werken met het portaal

- **Zoeken:** druk op `/` (of Ctrl+K) en zoek op container, B/L, referentie, CHED, schip of klant.
- **Nieuw:** de knop **+ Nieuw** rechtsboven maakt een container, transport, actie of klant aan, vanaf elke pagina.
- **Voor jou:** het belletje toont je open acties, ruilverzoeken en overlegvragen; het menu toont tellers voor CHED's en escalaties.
- **Thema:** licht of donker via het maan-icoon; het menu klap je in onderaan de zijbalk.
- **Zeevracht:** filterpillen (aankomst ≤ 7 dagen, keuring lopend, CHED aanmelden, schipwissels, vrije dagen bijna op), sorteerbare kolommen en export naar CSV.
- **Containerdossier:** reisvoortgang van laadhaven naar Rotterdam, aftellen tot de ETA en de vrije dagen, snel de status, keuring en douane bijwerken, en de knop **Bekijk bij rederij**.
- **Plak tracking:** kopieer de trackingpagina van de rederij (Ctrl+A, Ctrl+C) en plak die in het dossier. Het portaal haalt schip, reis, ETA, laadhaven, terminal en vertrekdatum eruit en meldt een schipwissel. Werkt zonder API of abonnement.

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

De `scheduler`-service ververst elke 30 minuten de ETA's en verstuurt om `DAILY_DIGEST_TIME` het
dagoverzicht en de dienstherinneringen. Zonder Docker gebruik je cron voor `refresh_tracking` en
`send_daily_mails`. Stel voor de e-mails de SMTP-gegevens en `PORTAL_BASE_URL` in (zie `.env.example`).

## Online zetten met Render (automatisch bijgewerkt vanuit GitHub)

1. Maak een account op render.com en koppel je GitHub-account.
2. Kies **New → Blueprint** en selecteer deze repository. Render leest `render.yaml` en maakt
   de webserver en de PostgreSQL-database aan.
3. Kies de branch waarvan Render moet bouwen. Elke push naar die branch wordt daarna automatisch
   gebouwd en live gezet (`autoDeploy: true`).
4. Vul in het Render-dashboard de geheime instellingen in: `TERMINAL49_API_KEY`,
   `DJANGO_ADMIN_USERNAME`, `DJANGO_ADMIN_EMAIL`, `DJANGO_ADMIN_PASSWORD` en (voor e-mail) de
   `EMAIL_*`-instellingen. Bij de eerste start worden de tabellen, de rollen, het team en de
   beheerder automatisch aangemaakt.
5. Laat een gratis cronservice (bijv. cron-job.org) elke 10 minuten
   `https://<jouw-app>.onrender.com/cron/<CRON_TOKEN>/` aanroepen. Het `CRON_TOKEN` staat bij de
   instellingen van de webservice. Dit ververst de ETA's, verstuurt de dagelijkse mails en houdt de
   gratis server wakker.

Let op bij het gratis plan: de server slaapt na 15 minuten zonder verkeer, de gratis database
verloopt na 30 dagen en geüploade documenten verdwijnen bij een herstart. Voor echt gebruik:
het betaalde plan (vanaf ongeveer $7 per maand plus database) of een server via IT.

## ETA en zeeschip via API (gratis)

De gratis route loopt rechtstreeks via de API's van de rederijen. Bijna alle grote rederijen
gebruiken dezelfde DCSA Track & Trace-standaard, die het portaal al ondersteunt. Per rederij maak je
een (gratis) developer-account aan en vul je de gegevens in bij *Stamgegevens → Rederijen*:

| Rederij | Waar aanvragen | Wat je invult |
|---|---|---|
| Maersk (ook Hamburg Süd) | developer.maersk.com, self-service | API base URL, `Consumer-Key` (env var) + OAuth2 token-URL, client-ID en client-secret (env vars) |
| Hapag-Lloyd | api-portal.hlag.com, self-service (bèta) | API base URL + API-sleutel (env var) |
| CMA CGM (ook APL/ANL) | api-portal.cma-cgm.com | API base URL + publieke API-sleutel, of OAuth2 voor de private API |
| MSC, ONE, Evergreen, COSCO, ZIM | via de accountmanager / het developerportaal van de rederij | afhankelijk van de rederij: API-sleutel of OAuth2 |

Zet de sleutels zelf **niet** in de database maar in omgevingsvariabelen (bijv. `MAERSK_API_KEY`),
en vul in het portaal alleen de *naam* van die variabele in.

Per rederij stel je een tracking provider in:

- **`mock`**: demodata met kleine ETA-verschuivingen en af en toe een schipwissel, om het portaal te testen zonder API-sleutels.
- **`dcsa`**: de [DCSA Track & Trace](https://dcsa.org/standards/track-and-trace/) REST-standaard (v2.2 en v3). Die wordt ondersteund door onder andere Maersk, Hapag-Lloyd, CMA CGM, ONE, Evergreen en ZIM. Vul de API base URL in, en de naam van de omgevingsvariabele waarin de API-sleutel staat (de sleutel zelf komt niet in de database).
- **`none`**: geen automatische tracking voor deze rederij.

Een rederij zonder eigen API kun je later via een betaalde aggregator (bijv. ShipsGo of Vizion) of
via Portbase toevoegen. Wil je een andere bron toevoegen, zoals Portbase, Vizion, Terminal49 of ShipsGo? Schrijf dan een klasse
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
customer_portal/  afgeschermd klantportaal
```
