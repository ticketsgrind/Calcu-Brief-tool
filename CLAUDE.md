# CLAUDE.md

Deze repository is in het Nederlands: code, commentaar, variabelenamen,
commitberichten en documentatie. Zie ook `README.md` voor de indeling en hoe
de tool te starten.

## Wat dit is

De samenvoeging van twee eerder losse tools (calculatietool + brieventool)
tot één app: stap 1 is de calculatie, stap 2 de offertebrief, met een
overdracht ertussen die nooit gokt. Zie `README.md` §Herkomst voor de
achtergrond van die samenvoeging.

## De architectuurregel: één plek per berekening

`calculatie/rekenkern.py` is de ENIGE plek die de marge/uren/afgeleide
materiaalregels uitrekent, en `brieventool/samenstellen.py` de enige plek die
bepaalt wat er in de brief komt te staan. Het scherm (`scherm/*.js`) rekent
zelf niets uit: elke wijziging gaat naar `POST /bereken` resp. `POST /brief`
en het scherm tekent alleen het antwoord. Voeg nooit een tweede
implementatie van een rekenregel of blokselectie toe aan de JS-kant, ook niet
"voor de snelheid" — dat is precies het risico dat deze samenvoeging moest
oplossen (calculatie en brief die een ander bedrag laten zien).

Wat wél client-side blijft: triviale, niet-interpretatiegevoelige arithmetiek
(`regelTotaal`/`lijstTotaal` in `scherm/calculatie.js` — gewoon aantal ×
prijs) en het zoeken/bladeren in de materiaalcatalogus. Dat is opzoeklogica,
geen rekenregel, en dupliceert dus niets business-kritisch.

## `overdracht.py`: nooit gokken, wel afleiden

Drie statussen per veld, zie de moduledocstring:
- **direct** — simpele overname (datum, verkoopprijs).
- **afgeleid** — een toegepaste regel met een niet-triviale aanname; krijgt
  in het scherm altijd het label "afgeleid — controleer"
  (`overdracht.VeldOverdracht`, gerenderd via `controleBadge()` in
  `scherm/brief.js`). De systeemsoort-vertaling (calculatie se grove
  VRF/RAC/PAC/Overig → de fijnere indeling van de brief) is hier het
  voorbeeld: RAC/PAC met 1 binnendeel wordt splitsystem, met meer een
  multi-splitsystem — ook als het in werkelijkheid meerdere losse
  splitsystemen zijn. Vandaar altijd het controleer-label.
- **keuze_nodig** — de calculatie bevat de informatie niet; het veld blijft
  leeg. "Overig" kan zowel warmtepomp als vloeistofkoelmachine zijn en krijgt
  daarom nooit een gok, altijd een lege keuze met beide opties.

Een `keuze_nodig`- of leeg veld hoeft geen aparte "ontbreekt"-lijst: zodra
het een normaal offerte-veld is loopt het gewoon door de bestaande
`brieventool/controle.ontbrekende_gegevens()`. **`systeemsoort` is om die
reden toegevoegd aan `controle.INSTALLATIEVELDEN`** (was er niet in de
losstaande brieventool, omdat daar nog geen formulier bestond en elke
offerte met de hand in YAML werd geschreven) — zonder systeemsoort matcht
geen enkel blok in de sectie "systeemomschrijving" en blijft die
installatieregel stilzwijgend zonder omschrijving.

## `bibliotheek.velden()`: geen hardcoded keuzelijsten

Facturering, betaling, condensafvoer, bediening, opstelling_buitenunit,
aanleiding, technische_specificaties en de werkzaamhedenlijsten hardcoderen
hun mogelijke waarden nergens in `scherm/brief.js`. `bibliotheek.velden()`
leidt ze af uit de voorwaarden in `analyse/teksten.yaml` zelf (`veld ==
'waarde'` → losse keuze, `'waarde' in veld` → checkbox-lijst, kale naam →
vinkje). Voeg je een nieuwe factureringsvariant toe aan `teksten.yaml`, dan
verschijnt die vanzelf in het formulier — geen codewijziging nodig. Alleen
`klanttype`, `installatietype`, `aanspreekvorm`, `documentsoort` en de
per-installatie velden (`systeemsoort`, `montagewijze`) zijn wél hardcoded in
`scherm/brief.js`: die zijn structureel (sturen te veel andere velden, of
hebben geen `omschrijving`-blok om de waarde uit af te leiden) en veranderen
zelden. `meerprijs_coating`/`meerprijs_ral` gedragen zich in `teksten.yaml`
als vlag (elk bedrag > 0 is "waar") maar zijn een bedrag, geen ja/nee — ze
staan daarom expliciet uitgezonderd van de generieke vinkjes-render
(`BEDRAG_VLAGGEN` in `scherm/brief.js`).

## `scherm/*.js` staan zonder modules naast elkaar

`calculatie.js` en `brief.js` worden allebei als gewoon `<script>` geladen
(geen `type=module`) en delen dus één globale scope met `gedeeld.js`. Beide
zijn daarom in een IIFE gewrapt — zonder dat botsen hun `const`/`let` op
topniveau (was ook meteen de eerste bug bij het testen: `eur`/`pct` werden in
allebei gedestructureerd uit `CB`). Voeg een derde scherm-bestand toe? Wrap
het ook in een IIFE, of zet het als module.

## Server-static-bestanden: het pad-voorvoegsel is verplicht

`server.py` serveert `scherm/` en `data/` alleen onder hun eigen
voorvoegsel (`/scherm/app.js`, `/data/foo.json`) — nooit op de root. HTML/JS
die naar deze bestanden verwijst moet dus `scherm/...` schrijven, niet een
kale bestandsnaam (die zou naar `/bestand.js` resolven, wat een 404 geeft).

