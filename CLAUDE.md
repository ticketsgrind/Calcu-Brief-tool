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
- **afgeleid** — een toegepaste regel met een niet-triviale aanname. De
  systeemsoort-vertaling (calculatie se grove VRF/RAC/PAC/Overig → de fijnere
  indeling van de brief) is hier het voorbeeld: RAC/PAC met 1 binnendeel
  wordt splitsystem, met meer een multi-splitsystem — ook als het in
  werkelijkheid meerdere losse splitsystemen zijn.
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

**De koppeling zit in `scherm/brief.html`, niet in `overdracht.py` zelf** —
zie de sectie "De briefstap is 1-op-1 overgenomen" hieronder voor waar en
hoe. Voor de "afgeleid"-status geldt daar: dit scherm heeft geen los
badge-per-veld-systeem zoals eerder werd geprobeerd; in plaats daarvan noemt
`vulVanuitCalculatie()` de afgeleide velden expliciet in een melding na de
overdracht, zodat "nooit stilzwijgend" behouden blijft zonder de
overgenomen UI te hoeven aanpassen.

**Btw bij overdracht.** De calculatie rekent altijd exclusief btw (er is geen
klanttype-begrip in stap 1). `overdracht.zet_over()` krijgt daarom optioneel
`klanttype` mee (door `scherm/brief.html` meegestuurd als de huidige waarde
van `A.klanttype` op het moment van de klik) en telt er 21% bij op vóór het
bedrag in `prijsregels` komt, maar alleen bij `klanttype == "particulier"`
-- onbekend/leeg klanttype blijft exclusief, nooit een gok welke kant op.
Wordt klanttype pas ná de eerste overdracht ingesteld, dan klopt het bedrag
dus nog niet totdat de overdracht opnieuw wordt toegepast (de knop "↺ Vanuit
calculatie" in `scherm/brief.html`).

## Meerdere opties (bijv. Panasonic vs. Toshiba) in één project

Eén project kan meerdere volledig losse calculaties bevatten — "opties", elk
met een eigen tabblad boven de calculatie (`#optieBalk` in `scherm/index.html`,
gerenderd door `renderOptieBalk()`/`bindOpties()` in `scherm/calculatie.js`).
Op verzoek van Lars (29 september 2026): "Het zijn dan 2 losse calculaties...
welke dan worden samengevoegd in één brief. In de brief zul je dan zien bij
aanbieding optie A en optie B, en bij totaalprijs ook pos. A en pos. B." Elke
optie is bewust **volledig zelfstandig** — geen gedeelde installaties/uren/
uitbesteding tussen opties, op de projectgegevens (klant, adres, Q-nummer) na
(zie hieronder) — dit is dus geen variant-op-dezelfde-calculatie, maar
letterlijk een tweede, eigen calculatie ernaast.

**Aan de briefkant hoefde hiervoor niets te veranderen.** Een voorbeeldbrief
van Lars liet zien dat "pos. A"/"pos. B"-prijsregels en een eigen kopregel per
installatie-alternatief allebei al bestaande, al werkende mechanismen zijn in
de brieftool (zie `voorbeelden/zakelijk-cassette-meervoud.yaml`, het
`prijs_regel_positie`-blok in `analyse/teksten.yaml`, en de knop
"+ Prijspositie toevoegen" in `scherm/brief.html`) — een meerdere-opties-brief
was dus altijd al te maken, alleen niet vanuit de calculatiekant. Aan
`analyse/teksten.yaml`, `brieventool/samenstellen.py` of het Word-sjabloon is
voor deze functie dan ook niets gewijzigd.

**`overdracht.zet_meerdere_over()`** (`overdracht.py`) is de nieuwe, bredere
ingang; `zet_over()` is er nu een dunne wrapper omheen voor het geval van
precies één calculatie (identieke uitkomst, geen "positie" op de prijsregel —
dat zou een gewone, enkelvoudige brief onnodig een "pos. A"-label geven). Bij
twee of meer calculaties: installaties van alle opties worden na elkaar
geplakt (met doorlopende index voor de "controleer dit"-paden, dus niet per
optie herstartend bij 0), en elke optie krijgt een prijsregel met een positie
("pos. A", "pos. B", ... naar volgorde in de lijst, niet naar hoeveel opties
uiteindelijk een prijs hebben — anders zou een nog niet doorgerekende eerste
optie de tweede foutief "pos. A" laten heten). Projectbrede velden (datum,
Q-nummer, klantnaam) komen uitsluitend uit de EERSTE optie; zie de reden
hieronder.

**`server.py`'s `/overdracht`** accepteert `opties` (een lijst calculatie-
states) met voorrang boven het oudere `calculatie` (één state), voor
compatibiliteit met een eventueel nog niet-bijgewerkt scherm.

**Aan de calculatiekant** (`scherm/calculatie.js`) is `state` nog steeds de
invoer van precies de ACTIEVE optie — dat hield de rest van dit al grote
bestand ongemoeid. `opties`/`actieveOptieIndex` zijn er los naast gezet, met
`bewaarActieveOptie()` die `state` voor gebruik terugschrijft in
`opties[actieveOptieIndex].staat`. Een nieuwe optie krijgt de projectgegevens
(`meta`: klant, adres, Q-nummer, ...) van de optie waar hij vandaan werd
aangemaakt vooraf ingevuld — dat is precies waarom `overdracht.py` hierboven
alleen naar de EERSTE optie voor die velden kijkt: in de praktijk delen alle
opties toch al dezelfde projectgegevens. Installaties/materiaal/uren/etc.
starten voor een nieuwe optie wél leeg — dat is het hele punt van "volledig
losse calculatie".

**Het projectbestand (versie 2)** bewaart nu `opties: [{naam, calculatie},
...]` + `actieveOptie` in plaats van één vlakke `calculatie` (versie 1).
`CB.optiesUitProject()` (`scherm/gedeeld.js`) zet een geopend of bewaard
bestand om naar de nieuwe vorm, met terugval op het oude formaat (als
"Optie A") zodat een bestaand opgeslagen bestand of browser-autosave van vóór
deze functie gewoon blijft werken. `scherm/brief.html`'s
`calculatieOptiesOphalen()` (voorheen `calculatieStaatOphalen()`, enkelvoud)
doet hetzelfde aan de briefkant, en stuurt bij "↺ Vanuit calculatie" nu de
hele lijst opties naar `/overdracht` in plaats van precies één calculatie.

**Naamgeving van de opties** ("Optie A", "Optie B", ..., met dubbelklik op de
tab om te hernoemen) is puur voor de gebruiker zelf, om tabs uit elkaar te
houden — de "pos. A"/"pos. B"-lettering in de brief volgt altijd de volgorde
in de lijst, nooit de zelfgekozen naam.

## Het ingevulde Excel-calculatieblad downloaden (`calculatie/calculatieblad.py`)

Op verzoek van Lars (29 september 2026, samen met de meerdere-opties-feature
hierboven): naast de calculatie in de tool zelf, ook een gevuld exemplaar van
het **oorspronkelijke Excel-bedrijfssjabloon** (`Template_Calculatieblad.xltx`,
door Lars aangeleverd, nu in `sjablonen/`) kunnen downloaden — "een ingevuld
calculatieblad (zoals wij eerst gebruikte)". De knop "Calculatieblad
downloaden" (`scherm/index.html`, naast "Calculatie opslaan als .json")
stuurt de ACTIEVE optie se `state` naar `POST /calculatieblad`
(`server.py`/`_calculatieblad`), die `calculatie/calculatieblad.py` aanroept
en de bytes van het resulterende `.xlsx`-bestand teruggeeft; de bestandsnaam
komt client-side tot stand (`calculatiebladBestandsnaam()` in
`scherm/calculatie.js`), net als bij het JSON-projectbestand.

**Per optie, niet gecombineerd.** Anders dan de brief (die alle opties
samenvoegt) is het calculatieblad altijd de export van precies één optie —
het sjabloon kent geen "meerdere opties"-begrip (dat is een verzinsel van
deze samenvoeging, alleen aan de briefkant), en "2 losse calculaties" (Lars
se eigen woorden) betekent hier dus ook gewoon 2 losse calculatiebladen: de
knop exporteert de optie die op dat moment open staat.

**Waarom kale ZIP+XML-manipulatie, net als `brieventool/sjabloon.py`.** Deze
ontwikkelomgeving kan geen `pip install openpyxl` doen (het sandbox-
netwerkbeleid blokkeert PyPI: "Host not in allowlist") en heeft ook geen
werkende LibreOffice Calc (`libreoffice-calc` staat niet naast `soffice`
zelf geïnstalleerd — zelfs een kaal, met de hand in elkaar gezet .xlsx-
bestand faalt hier met "source file could not be loaded"). Dat dwong tot
dezelfde aanpak die `sjabloon.py` al voor het Word-sjabloon gebruikt: de
`.xltx` is een ZIP met XML erin, en een cel overschrijven is tekst-vervanging
in die XML (`SheetSchrijver` in `calculatieblad.py`), niet een aparte
bibliotheek. Dat maakt het ook meteen consistent met hoe deze repo al Office-
bestanden genereert — geen nieuwe afhankelijkheid voor een taak die dit
project al eerder zonder kon.

**Elke cel die geld of uren voorstelt komt letterlijk uit
`rekenkern.bereken()`, nooit uit een Excel-formule die iets opnieuw
uitrekent.** Dit is dezelfde "één plek per berekening"-regel bovenaan dit
bestand, hier toegepast op de export: het sjabloon staat vol SUM/PRODUCT/
VLOOKUP-formules die in de oorspronkelijke, losstaande Excel-tool de hele
marge-opbouw deden. Die laten we bewust met rust qua *resultaat* — een
formule laten staan die op basis van onze letterlijke invoercellen (aantal,
tarief, ...) toevallig hetzelfde uitkomt was voor een aantal triviale
optel-/vermenigvuldigsommen (`H = PRODUCT(aantal, prijs)`, dezelfde categorie
als `regelTotaal`/`lijstTotaal` in `scherm/calculatie.js`) best verdedigbaar
geweest, maar bleek in de praktijk een risico: een uitbestedingsregel zonder
bekende prijs staat in het sjabloon als tekst `"op aanvraag"`, en
`PRODUCT(aantal, "op aanvraag")` kan een `#VALUE!`-fout geven die vervolgens
via de SUM-keten (`H417` → `Quotation sheet!R48` → `R59` → `R61` → ... →
`R76`) de hele verkoopprijs zou besmetten. Daarom schrijft `calculatieblad.py`
voor elke rij die het aanraakt (materiaal, uitbesteding, equipment, uren,
de hele marge-opbouw op Quotation sheet) de kant-en-klare waarde uit
`rekenkern.bereken()` direct in de cel, met de formule (`<f>`) verwijderd —
zie de moduledocstring voor de volledige redenering. De enige plekken die
zelf nog optellen zijn `calculatieblad.py` se eigen sectie-subtotalen
(`_sectie_totalen`) en de leesbare uren-uitsplitsing per monteur-regel
(`_monteur_termen`) — allebei met dezelfde triviale rekenkern-bouwstenen
(`rk.installatie_totalen`, `rk.leiding_meters`, ...), nooit een eigen
rekenregel.

**Scope: alleen de bladen "Calculatie" en "Quotation sheet" worden
aangeraakt.** De overige 14 tabbladen (Info, Mat. lijst, Budget voor admin,
YIMM, Parkeertarieven, ...) zijn óf pure naslag die niets met dit project te
maken heeft (YIMM, Parkeertarieven, Systemen, ...), óf een blad dat zelf via
een formule uit Quotation sheet/Calculatie put (Mat. lijst, Budget voor
admin) — voor dat laatste geval hoeft `calculatieblad.py` die formules niet
te snappen of te dupliceren: zodra Excel het bestand opent (`fullCalcOnLoad`
staat aan, zie hieronder) rekent het die vanzelf door op basis van de
inmiddels bevroren Calculatie-/Quotation-cellen. Bewust NIET geprobeerd: Mat.
lijst zelf al gevuld opleveren — dat blad gebruikt `FILTER`/`SORT`/`IMAGE()`
(Excel-365-only), functies die hier toch niet te verifiëren zijn (zie
hieronder) en die weinig toevoegen aan wat de tool se eigen "bestellijst"-
knop (`scherm/calculatie.js`) al biedt.

**Rijnummers komen uit `data/materiaal_catalogus.json`'s `row`-veld**, niet
uit een aparte opzoektabel in `calculatieblad.py` zelf — dat veld staat er al
sinds het overzetten van de rekenkern (zie "Materiaal" in
`analyse/01-rekenbladen-per-tabblad.md` van de losstaande calculatietool-
repo) en wijst per definitie naar precies de Excel-rij waar dat artikel
oorspronkelijk vandaan kwam. Voor uitbesteding/equipment bestaat zo'n veld
niet (die lijsten hebben geen rijnummer in hun Python-representatie); daarom
een losse naam→rij-koppeling (`UITBESTEDING_RIJEN`/`EQUIPMENT_RIJEN`) voor de
vaste standaardregels, met de 5 resp. 4 "lege" rijen aan het eind van elk
blok (412-416/424-428) voor eigen, met de hand toegevoegde regels. **Meer
eigen regels dan er lege rijen zijn?** Die extra regels krijgen dan geen
zichtbare rij in het blad — maar de TOTAALCEL (`H417`/`H429`) komt
rechtstreeks uit `rekenkern.bereken()`, dus het bedrag klopt hoe dan ook,
alleen de post-per-post-zichtbaarheid in het blad niet. Dat is in de
praktijk een zeldzame situatie (13 standaardregels + 5 eigen regels is al
ruim) en geen half werk: liever een correct totaal met een onvolledige
uitsplitsing dan een crash.

