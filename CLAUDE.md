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

## Git

Ontwikkel op de branch `claude/magical-davinci-63dmec`. Commitberichten in
het Nederlands, beschrijvend (niet gebiedende wijs, niet verleden tijd), met
uitleg van het waarom bij niet voor de hand liggende keuzes.