## De dubbelklik-opstarters gaan uit van hun plek in de projectmap

`Calcu-Brief-tool.app` (Mac) en `start-app.pyw`/`start.bat` (Windows) vinden
`server.py` via een relatief pad vanaf hun eigen locatie — ze moeten dus
in de projectmap blijven staan. Een `.app` die je los naar het Bureaublad
sleept, verliest die relatie; een Finder-alias (of op Windows een
snelkoppeling) niet, vandaar dat de README dat aanraadt in plaats van
verplaatsen/kopiëren. macOS start een `.app`-bundel headless (geen
Terminal-venster): `Contents/MacOS/start` toont fouten daarom als
`osascript display alert` in plaats van ze te printen, en logt de server
zelf naar `.calcubrief-server.log` (gitignored) voor het geval de melding
niet genoeg zegt. Windows-equivalent: `start-app.pyw` draait via
`pythonw.exe` (geen console) en gebruikt `tkinter.messagebox` voor
foutmeldingen.

## De standalone build: `--onedir`, niet `--onefile`

`.github/workflows/build-app.yml` bouwt met PyInstaller op GitHub's eigen
Windows-/Mac-runners (een .exe/.app is niet vanaf Linux te cross-compileren).
Windows gebruikt expliciet `--onedir`: een `--onefile`-.exe pakt zichzelf bij
**elke** start opnieuw uit naar een tijdelijke map voordat er ook maar één
regel Python draait — met het laadscherm-filmpje erbij (~7MB) merkbaar genoeg
om, in combinatie met een dubbelklik die daarna ook nog op de browser moet
wachten, als "traag opstarten" op te vallen. `--onedir` slaat die uitpakstap
over; de prijs is dat de download een map is (`CalcuBriefTool-windows.zip`
uitpakken, `CalcuBriefTool.exe` **in** die map dubbelklikken) in plaats van
één los bestand. Mac gebruikt sowieso al `--onedir` (PyInstaller's eigen
standaard, alleen Windows had `--onefile` nodig gehad om er één bestand van
te maken) — vandaar dat daar niets hoefde te veranderen.

`server.py`'s `WORTEL`/`DATA_MAP`/`SJABLOON`/`SCHERM_MAP` (frozen-detectie via
`sys.frozen`/`sys._MEIPASS`, zie de constante bovenin het bestand) werken
voor beide PyInstaller-modi identiek: `sys._MEIPASS` wijst bij `--onedir` naar
de map naast de `.exe` in plaats van een tijdelijke uitpakmap, maar de code
hoeft dat onderscheid niet te kennen.

## Laadscherm: twee lagen, met opzet gescheiden

**Laag 1 — `scherm/splash.html`, het filmpje.** `server.py:start()` opent de
browser altijd hier eerst (niet op `/`), pas ná het laden van bibliotheek en
calculatiegegevens — de server is dus al klaar op het moment dat dit scherm
draait. Het speelt `scherm/laadscherm.mp4` (staand formaat, 10,24s, afgeleid
uit de mp4-boxen zelf met een klein scriptje, niet afgespeeld — deze omgeving
kon de video niet decoderen om te bekijken) helemaal af en schakelt dan pas
door naar `/` (`location.replace`). Dat "helemaal afspelen, dan pas de tool"
is een expliciete eis (niet zomaar een "tot het geladen is"-vangnet): omdat
de server al klaar is tegen de tijd dat dit scherm opent, hoeft er verder
nergens op gewacht te worden. Terugval bij een niet-afspeelbare video: zowel
een `error`-listener als (want niet elke browser stuurt daadwerkelijk een
`error`-event bij een ontbrekende codec) een noodrem van 15s. Bewust geen
afhankelijkheid van `gedeeld.js`/`calculatie.js`/`brief.js`: dit bestand moet
werken voordat er verder nog iets anders geladen is.

**Laag 2 — de overlay in `scherm/index.html`** (`#laadscherm`, spinner-only,
geen video meer sinds het filmpje naar `splash.html` is verhuisd) dekt alleen
de eigen, veel kortere data-ophaal-stap van de tool zelf af: verdwijnt pas
als zowel `CB.calc.klaar` als `CB.brief.klaar` zijn opgelost (zie de inline
`<script>` onderaan dat bestand), dus na de materiaalcatalogus/YIMM/
Panasonic/Daikin-data, `/keuzes` en de eerste `/bereken`-ronde. Voeg je een
nieuwe async opstartstap toe aan een van beide stappen, neem die dan op in de
`klaar`-promise van die stap, anders verdwijnt deze overlay te vroeg. Deze
laag bestaat vooral voor wie rechtstreeks op `/` uitkomt zonder via de splash
te zijn gegaan (bijv. een herlaadde pagina) — `MINIMALE_DUUR_MS` staat hier
daarom laag (300ms, alleen om een flits-en-weg-effect te voorkomen), niet
hoog zoals toen deze laag zelf nog de video liet zien.

**Waarom niet één laag?** Het `.exe`-opstartmoment (dubbelklikken tot de
browser opent) valt buiten wat een pagina kan dekken — daar draait nog geen
JavaScript. `splash.html` bestaat specifiek om dát moment te vullen met iets
zichtbaars, onafhankelijk van hoe snel de rest daarna laadt.

## Git

Ontwikkel op de branch `claude/magical-davinci-63dmec`. Commitberichten in
het Nederlands, beschrijvend (niet gebiedende wijs, niet verleden tijd), met
uitleg van het waarom bij niet voor de hand liggende keuzes.