**`xl/calcChain.xml` wordt verwijderd** (plus zijn `Content_Types`- en
`workbook.xml.rels`-vermelding) in plaats van bijgewerkt: dat bestand is
Excel se eigen "volgorde om formules te herberekenen"-cache, en na het
verwijderen van zoveel formules zou het alleen nog verwijzingen naar
niet-bestaande formules bevatten — een klassieke bron van een "we hebben een
probleem met deze inhoud gevonden"-herstelmelding bij het openen. Excel bouwt
'm vanzelf opnieuw op. **`fullCalcOnLoad="1"`** wordt aan `xl/workbook.xml`
toegevoegd zodat de overgebleven formules (in de ongemoeide bladen, en de
paar triviale doorverwijzingen die wél bleven staan, zoals `Quotation
sheet!J6 = Calculatie!B2`) bij het openen vers doorrekenen op basis van de nu
bevroren cellen, in plaats van een verouderd gecachet nulletje te tonen. Het
`.xltx`-sjabloon-contenttype in `[Content_Types].xml` wordt omgezet naar een
gewone `.xlsx`-werkmap (anders opent Excel het resultaat als "nieuw document
gebaseerd op dit sjabloon" in plaats van als het bestand zelf).

**Getest zonder Excel of een werkende LibreOffice Calc.** Deze
ontwikkelomgeving heeft geen van beide (zie hierboven) — `tests/
test_calculatieblad.py` toetst daarom zelf, met dezelfde kale
`zipfile`/`xml.etree`-aanpak als de module gebruikt, dat (a) het resultaat
welgevormde XML blijft en geen `calcChain.xml` meer bevat, en (b) elke cel
die de module beschrijft letterlijk de waarde bevat die `rekenkern.bereken()`
voor diezelfde staat teruggeeft. Dat bewijst dat de cel-toewijzingen kloppen;
het bewijst niet dat Excel het bestand ook daadwerkelijk zonder
herstelmelding opent. Verander je iets aan de celverwijzingen in dit
bestand: laat het eerste geëxporteerde bestand van deze functie door Lars
(die wél Excel heeft) controleren voordat je verdere wijzigingen erop bouwt.

## Opmaak-opschoning van de calculatiestap (29 september 2026)

Vier kleine, puur visuele wijzigingen in `scherm/index.html`/`calculatie.js`/
`stijl.css`, naar aanleiding van het doorlopen van een aantal verschillende
calculaties (klein, groot/complex, meerdere opties) — geen van alle raakt
`rekenkern.py` of de berekening zelf:

- **De materiaal-sectie had drie parallelle manieren om een artikel toe te
  voegen** (zoekbalk, snelkeuze-chips per sectie, én een altijd-open raster
  van 10 dropdowns "OF BLADER DOOR EEN ONDERDEEL"). Dat laatste staat nu
  dichtgeklapt achter een knop (`#materiaalSectieBrowserToggle`,
  `uiState.toonSectieBrowser`) — hetzelfde "+ Meer standaardposten tonen"-
  patroon dat Uitbesteding/Equipment al hadden. `renderSectieBrowser()` bouwt
  de 10 selects nu ook pas als het scherm openstaat, niet meer bij elke
  `renderAll()`.
- **Elke installatiekaart herhaalde dezelfde uitlegzin** ("Merk, montagewijze
  en type binnendeel zijn ter documentatie..."). Die staat nu één keer, na de
  lijst installaties in plaats van per kaart (`#installatiesHint` in
  `index.html`, weggehaald uit de per-kaart-template in
  `renderInstallaties()`).
- **De "8 buitendelen + 19 binnendelen"-toelichting** stond als permanente
  alinea boven de installatiekaarten; dat is nu een klein (ⓘ)-icoontje naast
  de sectiekop (`.info-icon`, native `title`-tooltip in plaats van
  `textContent`) — vandaar ook de uitzondering voor `.info-icon` in
  `bindCollapsibles()`, anders zou een klik erop de hele kaart dichtklappen.
- **De kopbalk had 4 knoppen zonder groepering**, met alleen "Calculatie
  opslaan als .json" toevallig blauw (geen inhoudelijke reden, gewoon de
  originele stijl). Nieuw/Openen en Opslaan/Calculatieblad-downloaden staan nu
  in twee visuele groepjes (`.topbar-divider`), alle vier in dezelfde
  `.secondary`-stijl — geen van de vier is namelijk belangrijker dan de
  andere drie.

## Vier gaten in de overdracht (29 september 2026), gevonden door 'm echt te draaien

Op verzoek van Lars een beoordeling van de calculatie→brief-koppeling: komen
montagewijze/type/model, Q-nummer/klantnaam, systeemsoort (enkelvoud/meervoud,
wandmodel/cassette) goed over, en is duidelijk wat automatisch is ingevuld?
Statisch lezen van `overdracht.py` zag er goed uit (het bestand is expliciet
over "nooit gokken"); pas het écht draaien met een paar verschillende
calculaties (Playwright, geen handmatig geklik) liet zien dat de praktijk op
vier punten afweek van wat de code belooft. Alle vier zijn hierna gefixt.

**1. De "controleer dit"-melding verdween zichzelf binnen een fractie van een
seconde (`scherm/brief.html`).** `vulVanuitCalculatie()` riep na een overdracht
`toonFout("...controleer: ...")` aan voor de "afgeleid"-velden -- maar
`ver vers()`, vlak daarvóór al aangeroepen, zet op de achtergrond ook
`vraagAanApp()` in gang (de briefvoorvertoning ophalen), en die functie doet
bij succes onvoorwaardelijk `toonFout(null)` -- wat dezelfde banner alweer
leegveegt zodra die ronde terugkomt. Aangetoond met een instrumentatie-test
(`toonFout` tijdelijk gepatcht om aanroepen te loggen): de melding werd wel
degelijk gezet, en een fractie later alweer gewist, zonder dat er ooit een
mens naar had kunnen kijken. Fix: een eigen banner (`toonControleer()`/
`#controleerbalk`, los van `#foutbalk`) die `vraagAanApp()` niet aanraakt. Bij
diezelfde gelegenheid: de melding noemde rauwe paden ("installaties[0].
systeemsoort") -- `overdrachtPadNaarLabel()` maakt daar "systeemsoort van
installatie 1" van, en de melding noemt nu ook "keuze_nodig"-velden (zag er
eerder helemaal niet in, alleen "afgeleid" telde mee) onder een apart
"nog zelf invullen"-kopje.

**2. Een "Overig"-installatie werd stilzwijgend een gewoon "Split"-systeem
van het merk Panasonic (`installatiesSamenvoegen()` in `scherm/brief.html`).**
Precies het geval waar `overdracht.py` NOOIT mag gokken (systeemsoort
"keuze_nodig" bij "Overig": kan warmtepomp of vloeistofkoelmachine zijn) liet
`regel["systeemsoort"]` bewust ongezet -- maar `installatiesSamenvoegen()`
bouwde een nieuwe regel als `Object.assign(nieuweInstallatie(), regel)`, en
`nieuweInstallatie()` se eigen sjabloon-standaard is
`systeemsoort:"splitsystem", merk:MERKEN[0]` (Panasonic). Object.assign laat
een sleutel die `regel` niet heeft gewoon op de standaardwaarde staan -- dus
kwam een "Overig"-installatie zonder merk in de brief aan als een doodgewoon
Split-systeem van Panasonic, aantoonbaar via `CB.calc.staat`/`A.installaties`
in een live test. Erger: het veld is dan niet meer léég, dus de bestaande
`controle.ontbrekende_gegevens()`-vangnet (die hier juist voor is uitgebreid,
zie de `overdracht.py`-sectie hierboven) ziet niets fout meer -- een
Word-bestand met een verzonnen systeemsoort én verzonnen merk zou zonder één
waarschuwing de deur uit kunnen. Fix: een aparte, minimale
`legeOverdrachtInstallatie()` als Object.assign-basis specifiek voor
overdracht-regels (systeemsoort/montagewijze/merk/type_binnendeel leeg in
plaats van een sjabloon-gok) -- `nieuweInstallatie()` zelf blijft ongewijzigd,
want die standaardwaarden zijn juist wél passend voor een met de hand
toegevoegde nieuwe regel (iemand gaat 'm toch invullen).

**3. "Type binnendeel" in de brief is een productmodel (bijv. "TZ50"), geen
montage-categorie.** `overdracht.py` kopieerde calculatie se
`installatie.typeBinnendeel` (Kanaalunit/Cassetteunit/Wandunit/Vloerunit/
Overig -- puur voor documentatie, telt niet mee in de urenberekening, zie
"Installaties" hierboven) rechtstreeks naar de brief se `type_binnendeel`.
Maar dat veld verwacht een echt modelnummer: het eigen voorbeeld in
`scherm/brief.html` toont `type_binnendeel:"KIT-Z25-UFE"`, het formulier
labelt het veld zelf als "Type binnendeel (code)", en `analyse/teksten.yaml`
zet het letterlijk in de zin ("...fabrikaat Panasonic type
{{ regel.type_binnendeel }}"). Live getest: dit gaf dus een brief met "...type
Wandunit" in plaats van een echt modelnummer -- en dit stond als "direct"
gemarkeerd (geen "controleer dit"-label), dus dit gleed sowieso stilletjes
door, ook los van gat 1 hierboven.

Op verzoek van Lars (29 september 2026): het juiste model staat al in de
calculatie, alleen niet bij de installatie zelf -- het zit in de
materiaallijst, zodra het via de zoekbalk of de Panasonic/Daikin-catalogus is
toegevoegd (`voegMateriaalToe`/`voegPanasonicToe`/`voegDaikinToe` in
`scherm/calculatie.js`, sectie APPARATUUR). Er was alleen nog geen koppeling
tussen een installatiekaart en zo'n materiaalregel (met opzet: zie de
`renderInstallatiesApparatuurHint()`-uitleg hieronder over waarom installaties
en materiaal onafhankelijke lijsten zijn). Nieuw veld `installatie.materiaalId`
+ een "Model (uit materiaallijst)"-dropdown in de installatiekaart
(`materiaalOptiesVoorInstallatie()`, gevuld met de APPARATUUR-regels van de
huidige optie) legt die koppeling **expliciet** -- een keuze die de gebruiker
zelf maakt, geen gok van de tool. `overdracht.py` se `_zet_installatie_over()`
zoekt de gekoppelde regel op (`materiaal_op_id`, per calculatie-optie
opgebouwd in `zet_meerdere_over()`) en gebruikt `artikelcode` (bijv.
"KIT-TZ20-CKE"), of bij ontbreken daarvan `omschrijving`, als `type_binnendeel`
-- status "direct" (het is een echte verwijzing, geen interpretatie). Zonder
koppeling: "keuze_nodig" in plaats van de oude, foute categorie-doorgifte --
dat veld blijft dus leeg totdat de gebruiker zelf koppelt of het in de brief
met de hand invult, en de bestaande ontbrekende-gegevens-controle pikt een
niet-gekoppelde installatie daardoor ook weer gewoon op.

**Getest:** 4 nieuwe Python-tests (`tests/test_overdracht.py`,
`TestTypeBinnendeelKoppeling`) voor de materiaal-koppeling, en uitgebreid
live in de browser (Playwright) voor alle vier de gaten hierboven --
inclusief een oud projectbestand zonder `materiaalId` (laadt gewoon, lege
koppeling) en de calculatieblad-download (ongemoeid, raakt dit bestand niet
aan).

## De briefstap is 1-op-1 overgenomen uit de losstaande brieventool

`scherm/brief.html` is vrijwel een letterlijke kopie van
`ontwerp/prototype.html` uit de losstaande brieventool (repo
`brieven-tool-schilt-bedrijven`) — niet een eigen bouwsel zoals de eerdere
`scherm/brief.js` dat was. Reden: die eigen JS-implementatie leek te werken
in tests, maar de echte brief week op punten af van wat de losstaande tool
maakte, en het Word-bestand daaruit klopte niet altijd. Het prototype is
grondig getest (eigen `test_spiegel.py`/`test_server.py` in de bronrepo) en
praat via `fetch("app")`/`fetch("brief")`/`fetch("docx")`/`fetch("briefpapier")`/
`fetch("datablad")` rechtstreeks met dezelfde `brieventool.samenstellen`/
`brieventool.sjabloon`-code als deze tool — er is dus precies één plek die
bepaalt wat er in de brief staat, ook nu.

**Waarom een aparte pagina en geen tab zoals stap 1.** Het prototype is een
complete, op zichzelf staande pagina (eigen `<style>`, eigen kop met
Nieuw/Openen/Opslaan/Word-bestand-knoppen) — die in de bestaande
tab-structuur van `index.html` proppen zou of de CSS van de twee stappen
laten botsen, of de eigen kop van het prototype dubbel neerzetten naast de
stappen-nav. `server.py` serveert `scherm/brief.html` daarom op het
root-niveau (`/brief.html`, niet onder `/scherm/`), zodat de relatieve
`fetch("app")` etc. in dat bestand — ongewijzigd overgenomen — gewoon naar
`/app` etc. resolven zonder dat de URL's aangepast hoefden te worden. De
"Calculatie klaar → verder naar de brief"-knop en de "2 Brief →"-knop in de
stappen-nav (`scherm/index.html`) doen daarom een echte paginanavigatie
(`location.href = 'brief.html'`), geen tab-wissel meer.

**De koppeling met de calculatie** (niet in het origineel, want die kende
geen calculatiestap) zit in een apart, duidelijk afgebakend script-blok
onderaan `scherm/brief.html`, vlak vóór de bestaande opstart-IIFE:
- `calculatieStaatOphalen()` leest `localStorage['calcubrief.concept']` —
  dezelfde sleutel als `AUTOSAVE_SLEUTEL` in `scherm/gedeeld.js` — en pakt
  daar alleen `.calculatie` uit; er wordt hier nooit iets teruggeschreven.
- `vulVanuitCalculatie()` stuurt die calculatiestaat plus het huidige
  `A.klanttype` naar `POST /overdracht` en voegt het resultaat toe aan `A`
  (`Object.assign`, dus een aanvulling, geen vervanging — bestaande, met de
  hand ingevulde velden blijven staan). `installaties[]` is een
  uitzondering: de EERSTE keer (`A._vanuitCalculatieToegepast` nog niet
  gezet) vervangt de calculatie de voorbeeldinstallaties helemaal — die
  samenvoegen zou verwarrende resten van de voorbeelddata achterlaten als de
  aantallen niet overeenkomen. Bij een volgende toepassing (na eigen
  aanpassingen zoals "ruimte" of "eigen kopregel") wordt per regel
  samengevoegd, zodat die aanpassingen niet verloren gaan.
- De knop "↺ Vanuit calculatie" in de kop roept dit handmatig aan; een
  eenmalige `sessionStorage`-vlag (`calcubrief.naarBrief`, gezet door
  `scherm/index.html` vlak vóór de navigatie) laat het bij binnenkomst ook
  automatisch één keer gebeuren — zodat "één klik doet alles" behouden
  blijft zonder dat deze pagina iets hoeft te weten van hoe `index.html` dat
  aanroept, en andersom.
- De standaard bestandsnaam (`bestandsnaam()`, ook gebruikt door de eigen
  Opslaan-als-JSON-knop van dit scherm) is de enige andere aanpassing t.o.v.
  het origineel: die las daar `achternaam-plaats-sa_nummer`, hier leest hij
  eerst `localStorage['calcubrief.concept'].calculatie.meta` (klantnaam +
  projectnaam) zodat de calculatie- en briefbestanden van hetzelfde project
  dezelfde naam delen (`Calculatie-…`/`Brief-…`, zie `CB.projectBestandsnaam`
  in `gedeeld.js`) — en valt terug op de oorspronkelijke naamgeving als er
  geen calculatieproject bekend is (de brief kan nog steeds los gebruikt
  worden).

**Bijwerken na een wijziging in `analyse/teksten.yaml` of
`sjablonen/brief.docx`.** Net als het origineel heeft `scherm/brief.html` de
tekstblokken en het Word-sjabloon ingebakken (voor de fallback-modus zonder
server, zie hieronder) — dat loopt dus niet vanzelf gelijk met een wijziging
in die bronbestanden. Draai na zo'n wijziging:

    python3 tools/ververs_brief_scherm.py

(een aangepaste versie van `ontwerp/ververs_prototype.py` uit de bronrepo,
die hier `scherm/brief.html` bijwerkt in plaats van `ontwerp/prototype.html`).

**Bijwerken na een wijziging in `ontwerp/prototype.html` zelf (de bronrepo
`brieven-tool-schilt-bedrijven`), dus het formulier/de JS-logica, niet de
tekst/het sjabloon.** `tools/ververs_brief_scherm.py` raakt alleen de
ingebakken tekstblokken/sjabloon/logo aan (zie hierboven) — een wijziging in
het prototype zelf (een nieuw veld, een andere standaardwaarde, een andere
knoptekst) komt daar niet in mee, want `scherm/brief.html` is met de hand
op prototype.html afgestemd, niet automatisch gegenereerd. Zo'n wijziging
overzetten: kloon `brieven-tool-schilt-bedrijven` erbij (bijv. via
`add_repo`), vergelijk `ontwerp/prototype.html` daar met `scherm/brief.html`
hier (`diff`), en zet alleen de inhoudelijke wijzigingen daaruit over —
**niet** de stukken die hier bewust al anders zijn (de calculatie-
koppeling onderaan, de "← Calculatie"/"↺ Vanuit calculatie"-knoppen in de
kop, en `bestandsnaam()`, alle drie hierboven al beschreven). Zo ook
gedaan voor twee aanpassingen van Lars (23 september 2026): een leeg
`opsteller_initialen`/`sa_nummer` in plaats van een voorbeeldwaarde, en een
"Aantal systemen"-veld bij een splitsystem-installatie (het onderliggende
sjabloon ondersteunde `regel.aantal_systemen` al voor meervoud/enkelvoud;
alleen het formulierveld om het in te stellen ontbrak) — in beide gevallen
bleek `analyse/teksten.yaml`/`sjablonen/brief.docx` zelf ongewijzigd, dus was
`ververs_brief_scherm.py` hier niet nodig, alleen de handmatige patch.

**De ingebakken "motor"/"word"-fallback (tussen `/*<motor>*/`...`/*</motor>*/`
en `/*<word>*/`...`/*</word>*/`) is ongebruikte, maar bewust niet verwijderde
code.** Die draait alleen als `fetch("app")` faalt (geen server) — in deze
tool draait er altijd een server, dus dit pad wordt in de praktijk nooit
gebruikt, behalve als noodgreep wanneer de server tijdens gebruik wegvalt
(`verversViaApp`'s catch-blok zet dan `VIA_APP=false`). Verwijderen zou de
1-op-1-overname minder letterlijk maken voor weinig winst; laten staan kost
niets (het weegt niet mee in wat de browser laadt totdat het echt nodig is).
Bijkomend voordeel: de bronrepo's eigen `test_spiegel.py` bewijst al dat deze
JS-motor hetzelfde resultaat geeft als `samenstellen.py` — dat is hier niet
opnieuw getest, maar de logica zelf is ongewijzigd overgenomen.

## `scherm/*.js` staan zonder modules naast elkaar

`calculatie.js` wordt als gewoon `<script>` geladen (geen `type=module`) en
deelt dus één globale scope met `gedeeld.js`. Het is daarom in een IIFE
gewrapt — zonder dat botsen `const`/`let` op topniveau met wat `gedeeld.js`
daar zelf neerzet. Voeg je een derde scherm-bestand toe dat **op dezelfde
pagina** als `gedeeld.js` draait (dus niet `scherm/brief.html`, dat is een
eigen pagina zonder gedeelde scripts), wrap het dan ook in een IIFE, of zet
het als module.

## De autosave moet gelezen worden vóór de eerste `renderAll()`, niet erna

`renderAll()` (`scherm/calculatie.js`) roept aan het eind altijd `CB.autosave()`
aan — ook tijdens de allereerste berekening bij het opstarten van de
calculatiestap, met dan nog de lege `nieuweStaat()`. `initCalculatie()` laadt
de bewaarde staat daarom zelf, vóór die eerste `renderAll()`:

    state = CB.leesAutosaveCalculatie() || nieuweStaat();

**Dit stond eerder andersom en dat gaf een leeg calculatieblad bij elke
terugkeer naar deze pagina** (de "← Calculatie"-link in `scherm/brief.html`,
maar ook een gewone F5). De oude opzet liet `index.html` pas ná
`CB.calc.klaar` de bewaarde staat inladen (`CB.laadAutosave()`, die
`CB.calc.vulStaat()` aanriep) — maar `CB.calc.klaar` (dus `initCalculatie()`)
was op dat moment allang minstens één keer door `renderAll()` heen geweest,
die de dan nog lege `nieuweStaat()` al naar `localStorage` had weggeschreven.
Het bewaarde project was dus alweer overschreven met lege staat vóórdat er
ooit naar gekeken werd — de data stond op het moment van wegnavigeren nog
prima in `localStorage`, maar was tegen de tijd dat er iets mee gedaan werd
alweer weg.

`CB.leesAutosaveCalculatie()` (`scherm/gedeeld.js`) is daarom bewust een pure
leesfunctie zonder side-effect op `CB.calc` (in tegenstelling tot de oude
`CB.laadAutosave()`, die naast lezen ook meteen `vulStaat()`+`renderAll()`
aanriep) — `initCalculatie()` gebruikt het resultaat gewoon als startwaarde
van `state`, en de daaropvolgende `bindMeta()`/.../`herbereken()`-reeks
rendert daar vanzelf één keer overheen. Voeg je zelf iets toe dat de
calculatiestaat ergens vroeg in het opstarten leest of overschrijft: doe dat
vóór de eerste `renderAll()`/`herbereken()`-aanroep in `initCalculatie()`,
niet erna vanuit `index.html`.

## Server-static-bestanden: het pad-voorvoegsel is verplicht

`server.py` serveert `scherm/` en `data/` alleen onder hun eigen
voorvoegsel (`/scherm/app.js`, `/data/foo.json`) — nooit op de root. HTML/JS
die naar deze bestanden verwijst moet dus `scherm/...` schrijven, niet een
kale bestandsnaam (die zou naar `/bestand.js` resolven, wat een 404 geeft).

## `CB.getJSON`/`CB.postJSON`: de foutafhandeling loopt uiteen, met opzet

`CB.getJSON` (`scherm/gedeeld.js`) is alleen voor statische `/data/*.json`-
bestanden en gooit een fout bij elke niet-2xx-status. `CB.postJSON` is voor
de RPC-achtige endpoints (`/bereken`, `/overdracht`, `/brief`, ...) die
bewust een niet-2xx-status mét een `{"fout": "..."}`-body teruggeven, die de
aanroeper zelf afhandelt (bijv. `if (resultaat.fout) { CB.toast(...) }` in
`calculatie.js`) — die blijft daarom werken ongeacht de statuscode. Verwar
deze twee niet: een missend statisch bestand geeft in `server.py` óók een
`{"fout": "onbekend adres"}`-body (dezelfde generieke 404-handler als voor
elk onbekend pad), dus zonder de aparte, strengere controle in `getJSON` zou
zo'n missend bestand stilzwijgend als (verkeerde) data zijn gebruikt in
plaats van een duidelijke fout te geven — precies gebeurd bij het uitzoeken
van een "laadscherm blijft oneindig draaien"-melding.

**`CB.calc.klaar` (index.html) heeft daarom ook een `.catch()`, niet alleen
een `.then()`.** Zonder die `.catch()` bleef het laadscherm-overlay bij zo'n
mislukte data-ophaal-stap eindeloos draaien: de promise-keten wees dan
gewoon nergens meer heen, en `CB.laadscherm.verberg()` (in de `.then()`)
werd dus nooit aangeroepen — voor de gebruiker geen enkel verschil met
"duurt gewoon nog even", met geen enkele aanwijzing wat er misging.
`CB.laadscherm.toonFout(fout)` toont die fout nu in plaats daarvan in het
laadscherm zelf. Voeg je een nieuwe async opstartstap toe aan de
calculatiestap (zie ook de laadscherm-sectie hierboven): laat een fout
daarin altijd omhoogkomen (gooi 'm, vang 'm niet stil weg) zodat hij hier
terechtkomt, in plaats van een tweede stille-hang-plek te scheppen.

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

## De Release-pagina wordt door één losse job beheerd, na beide builds

`windows` en `macos` in `build-app.yml` bouwen alleen en leveren hun zip af
als workflow-artifact (`actions/upload-artifact`) — geen van beide raakt de
Release-pagina zelf aan. Een aparte `publiceer`-job (`needs: [windows,
macos]`, `ubuntu-latest`, ver goedkoper dan nog een Windows-/Mac-runner)
haalt beide artifacts op (`actions/download-artifact`) en is de enige plek
die `gh release` aanroept — dat voorkomt dat "windows lukt, mac loopt vast"
de mac-job voor een lastige keuze stelt over een release-object dat windows
net had opgezet.

**Het echte probleem bleek de navraag, niet de upload.** Een aantal eerdere
versies van deze stap (zie git-historie) trokken, op basis van `gh release
view --json assets` die na een upload leeg bleef, de conclusie dat GitHub's
release-API de upload zelf liet mislukken — met als "oplossing" steeds
grovere pogingen: `--clobber`, een losse `gh release delete-asset` vooraf, en
uiteindelijk de hele release bij elke mislukte navraag weggooien en opnieuw
aanmaken. Een diagnostische versie van deze stap (zonder foutonderdrukking,
met de rauwe JSON via `gh api repos/OWNER/REPO/releases/tags/app-download`
in plaats van `gh release view`) liet uiteindelijk zien dat dit een
verkeerde diagnose was: `gh release upload` gaf steeds gewoon exitcode 0, en
`gh api` op diezelfde release liet **seconden** na de upload, in dezelfde
job, al beide assets zien met `"state": "uploaded"` en de juiste
bestandsgrootte. De uploads werkten dus de hele tijd al.

`gh release view --json assets` zelf bleek het onbetrouwbare stuk: die bleef
ook ver na een bewezen geslaagde upload nog `assets: []` teruggeven — zelfs
een onafhankelijke navraag (niet via `gh`, een aparte losse API-aanroep)
liet pas na zo'n **kwartier** de echte, juiste asset-lijst zien. Met andere
woorden: de eerdere "fixes" reageerden op een navraagmethode die simpelweg
traag/onbetrouwbaar is voor een net aangemaakte release, en loste daarmee
niets op — erger nog, het herhaaldelijk weggooien-en-opnieuw-aanmaken van de
hele release bij zo'n foute "nee" kan een release hebben vernietigd waarvan
de assets allang goed stonden, alleen nog niet zichtbaar via die navraag.

**De huidige opzet.** Eén keer verwijderen + aanmaken (geen herhaal-cyclus
van de hele release meer), dan allebei de bestanden uploaden (met een kleine
retry per bestand als de upload zelf een keer mislukt — niet als de navraag
niets laat zien), en ná een korte wachttijd navragen via `gh api ...
--jq '.assets[].name'` — nadrukkelijk niet via `gh release view --json
assets`, want die bleek bij herhaling het onbetrouwbare stuk. Zie je zelf
(bijv. via de GitHub API, of door meteen na een build de Release-pagina te
verversen) dat een net gepubliceerd bestand er nog niet lijkt te staan: geef
het gewoon een paar minuten, er hoeft niets opnieuw gebouwd of gepubliceerd
te worden — de asset staat er wel, de weergave loopt alleen nog achter. De
downloadlink (`.../releases/tag/app-download`) blijft ondertussen hetzelfde,
want de tagnaam verandert niet.

## Laadscherm: het filmpje speelt in de browser, niet meer native ervoor

**Wat er eerst was geprobeerd, en waarom dat uitgeschakeld is.** Om het
"duurt lang"-moment tussen dubbelklikken op de `.exe` en het openen van de
browser (10-20s blauwe laadcirkel, met niets erachter) te dekken, speelde
`server.py` vóór het openen van de browser `scherm/laadscherm.mp4` af als
gif in een eigen, kaderloos tkinter-venster. Dit was letterlijk het enige
stuk van de hele tool dat niet vanuit deze ontwikkelomgeving te testen was
(geen tkinter, geen beeldscherm in de sandbox) — en het bleek op een echte
Windows-machine de app te laten crashen vóórdat er iets te zien was, op een
manier die zelfs Python's eigen foutafhandeling omzeilde (leeg
`calcubrief-log.txt`, wat op een harde, native crash wijst, vermoedelijk in
de Tcl/Tk-bibliotheek zelf). Zie git-historie voor de volledige diagnose;
dit is toen volledig verwijderd uit `server.py` (geen
`_toon_native_laadscherm()`/`_native_laadscherm_pad()`/`LAADSCHERM_FPS`
meer) en `build-app.yml` (geen ffmpeg/gif-stap meer).

**Nu speelt het filmpje in de pagina zelf** — gewoon een `<video>`-element
(`#laadschermVideo`) in de `#laadscherm`-overlay van `scherm/index.html`,
niet meer native vóórdat de browser open is. Dat is fundamenteel veiliger:
een `<video>` draait in de browser's eigen sandbox, dus een probleem daarmee
(ontbrekend bestand, browser ondersteunt de codec niet) kan nooit meer de
hele app meetrekken zoals de tkinter-versie deed. `CB.laadscherm.init()`
(`scherm/gedeeld.js`) luistert daarom naar het `error`-event op de video en
valt bij zo'n fout terug op de oude spinner (`#laadschermMerk` +
`#laadschermSpinner`, beide standaard verborgen) in plaats van een lege plek
waar het filmpje stond — dat gebeurde ook echt tijdens het bouwen hiervan:
de headless Chromium in deze ontwikkelomgeving kan dit specifieke bestand
niet decoderen (`DEMUXER_ERROR_NO_SUPPORTED_STREAMS`, vermoedelijk een build
zonder H.264-ondersteuning) — een goede, onbedoelde test van precies dit
terugvalpad. Reguliere browsers (Chrome/Edge/Safari op een echte pc/Mac)
ondersteunen H.264/AAC in mp4 wél gewoon.

**`MINIMALE_DUUR_MS` is expres (ongeveer) de duur van het filmpje** (10,24s
op het moment van schrijven, `10300` als terugvalwaarde in de code totdat
`loadedmetadata` de echte duur teruggeeft), niet meer een klein getal om
alleen een flits-en-weg-effect te voorkomen. Reden: de data-ophaal-stap
hieronder is lokaal typisch een kwestie van milliseconden, dus zonder deze
langere wachttijd zou de overlay (met het filmpje erin) al verwijderd worden
ruim vóórdat het filmpje ook maar goed geladen is — de browser breekt zo'n
nog lopende download dan gewoon af (`net::ERR_ABORTED`, ook zo aangetroffen
tijdens het testen hiervan), waardoor het filmpje in de praktijk vrijwel
nooit te zien zou zijn geweest. Bij een `error` (zie hierboven) heeft
wachten geen zin meer: `_toonSpinnerTerugval()` zet `MINIMALE_DUUR_MS` dan
terug naar 300ms, zodat een gebruiker bij wie het filmpje niet afspeelt niet
alsnog onnodig 10 seconden naar een spinner hoeft te staren.

**`scherm/laadscherm.mp4` wordt weer meegepakt in de build** (`--add-data
"scherm;scherm"` bevat het al, dus er was geen aparte stap nodig) — de
eerdere "verwijder het filmpje uit de build"-stappen in `build-app.yml` zijn
verwijderd, want het bestand wordt nu wél gebruikt. Vervang je dit bestand
ooit door een andere versie: de duur wordt automatisch opnieuw uitgelezen
(zie `loadedmetadata` in `CB.laadscherm.init()`), dus de `10300`-terugvalwaarde
hoeft dan niet per se aangepast te worden (die is toch alleen de korte
overbrugging vóórdat de echte duur bekend is) — wel zo netjes om 'm bij een
bewuste, blijvende vervanging alsnog bij te werken zodat de code zichzelf
blijft documenteren.

**De rest van de laadscherm-diagnostiek blijft wel relevant.** Een
`--windowed`/`--noconsole`-build (zowel de Windows-.exe als de Mac-.app)
heeft geen console — `sys.stdout`/`sys.stderr` zijn dan `None`, geen
writable stream. Een doodgewone `print()` (er staan er een paar, vlak na het
opstarten van de server, vóór de browser wordt geopend) crasht zo'n build
dan met een `AttributeError` — onzichtbaar, want er is geen console om iets
te tonen: de app "doet niets". `pythonw.exe` (`start-app.pyw`) heeft
hetzelfde probleem, ook zonder frozen build. Fix: bovenin `server.py` wordt
`sys.stdout`/`sys.stderr` vervangen als ze `None` zijn, vóór er ergens
geprint wordt -- bij een gebouwde app naar `calcubrief-log.txt` naast de
.exe/.app (regel-gebufferd, niet naar een stille `os.devnull`-sink: dat
loste de crash op maar maakte een volgend probleem juist onmogelijk te
diagnosticeren). Direct na die omwisseling wordt altijd één regel gelogd
("opgestart, <tijdstip>") — staat die regel er niet eens in bij een volgend
probleem, dan is de app niet eens tot in `server.py` gekomen, of is
midden in iets abrupt afgebroken (een harde/native crash, zoals hierboven
bij het laadscherm) — allebei iets heel anders dan een gewone Python-fout,
die wél in het logbestand terechtkomt vóórdat `main()`'s eigen
`tkinter.messagebox`-foutmelding verschijnt (alleen wanneer `sys.frozen`
waar is). Kortom: **een "doet niets bij het opstarten"-melding voor de
gebouwde app** — check eerst of `calcubrief-log.txt` bestaat en wat erin
staat (leeg bestand = harde crash, geen bestand = nog niet eens tot in
`server.py` gekomen, een foutmelding erin = een gewone, opgevangen fout).

**De overlay in `scherm/index.html`** (`#laadscherm`, met het filmpje erin,
zie hierboven) dekt de eigen data-ophaal-stap van de calculatiestap zelf af
zodra de browser eenmaal open is: verdwijnt pas als zowel `CB.calc.klaar` is
opgelost (zie de inline `<script>` onderaan dat bestand) als de
`MINIMALE_DUUR_MS`-wachttijd voorbij is — dus na de materiaalcatalogus/YIMM/
Panasonic/Daikin-data, de eerste `/bereken`-ronde, én (in het normale geval)
het filmpje. Voeg je een nieuwe async opstartstap toe aan de calculatiestap,
neem die dan op in die `klaar`-promise, anders verdwijnt deze overlay te
vroeg. `scherm/brief.html` is een eigen pagina met zijn eigen (eenvoudigere)
laadgedrag, zie hierboven.

## Synchronisatie met de losstaande brieventool (30 september 2026)

Op verzoek van Lars: twee commits uit `brieven-tool-schilt-bedrijven` (sinds
het laatste syncpunt, `c3b8aef`) overgezet naar deze tool. Dezelfde procedure
als eerder in dit bestand beschreven onder "De briefstap is 1-op-1
overgenomen" — kloon de bronrepo erbij, vergelijk, zet de inhoudelijke
wijzigingen over, laat de hier bewust-andere stukken (calculatie-koppeling,
"← Calculatie"/"↺ Vanuit calculatie", `bestandsnaam()`, en nu ook de
Fase-5-materiaalId-koppeling hierboven) met rust.

**Wat er over kwam: de systeemomschrijving kiest nu per installatieregel, niet
meer voor de hele brief.** Tot deze wijziging had een offerte-breed veld
`model_binnenunit` (wand/cassette/kanaal/vloer/plafondonderbouw/vrf) dat
bepaalde welke van de `systeem_*`-blokken in `analyse/teksten.yaml` meegaan —
dus bij een brief met bijvoorbeeld zowel een cassette- als een
wandmodel-installatie kreeg je maar één van de twee omschrijvingen, nooit
allebei. `model_binnenunit` is nu een veld per installatieregel:
- `brieventool/samenstellen.py`: de 14 `systeem_*`-blokken staan nu in de
  sectie `specificatie` (die al herhaalt per installatie, zie `LOOPSECTIES`)
  in plaats van `systeemomschrijving` (eenmalig voor de hele brief), met hun
  `voorwaarde` voorzien van een `regel.`-voorvoegsel. Nieuwe functie
  `_verrijk_installatie()` voegt `aantal_binnenunits`/`aantal_buitenunits` per
  regel toe (voorheen alleen voor de hele brief in `_bouw_context`), want het
  enkelvoud/meervoud van de omschrijving ("De binnenunit is" vs. "De
  binnenunits zijn") moet nu ook per regel kloppen. `systeem_opbouw_*`,
  `storingscontact_*` en `verse_lucht_*` blijven bewust wél offerte-breed —
  daar is geen voorbeeld dat ze per regel zouden moeten verschillen.
- `brieventool/controle.py`: `("model_binnenunit", "het model binnenunit")`
  toegevoegd aan `INSTALLATIEVELDEN`, náást de al bestaande, combinatie-tool-
  specifieke `systeemsoort`-regel — zonder dit veld matcht voor die
  installatieregel geen enkel `systeem_*`-blok meer, net zo'n stil gat als
  het eerdere systeemsoort-gat.
- `scherm/brief.html`: dezelfde wijzigingen 1-op-1 overgezet naar de
  JS-motor/-formulier-kant (zie "`scherm/*.js` staan zonder modules naast
  elkaar" resp. de uitleg over het motor/word-blok hierboven) — `model_binnenunit`
  is nu een keuzeveld per installatiekaart (`bouwInstallaties()`) in plaats
  van een document-breed veld in de groep "Uitvoering", en `bouwContext()`/
  `redenVan()` spiegelen `_verrijk_installatie()` resp. het nieuwe
  `regel.`-voorvoegsel in de "waarom staat dit blok hier"-tip.

**Bijkomende fix: altijd een witregel vóór "Niet tot onze werkzaamheden
behoren:".** `samenstellen.py`'s `_zet_witregels()` liet tot nu toe alleen de
kopregel van "... inclusief:" een lege regel erna krijgen; de laatste regel
van dat stuk (vlak vóór de kop van "... exclusief:") kreeg er geen, dus de
twee stukken van de werkzaamhedenlijst stonden aaneengesloten. Nu krijgt ook
die laatste regel een witregel erna (`LAATSTE_AANEENGESLOTEN`-constante
vervallen, de voorwaarde is nu gewoon "eerste of laatste regel van het
stuk") — hetzelfde gespiegeld in `scherm/brief.html`'s `zetWitregels()`.

**`overdracht.py` kreeg er zelf ook iets bij: een `typeBinnendeel`→
`model_binnenunit`-vertaling.** Met het nieuwe per-regel veld in de brief
heeft calculatie se eigen `installatie.typeBinnendeel`
(Kanaalunit/Casetteunit/Plafondonderbouw/Wandunit/Vloerunit/Overig,
`data/systemen.json`) nu een natuurlijke bestemming — dezelfde montage-
categorie, alleen anders gespeld. `MODEL_BINNENUNIT_VERTALING` (naast de
bestaande `MONTAGEWIJZE_VERTALING`) vertaalt 1-op-1, status "direct" (geen
aanname, alleen een naam die verschilt). "Overig" heeft geen eenduidig
brief-equivalent en blijft daarom "keuze_nodig" met alle zes opties, nooit
een gok — dezelfde "nooit gokken, wel afleiden"-regel als de rest van dit
bestand. `legeOverdrachtInstallatie()` kreeg `model_binnenunit:""` erbij
(anders zou `nieuweInstallatie()`'s sjabloonstandaard "wand" stilzwijgend
verschijnen bij een "Overig"-installatie, precies het gat dat Fase 5
hierboven al dichtte voor `systeemsoort`/`merk`/`type_binnendeel`), en
`OVERDRACHT_VELDLABELS` een `model_binnenunit`-label voor de
controleerbalk-melding.

Niet overgezet (uitgesloten omdat dit repo-interne documentatie van de
bronrepo is die hier geen tegenhanger heeft): `analyse/skelet.md`,
`analyse/variabelen.md`, `analyse/vragen.md` — deze combinatietool heeft geen
`analyse/`-map behalve `teksten.yaml` zelf; dit bestand hier is de
documentatie-plek voor de combinatietool.

**Getest:** `tools/ververs_brief_scherm.py` gedraaid na de `teksten.yaml`-
wijziging (regenereert alleen de ingebakken BLOKKEN-JSON-blob in
`scherm/brief.html`, het Word-sjabloon zelf was ongewijzigd). De drie
bestaande voorbeeldbestanden (`voorbeelden/particulier-wand-enkelvoud.yaml`,
`toets-uitgewerkt-3.yaml`, `zakelijk-cassette-meervoud.yaml`) kregen
`model_binnenunit` per installatieregel in plaats van offerte-breed, 1-op-1
gelijk aan de bronrepo. Bestaande tests in `tests/test_samenstellen.py`/
`test_controle.py`/`test_werkzaamheden.py` bijgewerkt naar de nieuwe
verwachte uitvoer, plus nieuwe tests: `test_systeemomschrijving_volgt_de_eigen_regel`
(een cassette- én een wandmodel-installatie op één brief, allebei met hun
eigen, correcte omschrijving) en `TestModelBinnenunitVertaling` in
`tests/test_overdracht.py` (alle vijf categorieën vertalen direct, "Overig"
vraagt een keuze). 265 tests slagen. Live gecontroleerd met Playwright: twee
installaties (Casetteunit/Wandunit) via de calculatie, overdracht naar de
brief, en de briefvoorvertoning bevat zowel de cassette- als de
wand-omschrijving (voorheen zou er maar één zijn getoond).

## Autosave is per sessie (tabblad), niet meer een archief over het sluiten heen (2 oktober 2026)

Op verzoek van Lars: bij het openen van de tool stond er nog informatie uit
een eerdere calculatie/brief in. Dat was geen bug maar het directe gevolg van
de autosave-naar-`localStorage` hierboven beschreven ("De autosave moet
gelezen worden vóór de eerste `renderAll()`"): `localStorage` overleeft het
sluiten van het tabblad, dus elke nieuwe werksessie begon met de laatste
stand van de vórige. Gewenst gedrag is nu: binnen één sessie niets verliezen
(stap naar de brief en terug, een F5), maar bij het sluiten van het
tabblad/de app eerst vragen of er nog iets niet is opgeslagen, en bij een
nieuw geopende sessie een lege tool.

**`localStorage` → `sessionStorage`, verder ongewijzigd.** `AUTOSAVE_SLEUTEL`
(`scherm/gedeeld.js`, `CB.autosave()`/`CB.leesAutosaveOpties()`) en de twee
sleutels in `scherm/brief.html` die dezelfde soort autosave doen
(`CONCEPT`/`bewaarConcept()`/`haalConceptOp()` voor de brief zelf,
`CALCULATIE_CONCEPT_SLEUTEL`/`calculatieOptiesOphalen()` die de calculatiekant
leest voor de overdracht) gebruiken nu alledrie `sessionStorage` in plaats van
`localStorage`. De reden dat dit precies het gevraagde gedrag geeft: een
browsertabblad heeft een eigen, geïsoleerde `sessionStorage` die normale
navigatie en een herlaad (F5) **wel** overleeft (dus de bestaande "nooit een
leeg calculatieblad bij terugkeer"-fix hierboven blijft onaangetast werken),
maar leeg begint zodra er een nieuw tabblad wordt geopend -- en dat is precies
wat er gebeurt bij elke nieuwe start van de app (`webbrowser.open()` in
`server.py` opent een nieuw tabblad, nooit hetzelfde oude). Geen enkele andere
code hoefde te weten van dit onderscheid: alle bestaande `probeer/catch`-
foutafhandeling, het "vóór de eerste `renderAll()`"-leesmoment, en de
terugval-op-ouder-formaat-logica (`CB.optiesUitProject()`) werken identiek,
alleen de opslagplek is anders.

**De beforeunload-waarschuwing is de andere helft.** Wat `localStorage`
eerder wél deed -- een vangnet tegen per ongeluk een tabblad dichtklikken --
moest met `sessionStorage` ergens anders vandaan komen. `scherm/index.html`
en `scherm/brief.html` luisteren daarom allebei naar `window.beforeunload` en
roepen `e.preventDefault()`/zetten `e.returnValue` als er iets staat dat nog
niet is opgeslagen. **Een pagina kan de tekst van dit venster niet zelf
bepalen** -- elke browser toont hier al jaren alleen zijn eigen, generieke
"Wijzigingen die u hebt aangebracht, worden mogelijk niet opgeslagen"-melding
met Annuleren/Verlaten, als beveiliging tegen misbruik van een zelfverzonnen
tekst (bijv. om een gebruiker te misleiden een tabblad toch niet te sluiten).
Dat is dus geen keuze die deze tool kan maken; wél bepaalt de tool **wanneer**
dat venster verschijnt:
- **Calculatiestap** (`scherm/index.html`): `CB.heeftInhoud()`, dezelfde toets
  die de "Nieuw"-knop al gebruikte. Bij het uitschrijven hiervan bleek
  `staatHeeftInhoud()` (`scherm/calculatie.js`) een bestaande makke te hebben:
  `meta.datum` staat in een kersverse `nieuweStaat()` altijd al op vandaag, dus
  telde als "ingevuld" ook al was er he-le-maal niets aangeraakt -- elke net
  geopende, nog maagdelijke sessie zou dan alsnog een "weet u het zeker?"
  geven bij het sluiten (en liet "Nieuw" vlak na het openen van de tool ook al
  onnodig waarschuwen, een kleinere versie van hetzelfde euvel die er
  blijkbaar al die tijd al was). Fix: `datum` telt niet meer mee in die toets.
- **Briefstap** (`scherm/brief.html`): hier kan "staat er iets in" niet
  gebruikt worden zoals bij de calculatie -- `A` begint altijd gevuld, met een
  compleet uitgewerkt voorbeeld (`BEGINSTAND`), geen lege staat. In plaats
  daarvan een momentopname (`laatsteBewaarSnapshot`/`zetBewaarSnapshot()`):
  ververst bij elk "schoon"-moment (geladen bij opstarten, na Opslaan, na
  Openen, na Nieuw) en vergeleken met de huidige `A` in
  `heeftNietOpgeslagenWijzigingen()`. Een automatische overdracht vanuit de
  calculatie (bij binnenkomst, of via "↺ Vanuit calculatie") telt bewust wél
  als wijziging -- dat is nieuwe data die nog niet is opgeslagen, ook al heeft
  de gebruiker zelf niets getypt.
- **Nooit bij de normale stap-navigatie binnen de tool.** `beforeunload` kan
  niet onderscheiden "tabblad dicht" van "naar een andere pagina op dezelfde
  site" -- allebei vuren hetzelfde event. Zonder verder onderscheid zou dus
  ook een doodgewone klik op "Calculatie klaar → verder naar de brief" of
  "← Calculatie" de native waarschuwing laten verschijnen, bij elke stap --
  onbruikbaar, want dat is helemaal geen dataverlies (de sessionStorage-
  autosave gaat gewoon mee). Een simpele, in-memory vlag
  (`interneNavigatieOnderweg`, gezet vlak vóór `location.href=...` in de
  klikhandler van "Brief →" resp. "← Calculatie") die de beforeunload-
  functie eerst checkt, lost dit op -- de vlag hoeft niet over de
  paginagrens heen te overleven, want hij wordt gelezen op dezelfde pagina
  die 'm zet, vlak voordat die pagina al navigerend verdwijnt.

**Getest met Playwright** (twee tabbladen in dezelfde browsercontext, om een
echte nieuwe-sessie-situatie na te bootsen): calculatie invullen → naar de
brief (gegevens komen over, `sessionStorage` gevuld, `localStorage`
ongebruikt) → terug naar calculatie via de link (geen beforeunload-blokkade,
gegevens nog aanwezig) → een gesimuleerd `beforeunload`-event bevestigt dat de
browser zou waarschuwen zolang er inhoud/wijzigingen staan. Een tweede,
volledig nieuw tabblad in dezelfde context laat vervolgens zowel de
calculatie als de brief leeg zien (`CB.heeftInhoud()` nu terecht `false`), en
hetzelfde gesimuleerde event bevestigt dat er dán juist géén waarschuwing
komt. Volledige Python-testsuite (265 tests) ongewijzigd en nog steeds groen
-- deze wijziging raakt alleen `scherm/*.js`/`scherm/*.html`.

## Drie samenhangende bugs in de "aantal"-velden (2 oktober 2026)

Op verzoek van Lars: het standaardgetal "0" in een aantal-veld (installaties,
materiaal, uitbesteding, equipment) kon niet worden weggehaald om een eigen
getal te typen, een meercijferig getal typen gaf de cijfers in de verkeerde
volgorde terug, en typen in een Uitbesteding-regel liet de focus naar een
aantal-veld bij APPARATUUR springen. Alle drie bleken gevolgen van hoe
`renderAll()` (`scherm/calculatie.js`) werkt: dat rendert bij ELKE
toetsaanslag de hele sectie opnieuw (nodig omdat de rest van het scherm --
totalen, afgeleide regels -- moet meebewegen), met `captureFocus()`/
`restoreFocus()` als vangnet om de cursor na die herbouw weer op de juiste
plek te krijgen.

1. **"0" liet zich niet weghalen.** De render-sjablonen voor deze velden
   toonden `value="${r.aantal||0}"`: zodra het veld leeg werd gemaakt
   (`r.aantal` dan `''`, een falsy waarde), zette `||0` de weergave bij de
   eerstvolgende render -- die na élke toetsaanslag gebeurt -- alweer op "0",
   vóórdat er ooit een nieuw cijfer in getypt kon worden. Nieuwe helper
   `weergaveAantal()` maakt onderscheid tussen "leeggemaakt" (`''`, blijft
   leeg) en "nog nooit gezet" (`null`/`undefined`, wordt 0 als startpunt voor
   een net aangemaakte regel) -- gebruikt op alle vier plekken die dit
   patroon hadden. Bijkomende, aparte bug in `bindLijst()` (de gedeelde
   handler achter Uitbesteding/Equipment): die zette bij een leeggemaakt
   "aantal"-veld expliciet `0` in de state zelf (niet pas in de weergave),
   dus zelfs met `weergaveAantal()` zou dat veld alsnog meteen "0" tonen.
   Rechtgetrokken naar hetzelfde patroon als materiaal/installaties
   (`nonNegatief(e.target.value)`, dat een lege string al langer ongemoeid
   liet).
2. **Cijfers kwamen in de verkeerde volgorde terug** ("123" typen gaf "321").
   `restoreFocus()` bewaart en herstelt de cursorpositie via
   `setSelectionRange()` -- maar die methode bestaat niet voor
   `input type="number"` (de bestaande `catch`-regel wist dit al, zonder dat
   er ooit iets mee werd gedaan). Zonder herstelde cursorpositie valt de
   cursor na elke her-render terug op het begin van het veld, dus kwam elk
   volgend cijfer vóór het vorige te staan in plaats van erachter. Fix: de
   vier "aantal"-velden gebruiken nu `type="text" inputmode="numeric"` in
   plaats van `type="number"` -- `setSelectionRange()` werkt daar wél, dus
   landt de cursor na elke render weer op de juiste plek. (Bewust alleen deze
   vier velden: prijs/tarief/uren-velden delen dezelfde onderliggende
   kwetsbaarheid maar zijn niet gemeld als stuk; zelfde fix toepassen zodra
   dat wél gebeurt.) De numerieke validatie die `type="number"` bood komt
   hiermee te vervallen, maar niets rekent ooit met een ongeldige tekststring
   zonder terugval: `Number(x)||0` aan de clientkant en `_num()`
   (`calculatie/rekenkern.py`) aan de serverkant behandelen een leeg of
   onverwerkbaar "aantal" allebei al stilzwijgend als 0.
3. **Typen in Uitbesteding sprong naar een veld bij APPARATUUR.** `newId()`
   (`let uid=1; () => 'calcid'+(uid++)`) is een simpele, gedeelde teller --
   maar die teller is alleen een in-memory JS-variabele en begint dus bij
   élke pagina-herlaad weer bij 1, terwijl een herladen project (autosave of
   een geopend bestand) rijen met al bestaande ids als "calcid7" meebrengt.
   Werd er ná zo'n herlaad een nieuwe rij toegevoegd (bijv. een
   materiaalartikel via de zoekbalk), dan gaf `newId()` een id terug dat al
   in gebruik was door een rij uit een ANDERE lijst -- twee rijen met
   hetzelfde `data-id`. `restoreFocus()` matcht enkel op
   `data-id`+`data-field` en pakt de EERSTE match in DOM-volgorde; omdat
   Materiaal vóór Uitbesteding rendert in `renderAll()`, won het
   APPARATUUR-veld dat toevallig hetzelfde id had. Nieuwe
   `hersynchroniseerIdTeller()` zet `uid` na het laden van een project
   (zowel bij opstarten als bij "Openen") op één hoger dan het hoogste
   gevonden `calcidN` over alle opties en lijsten heen, zodat een
   nieuw-toegevoegde rij nooit meer een bestaand id kan hergebruiken.

**Getest met Playwright:** een installatieveld leegmaken en een nieuw getal
typen (blijft leeg tot er getypt wordt, geen "0" die terugkomt); "1", "2", "3"
na elkaar typen in een leeg aantal-veld geeft "123", niet "321"; een pagina-
herlaad gevolgd door een nieuw toegevoegd materiaalartikel geeft nog steeds
allemaal unieke ids; typen in een Uitbesteding-aantal-veld laat de focus op
diezelfde regel staan. Volledige Python-testsuite (265 tests) ongewijzigd en
nog steeds groen -- ook deze wijziging raakt alleen `scherm/calculatie.js`.

## Een al ingevuld Excel-calculatieblad weer INLADEN (`calculatie.calculatieblad.lees_calculatieblad`, 2 oktober 2026)

Op verzoek van Lars: "Calculatie openen" kon tot nu toe alleen het eigen
`.json`-projectbestand van deze tool openen, terwijl alle bestaande
calculaties in het Excel-bedrijfssjabloon staan (hetzelfde
`Template_Calculatieblad.xltx` dat `calculatie/calculatieblad.py` hierboven
al vult voor de downloadknop) -- zodat voor een bestaande calculatie alsnog
snel een brief gemaakt kan worden, moet zo'n al ingevuld `.xlsx`-bestand ook
weer in te laden zijn. Nieuwe knop **"Calculatieblad importeren…"**
(`scherm/index.html`, naast "Calculatie openen…"), nieuw endpoint
**`POST /calculatieblad/importeer`** (`server.py`, base64-gecodeerd bestand
net als `/datablad`), nieuwe functie **`lees_calculatieblad()`** in
`calculatie/calculatieblad.py`.

**Het vertrekpunt is de letterlijk omgekeerde celtabel van
`schrijf_calculatieblad()`** (dezelfde module, hierboven al uitgebreid
gedocumenteerd): elke cel die daar een eigen, overschrijfbare INVOER is, is
hier een leesbare bron voor een state-veld; elke cel die daar een
AFGELEIDE/berekende waarde is (`B5`/`B6`/`B9`, de "definitief"-formules in de
uren-sectie, `F440`/`F443`, alle Quotation-sheet-totalen) wordt bewust NIET
gelezen -- die komt vanzelf weer goed zodra `rekenkern.bereken()` op de
geïmporteerde staat draait. Dezelfde "één plek per berekening"-regel
bovenaan dit bestand, nu toegepast op import: een rekenkern-uitkomst wordt
hier nooit teruggelezen alsof het invoer was.

**Moet twee heel verschillende soorten bestanden aankunnen.** Een bestand dat
deze tool zelf exporteerde (platte getallen/`inlineStr`, zie
`SheetSchrijver`) is het makkelijke geval; de eigenlijke reden van bestaan is
een ECHT, met de hand in de oorspronkelijke, losstaande Excel-tool ingevuld
bestand -- en dat laat de sjabloonformules doorgaans gewoon intact (iemand
vult het in zoals een willekeurig Excel-bestand) en gebruikt voor tekst bijna
altijd shared strings (`t="s"`, een verwijzing naar `xl/sharedStrings.xml`)
in plaats van inline-tekst. **`SheetLezer`** leest daarom altijd de door
Excel laatst gecachte `<v>`/tekstwaarde van een cel, ongeacht of die cel een
formule heeft -- voor een cel die zelf nooit wordt overschreven (zoals de
"definitief"-uren, die in het KALE sjabloon een `ROUNDUP(...)`-formule zijn,
geverifieerd door het sjabloon zelf uit te pakken en na te lezen, zie
git-geschiedenis) is dat precies de waarde die Excel bij de laatste keer
opslaan ook liet zien. **`_sheet_pad()`** zoekt het tabblad bovendien altijd
op NAAM (`"Calculatie"`/`"Quotation sheet"`, via `workbook.xml` +
`workbook.xml.rels`) in plaats van op de huidige `sheet5.xml`/`sheet4.xml`
van de schrijfkant hierboven te vertrouwen -- een jarenlang met de hand
bijgehouden bestand kan een andere interne bestandsvolgorde hebben gekregen,
ook al heet het tabblad voor de gebruiker nog steeds hetzelfde.

**Niet herleidbaar: losse installatieregels.** `_vul_installaties`
exporteert per systeemsoort alleen het TOTAAL aantal buiten-/binnendelen
(`B12/13`, `B16/17`, `B20/21`, `B24/25`) -- zo legde de oorspronkelijke,
losstaande Excel-tool dit al vast vóórdat deze tool bestond, met vier vaste
slots ("SOORT INSTALLATIE 1" t/m "4" = VRF/RAC/PAC/Overig, bevestigd door het
kale sjabloon zelf uit te pakken). Er is geen cel die vastlegt uit hoeveel
LOSSE installaties (elk met een eigen merk/montagewijze/model) dat totaal is
opgebouwd. Import maakt daarom per systeemsoort met een niet-nul totaal
precies ÉÉN synthetische installatieregel aan met dat totaal, en laat
merk/montagewijze/model bewust leeg -- nooit een gok welke installatie(s) dat
totaal vormen. De geretourneerde `waarschuwingen`-lijst (zie hieronder) noemt
dit altijd expliciet zodra er installaties zijn geïmporteerd, zodat
"controleer dit" behouden blijft zonder dat er ergens een los
badge-per-veld-systeem bij hoefde (dezelfde aanpak als de
"controleer dit"-melding bij de calculatie→brief-overdracht hierboven).

**Niet herleidbaar (bewust, al sinds de exportkant): materiaal zonder
`row`.** `_vul_materiaal` slaat een materiaalregel zonder `row`-veld al over
bij het EXPORTEREN (geen Excel-rij om in te schrijven) -- dat raakt specifiek
een via de Panasonic/Daikin-zoekbalk toegevoegd artikel (`bron:
"panasonic"/"daikin"`, geen `row`) en een vrije PROJECTBESTELLING-regel. Zo'n
regel is dus ook bij het weer INLEZEN nooit terug te vinden: hetzelfde,
al bestaande gat in beide richtingen, geen nieuwe beperking van deze functie.
In de praktijk raakt dit vooral calculaties die al in déze tool zijn gemaakt
met de nieuwere Panasonic/Daikin-zoekfunctie (die bestond niet in de
oorspronkelijke Excel-tool) -- een ECHTE historische Excel-calculatie had het
model altijd al rechtstreeks in een van de vrije, naamloze APPARATUUR-rijen
staan (`data/materiaal_catalogus.json` se rijen 37-46 e.d. hebben
`omschrijving: null`, precies de vrije rijen waar iemand in Excel het
model+de prijs met de hand intypte) -- en díe rijen hebben wél een `row` en
komen dus gewoon mee, D/E/F/A-kolom en al.

**Herkent een bewuste override, verzint er nooit zelf een.**
`A343`/`A356`/`A377` (servicemonteur/hoofd-/hulpmonteur "definitief") zijn in
het sjabloon zelf `ROUNDUP(...)`-formules die het automatische voorstel
uitrekenen -- maar met de hand te overschrijven (vandaar de
`override`-velden in `rekenkern.nieuwe_staat()`). Om "nooit aangeraakt" van
"bewust overschreven" te onderscheiden herberekent de import het voorstel
opnieuw (`rk.servicemonteur_voorstel()`/`rk.monteur_voorstel()`) met de dan
al geïmporteerde installaties/materiaal/instellingen/overig, en vergelijkt
dat met de gelezen waarde: wijken ze (met een kleine afrondingsmarge) af,
dan was het een override en komt die met de echte waarde mee; komen ze
overeen, dan blijft `override` gewoon `None` -- een rondje export→import mag
nooit op zichzelf al een calculatie "overschreven" laten lijken die dat niet
was.

**Onherkende waarden (moeilijkheidsgraad/provincie/bonusklant/provisieklant)
vallen terug op de bijbehorende `rekenkern.nieuwe_staat()`-standaardwaarde,
nooit een gok** -- met een leesbare waarschuwing in de geretourneerde lijst,
zelfde "nooit gokken, wel een duidelijke melding"-regel als `overdracht.py`.
Een `R71` (verkoopprijs) van letterlijk `0` wordt ook behandeld als "nog niet
ingevuld" (`None`): het kale sjabloon begint daar zelf al op `0` te staan,
niet te onderscheiden van een bewust ingevulde prijs van nul euro (die in de
praktijk nooit voorkomt).

**Getest zonder een door Lars aangeleverd, écht ingevuld voorbeeldbestand.**
Deze implementatie is opgebouwd uit een handmatige inspectie van het kale
`Template_Calculatieblad.xltx` zelf (uitgepakt en nagelezen: shared strings,
welke cellen een formule hebben, de exacte rijlabels) plus rondje-tests
(`tests/test_calculatieblad.py`, `TestInlezenRondje`): een staat exporteren,
weer inlezen, en controleren dat `rekenkern.bereken()` op de geïmporteerde
staat dezelfde marge/uren teruggeeft als op de oorspronkelijke -- voor alles
wat wél herleidbaar is (zie hierboven voor wat bewust niet is). **Eén test
(`TestInlezenEchteSjabloon`) leest het kale sjabloonbestand zelf** (dus geen
door deze module zelf geschreven bestand) -- dat gebruikt al overal ECHTE
shared strings en laat zijn formules intact, de dichtstbijzijnde benadering
van een écht ingevuld bestand die hier zonder een voorbeeld van Lars te
krijgen is. Dat bewijst dat de celverwijzingen kloppen en dat shared-strings/
formule-cellen correct worden gelezen; het bewijst niet dat een jarenlang met
de hand bijgehouden bestand geen rijen heeft verplaatst, extra tabbladen
heeft gekregen, of op een andere manier afwijkt van dit ene sjabloon. **Stuur
hier je eerste paar echt ingevulde calculatiebladen doorheen voordat je
hierop vertrouwt voor belangrijk werk** -- precies dezelfde voorzichtigheid
die bij de downloadkant hierboven ook al gold, nu voor de andere richting.

**Inmiddels getoetst tegen een écht door Lars ingevuld bestand (2 oktober
2026).** Las zonder crash in, en alle instellingen/installaties/materiaal/
uitbesteding/equipment/uren kwamen er correct uit -- geverifieerd cel voor
cel door het bestand zelf uit te pakken en met de uitkomst te vergelijken
(bijv. `B334`=2 → `uren.projectleider.werk`, `D433`="Geen parkeerkosten" →
`instellingen.provincie`, `A356`/`A377` allebei 11 → geen override, want
hoofd- en hulpmonteur komen in dit bestand toevallig op hetzelfde automatische
voorstel uit). **Eén echte bug eruit gehaald:** iemand had in dit bestand een
kaal getal (`1`, geen tekst) getypt in de TYPE-kolom van een eigen
APPARATUUR-regel (rij 37) -- `SheetLezer.tekst()` deed daar `str(1.0)` mee,
wat `"1.0"` opleverde in plaats van het nette `"1"` dat iemand in Excel ziet.
Fix: `tekst()` hergebruikt nu dezelfde opmaakregel als `_getal_tekst()` (de
schrijfkant hierboven) voor een cel die toevallig numeriek blijkt te zijn,
óók als het om een "tekst"-kolom gaat. Vastgelegd als regressietest
(`test_kaal_getal_in_een_tekstkolom_geeft_geen_punt_nul`). Live door het
scherm heen getest (Playwright): importeren, renderen van de installatiekaart,
en doorrekenen via `/bereken` gaven alle drie geen fouten.

## Drie meldingen van Lars, live uitgezocht (5 oktober 2026)

Lars vroeg de laatste commit van `Calculatie-tool-Schilt` (de losstaande
calculatietool, niet de brieventool — zie git-historie voor hoe dat
misverstand is uitgezocht: die bleek al volledig verwerkt) te bekijken, en gaf
daarbij meteen drie losse meldingen door. Alle drie zijn uitgezocht door het
écht te draaien (Playwright), niet alleen door de code te lezen — precies de
werkwijze die bij de "Vier gaten in de overdracht"-sectie hierboven ook al
twee keer een stil gat vond dat bij statisch lezen onzichtbaar bleef.

### 1. Twee ontbrekende Q-kosten-regels in het calculatieblad

Het Excel-sjabloon (Quotation sheet!I38/I39) kent twee vaste kostenregels,
"SHORT TRIP ALLOWANCE" (dagen × tarief) en "TRANSFER QUOTATION FULL COST"
(uren × tarief) — Lars: "Dit zijn de Qkosten die bij elke calculatie moet
worden toegevoegd." Geen van beide had een tegenhanger in deze tool: niet als
invoerveld in het scherm, niet in `rekenkern.bereken()`, en dus ook niet in
het geëxporteerde of geïmporteerde calculatieblad (`calculatieblad.py`) —
elke calculatie in deze tool miste dit bedrag domweg.

**Nieuwe velden `overig.shortTripDagen`/`shortTripTarief`/`transferUren`/
`transferTarief`** (`calculatie/rekenkern.py`, `scherm/calculatie.js`), twee
nieuwe regels in de "Overig"-kaart (`scherm/index.html`) en twee nieuwe
regels in de margetabel (`mg_shorttrip`/`mg_transfer`, direct na "Arbeid").
In het Excel-sjabloon zelf staan deze twee regels bij de arbeidskosten
(`R42` = `SUM(R34:R40)`, dus arbeid + deze twee regels samen, vóór de
materiaal/uitbesteding-kant) — `marge_berekening()` telt
`shortTripKosten`/`transferKosten` daarom ook rechtstreeks bij `ic` op, niet
bij `overigeKosten` (dat is bewust de materiaal/uitbesteding-stroom).

**Standaardwaarden volgen hetzelfde patroon als `nachten`/`nachtprijs`**: het
AANTAL (dagen/uren) begint op 0 — dat is per calculatie verschillend en nooit
een gok — maar `transferTarief` krijgt wel een zinnige standaardwaarde
(`DEFAULT_TARIEVEN["projectmanager"]` = 158, hetzelfde tarief: deze kosten
zijn immers diens tijd om de offerte over te dragen). Belangrijk hierbij:
0 uren/dagen × een tarief blijft altijd 0 euro, dus deze toevoeging verandert
niets aan een calculatie die het veld niet gebruikt — geen van de 292
bestaande tests hoefde aangepast te worden op dit punt. `shortTripTarief`
heeft geen vergelijkbaar vast tarief (staat ook leeg in het kale
Excel-sjabloon) en begint dus op 0.

**`calculatie/calculatieblad.py`**: `_vul_quotation()` schrijft `M38`/`P38`/
`R38` en `M39`/`P39`/`R39` nu als kant-en-klare waarden (formule verwijderd,
dezelfde regel als de rest van deze module), en `R42` is nu
`arbeid + shortTripKosten + transferKosten` in plaats van alleen `arbeid`.
Nieuwe leesfunctie `_lees_quotation_overig()` (naast de bestaande
`_lees_overig()`, die op het blad "Calculatie" leest — deze twee regels staan
op "Quotation sheet") maakt dit ook bij het importeren rond: een bestaand,
extern ingevuld calculatieblad dat deze twee regels al had ingevuld, komt nu
ook echt met die bedragen mee in plaats van ze stilzwijgend te laten vallen.

**Getest:** nieuwe rekenkern-tests (`test_short_trip_en_transfer_tellen_mee_in_ic`,
`test_nieuwe_staat_heeft_geen_qkosten_zonder_aantal`), nieuwe
calculatieblad-tests voor zowel export (`test_short_trip_en_transfer_cellen`)
als het exportrondje (`test_overig_en_marge_komen_over` uitgebreid,
`test_short_trip_nul_blijft_nul_na_rondje` nieuw). Live getest met Playwright:
2 dagen × €65 + 5 uur × €158 ingevuld, marge-tabel en `/bereken` toonden
beide correct €130 + €790 = €920 extra in de intermediary cost, en het
gedownloade calculatieblad bevatte de juiste, formuleloze cellen (met de hand
nagelezen in de ruwe XML) — een rondje export→import gaf dezelfde waarden
terug.

### 2. De klantnaam kwam niet zichtbaar over — een echt gat, geen misverstand

Lars: "Hij neemt niet alles over vanuit de calculatie, Q nummer, klantnaam,
welke installatie model." Het Q-nummer en de systeemsoort/model-per-installatie
bleken bij live testen gewoon te werken (zie "Vier gaten"/"Synchronisatie"
hierboven) — maar de klantnaam bleek een echt, nieuw gat.

**De oorzaak.** De calculatie heeft precies één vrij tekstveld voor de
klantnaam; de brief onderscheidt een organisatie (zakelijke klant) van een
persoon (`aanspreekvorm`/`voorletters`/`achternaam`, ook als contactpersoon
bíj een zakelijke klant) via `klanttype` — een begrip dat uitsluitend in de
brief bestaat (zie de btw-uitleg hierboven). Bij de EERSTE overdracht staat
`klanttype` dus nog op zijn standaardwaarde "particulier". `overdracht.py`
zette de klantnaam al in `organisatie`, gemarkeerd als "afgeleid" — maar een
`organisatie`-blok in de brief rendert alleen bij `klanttype == 'zakelijk'`.
Bij "particulier" (de standaard) bleef `achternaam` daardoor gewoon op het
voorbeeld uit `BEGINSTAND` staan ("ten Broek") — en omdat dat veld dus al
"gevuld" is, zag `controle.ontbrekende_gegevens()` niets mis.

**Live aangetoond:** een calculatie voor klant "Jansen Vastgoed BV" leverde
een briefvoorvertoning op die echt "De heer K. ten Broek" aanschreef, zonder
enige waarschuwing — de werkelijke naam stond wel (gemarkeerd) in
`organisatie`, maar was in de praktijk onzichtbaar. Dit is precies zo'n gat
als de vier eerdere (zie hierboven): bij statisch lezen van `overdracht.py`
leek dit in orde ("afgeleid" + een eigen waarschuwingstekst die zelfs met
zoveel woorden zegt "bij een particuliere klant hoort deze juist leeg te
blijven"), maar niemand trok daar de consequentie uit totdat de brief er
echt bij stond.

**De fix.** Hier valt niet te gokken of de klant een bedrijf of een
privépersoon is — dat onderscheid bestaat alleen in de brief. In plaats van
zelf te raden in welk veld de naam hoort, maakt `overdracht.py` `achternaam`
nu bewust LEEG zodra er een klantnaam is (status "keuze_nodig", niet
"afgeleid" — er wordt immers geen waarde gegeven). Dat maakt het gat
zichtbaar via de al bestaande `controle.ontbrekende_gegevens()`-controle
(`achternaam` staat al in `controle.VASTE_VELDEN`, zie de commentaar
daarboven) in plaats van een plausibele maar verzonnen naam onopgemerkt te
laten staan. `OVERDRACHT_VELDLABELS` (`scherm/brief.html`) kreeg er een label
voor, zodat de controleerbalk "Achternaam (contactpersoon/particuliere
klant)" noemt in plaats van het rauwe veldpad.

**Dit overschrijft een eventueel al met de hand ingevulde achternaam bij een
volgende klik op "↺ Vanuit calculatie"** — maar dat gold al voor
`organisatie`/`projectnummer`/`briefdatum` (plain `A[sleutel]=waarde` voor
elke sleutel die `overdracht.py` teruggeeft, zie "De briefstap is 1-op-1
overgenomen" hierboven): die knop is bedoeld als "opnieuw synchroniseren
vanuit de calculatie", dus dit is bestaand, verwacht gedrag, geen nieuw
risico.

**Getest:** nieuwe tests in `tests/test_overdracht.py`
(`test_klantnaam_maakt_achternaam_bewust_leeg`,
`test_geen_klantnaam_laat_achternaam_ongemoeid`). Live met Playwright herhaald
na de fix: dezelfde calculatie geeft nu een brief met een lege
aanhef/adresregel voor de achternaam (zichtbaar `ten Broek`-vrij) én
`controle.ontbrekende_gegevens()` noemt "de achternaam" nu terecht als
ontbrekend.

### 3. Het laadscherm-filmpje speelde opnieuw af bij elke terugkeer naar de calculatie

Lars: "Ook wanneer ik vanuit de brief terug ga naar de calculatie speelt het
laadscherm/filmpje weer af. Dit filmpje moet enkel afspelen wanneer de tool
de eerste keer wordt opgestart." `CB.laadscherm` (`scherm/gedeeld.js`) had
geen geheugen van "is dit al vertoond in deze sessie" — elke keer dat
`index.html` opnieuw laadt (de "← Calculatie"-link in `scherm/brief.html`,
maar ook een gewone F5) begon de hele overlay, inclusief de opzettelijk lange
`MINIMALE_DUUR_MS` (~10,3s, zie de laadscherm-sectie hierboven), gewoon
opnieuw.

**Fix:** een nieuwe `sessionStorage`-sleutel (`calcubrief.laadschermGetoond`,
zelfde opslagplek/reden als `AUTOSAVE_SLEUTEL`: per tabblad, overleeft
navigatie/F5, begint leeg bij een nieuw tabblad — exact het gewenste "éénmaal
per sessie"-gedrag). `init()` slaat de video nu over en valt direct terug op
de bestaande `_toonSpinnerTerugval()`-route (dezelfde korte, 300ms-wachttijd
als wanneer het filmpje niet kan worden afgespeeld) zodra deze sleutel al
gezet is — geen nieuwe code-paden, alleen een eerder bestaand terugvalpad
hergebruikt.

**Getest met Playwright:** een eerste `index.html`-load in een nieuwe tab zet
de sessionStorage-sleutel en toont het filmpje; een navigatie naar
`brief.html` en terug (`page.goBack()`) laat het laadscherm-element nog heel
even verschijnen maar zonder de video (overgeslagen) en verdwijnt binnen
~350ms in plaats van de volle ~10 seconden.

**Volledige Python-testsuite: 298 tests, groen** (was 292 — de nieuwe
Q-kosten- en achternaam-tests erbij). Deze drie wijzigingen raken
`calculatie/rekenkern.py`, `calculatie/calculatieblad.py`, `overdracht.py`,
`scherm/calculatie.js`, `scherm/index.html`, `scherm/brief.html` en
`scherm/gedeeld.js` — niet `brieventool/samenstellen.py` of
`analyse/teksten.yaml` (dus geen `tools/ververs_brief_scherm.py` nodig).

## Panasonic RAC/PAC-prijscatalogus bijgewerkt naar oktober 2026 (5 oktober 2026)

Lars leverde twee nieuwe prijslijst-PDF's aan (`prijscatalogus-rac_102026` en
`-paci_102026`, "geldig vanaf 1 oktober 2026") met de uitdrukkelijke
instructie: dit zijn BRUTO prijzen, en de tool moet NETTO rekenen (bruto −
43% korting). Dat is precies wat `data/panasonic/rac.json`/`pac.json` al
deden (`meta.korting_pct: 0.43`, `netto_prijs = round(bruto_prijs * 0.57, 2)`,
zie `scherm/calculatie.js` se `materiaalRegelUitPanasonic()`/
`voegPanasonicToe()`) — dit was dus een kwestie van de 189 `bruto_prijs`-
waarden in die twee bestanden bijwerken en `netto_prijs` opnieuw laten
uitrekenen, niet een nieuwe functie bouwen.

**Waar prijsdata hoort.** Lars vroeg expliciet of nieuwe prijslijsten in déze
chat/repo thuishoren of in de losstaande `Calculatie-tool-Schilt`-repo
(waarnaar elders in dit bestand wordt verwezen voor UI-synchronisatie). Het
antwoord: hier, in `data/panasonic/` — dat is waar deze tool, de app die Lars
dagelijks gebruikt, zijn prijzen vandaan haalt. De losstaande
`calculatie-tool-schilt`-repo is alleen een referentie voor UI-verbeteringen,
geen bron van actuele prijsdata voor déze app.

**Geen PDF-bibliotheek beschikbaar, dus `tools/extract_pdf.py` hergebruikt.**
Dezelfde kale, stdlib-only tekst-extractor die al voor brieven bestond (zie
de moduledocstring daar: Flate-decompressie + regex over de PDF-tekst-
operatoren, géén volwaardige PDF-parser) bleek ook deze twee prijscatalogus-
PDF's (9,5-9,6MB, tekst-laag, geen scans) uitstekend leesbaar te maken — een
schone, regelmatige tekstdump per productrij (code/kW/SEER/SCOP/prijs, elk op
een eigen regel). `pdftoppm`/`pdftotext` (poppler) en elke Python PDF-
bibliotheek (pypdf, PyMuPDF, pdfplumber) zijn hier niet beschikbaar en niet
te installeren (apt/pip allebei door het sandbox-netwerkbeleid geblokkeerd,
zelfde beperking als bij `calculatieblad.py` hierboven) — dit was dus de
enige begaanbare weg, geen bewuste keuze tussen alternatieven.

**Elke rij handmatig tegen de bestaande JSON-structuur gelegd, niet
automatisch geparsed.** Met 75 (RAC) + 114 (PAC) bestaande artikelen, elk met
een eigen `rol`/`systeemtype`/`lijn`-indeling die niet uit de tekst zelf is
af te leiden (die indeling komt uit de visuele pagina-indeling van het
origineel, niet uit de kale tekststroom), was een generieke regel-parser een
groter risico dan baat: de bestaande volgorde en indeling van beide bestanden
is regel-voor-regel nagelopen tegen de nieuwe catalogustekst (zelfde
productcode, zelfde positie in de lijst), en alleen `bruto_prijs` (plus een
klein aantal hieronder genoemde correcties) is aangepast. Dat garandeert dat
geen enkel bestaand artikel per ongeluk van categorie wisselt of een verkeerd
label krijgt.

**Vier dingen die verder zijn gevonden, niet alleen prijzen:**
- **Twee bestaande typefouten gecorrigeerd.** RAC Solo's binnenunit-/
  buitenunitcode stond als `P-M0G16IC5-E`/`P-M0Z20IC5-E` (cijfer "0") in
  plaats van het echte `P-MOG16IC5-E`/`P-MOZ20IC5-E` (letter "O") — de nieuwe
  catalogustekst laat dit ondubbelzinnig zien, dus rechtgezet.
- **Twee PACi-productcodes zijn door Panasonic zelf hernoemd** in deze
  editie: "Jet Air Stream Standard" se binnenunit werd
  `P-VTVF140/250NC5A-PE` (was `P-VTVF140/250MC5-PE`, een N- in plaats van een
  M-serie), en "Jet Air Stream Ducted" se set-code kreeg een extra "A"
  (`KIT-140/250PC5AZH8`, was `KIT-140/250PC5ZH8`). Beide alleen zo
  overnemen (niet de oude code laten staan) omdat zoeken op de oude code na
  deze catalogus-editie toch niets meer zou opleveren.
- **Eén ontbrekende regel toegevoegd:** `LBK-aansluitkit Elite` had in het
  bestaande bestand geen aparte prijs voor `U-71PZH4E8` (alleen voor
  `U-71PZH4E5`) — de nieuwe catalogus laat beide zien. Toegevoegd vlak na de
  E5-regel (met dezelfde `lijn`/`systeemtype`), dus `pac.json` heeft nu 115
  in plaats van 114 artikelen.
- **Eén categorie kon NIET worden bijgewerkt: losse "Utiliteit twin/triple/
  double-twin"-buitenunits** (PACi NX Standard/Elite, de oude artikelen
  82-92). Deze catalogus-editie bevat voor deze buitenunits alleen nog een
  combinatiematrix (welke binnenunits met welke buitenunit, zónder prijs) --
  geen eigen prijsregel meer zoals eerder. De oude bruto-prijzen zijn daarom
  bewust ONGEWIJZIGD gelaten in plaats van te gokken of ze nog kloppen, met
  een `meta.niet_bijgewerkt`-vermelding in `pac.json` zelf als geheugensteun.
  **Navraag bij Lars nodig:** worden deze nog los verkocht, en zo ja tegen
  welke prijs?

**`panasonic_id` (client-side, `scherm/calculatie.js`) is een array-index,
geen stabiele sleutel** (`'RAC-' + i`/`'PAC-' + i`, toegekend bij het laden
van de JSON) — gebruikt alleen om bij het TOEVOEGEN via de zoekbalk te
herkennen "dit artikel staat al in de materiaallijst, aantal ophogen in
plaats van dupliceren". Een eerder opgeslagen project bewaart de waarde van
een materiaalregel (`prijs`/`omschrijving`/...) altijd al als momentopname,
nooit een live verwijzing naar de catalogus -- dus het invoegen van de
nieuwe LBK-regel (met een verschuiving van alle latere PAC-indices) kan geen
bestaand opgeslagen project corrumperen; in het ongunstigste geval herkent
een hernieuwde toevoeging van exact hetzelfde artikel via de zoekbalk het
niet meer als "al toegevoegd" en komt het er een keer dubbel bij in plaats
van het aantal op te hogen -- een onschuldig randgeval, geen dataverlies.

**Getest:** alle 298 Python-tests ongewijzigd en groen (de Python-kant van
deze tool leest `data/panasonic/*.json` nooit -- dat is pure
scherm/calculatie.js-opzoeklogica, zie de architectuurregel bovenaan dit
bestand). Live met Playwright: totaal aantal artikelen (75 RAC + 115 PAC)
geklopt, een paar steekproeven (KIT-TZ20-CKE, de hernoemde Ducted-code, de
nieuwe LBK-regel, de gecorrigeerde RAC Solo-code) gaven stuk voor stuk de
juiste bruto/netto-prijs terug, en de echte zoekbalk in het scherm (typen
"TZ20") toonde de bijgewerkte prijs (€ 501,60) in de resultatenlijst.

## Git

Ontwikkel op de branch `claude/magical-davinci-63dmec`. Commitberichten in
het Nederlands, beschrijvend (niet gebiedende wijs, niet verleden tijd), met
uitleg van het waarom bij niet voor de hand liggende keuzes.

## Lege `<select>`-velden in de brief toonden stilzwijgend de verkeerde optie (8 oktober 2026)

Lars, met een screenshot van een installatiekaart in `scherm/brief.html`:
"ik wil dat er alleen dingen vooraf worden ingevuld vanuit de calculatie,
alles wat je niet weet of niet kan overnemen gewoon leeg laten om verwarring
te voorkomen [...] wat wel en niet juist is overgenomen." De screenshot toonde
"Systeem: Split" en "Merk: Panasonic" bij een installatie die daar volgens
hem niets van wist.

**De data was al correct leeg -- het probleem zat puur in de weergave.** Live
getest (Playwright, een "Overig"-installatie zonder merk): `A.installaties[0]`
had `systeemsoort:""` en `merk:""`, precies zoals `overdracht.py` dat hoort
te doen bij "keuze_nodig" (zie de moduledocstring daar). Maar de
`keuzeveld()`-dropdowns voor `systeemsoort`/`merk`/`model_binnenunit` in
`bouwInstallaties()` (`scherm/brief.html`) hadden geen `<option value="">` --
en zonder een optie die matcht met een lege waarde selecteert de browser
gewoon stilzwijgend de EERSTE optie in de lijst (`"splitsystem"`/`MERKEN[0]`
= Panasonic). De onderliggende data bleef dus kloppen (een Word-bestand zou
hier niet per ongeluk "Panasonic" in krijgen, en `controle.ontbrekende_gegevens()`
zag dit gat ook niet, want die kijkt niet naar deze velden), maar het SCHERM
loog: het zag eruit als een zelfverzonnen gok die nooit had mogen gebeuren.

**Fix:** een `["", "— nog niet bekend —"]`-optie toegevoegd als eerste keuze
in alle drie de dropdowns (`systeemsoort`, `merk`, `model_binnenunit`). Een
installatie die met de hand in de brief wordt toegevoegd (`plus.onclick` in
`bouwInstallaties()`) blijft wél met zinnige standaardwaarden beginnen
(`splitsystem`/`MERKEN[0]`/`wand`) -- iemand gaat zo'n regel toch zelf
invullen, dat is dus geen gok maar een handig startpunt, net als
`nieuweInstallatie()` aan de calculatiekant. Alleen de koppeling tussen een
ECHT lege waarde (uit de overdracht) en een misleidende weergave is
rechtgezet.

**"Type binnendeel" heette verwarrend.** Dat veld bevat sinds de Fase-5-fix
(zie hierboven, "Vier gaten in de overdracht", punt 3) een productmodel
(bijv. "KIT-TZ20-CKE"), geen montage-categorie -- de naam "Type binnendeel"
paste daar al niet goed bij, en Lars vroeg expliciet om "Type installatie".
Hernoemd in het formulier (`tekstveld("type_binnendeel", "Type installatie", ...)`)
en in `OVERDRACHT_VELDLABELS` (de controleerbalk-tekst) -- de onderliggende
sleutel `type_binnendeel` blijft ongewijzigd (die staat ook in
`analyse/teksten.yaml`/het Word-sjabloon/`brieventool/controle.py`, een
hernoeming daarvan is een heel andere, veel grotere wijziging die hier niet
gevraagd is).

**De materiaal-koppeling zelf werkt al correct -- bevestigd door 'm echt te
draaien.** Lars vroeg zich af of het voor de tool "niet duidelijk is welke
van de geselecteerde onderdelen in de calculatie het systeem is," en stelde
voor een aparte selectie-optie te maken. Die bestaat al: `installatie.materiaalId`
+ de "Model (...)"-dropdown in de installatiekaart (`scherm/calculatie.js`,
zie Fase 5 hierboven) -- live getest (Playwright): een Panasonic-systeem via
de zoekbalk toegevoegd, gekoppeld aan een installatie, en `A.installaties[0]
.type_binnendeel` kwam er na de overdracht correct als `"KIT-TZ20-CKE"` uit.
Geen bug dus, maar waarschijnlijk een **ontdekkingsprobleem**: de
installatiekaart heeft TWEE velden die allebei met "het systeem" te maken
lijken te hebben -- "Type binnendeel" (een grove montage-categorie,
Kanaalunit/Cassetteunit/..., puur voor de `model_binnenunit`-vertaling, telt
niet mee in de urenberekening) vlak boven "Model (uit materiaallijst)" (de
echte productkoppeling voor de brief) -- en het is aannemelijk dat niet
duidelijk was dat specifiek de TWEEDE van die twee bepaalt wat er in de brief
als modelnummer verschijnt. Het label is daarom hernoemd naar "Model
(koppeling voor de brief)" met een (ⓘ)-tooltip die expliciet zegt wat het
doet en wat er gebeurt zonder koppeling (hetzelfde `.info-icon`-patroon als
elders in deze kaart, zie "Opmaak-opschoning" hierboven) -- geen nieuw
mechanisme, wel een duidelijkere aanwijzing naar het bestaande.

**Getest:** volledige Python-testsuite (298 tests) ongewijzigd en groen --
deze wijziging raakt alleen `scherm/brief.html`/`scherm/calculatie.js`. Live
met Playwright: de "Overig"-installatie toont nu "— nog niet bekend —" voor
Systeem/Merk in plaats van Split/Panasonic; een installatie met een echte,
afgeleide systeemsoort (RAC + 1 binnendeel → splitsystem) toont nog
steeds gewoon de juiste waarde; de materiaal-koppeling geeft nog steeds het
juiste modelnummer door; de controleerbalk noemt het veld nu "type
installatie (model)".

## Nieuw Excel-bedrijfssjabloon (9 oktober 2026): rij-layout verschoven, nieuwe Betalingskorting

Lars leverde een nieuwe versie van `Template_Calculatieblad.xltx` aan: "Zo
hebben er een aantal veranderingen plaatsgevonden in het calculatieblad.
Producten hebben andere namen gekregen, prijzen zijn veranderd etc etc." Een
cel-voor-cel diff tegen het vorige sjabloon (beide uitgepakt als ZIP+XML,
zelfde aanpak als `calculatieblad.py` zelf gebruikt) liet zien dat dit meer
was dan alleen productdata: de rij-layout van het blad "Calculatie" zelf
verschoof, en er is een nieuw kortingsmechanisme bijgekomen.

**Eén rij verwijderd, dus alles erna schuift op.** Rij 117 (een vervallen
artikel, "Stuurstroomkabel LSOH Cca 4x1,5 mm2" -- hetzelfde artikel is ook
uit de YIMM-lijst verdwenen, zie hieronder) bestaat niet meer in het nieuwe
sjabloon. Elke rij ná 117 ligt daardoor één lager dan voorheen -- bevestigd
door de materiaalcatalogus-rijen (80-242) te matchen op artikelcode
(stabiel, rij-onafhankelijk) tussen oud en nieuw sjabloon: nul onverwachte
afwijkingen voor alle 159 YIMM-gekoppelde regels zodra de -1-regel werd
toegepast.

**Een nieuw ingevoegd blok (Betalingskorting) schuift op zijn beurt weer
3 rijen terug.** Tussen de bestaande Omzetbonus- en Provisie-blokken (rijen
438-440 resp. 444-445 in de nieuwe nummering) staat nu een derde,
gelijkvormig blok: Betalingskorting (rij 441-443). Het resultaat is dus geen
uniforme verschuiving over het hele blad: rijen 118 t/m 441 liggen -1 t.o.v.
het vorige sjabloon, rijen 442 en hoger weer +2 (per saldo) t.o.v. het vorige
sjabloon. Dezelfde twee verschuivingen gelden voor de corresponderende
formules op "Quotation sheet" die naar "Calculatie" verwijzen (bijv.
`Calculatie!A330` → `Calculatie!A329`) -- de Quotation-sheet-rijen zelf
onder rij 74 zijn ongewijzigd, pas vanaf rij 74 (de nieuwe BETALINGSKORTING-
rij, zie hieronder) schuift ook dat blad.

**Alle rij-constanten in `calculatie/calculatieblad.py` zijn dienovereenkomstig
bijgewerkt**, zowel de schrijf- als de leeskant: `SECTIE_SUBTOTAAL_RIJ`,
`UITBESTEDING_RIJEN`/`UITBESTEDING_LEGE_RIJEN`, `EQUIPMENT_RIJEN`/
`EQUIPMENT_LEGE_RIJEN`, alle rijen in `_vul_uren`/`_lees_uren`, de
instellingen-cellen (provincie/bonusklant/kortingklant/provisieklant,
nu D432/D439/D442/D445), de kabelgoot-materiaalrijen in `_monteur_termen`
(123-125 → 122-124), en de Quotation-sheet-cellen voor
garantie/verkoopprijs (zie hieronder). **`data/materiaal_catalogus.json`'s
`row`-veld is voor elke regel met een oude rij > 117 met 1 verlaagd**, de
regel op de verwijderde rij 117 is uit de catalogus gehaald, en de
nieuwe prijzen/namen (zie hieronder) zijn erin verwerkt.

**Een subtiele tweede trap: `afgeleid_van`-verwijzingen binnen de catalogus
zelf.** Een paar materiaalregels (trillingsdempers, een paar luchtverdeel-
onderdelen) worden automatisch afgeleid van het aantal van een ANDERE regel
in dezelfde catalogus (`rekenkern.sync_afgeleide_aantallen()`,
`afgeleid_van: [{"row": N, "factor": F}, ...]`). Die `row`-verwijzingen zijn
GEEN Excel-celadressen maar interne verwijzingen tussen catalogusregels --
en dus net zo goed onderhevig aan dezelfde -1-verschuiving als de regels
zelf. De eerste migratiepas verschoof alleen het top-level `row`-veld van
elke regel, niet deze geneste verwijzingen -- een test die een specifieke
bronrij hardcodeerde (`test_afgeleide_regel_komt_ook_letterlijk_terecht`)
ving dit direct op (de bronregel die hij aansprak bleek na de migratie een
ANDERE, zelf-afgeleide regel geworden, dus "geen enkele afgeleide regel"
in plaats van de verwachte). Rechtgezet met een aparte migratiepas specifiek
voor deze geneste `row`-velden, en de test zelf bijgewerkt naar de nieuwe
rijnummering.

## Nieuw: Betalingskorting (derde debiteur-kortingslijst naast Omzetbonus/Provisie)

Het nieuwe sjabloon heeft een hernoemd verborgen blad
("Omzetbonus+Provisie" → "Omzetbonus+Provisie+Bet. korting") met een derde
kolomgroep (G/H: debiteur → kortingspercentage, bijv. "Hoppenbrouwers" → 2%)
naast de bestaande Bonus- (A/B) en Provisie-kolommen (D/E). Qua Excel-formule
werkt het identiek aan Omzetbonus: `Calculatie!F442` doet een VLOOKUP tegen
deze lijst, en `Quotation sheet!R74` (`=R71*P74`) telt die korting bij de
verkoopprijs op -- **niet als een korting die van de prijs afgaat**, maar
net als omzetbonus/garantie als een bedrag dat MEE gegrossdeerd wordt in de
`SALES PRICE`-formule (nu `R77 = (R71+R73+R74+R75)/(1-F445)`, was
`R76 = (R71+R73+R74)/(1-F443)` met R74=garantie): wie een klant een
betalingskorting geeft, moet de eigenlijke verkoopprijs dus naar boven
bijstellen om toch het beoogde projectresultaat te halen.

**Doorgevoerd als een volwaardig vierde instellingenveld**, hetzelfde patroon
als bonusklant/provisieklant:
- `data/omzetbonus_provisie.json` kreeg een derde lijst, `"korting"`
  (`"Geen betalingskorting"` → 0, `"Hoppenbrouwers"` → 0.02).
- `rekenkern.nieuwe_staat()`'s `instellingen` kreeg `kortingklant: "Geen
  betalingskorting"`; `marge_berekening()` zoekt het percentage op en telt
  `betalingskorting = project_price * korting_pct` nu mee in de
  `verkoopprijs`-formule, naast omzetbonus en garantie.
- **`.get()` in plaats van directe indexering** voor dit ene nieuwe veld
  (zowel in `rekenkern.py` als `calculatieblad.py`'s
  `_bonus_korting_en_provisie_pct()`): een al bewaard project/autosave van
  vóór deze toevoeging mist `instellingen.kortingklant` nog helemaal, en
  JSON laat een ontbrekende sleutel gewoon weg (geen `null`) -- zonder
  `.get()`-terugval zou zo'n bestaand project een `KeyError` geven zodra
  `/bereken` erop wordt losgelaten. `bonusklant`/`provisieklant` zelf blijven
  bewust ongemoeid (directe indexering): die velden bestonden al vanaf het
  begin van deze samenvoeging, dus er bestaat geen opgeslagen project zonder.
- `calculatie/calculatieblad.py`: nieuwe cellen `Calculatie!D442` (debiteur-
  naam) / `F442` (percentage, net als F439/F445 voor bonus/provisie
  rechtstreeks geschreven, niet via de VLOOKUP-formule) en
  `Quotation sheet!P74`/`R74`; `_vul_quotation`'s garantie/verkoopprijs-
  schrijfregels verschoven mee naar R75/R77 (zie hierboven). `_lees_instellingen`
  leest `D442` terug net als de andere twee kortingslijsten, met dezelfde
  "onbekende klant → standaardwaarde + waarschuwing"-aanpak.
- **Scherm**: nieuwe dropdown "Betalingskorting" (`#i_kortingklant`,
  `scherm/index.html`/`calculatie.js`) naast Bonusdragende klant/Provisie, en
  een nieuwe margetabel-regel `mg_betalingskorting` tussen Omzetbonus en
  Garantie.

## DGC-bonus 4% → 5%, en Lost/Financial costs 4%/0,7% → 5%/0,75%

Het nieuwe sjabloon laat drie percentages anders zien dan voorheen:
`Omzetbonus+Provisie`-blad B9 (DGC groep) 0.04 → 0.05
(`data/omzetbonus_provisie.json` bijgewerkt), en `Quotation sheet!P63`
(LOST QUOTATION COSTS) 0.04 → 0.05 resp. `P64` (FINANCIAL COSTS)
0.007 → 0.0075. Die laatste twee staan niet in een databestand maar
hardcoded in `rekenkern.marge_berekening()` (`lost = ic * 0.05`,
`financial = ic * 0.0075`, was `0.04`/`0.007`) -- rechtgezet, met de
bijbehorende labels in `scherm/index.html` ("Lost quotation costs (5%)",
"Financial costs (0,75%)") en de verwachte waarde in
`tests/test_rekenkern.py`'s scenario-3-test herrekend (`fullCost` 2697,934
→ 2723,995, `resultaat` 302,066 → 276,005).

## YIMM- en materiaalcatalogus-data bijgewerkt

`data/yimm.json`: 474 → 498 artikelen (1 verwijderd -- hetzelfde
Stuurstroomkabel-artikel als hierboven, 25 toegevoegd -- nieuwe
soldeerverloopsokken/-T-stukken en ACT-Cat6-patchkabels). Opnieuw
gegenereerd met een kale stdlib-extractor (zelfde beperking als bij de
Panasonic-prijscatalogus eerder: geen PDF/Excel-bibliotheek beschikbaar in
deze sandbox) die eerst tegen het VORIGE sjabloon is gevalideerd (moest
byte-exact `data/yimm.json` reproduceren -- ving een afrondingsbug op:
`voorraad` werd geforceerd naar `int()`, wat 3 artikelen met een fractionele
voorraad (koudemiddel in KG) afrondde; losgelaten ten gunste van dezelfde
`int(f) if f == int(f) else f`-opmaak die `prijs` al gebruikte) vóór de
aanname dat hij ook op het NIEUWE sjabloon te vertrouwen is.

`data/materiaal_catalogus.json` (de materiaalregels die rechtstreeks op het
blad "Calculatie" staan, met een `row`-veld -- zie "Rijnummers komen uit..."
verderop in dit bestand): 20 prijswijzigingen en 25 naamwijzigingen
(gevonden door te matchen op `artikelcode`, niet op positie, net als bij de
Panasonic-catalogus-update) zijn overgenomen, samen met de rij-verschuiving
hierboven. Twee opvallende, bewust ONGECORRIGEERDE eigenaardigheden: een
paar omschrijvingen in het nieuwe sjabloon zijn zelf halverwege afgekapt
("...voorraa", "...zwar", "4P/63A 380" zonder "V") -- bevestigd dat dit ook
letterlijk zo in de YIMM-brondata van het sjabloon staat (niet een eigen
extractiefout), dus overgenomen zoals het er staat, geen gok naar wat de
volledige tekst "hoort" te zijn.

**Getest:** alle bestaande tests bijgewerkt naar de nieuwe rijnummering (zie
hierboven), 8 nieuwe tests (`TestBetalingskorting`, `TestKortingklantRondje`
in `tests/test_calculatieblad.py`): schrijven/lezen van de nieuwe cellen,
het effect op de verkoopprijs-formule, en dat een staat zonder
`kortingklant`-sleutel (oud project) niet crasht. 303 tests groen (was 298).
Live getest met Playwright: de Betalingskorting-dropdown ("Geen
betalingskorting"/"Hoppenbrouwers"), de nieuwe margetabel-regel, en de
bijgewerkte Lost/Financial-labels. Een volledige calculatieblad-export →
import-rondje via de draaiende server (met het ECHTE, vervangen
sjabloonbestand, niet een test-fixture) bevestigde dat `kortingklant` en
`projectPrice` correct terugkomen. Zoals bij de vorige calculatieblad-
functies kon het resultaat hier niet in een echte Excel of werkende
LibreOffice Calc geopend worden (zelfde sandboxbeperking als eerder
gedocumenteerd) -- wel gecontroleerd dat elke cel-toewijzing cijfer voor
cijfer overeenkomt met `rekenkern.bereken()` (de bestaande
`tests/test_calculatieblad.py`-methodiek). **Net als bij de vorige
sjabloonwijzigingen: laat het eerste nieuwe calculatieblad dat met dit
sjabloon wordt gedownload door Lars (die wél Excel heeft) controleren
voordat er op wordt vertrouwd voor belangrijk werk** -- met name omdat de
rij-verschuiving dit keer het hele blad raakt, niet alleen nieuwe cellen.
