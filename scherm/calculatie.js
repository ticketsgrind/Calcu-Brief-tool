'use strict';
/* ============================================================================
   Calculatiestap — geport uit de losstaande calculatietool (tools/app.js).
   De rekenkern zelf (marge, uren, afgeleide materiaalregels) is overgezet
   naar Python (calculatie/rekenkern.py) en woont nu alleen daar: het scherm
   stuurt bij elke wijziging de staat naar POST /bereken en tekent het
   antwoord. Zo kunnen deze stap en de brief-stap nooit een ander bedrag laten
   zien. Zoeken/bladeren in de materiaalcatalogus (triviale opzoeklogica,
   geen rekenregel) blijft hier, net als voorheen.
   ============================================================================ */
(function () {

const ROL_LABELS = {
  projectmanager: 'Projectmanager', projectleider: 'Projectleider',
  werkvoorbereider: 'Werkvoorbereider', engineering: 'Engineering',
  servicemonteur: 'Servicemonteur', hoofdmonteur: 'Hoofdmonteur',
  hulpmonteur: 'Hulpmonteur', verkoper: 'Verkoper',
};
const DEFAULT_TARIEVEN = {
  // Zelfde waarden als calculatie/rekenkern.py se DEFAULT_TARIEVEN -- zie
  // daar (en CLAUDE.md) voor waar deze vandaan komen en waarom "verkoper"
  // zijn oude waarde (158) behield.
  projectmanager: 168, projectleider: 123, werkvoorbereider: 98, engineering: 112,
  servicemonteur: 85, hoofdmonteur: 72, hulpmonteur: 59, verkoper: 158,
};
const UITBESTEDING_DEFAULTS = [
  { omschrijving: 'Kleine kraan', eenheid: 'ST', prijs: 500, favoriet: true },
  { omschrijving: 'Grote kraan', eenheid: 'ST', prijs: null, favoriet: true },
  { omschrijving: 'Betonboring', eenheid: 'ST', prijs: 200, favoriet: true },
  { omschrijving: 'IBS / Support Leverancier', eenheid: 'ST', prijs: null, favoriet: false },
  { omschrijving: 'Luchtverdeelslang KE Fibertec, incl. inmeten en montage', eenheid: 'M', prijs: 140, favoriet: false },
  { omschrijving: 'Dakdekker', eenheid: 'POST', prijs: null, favoriet: false },
  { omschrijving: 'Brandwerende afwerking', eenheid: 'POST', prijs: null, favoriet: false },
  { omschrijving: 'Hulpconstructie', eenheid: 'POST', prijs: null, favoriet: false },
  { omschrijving: 'Elektrotechnisch', eenheid: 'POST', prijs: null, favoriet: false },
  { omschrijving: 'Loodgieter/CV', eenheid: 'POST', prijs: null, favoriet: false },
  { omschrijving: 'Spuiten grille', eenheid: 'POST', prijs: 250, favoriet: false },
  { omschrijving: 'Sloopwerkzaamheden', eenheid: 'POST', prijs: null, favoriet: false },
  { omschrijving: 'PED keuring (per VRF systeem)', eenheid: 'ST', prijs: 75, favoriet: false },
];
const EQUIPMENT_DEFAULTS = [
  { omschrijving: 'Hoogwerker', eenheid: 'WEEK', prijs: 700, favoriet: true },
  { omschrijving: 'Heftruck', eenheid: 'POST', prijs: null, favoriet: true },
  { omschrijving: 'Steiger', eenheid: 'POST', prijs: null, favoriet: true },
  { omschrijving: 'Huur cilinder koudemiddel (per dag)', eenheid: 'DAG', prijs: 0.27, favoriet: false },
];
const MATERIAAL_SECTIES = ['APPARATUUR','BALKEN/VOETEN/MUURSTEUN','LEIDINGEN/KABELS/SIFON','POMPEN','INOAC','SOLDEER','WERKSCHAKELAAR','KOUDE MIDDEL','DAKDOORVOERING','TOEBEHOREN LUCHTVERDELING'];
const MERK_OPTIES = ['Panasonic', 'Mitsubishi Electric', 'Toshiba', 'Daikin', 'LG'];
const MONTAGEWIJZE_OPTIES = ['Wandmontage', 'Plafondinbouwmontage', 'Vloermontage'];
// Rijnummers volgen data/materiaal_catalogus.json's row-veld -- zie
// CLAUDE.md (sjabloonupdate oktober 2026) voor de -1-verschuiving t.o.v.
// het vorige sjabloon. Rij 117 (Stuurstroomkabel LSOH) is daarbij uit de
// LEIDINGEN/KABELS/SIFON-lijst gehaald: dat artikel bestaat niet meer in de
// catalogus, en de rij waar "117" nu wél naar wijst is een ander,
// ongerelateerd artikel -- een geschoven rijnummer zonder meer zou hier dus
// stilzwijgend het verkeerde chip-label zijn gaan tonen.
const FAVORIETEN_ROWS = {
  'BALKEN/VOETEN/MUURSTEUN': [84, 82],
  'LEIDINGEN/KABELS/SIFON': [102, 103, 104, 105, 108, 111, 110, 123],
  'POMPEN': [139, 140, 142],
  'INOAC': [155, 156, 157, 160, 161, 163, 164, 186],
};

const { eur, pct } = CB;
let uid = 1;
const newId = () => 'calcid' + (uid++);
// Voorkomt dat newId() na het laden van een bewaard project (autosave of een
// geopend bestand) weer bij 1 begint terwijl de geladen rijen al ids als
// "calcid7" dragen -- zonder deze stap zou de eerstvolgende nieuw toegevoegde
// rij zo'n bestaand id hergebruiken (newId() geeft dan weer "calcid1"), met
// als gevolg dat twee rijen in verschillende lijsten (bijv. een
// uitbestedingsregel en een materiaalregel) hetzelfde data-id dragen.
// restoreFocus() matcht na elke toets alleen op data-id+data-field en pakt
// dan de EERSTE regel met dat id in DOM-volgorde -- dat gaf het "typen in
// Uitbesteding springt naar het aantal-veld bij APPARATUUR"-effect, want
// Materiaal rendert vóór Uitbesteding in renderAll(). uid is een module-brede
// teller (niet per optie), dus dit kijkt over alle opties heen.
function hersynchroniseerIdTeller(nieuweOpties) {
  let hoogste = 0;
  for (const optie of nieuweOpties) {
    const s = optie.staat;
    if (!s) continue;
    for (const lijst of [s.installaties, s.materiaal, s.uitbesteding, s.equipment]) {
      for (const regel of lijst || []) {
        const match = /^calcid(\d+)$/.exec(regel.id || '');
        if (match) hoogste = Math.max(hoogste, Number(match[1]));
      }
    }
  }
  if (hoogste >= uid) uid = hoogste + 1;
}

let DATA = null;      // catalogi, geladen bij init() uit /data/*.json
let state = null;     // de calculatie-invoer van de ACTIEVE optie
let berekening = null; // laatste antwoord van POST /bereken (null tot de eerste ronde klaar is)

// Eén project kan meerdere losse calculaties ("opties") bevatten, bijv. een
// Panasonic- en een Toshiba-uitvoering van dezelfde aanvraag -- die komen bij
// "naar de brief" samen terecht als pos. A/pos. B in één brief (overdracht.py
// zet_meerdere_over(), zie CLAUDE.md). `state` blijft de invoer van precies
// de actieve optie; `opties[i].staat` is alleen actueel voor de NIET-actieve
// opties (bewaarActieveOptie() synchroniseert `state` erin terug vóór elk
// gebruik van de volledige lijst).
let opties = [{ naam: 'Optie A', staat: null }];
let actieveOptieIndex = 0;

function nieuweStaat() {
  return {
    meta: { qnummer: '', projectnaam: '', klantnaam: '', klantnummer: '', uitgangspunten: '', datum: new Date().toISOString().slice(0, 10) },
    instellingen: { moeilijkheid: 'Standaard', reistijd: 1, provincie: 'Geen parkeerkosten', bonusklant: 'Geen bonusdragende klant', kortingklant: 'Geen betalingskorting', provisieklant: 'Geen provisie' },
    installaties: [],
    materiaal: [],
    uren: {
      projectmanager: { werk: 0, reis: 0, tarief: DEFAULT_TARIEVEN.projectmanager },
      projectleider: { werk: 0, reis: 0, tarief: DEFAULT_TARIEVEN.projectleider },
      werkvoorbereider: { werk: 0, reis: 0, tarief: DEFAULT_TARIEVEN.werkvoorbereider },
      engineering: { werk: 0, reis: 0, tarief: DEFAULT_TARIEVEN.engineering },
      servicemonteur: { overig: 0, tarief: DEFAULT_TARIEVEN.servicemonteur, override: null },
      hoofdmonteur: { tarief: DEFAULT_TARIEVEN.hoofdmonteur, override: null },
      hulpmonteur: { tarief: DEFAULT_TARIEVEN.hulpmonteur, override: null },
      verkoper: { uren: 0, tarief: DEFAULT_TARIEVEN.verkoper },
    },
    uitbesteding: UITBESTEDING_DEFAULTS.map(d => ({ id: newId(), aantal: 0, ...d })),
    equipment: EQUIPMENT_DEFAULTS.map(d => ({ id: newId(), aantal: 0, ...d })),
    // shortTrip*/transfer*: zie CLAUDE.md §Q-kosten -- het aantal (dagen/
    // uren) start op 0 zoals nachten hierboven, het tarief krijgt wel een
    // zinnige standaardwaarde (158 = hetzelfde tarief als projectmanager),
    // zodat 0 × tarief nog altijd op 0 euro uitkomt.
    overig: { nachten: 0, nachtprijs: 150, shortTripDagen: 0, shortTripTarief: 0,
              transferUren: 0, transferTarief: DEFAULT_TARIEVEN.projectmanager },
    marge: { contingencyReserves: 0, contingencyOnderhandeling: 0, projectPrice: null },
  };
}

/* ------------------------------------- opties ------------------------------------- */
// `state` is steeds de invoer van de actieve optie; dit zet 'm terug in
// `opties` vóór elk gebruik van de volledige lijst (wisselen, opslaan,
// verwijderen, tellen) -- zonder dit zou de niet-actieve helft van `opties`
// een verouderde snapshot blijven.
function bewaarActieveOptie() {
  if (opties[actieveOptieIndex]) opties[actieveOptieIndex].staat = state;
}

function wisselOptie(index) {
  if (index === actieveOptieIndex || !opties[index]) return;
  bewaarActieveOptie();
  actieveOptieIndex = index;
  state = opties[actieveOptieIndex].staat;
  berekening = null; laatstVerzonden = null;
  renderOptieBalk();
  renderAll();
}

function optieToevoegen() {
  bewaarActieveOptie();
  const nieuw = nieuweStaat();
  // Projectgegevens (klant, adres, Q-nummer, ...) horen bij het project als
  // geheel, niet bij één optie -- overnemen scheelt dubbel intypen. De rest
  // (installaties, materiaal, uren, ...) start leeg: dit is een volledig
  // losse, zelfstandige calculatie, geen variant die iets deelt. Op verzoek
  // van Lars (29 september 2026).
  nieuw.meta = Object.assign({}, state.meta);
  opties.push({ naam: 'Optie ' + String.fromCharCode(65 + opties.length), staat: nieuw });
  wisselOptie(opties.length - 1);
}

function optieVerwijderen(index) {
  if (opties.length <= 1 || !opties[index]) return; // altijd minstens één optie
  if (staatHeeftInhoud(index === actieveOptieIndex ? state : opties[index].staat)
      && !confirm(`${opties[index].naam} verwijderen? Niet-opgeslagen wijzigingen daarin gaan dan verloren.`)) return;
  opties.splice(index, 1);
  if (actieveOptieIndex >= opties.length) actieveOptieIndex = opties.length - 1;
  else if (index < actieveOptieIndex) actieveOptieIndex--;
  state = opties[actieveOptieIndex].staat;
  berekening = null; laatstVerzonden = null;
  renderOptieBalk();
  renderAll();
}

function optieHernoemen(index, naam) {
  const schoon = String(naam || '').trim();
  if (schoon && opties[index]) opties[index].naam = schoon;
  renderOptieBalk();
  CB.autosave();
}

function renderOptieBalk() {
  const balk = document.getElementById('optieBalk');
  if (!balk) return;
  const tabs = opties.map((optie, i) => `
    <div class="optie-tab${i === actieveOptieIndex ? ' actief' : ''}" data-index="${i}" title="Dubbelklik om te hernoemen">
      <span class="optie-naam">${optie.naam}</span>
      ${opties.length > 1 ? `<button class="optie-verwijder" type="button" data-action="verwijder-optie" data-index="${i}" title="Deze optie verwijderen">✕</button>` : ''}
    </div>`).join('');
  balk.innerHTML = tabs + `<button class="btn ghost small" type="button" id="btnOptieToevoegen"
    title="Een tweede, volledig losse calculatie toevoegen -- bijv. voor een alternatief aanbod met een ander fabricaat. Komt bij &quot;naar de brief&quot; samen met de andere opties terecht als pos. A/pos. B.">+ Optie toevoegen</button>`;
}

function bindOpties() {
  const balk = document.getElementById('optieBalk');
  balk.addEventListener('click', e => {
    const verwijderKnop = e.target.closest('[data-action="verwijder-optie"]');
    if (verwijderKnop) { optieVerwijderen(Number(verwijderKnop.dataset.index)); return; }
    if (e.target.closest('#btnOptieToevoegen')) { optieToevoegen(); return; }
    const tab = e.target.closest('.optie-tab');
    if (tab) wisselOptie(Number(tab.dataset.index));
  });
  balk.addEventListener('dblclick', e => {
    const tab = e.target.closest('.optie-tab');
    if (!tab) return;
    const index = Number(tab.dataset.index);
    const nieuweNaam = prompt('Naam voor deze optie:', opties[index].naam);
    if (nieuweNaam !== null) optieHernoemen(index, nieuweNaam);
  });
}

function staatHeeftInhoud(s) {
  // meta.datum staat in nieuweStaat() altijd al op vandaag (zie daar) -- dat
  // is een handig vooraf ingevulde waarde, geen teken dat er iets is
  // ingevuld. Zonder deze uitzondering was ELKE kersverse, nooit aangeraakte
  // staat al "heeft inhoud", wat zowel "Nieuw"/"Openen" hun waarschuwing
  // onnodig liet geven vlak na het openen van de tool, als (sinds de
  // beforeunload-waarschuwing bij het sluiten van het tabblad) een nooit
  // gebruikte calculatie bij het dichtklikken alsnog zou laten vragen of je
  // wel hebt opgeslagen.
  return s.installaties.length > 0 || s.materiaal.length > 0
    || Object.entries(s.meta).some(([sleutel, waarde]) => sleutel !== 'datum' && Boolean(waarde))
    || s.marge.projectPrice !== null;
}
// Kijkt over alle opties heen, niet alleen de actieve -- anders zou "Nieuw"/
// "Openen" een ingevulde tweede optie zonder waarschuwing kunnen wegvegen
// alleen omdat toevallig de eerste, lege optie in beeld stond.
function heeftInhoud() {
  bewaarActieveOptie();
  return opties.some(o => staatHeeftInhoud(o.staat));
}

function nonNegatief(waarde) {
  if (waarde === '' || waarde === null || waarde === undefined) return waarde;
  const n = Number(waarde);
  return (!isNaN(n) && n < 0) ? 0 : waarde;
}

// Voor het TONEN van een aantal-veld: een leeggemaakt veld (nonNegatief()
// hierboven bewaart dat bewust als '', niet als 0) moet ook leeg BLIJVEN
// staan tot de gebruiker zelf een cijfer intikt. "x || 0" -- wat hier eerder
// stond -- zet zo'n geleegd veld bij de eerstvolgende render (die na ELKE
// toetsaanslag gebeurt, zie renderAll()) alweer op "0", vóórdat er ooit een
// nieuw cijfer in getypt kon worden: de 0 "bleef staan" zodra je 'm probeerde
// weg te halen. Alleen een nog nooit ingevulde waarde (null/undefined, bijv.
// een net aangemaakte regel) krijgt hier alsnog een 0 als startpunt.
function weergaveAantal(x) {
  return x === '' ? '' : (x ?? 0);
}

/* ---------------------------- lege berekening (voor het eerste scherm, nog voor /bereken is teruggekomen) --- */
function legeBerekening() {
  const nulLijst = { totaal: 0, onvolledig: 0 };
  const nulUren = { voorstel: 0, definitief: 0 };
  return {
    materiaal: state.materiaal,
    uren: Object.fromEntries(Object.keys(ROL_LABELS).map(r => [r, nulUren])),
    verdeelboxenAantal: 0, monteurWerkurenAuto: 0,
    servicemonteurVoorstel: { werk: 0, auto: 0, vrfIbs: 0, reis: 0, totaal: 0 },
    marge: {
      materiaal: nulLijst, uitbesteding: nulLijst, equipment: nulLijst, arbeid: 0,
      parkeeruren: 0, parkeerkosten: 0, overnachtingen: 0, reiskosten: 0,
      overheadInkoop: 0, overheadUitbesteding: 0, contingencyReserves: 0, contingencyOnderhandeling: 0,
      overigeKosten: 0, ic: 0, lost: 0, financial: 0, groupFees: 0, fullCost: 0,
      projectPrice: null, resultaat: null, omzetbonus: null, garantie: null, verkoopprijs: null, resultaatPct: null,
    },
  };
}

/* ---------------------------------- server-aanroep -------------------------------- */
let laatstVerzonden = null;
async function herbereken() {
  const lichaam = JSON.stringify(state);
  if (lichaam === laatstVerzonden) return; // niets gewijzigd sinds de laatste ronde
  laatstVerzonden = lichaam;
  const resultaat = await CB.postJSON('/bereken', state);
  if (resultaat.fout) { CB.toast(resultaat.fout); return; }
  state.materiaal = resultaat.materiaal; // neemt afgeleide regels (trillingsdempers e.d.) over
  berekening = resultaat;
  renderAll(true);
}
const plannenHerberekening = CB.debounce(herbereken, 250);

/* -------------------------------- triviale weergave-helpers ------------------------ */
// Puur arithmetisch (aantal x prijs, optellen) — geen rekenregel/formule, dus
// hier dupliceren voor directe feedback per toetsaanslag is geen risico op
// een ander bedrag dan de server; de AUTORITATIEVE totalen (marge, uren,
// verkoopprijs) komen uitsluitend uit `berekening`, hierboven.
function regelTotaal(r) {
  const prijs = (r.prijs === null || r.prijs === undefined || r.prijs === '') ? null : Number(r.prijs);
  const aantal = Number(r.aantal) || 0;
  if (prijs === null) return null;
  return aantal * prijs;
}
function lijstTotaal(lijst) {
  let totaal = 0, onvolledig = 0;
  for (const r of lijst) {
    const t = regelTotaal(r);
    if (t === null) { if ((Number(r.aantal) || 0) > 0) onvolledig++; }
    else totaal += t;
  }
  return { totaal, onvolledig };
}
function materiaalPerSectie() {
  const secties = {};
  for (const r of state.materiaal) {
    secties[r.sectie] = secties[r.sectie] || [];
    secties[r.sectie].push(r);
  }
  return secties;
}

/* -------------------------------- materiaal zoeken/toevoegen ----------------------- */
function catalogusItem(artikelcode) {
  if (!artikelcode) return null;
  return DATA.yimm.find(a => a.code === artikelcode) || null;
}
const CATALOGUS_BY_ROW = {};

function zoekMateriaal(q) {
  q = q.trim().toLowerCase();
  if (q.length < 2) return [];
  return DATA.materiaal_catalogus.filter(c =>
    !c.afgeleid_van && (
      (c.omschrijving && c.omschrijving.toLowerCase().includes(q)) ||
      (c.artikelcode && c.artikelcode.toLowerCase().includes(q))
    )
  ).slice(0, 25);
}
function materiaalRegelUitCatalogus(catalogusEntry) {
  const live = catalogusEntry.artikelcode ? catalogusItem(catalogusEntry.artikelcode) : null;
  // Bron "projectbestelling" heeft in het bronbestand een prijs van 0 staan
  // als plekhouder ("moet nog ingevuld worden"), geen echte nulprijs -- die
  // zou anders als "bekend" meetellen in de totalen zonder dat er ooit een
  // bedrag is ingevuld. Zie ook renderMateriaal(), die dit veld bewerkbaar
  // maakt voor precies deze bron.
  const prijs = live ? live.prijs : (catalogusEntry.bron === 'projectbestelling' ? null : catalogusEntry.prijs);
  return {
    id: newId(), sectie: catalogusEntry.sectie, row: catalogusEntry.row, bron: catalogusEntry.bron,
    artikelcode: catalogusEntry.artikelcode,
    omschrijving: live ? live.omschrijving : catalogusEntry.omschrijving,
    eenheid: live ? live.eenheid : catalogusEntry.eenheid,
    prijs,
    per_meter_type: catalogusEntry.per_meter_type || null,
    leiding_categorie: catalogusEntry.leiding_categorie || null,
    montage_uur_per_eenheid: catalogusEntry.montage_uur_per_eenheid || null,
    servicemonteur_trigger: catalogusEntry.servicemonteur_trigger || null,
    instellingen_koppeling: catalogusEntry.instellingen_koppeling || null,
    afgeleid: !!catalogusEntry.afgeleid_van, aantal: 1,
  };
}
function voegMateriaalToe(catalogusEntry) {
  const bestaand = state.materiaal.find(r => r.row === catalogusEntry.row);
  if (bestaand) { bestaand.aantal = (Number(bestaand.aantal) || 0) + 1; renderAll(); return; }
  state.materiaal.push(materiaalRegelUitCatalogus(catalogusEntry));
  renderAll();
}
function zoekPanasonic(q) {
  q = q.trim().toLowerCase();
  if (q.length < 2) return [];
  return DATA.panasonic.filter(a => a.zoekcodes.some(code => code.toLowerCase().includes(q))).slice(0, 25);
}
function panasonicOmschrijving(a) {
  const codes = [a.set_code, a.binnenunit_code, a.buitenunit_code, a.artikelcode].filter(Boolean);
  return `${a.lijn}${a.kleur ? ' (' + a.kleur + ')' : ''} — ${codes.join(' / ')}`;
}
function materiaalRegelUitPanasonic(a) {
  return {
    id: newId(), sectie: 'APPARATUUR', bron: 'panasonic', panasonic_id: a.panasonic_id,
    artikelcode: a.set_code || a.buitenunit_code || a.binnenunit_code || a.artikelcode,
    omschrijving: panasonicOmschrijving(a), eenheid: 'ST', prijs: a.netto_prijs, aantal: 1,
    opmerking: a.bruto_prijs === null
      ? `Panasonic ${a.catalogus} — prijs "op aanvraag" in de catalogus, pagina ${a.pagina}${a.opmerking ? '. ' + a.opmerking : ''}`
      : `Panasonic ${a.catalogus} — bruto ${eur(a.bruto_prijs)} − 43% korting, pagina ${a.pagina}${a.opmerking ? '. ' + a.opmerking : ''}`,
  };
}
function voegPanasonicToe(a) {
  const bestaand = state.materiaal.find(r => r.panasonic_id === a.panasonic_id);
  if (bestaand) { bestaand.aantal = (Number(bestaand.aantal) || 0) + 1; renderAll(); return; }
  state.materiaal.push(materiaalRegelUitPanasonic(a));
  renderAll();
}
function zoekDaikin(q) {
  q = q.trim().toLowerCase();
  if (q.length < 2) return [];
  return DATA.daikin.filter(a => a.zoekcodes.some(code => code.toLowerCase().includes(q))).slice(0, 25);
}
function materiaalRegelUitDaikin(a) {
  const typefoutNoot = a.mogelijke_typefout_in_bron ? ` LET OP: ${a.opmerking}` : '';
  return {
    id: newId(), sectie: 'APPARATUUR', bron: 'daikin', daikin_id: a.daikin_id,
    artikelcode: a.code_of_combinatie || a.artikelcode, omschrijving: a.omschrijving,
    eenheid: 'ST', prijs: a.netto_prijs, aantal: 1,
    opmerking: `Daikin — bruto ${eur(a.bruto_prijs)} − 65% korting, pagina ${a.pagina}.${typefoutNoot}`,
  };
}
function voegDaikinToe(a) {
  const bestaand = state.materiaal.find(r => r.daikin_id === a.daikin_id);
  if (bestaand) { bestaand.aantal = (Number(bestaand.aantal) || 0) + 1; renderAll(); return; }
  state.materiaal.push(materiaalRegelUitDaikin(a));
  renderAll();
}
function materiaalKoppelLabel(r) {
  const code = r.artikelcode ? ` — ${r.artikelcode}` : '';
  return `${r.omschrijving || '(geen omschrijving)'}${code}`;
}
function materiaalOptiesVoorInstallatie(huidigeMateriaalId) {
  // Alleen APPARATUUR-regels: dat is waar een compleet systeem (eigen
  // catalogus, Panasonic of Daikin) terechtkomt zodra het via de zoekbalk of
  // de Panasonic/Daikin-catalogus is toegevoegd (zie voegMateriaalToe/
  // voegPanasonicToe/voegDaikinToe hierboven) -- dit is dus de plek waar het
  // echte modelnummer (bijv. "TZ50") vandaan komt, niet de grove "Type
  // binnendeel"-categorie hieronder.
  const kandidaten = state.materiaal.filter(r => r.sectie === 'APPARATUUR' && !r.afgeleid);
  const opties = kandidaten.map(r =>
    `<option value="${r.id}" ${r.id === huidigeMateriaalId ? 'selected' : ''}>${materiaalKoppelLabel(r).replace(/"/g, '&quot;')}</option>`
  ).join('');
  return `<option value="" ${!huidigeMateriaalId ? 'selected' : ''}>— geen koppeling —</option>${opties}`;
}
function materiaalRegelLabel(r) {
  if (r.bron === 'panasonic') {
    const a = DATA.panasonic.find(x => x.panasonic_id === r.panasonic_id);
    return `Panasonic ${a ? a.catalogus : ''}`.trim();
  }
  if (r.bron === 'daikin') return 'Daikin';
  const bronLabel = { voorraad: 'voorraad', projectbestelling: 'projectbestelling', 'leverancier:ST': 'leverancier ST', 'per-meter-berekening': 'per meter' }[r.bron] || r.bron;
  return bronLabel;
}

/* ==================================== RENDERING ==================================== */
function fillSelect(el, options, current) {
  el.innerHTML = options.map(o => `<option value="${o}" ${o === current ? 'selected' : ''}>${o}</option>`).join('');
}
function renderInstellingenOpties() {
  fillSelect(document.getElementById('i_provincie'), DATA.parkeertarieven.map(p => p.provincie), state.instellingen.provincie);
  fillSelect(document.getElementById('i_bonusklant'), DATA.omzetbonus.omzetbonus.map(b => b.klant), state.instellingen.bonusklant);
  fillSelect(document.getElementById('i_kortingklant'), DATA.omzetbonus.korting.map(k => k.klant), state.instellingen.kortingklant);
  fillSelect(document.getElementById('i_provisieklant'), DATA.omzetbonus.provisie.map(p => p.klant), state.instellingen.provisieklant);
}
function renderMeta() {
  document.getElementById('m_qnummer').value = state.meta.qnummer;
  document.getElementById('m_projectnaam').value = state.meta.projectnaam;
  document.getElementById('m_klantnaam').value = state.meta.klantnaam;
  document.getElementById('m_klantnummer').value = state.meta.klantnummer;
  document.getElementById('m_uitgangspunten').value = state.meta.uitgangspunten;
  document.getElementById('i_moeilijkheid').value = state.instellingen.moeilijkheid;
  document.getElementById('i_reistijd').value = state.instellingen.reistijd;
  document.getElementById('i_verdeelboxen_out').textContent = berekening.verdeelboxenAantal;
  document.getElementById('ov_nachten').value = state.overig.nachten;
  document.getElementById('ov_nachtprijs').value = state.overig.nachtprijs;
  // ?? 0/158: een project opgeslagen vóór deze velden bestonden heeft ze niet
  // in zijn overig-object staan -- zonder deze terugval zou het veld hier de
  // letterlijke tekst "undefined" tonen in plaats van gewoon leeg/0.
  document.getElementById('ov_shorttrip_dagen').value = state.overig.shortTripDagen ?? 0;
  document.getElementById('ov_shorttrip_tarief').value = state.overig.shortTripTarief ?? 0;
  document.getElementById('ov_transfer_uren').value = state.overig.transferUren ?? 0;
  document.getElementById('ov_transfer_tarief').value = state.overig.transferTarief ?? DEFAULT_TARIEVEN.projectmanager;
  document.getElementById('mg_contingency_reserves').value = state.marge.contingencyReserves;
  document.getElementById('mg_contingency_onderhandeling').value = state.marge.contingencyOnderhandeling;
  document.getElementById('mg_projectprice').value = state.marge.projectPrice === null ? '' : state.marge.projectPrice;
  document.getElementById('sm_overig').value = state.uren.servicemonteur.overig;
}
function renderInstallaties() {
  const wrap = document.getElementById('installatiesList');
  wrap.innerHTML = '';
  state.installaties.forEach(inst => {
    const div = document.createElement('div');
    div.className = 'installatie-card';
    div.innerHTML = `
      <div class="installatie-acties no-print">
        <button class="icon-btn" data-id="${inst.id}" data-action="dupliceer-installatie" title="Dupliceren">⧉</button>
        <button class="icon-btn verwijder" data-id="${inst.id}" data-action="verwijder-installatie" title="Verwijderen">✕</button>
      </div>
      <div class="grid cols-4">
        <div class="field"><label>Systeemsoort</label>
          <select data-id="${inst.id}" data-field="systeemsoort">
            ${['VRF','RAC','PAC','Overig'].map(s=>`<option ${s===inst.systeemsoort?'selected':''}>${s}</option>`).join('')}
          </select>
        </div>
        <div class="field"><label>Merk</label>
          <select data-id="${inst.id}" data-field="merk">
            <option value="" ${!inst.merk ? 'selected' : ''}>— kies —</option>
            ${MERK_OPTIES.map(m=>`<option ${m===inst.merk?'selected':''}>${m}</option>`).join('')}
          </select>
        </div>
        <div class="field"><label>Montagewijze</label>
          <select data-id="${inst.id}" data-field="montagewijze">
            <option value="" ${!inst.montagewijze ? 'selected' : ''}>— kies —</option>
            ${MONTAGEWIJZE_OPTIES.map(m=>`<option ${m===inst.montagewijze?'selected':''}>${m}</option>`).join('')}
          </select>
        </div>
        <div class="field"><label>Type binnendeel</label>
          <select data-id="${inst.id}" data-field="typeBinnendeel">
            ${DATA.systemen.soort_binnendeel.map(s=>`<option ${s===inst.typeBinnendeel?'selected':''}>${s}</option>`).join('')}
          </select>
        </div>
        <div class="field"><label>Model (koppeling voor de brief) <span class="info-icon" title="Dit is het modelnummer dat in de offertebrief komt te staan (bijv. KIT-TZ20-CKE). Koppel hier het artikel uit Materiaal → Apparatuur dat bij deze installatie hoort — zonder koppeling blijft het modelnummer in de brief leeg in plaats van een gok.">ⓘ</span></label>
          <select data-id="${inst.id}" data-field="materiaalId">
            ${materiaalOptiesVoorInstallatie(inst.materiaalId)}
          </select>
        </div>
        <div class="field"><label>Aantal buitendelen</label><input type="text" inputmode="numeric" class="num-input" data-id="${inst.id}" data-field="aantalBuitendelen" value="${weergaveAantal(inst.aantalBuitendelen)}"></div>
        <div class="field"><label>Aantal binnendelen</label><input type="text" inputmode="numeric" class="num-input" data-id="${inst.id}" data-field="aantalBinnendelen" value="${weergaveAantal(inst.aantalBinnendelen)}"></div>
      </div>`;
    wrap.appendChild(div);
  });
  document.getElementById('installatiesHint').style.display = state.installaties.length ? 'block' : 'none';
  renderInstallatiesApparatuurHint();
}
function renderInstallatiesApparatuurHint() {
  const hintEl = document.getElementById('installatiesApparatuurHint');
  if (!hintEl) return;
  if (state.installaties.length === 0) { hintEl.style.display = 'none'; return; }
  let buiten = 0, binnen = 0;
  for (const i of state.installaties) { buiten += Number(i.aantalBuitendelen) || 0; binnen += Number(i.aantalBinnendelen) || 0; }
  const apparatuurAantal = state.materiaal.filter(r => r.sectie === 'APPARATUUR').reduce((s, r) => s + (Number(r.aantal) || 0), 0);
  hintEl.style.display = 'inline-flex';
  hintEl.title = `Ter info: hierboven staat in totaal ${buiten} buitendeel/-delen + ${binnen} binnendeel/-delen ingevuld (stuurt de urenberekening) — bij Materiaal → Apparatuur staan momenteel ${apparatuurAantal} stuk(s) apparatuur toegevoegd (stuurt de materiaalkosten). Deze twee hoeven niet gelijk te zijn, maar controleer ze even naast elkaar voordat de calculatie de deur uitgaat.`;
}
function renderFavorieten() {
  const wrap = document.getElementById('materiaalFavorieten');
  wrap.innerHTML = '';
  const inLijstRows = new Set(state.materiaal.filter(r => (Number(r.aantal) || 0) > 0).map(r => r.row));
  for (const [sectie, rows] of Object.entries(FAVORIETEN_ROWS)) {
    const div = document.createElement('div');
    div.className = 'favorieten-sectie';
    const chips = rows.map(row => {
      const c = CATALOGUS_BY_ROW[row];
      if (!c) return '';
      const inLijst = inLijstRows.has(row);
      return `<button type="button" class="chip${inLijst ? ' in-lijst' : ''}" data-row="${row}" data-action="favoriet-toevoegen">
        ${inLijst ? '✓ ' : '+ '}${c.omschrijving} <span class="chip-prijs">${c.prijs === null ? 'onbekend' : eur(Number(c.prijs))}</span>
      </button>`;
    }).join('');
    div.innerHTML = `<div class="titel">${sectie} — snelkeuze</div><div class="favorieten-chips">${chips}</div>`;
    wrap.appendChild(div);
  }
}
function renderSectieBrowser() {
  const toggleBtn = document.getElementById('materiaalSectieBrowserToggle');
  const toonAlles = uiState.toonSectieBrowser;
  document.getElementById('materiaalSectieBrowserWrap').style.display = toonAlles ? '' : 'none';
  toggleBtn.textContent = toonAlles ? 'Bladeren per onderdeel verbergen' : 'Bladeren per onderdeel tonen — handig als je de naam niet uit je hoofd weet';
  if (!toonAlles) return; // niets te bouwen zolang het dichtgeklapt is
  const wrap = document.getElementById('materiaalSectieBrowser');
  wrap.innerHTML = '';
  for (const sectie of MATERIAAL_SECTIES) {
    // Regels zonder omschrijving zijn lege plekhouder-rijen uit het bronbestand
    // (bijv. 30 van de 39 APPARATUUR-regels) -- niets om te kiezen, dus weg
    // uit de lijst in plaats van als "(geen omschrijving)" te tonen.
    const items = DATA.materiaal_catalogus.filter(c => c.sectie === sectie && !c.afgeleid_van && c.omschrijving);
    if (items.length === 0) continue;
    const options = items.map(c =>
      `<option value="${c.row}">${c.omschrijving.replace(/"/g, '&quot;')} — ${c.prijs === null ? 'prijs onbekend' : eur(Number(c.prijs))}</option>`
    ).join('');
    const div = document.createElement('div');
    div.className = 'sectie-browser-row field';
    div.innerHTML = `
      <label>${sectie} <span class="muted" style="font-weight:400;">(${items.length})</span></label>
      <select data-sectie-browser="1">
        <option value="" selected>Kies een artikel uit deze lijst…</option>
        ${options}
      </select>`;
    wrap.appendChild(div);
  }
}
function renderMateriaal() {
  const wrap = document.getElementById('materiaalSecties');
  wrap.innerHTML = '';
  const secties = materiaalPerSectie();
  const sectieVolgorde = [...MATERIAAL_SECTIES, 'PROJECTBESTELLING'];
  const aanwezig = Object.keys(secties).sort((a,b)=> sectieVolgorde.indexOf(a)-sectieVolgorde.indexOf(b));
  if (aanwezig.length === 0) {
    wrap.innerHTML = '<p class="muted">Nog geen materiaal toegevoegd — zoek hierboven een artikel.</p>';
    return;
  }
  for (const sectie of aanwezig) {
    const rows = secties[sectie];
    const div = document.createElement('div');
    div.innerHTML = `<div class="section-sub">${sectie}</div>`;
    const table = document.createElement('table');
    table.innerHTML = `<thead><tr><th>Omschrijving</th><th>Bron</th><th class="right">Aantal</th><th>Eenheid</th><th class="right">Prijs</th><th class="right">Totaal</th><th></th></tr></thead><tbody></tbody>`;
    const tbody = table.querySelector('tbody');
    for (const r of rows) {
      const totaal = regelTotaal(r);
      const besteld = (Number(r.aantal) || 0) > 0;
      const onvolledig = totaal === null && besteld;
      const tr = document.createElement('tr');
      tr.className = 'material-row' + (onvolledig ? ' onbekend' : '');
      const aantalCel = r.afgeleid
        ? `${r.aantal || 0} <div class="afgeleid-hint">automatisch</div>`
        : `<input type="text" inputmode="numeric" class="num-input" data-id="${r.id}" data-field="aantal" value="${weergaveAantal(r.aantal)}">`;
      // Bron "projectbestelling" (o.a. alle APPARATUUR-regels: verdeelboxen,
      // headers, T-stukken, ...) heeft nooit een cataloguswaarde -- de prijs
      // is hier altijd iets dat de invuller er zelf bij moet zetten.
      const prijsCel = (r.bron === 'projectbestelling' && !r.afgeleid)
        ? `<input type="number" min="0" step="0.01" class="price-input" data-id="${r.id}" data-field="prijs" placeholder="prijs invullen" value="${r.prijs===null?'':r.prijs}">`
        : (r.prijs === null ? `<span class="badge onbekend">onbekend</span>` : eur(Number(r.prijs)));
      tr.innerHTML = `
        <td>${r.omschrijving || ''}${r.artikelcode ? `<div class="hint">${r.artikelcode}</div>` : ''}</td>
        <td class="muted">${materiaalRegelLabel(r)}</td>
        <td class="right">${aantalCel}</td>
        <td>${r.eenheid || ''}</td>
        <td class="right prijs-cell">${prijsCel}</td>
        <td class="right">${onvolledig ? '<span class="badge onbekend">nog geen prijs</span>' : eur(totaal || 0)}</td>
        <td>${r.afgeleid ? '' : `<button class="icon-btn no-print" data-id="${r.id}" data-action="verwijder-materiaal" title="Verwijderen">✕</button>`}</td>`;
      tbody.appendChild(tr);
    }
    const scroll = document.createElement('div');
    scroll.className = 'table-scroll';
    scroll.appendChild(table);
    div.appendChild(scroll);
    wrap.appendChild(div);
  }
}
function renderUren() {
  const tbody = document.getElementById('urenBody');
  tbody.innerHTML = '';
  let totUren = 0, totKosten = 0;
  for (const rol of Object.keys(ROL_LABELS)) {
    const { voorstel, definitief } = berekening.uren[rol];
    const tarief = Number(state.uren[rol].tarief) || 0;
    const kosten = definitief * tarief;
    totUren += definitief; totKosten += kosten;
    const tr = document.createElement('tr');
    const isAuto = (rol === 'hoofdmonteur' || rol === 'hulpmonteur' || rol === 'servicemonteur');
    const overrideActief = isAuto && state.uren[rol].override !== null && state.uren[rol].override !== undefined;
    tr.innerHTML = `
      <td>${ROL_LABELS[rol]}</td>
      <td class="right muted">${voorstel === null ? '—' : voorstel}</td>
      <td class="right">
        ${rol === 'verkoper'
          ? `<input type="number" min="0" step="0.5" class="num-input" data-rol="${rol}" data-field="uren" value="${state.uren.verkoper.uren}">`
          : isAuto
            ? `<input type="number" min="0" step="1" class="num-input" data-rol="${rol}" data-field="override" value="${definitief}">`
            : `<input type="number" min="0" step="0.5" class="num-input" data-rol="${rol}" data-field="werk" value="${state.uren[rol].werk}" title="Werkuren">
               <input type="number" min="0" step="0.5" class="num-input" data-rol="${rol}" data-field="reis" value="${state.uren[rol].reis}" title="Reisuren" style="margin-top:3px;">`}
        ${overrideActief ? `<span class="override-flag no-print" data-rol="${rol}" data-action="reset-override" title="Terug naar automatisch voorstel">↺ auto</span>` : ''}
      </td>
      <td class="right"><input type="number" min="0" step="1" class="price-input" data-rol="${rol}" data-field="tarief" value="${tarief}"></td>
      <td class="right">${eur(kosten)}</td>
      <td></td>`;
    tbody.appendChild(tr);
  }
  document.getElementById('urenTotaalUren').textContent = totUren.toLocaleString('nl-NL');
  document.getElementById('urenTotaalKosten').textContent = eur(totKosten);
  const sm = berekening.servicemonteurVoorstel;
  document.getElementById('sm_auto').value = `${sm.auto + sm.vrfIbs} u (regelaar ${sm.auto}u + VRF IBS ${sm.vrfIbs}u)`;
}
const uiState = { toonAlleUitbesteding: false, toonAlleEquipment: false, toonSectieBrowser: false };
function renderLijst(lijst, tbodyId, totaalId, toonAlleKey) {
  const tbody = document.getElementById(tbodyId);
  tbody.innerHTML = '';
  const toonAlles = uiState[toonAlleKey];
  const verborgen = [];
  for (const r of lijst) {
    const isFavoriet = r.favoriet !== false;
    const inGebruik = (Number(r.aantal) || 0) > 0;
    if (!isFavoriet && !inGebruik && !toonAlles) { verborgen.push(r); continue; }
    const totaal = regelTotaal(r);
    const onvolledig = totaal === null && inGebruik;
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><input data-id="${r.id}" data-field="omschrijving" value="${r.omschrijving || ''}"></td>
      <td class="right"><input type="text" inputmode="numeric" class="num-input" data-id="${r.id}" data-field="aantal" value="${weergaveAantal(r.aantal)}"></td>
      <td><input data-id="${r.id}" data-field="eenheid" value="${r.eenheid||''}" style="max-width:70px;"></td>
      <td class="right"><input type="number" min="0" step="0.01" class="price-input" data-id="${r.id}" data-field="prijs" placeholder="onbekend" value="${r.prijs===null?'':r.prijs}"></td>
      <td class="right">${onvolledig ? '<span class="badge onbekend">onbekend</span>' : eur(totaal || 0)}</td>
      <td><button class="icon-btn no-print" data-id="${r.id}" data-action="verwijder-${tbodyId==='uitbestedingBody'?'uitbesteding':'equipment'}" title="Verwijderen">✕</button></td>`;
    tbody.appendChild(tr);
  }
  const { totaal, onvolledig } = lijstTotaal(lijst);
  document.getElementById(totaalId).innerHTML = eur(totaal) + (onvolledig ? ` <span class="badge onbekend">${onvolledig} onbekend</span>` : '');
  const toggleBtn = document.getElementById(tbodyId + 'Toggle');
  if (toggleBtn) {
    toggleBtn.style.display = (verborgen.length === 0 && !toonAlles) ? 'none' : '';
    toggleBtn.textContent = toonAlles ? 'Minder standaardposten tonen' : `+ Meer standaardposten tonen (${verborgen.length})`;
  }
}
function renderOverig(m) {
  document.getElementById('ov_parkeeruren').value = Math.round(m.parkeeruren * 100) / 100;
  document.getElementById('ov_parkeerkosten').value = eur(m.parkeerkosten);
}
function renderMarge(m) {
  document.getElementById('mg_materiaal').textContent = eur(m.materiaal.totaal) + (m.materiaal.onvolledig ? ` (+${m.materiaal.onvolledig} onbekend)` : '');
  document.getElementById('mg_arbeid').textContent = eur(m.arbeid);
  document.getElementById('mg_shorttrip').textContent = eur(m.shortTripKosten);
  document.getElementById('mg_transfer').textContent = eur(m.transferKosten);
  document.getElementById('mg_uitbesteding').textContent = eur(m.uitbesteding.totaal) + (m.uitbesteding.onvolledig ? ` (+${m.uitbesteding.onvolledig} onbekend)` : '');
  document.getElementById('mg_overhead').textContent = eur(m.overheadInkoop + m.overheadUitbesteding);
  document.getElementById('mg_equipment').textContent = eur(m.equipment.totaal) + (m.equipment.onvolledig ? ` (+${m.equipment.onvolledig} onbekend)` : '');
  document.getElementById('mg_reiskosten').textContent = eur(m.reiskosten);
  document.getElementById('mg_contingency_reserves_out').textContent = eur(m.contingencyReserves);
  document.getElementById('mg_contingency_onderhandeling_out').textContent = eur(m.contingencyOnderhandeling);
  document.getElementById('mg_ic').textContent = eur(m.ic);
  document.getElementById('mg_lost').textContent = eur(m.lost);
  document.getElementById('mg_financial').textContent = eur(m.financial);
  document.getElementById('mg_groupfees').textContent = eur(m.groupFees);
  document.getElementById('mg_fullcost').textContent = eur(m.fullCost);
  document.getElementById('mg_projectprice_out').textContent = eur(m.projectPrice);
  const resultaatIsVerlies = m.resultaat !== null && m.resultaat < 0;
  document.getElementById('mg_resultaat').textContent = eur(m.resultaat);
  document.getElementById('mg_resultaat').classList.toggle('negatief', resultaatIsVerlies);
  document.getElementById('mg_resultaat_pct').textContent = pct(m.resultaatPct);
  document.getElementById('mg_resultaat_pct').classList.toggle('negatief', resultaatIsVerlies);
  document.getElementById('mg_omzetbonus').textContent = eur(m.omzetbonus);
  document.getElementById('mg_betalingskorting').textContent = eur(m.betalingskorting);
  document.getElementById('mg_garantie').textContent = eur(m.garantie);
  document.getElementById('mg_verkoopprijs').textContent = eur(m.verkoopprijs);
  document.getElementById('tp_materiaal').textContent = eur(m.materiaal.totaal);
  document.getElementById('tp_arbeid').textContent = eur(m.arbeid);
  document.getElementById('tp_fullcost').textContent = eur(m.fullCost);
  document.getElementById('tp_resultaat').textContent = eur(m.resultaat);
  document.getElementById('tp_resultaat').classList.toggle('negatief', resultaatIsVerlies);
  document.getElementById('tp_verkoopprijs').textContent = eur(m.verkoopprijs);
}
function renderSectieSamenvattingen(m) {
  const set = (id, text) => { const el = document.getElementById(id); if (el) el.textContent = text; };
  const proj = state.meta;
  const projTitel = [proj.projectnaam || proj.qnummer, proj.klantnaam].filter(Boolean).join(' · ');
  set('sum_projectgegevens', projTitel || 'nog niet ingevuld');
  set('sum_instellingen', `${state.instellingen.moeilijkheid} · ${state.instellingen.provincie}`);
  const nInst = state.installaties.length;
  set('sum_installaties', nInst === 0
    ? 'nog geen installaties toegevoegd'
    : `${nInst} installatie${nInst === 1 ? '' : 's'} · ${berekening.monteurWerkurenAuto} werkuur`);
  const nMat = state.materiaal.length;
  set('sum_materiaal', nMat === 0
    ? 'nog geen materiaal toegevoegd'
    : `${nMat} regel${nMat === 1 ? '' : 's'} · ${eur(m.materiaal.totaal)}${m.materiaal.onvolledig ? ` (+${m.materiaal.onvolledig} onbekend)` : ''}`);
  set('sum_uren', `${document.getElementById('urenTotaalUren').textContent} u · ${document.getElementById('urenTotaalKosten').textContent}`);
  set('sum_uitbesteding', `${eur(m.uitbesteding.totaal)}${m.uitbesteding.onvolledig ? ` (+${m.uitbesteding.onvolledig} onbekend)` : ''}`);
  set('sum_equipment', `${eur(m.equipment.totaal)}${m.equipment.onvolledig ? ` (+${m.equipment.onvolledig} onbekend)` : ''}`);
  set('sum_overig', eur(m.reiskosten + m.shortTripKosten + m.transferKosten));
  set('sum_marge', m.verkoopprijs === null
    ? 'nog geen project price ingevuld'
    : `verkoopprijs ${eur(m.verkoopprijs)} · resultaat ${pct(m.resultaatPct)}`);
}
function renderIncompleteWarning(m) {
  const totaalOnvolledig = m.materiaal.onvolledig + m.uitbesteding.onvolledig + m.equipment.onvolledig;
  const el = document.getElementById('incompleteWarning');
  if (totaalOnvolledig > 0) {
    el.style.display = 'block';
    el.textContent = `⚠ ${totaalOnvolledig} regel(s) hebben nog geen prijs ("onbekend") — deze tellen nog niet mee in de totalen hierboven. Vul de prijs in zodra bekend, vóórdat de offerte de deur uit gaat.`;
  } else {
    el.style.display = 'none';
  }
}
function captureFocus() {
  const el = document.activeElement;
  if (!el || el === document.body) return null;
  return {
    elementId: el.id || null, id: el.dataset ? el.dataset.id || null : null,
    field: el.dataset ? el.dataset.field || null : null, rol: el.dataset ? el.dataset.rol || null : null,
    selStart: (typeof el.selectionStart === 'number') ? el.selectionStart : null,
    selEnd: (typeof el.selectionEnd === 'number') ? el.selectionEnd : null,
  };
}
function restoreFocus(f) {
  if (!f) return;
  let el = null;
  if (f.id && f.field) el = document.querySelector(`[data-id="${f.id}"][data-field="${f.field}"]`);
  else if (f.rol && f.field) el = document.querySelector(`[data-rol="${f.rol}"][data-field="${f.field}"]`);
  else if (f.elementId) el = document.getElementById(f.elementId);
  if (!el) return;
  el.focus();
  // input type="number" ondersteunt setSelectionRange() niet (de catch
  // hieronder) -- de cursor valt dan terug op het begin van het veld in
  // plaats van waar 'm stond, dus elke toetsaanslag (renderAll() rendert bij
  // elke wijziging deze hele rij opnieuw, zie hierboven) zet het volgende
  // cijfer vóór het vorige in plaats van erachter: "123" typen werd zo "321".
  // De "aantal"-velden (installaties/materiaal/uitbesteding/equipment)
  // gebruiken daarom bewust type="text" inputmode="numeric" i.p.v.
  // type="number" -- daar werkt setSelectionRange wél, dus landt de cursor na
  // elke render weer op de juiste plek.
  if (f.selStart !== null && el.setSelectionRange) {
    try { el.setSelectionRange(f.selStart, f.selEnd); } catch (e) { /* input type ondersteunt het niet (bijv. number) */ }
  }
}

function renderAll(nietOpnieuwPlannen) {
  if (!berekening) berekening = legeBerekening();
  const focus = captureFocus();
  renderMeta();
  renderInstellingenOpties();
  document.getElementById('i_moeilijkheid').value = state.instellingen.moeilijkheid;
  document.getElementById('i_provincie').value = state.instellingen.provincie;
  document.getElementById('i_bonusklant').value = state.instellingen.bonusklant;
  document.getElementById('i_kortingklant').value = state.instellingen.kortingklant;
  document.getElementById('i_provisieklant').value = state.instellingen.provisieklant;
  renderInstallaties();
  renderFavorieten();
  renderSectieBrowser();
  renderMateriaal();
  renderUren();
  renderLijst(state.uitbesteding, 'uitbestedingBody', 'uitbestedingTotaal', 'toonAlleUitbesteding');
  renderLijst(state.equipment, 'equipmentBody', 'equipmentTotaal', 'toonAlleEquipment');
  renderOverig(berekening.marge);
  renderMarge(berekening.marge);
  renderIncompleteWarning(berekening.marge);
  renderSectieSamenvattingen(berekening.marge);
  restoreFocus(focus);
  CB.autosave();
  if (!nietOpnieuwPlannen) plannenHerberekening();
}

/* ==================================== EVENTS ==================================== */
function bindMeta() {
  const map = { m_qnummer: 'qnummer', m_projectnaam: 'projectnaam', m_klantnaam: 'klantnaam', m_klantnummer: 'klantnummer', m_uitgangspunten: 'uitgangspunten' };
  for (const [id, field] of Object.entries(map)) {
    document.getElementById(id).addEventListener('input', e => { state.meta[field] = e.target.value; CB.autosave(); plannenHerberekening(); });
  }
  document.getElementById('i_moeilijkheid').addEventListener('change', e => { state.instellingen.moeilijkheid = e.target.value; renderAll(); });
  document.getElementById('i_reistijd').addEventListener('input', e => { state.instellingen.reistijd = nonNegatief(e.target.value); renderAll(); });
  document.getElementById('i_provincie').addEventListener('change', e => { state.instellingen.provincie = e.target.value; renderAll(); });
  document.getElementById('i_bonusklant').addEventListener('change', e => { state.instellingen.bonusklant = e.target.value; renderAll(); });
  document.getElementById('i_kortingklant').addEventListener('change', e => { state.instellingen.kortingklant = e.target.value; renderAll(); });
  document.getElementById('i_provisieklant').addEventListener('change', e => { state.instellingen.provisieklant = e.target.value; renderAll(); });
  document.getElementById('ov_nachten').addEventListener('input', e => { state.overig.nachten = nonNegatief(e.target.value); renderAll(); });
  document.getElementById('ov_nachtprijs').addEventListener('input', e => { state.overig.nachtprijs = nonNegatief(e.target.value); renderAll(); });
  document.getElementById('ov_shorttrip_dagen').addEventListener('input', e => { state.overig.shortTripDagen = nonNegatief(e.target.value); renderAll(); });
  document.getElementById('ov_shorttrip_tarief').addEventListener('input', e => { state.overig.shortTripTarief = nonNegatief(e.target.value); renderAll(); });
  document.getElementById('ov_transfer_uren').addEventListener('input', e => { state.overig.transferUren = nonNegatief(e.target.value); renderAll(); });
  document.getElementById('ov_transfer_tarief').addEventListener('input', e => { state.overig.transferTarief = nonNegatief(e.target.value); renderAll(); });
  document.getElementById('sm_overig').addEventListener('input', e => { state.uren.servicemonteur.overig = nonNegatief(e.target.value); renderAll(); });
  document.getElementById('mg_contingency_reserves').addEventListener('input', e => { state.marge.contingencyReserves = nonNegatief(e.target.value); renderAll(); });
  document.getElementById('mg_contingency_onderhandeling').addEventListener('input', e => { state.marge.contingencyOnderhandeling = nonNegatief(e.target.value); renderAll(); });
  document.getElementById('mg_projectprice').addEventListener('input', e => { state.marge.projectPrice = e.target.value === '' ? null : nonNegatief(e.target.value); renderAll(); });
}
function bindInstallaties() {
  document.getElementById('btnInstallatieToevoegen').addEventListener('click', () => {
    state.installaties.push({ id: newId(), systeemsoort: 'VRF', merk: '', montagewijze: '', typeBinnendeel: DATA.systemen.soort_binnendeel[0], materiaalId: null, aantalBuitendelen: 0, aantalBinnendelen: 0 });
    renderAll();
  });
  const onInstallatieVeld = e => {
    const id = e.target.dataset.id, field = e.target.dataset.field;
    if (!id || !field) return;
    const inst = state.installaties.find(i => i.id === id);
    if (inst) { inst[field] = nonNegatief(e.target.value); renderAll(); }
  };
  document.getElementById('installatiesList').addEventListener('input', onInstallatieVeld);
  document.getElementById('installatiesList').addEventListener('change', onInstallatieVeld);
  document.getElementById('installatiesList').addEventListener('click', e => {
    if (e.target.dataset.action === 'verwijder-installatie') {
      state.installaties = state.installaties.filter(i => i.id !== e.target.dataset.id);
      renderAll();
    }
    if (e.target.dataset.action === 'dupliceer-installatie') {
      const inst = state.installaties.find(i => i.id === e.target.dataset.id);
      if (inst) {
        const idx = state.installaties.indexOf(inst);
        state.installaties.splice(idx + 1, 0, { ...inst, id: newId() });
        renderAll();
      }
    }
  });
}
function bindMateriaal() {
  document.getElementById('materiaalSectieBrowserToggle').addEventListener('click', () => {
    uiState.toonSectieBrowser = !uiState.toonSectieBrowser;
    renderAll();
  });
  document.getElementById('materiaalFavorieten').addEventListener('click', e => {
    const btn = e.target.closest('[data-action="favoriet-toevoegen"]');
    if (!btn) return;
    const catEntry = CATALOGUS_BY_ROW[Number(btn.dataset.row)];
    if (catEntry) voegMateriaalToe(catEntry);
  });
  document.getElementById('materiaalSectieBrowser').addEventListener('change', e => {
    if (!e.target.dataset.sectieBrowser) return;
    const row = Number(e.target.value);
    if (!row) return;
    const catEntry = CATALOGUS_BY_ROW[row];
    if (catEntry) voegMateriaalToe(catEntry);
    e.target.value = '';
  });
  document.getElementById('btnVrijeRegel').addEventListener('click', () => {
    state.materiaal.push({ id: newId(), sectie: 'PROJECTBESTELLING', bron: 'projectbestelling', omschrijving: '', eenheid: 'ST', prijs: null, aantal: 1 });
    renderAll();
  });
  const zoekInput = document.getElementById('materiaalZoek');
  const zoekResults = document.getElementById('materiaalZoekResults');
  zoekInput.addEventListener('input', () => {
    const q = zoekInput.value;
    const treffers = [
      ...zoekMateriaal(q).map(c => ({ soort: 'catalogus', data: c, label: c.omschrijving, prijs: c.prijs })),
      ...zoekPanasonic(q).map(a => ({ soort: 'panasonic', data: a, label: panasonicOmschrijving(a) + ' — Panasonic ' + a.catalogus, prijs: a.netto_prijs })),
      ...zoekDaikin(q).map(a => ({ soort: 'daikin', data: a, label: a.omschrijving + ' — Daikin', prijs: a.netto_prijs })),
    ];
    if (treffers.length === 0) {
      zoekResults.style.display = q.trim().length >= 2 ? 'block' : 'none';
      zoekResults.innerHTML = q.trim().length >= 2 ? '<div class="item"><span class="d muted">Geen resultaten gevonden…</span></div>' : '';
      return;
    }
    zoekResults.style.display = 'block';
    zoekResults.innerHTML = treffers.map((t, i) =>
      `<div class="item" data-i="${i}"><span class="d">${t.label}</span><span class="p">${t.prijs === null ? 'onbekend' : eur(t.prijs)}</span></div>`
    ).join('');
    zoekResults.onclick = e => {
      const item = e.target.closest('.item');
      if (!item) return;
      const t = treffers[Number(item.dataset.i)];
      if (t.soort === 'catalogus') voegMateriaalToe(t.data);
      else if (t.soort === 'panasonic') voegPanasonicToe(t.data);
      else voegDaikinToe(t.data);
      zoekInput.value = ''; zoekResults.style.display = 'none';
    };
  });
  document.addEventListener('click', e => {
    if (!zoekResults.contains(e.target) && e.target !== zoekInput) zoekResults.style.display = 'none';
  });
  document.getElementById('materiaalSecties').addEventListener('input', e => {
    const id = e.target.dataset.id, field = e.target.dataset.field;
    if (!id || !field) return;
    const regel = state.materiaal.find(r => r.id === id);
    if (!regel) return;
    if (field === 'aantal') regel.aantal = nonNegatief(e.target.value);
    else if (field === 'prijs') regel.prijs = e.target.value === '' ? null : nonNegatief(e.target.value);
    else regel[field] = e.target.value;
    renderAll();
  });
  document.getElementById('materiaalSecties').addEventListener('click', e => {
    if (e.target.dataset.action === 'verwijder-materiaal') {
      state.materiaal = state.materiaal.filter(r => r.id !== e.target.dataset.id);
      renderAll();
    }
  });
}
function bindUren() {
  document.getElementById('urenBody').addEventListener('input', e => {
    const rol = e.target.dataset.rol, field = e.target.dataset.field;
    if (!rol || !field) return;
    state.uren[rol][field] = field === 'uren' || field === 'werk' || field === 'reis' || field === 'tarief' || field === 'override'
      ? nonNegatief(e.target.value) : e.target.value;
    renderAll();
  });
  document.getElementById('urenBody').addEventListener('click', e => {
    if (e.target.dataset.action === 'reset-override') {
      state.uren[e.target.dataset.rol].override = null;
      renderAll();
    }
  });
}
function bindLijst(tbodyId, stateKey) {
  document.getElementById(tbodyId).addEventListener('input', e => {
    const id = e.target.dataset.id, field = e.target.dataset.field;
    if (!id || !field) return;
    const regel = state[stateKey].find(r => r.id === id);
    if (regel) {
      // "aantal" leeg laten bij het legen van het veld (net als bij materiaal/
      // installaties hieronder) -- hier stond eerder expliciet 0, waardoor het
      // veld bij de eerstvolgende render alweer "0" toonde vóór er een nieuw
      // cijfer in getypt kon worden.
      regel[field] = field === 'aantal' ? nonNegatief(e.target.value)
        : field === 'prijs' ? (e.target.value === '' ? null : nonNegatief(e.target.value))
        : e.target.value;
      renderAll();
    }
  });
  document.getElementById(tbodyId).addEventListener('click', e => {
    const actie = e.target.dataset.action;
    if (actie === `verwijder-${stateKey}`) {
      state[stateKey] = state[stateKey].filter(r => r.id !== e.target.dataset.id);
      renderAll();
    }
  });
  const toggle = document.getElementById(tbodyId + 'Toggle');
  if (toggle) toggle.addEventListener('click', () => {
    const key = toggle.dataset.toggle;
    uiState[key] = !uiState[key];
    renderAll();
  });
}
function bindToevoegKnoppen() {
  document.getElementById('btnUitbestedingToevoegen').addEventListener('click', () => {
    state.uitbesteding.push({ id: newId(), omschrijving: '', eenheid: 'ST', prijs: null, aantal: 1, favoriet: true });
    renderAll();
  });
  document.getElementById('btnEquipmentToevoegen').addEventListener('click', () => {
    state.equipment.push({ id: newId(), omschrijving: '', eenheid: 'ST', prijs: null, aantal: 1, favoriet: true });
    renderAll();
  });
}
function bestellijstData() {
  const regels = state.materiaal.filter(r => (Number(r.aantal) || 0) > 0);
  const perSectie = {};
  for (const r of regels) { perSectie[r.sectie] = perSectie[r.sectie] || []; perSectie[r.sectie].push(r); }
  return perSectie;
}
function bindBestellijst() {
  document.getElementById('btnBestellijstPrint').addEventListener('click', () => {
    const perSectie = bestellijstData();
    const printArea = document.getElementById('printArea');
    printArea.innerHTML = Object.entries(perSectie).map(([sectie, regels]) => `
      <h3>${sectie}</h3>
      <table><thead><tr><th>Omschrijving</th><th>Artikelcode</th><th>Bron</th><th>Aantal</th><th>Eenheid</th></tr></thead>
      <tbody>${regels.map(r => `<tr><td>${r.omschrijving||''}</td><td>${r.artikelcode||''}</td><td>${materiaalRegelLabel(r)}</td><td>${r.aantal}</td><td>${r.eenheid||''}</td></tr>`).join('')}</tbody></table>`
    ).join('');
    printArea.style.display = 'block';
    window.print();
    printArea.style.display = 'none';
  });
  document.getElementById('btnBestellijstCsv').addEventListener('click', () => {
    const perSectie = bestellijstData();
    const regels = ['Sectie;Omschrijving;Artikelcode;Bron;Aantal;Eenheid'];
    for (const [sectie, rijen] of Object.entries(perSectie)) {
      for (const r of rijen) regels.push([sectie, r.omschrijving||'', r.artikelcode||'', materiaalRegelLabel(r), r.aantal, r.eenheid||''].join(';'));
    }
    const blob = new Blob([regels.join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = 'bestellijst.csv';
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
}
function bindCollapsibles() {
  for (const kop of document.querySelectorAll('#stapCalculatie .card > h2')) {
    kop.addEventListener('click', e => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.classList.contains('info-icon')) return;
      kop.closest('.card').classList.toggle('collapsed');
    });
  }
}

/* Het ingevulde Excel-calculatieblad (het oorspronkelijke bedrijfssjabloon)
   voor de ACTIEVE optie -- zie calculatie/calculatieblad.py op de server.
   Net als /overdracht en /brief is dit een POST die een rechtstreeks
   antwoord geeft (hier: de bytes van het .xlsx-bestand), geen CB.postJSON
   (die parset altijd als JSON, zie CLAUDE.md se uitleg van CB.getJSON/
   postJSON) -- bij een fout stuurt de server wél gewoon JSON terug, vandaar
   de Content-Type-controle hieronder (zelfde patroon als brief.html se
   haalWordVanApp()). */
function calculatiebladBestandsnaam() {
  const delen = [state.meta.klantnaam, state.meta.projectnaam].map(CB.veiligeBestandsnaamdeel).filter(Boolean);
  const basis = delen.length ? `Calculatieblad-${delen.join('-')}` : 'Calculatieblad';
  const naam = opties.length > 1 ? `${basis}-${CB.veiligeBestandsnaamdeel(opties[actieveOptieIndex].naam)}` : basis;
  return naam + '.xlsx';
}
/* Op verzoek van Lars (2 oktober 2026): alle bestaande calculaties staan al
   in dit Excel-sjabloon (zoals vóór deze tool met de hand werd bijgehouden),
   dus moet zo'n al ingevuld bestand ook weer INGELADEN kunnen worden -- niet
   alleen het eigen .json-projectbestand. Het bestand gaat, net als bij
   brief.html se datablad-upload, base64-gecodeerd naar de server
   (POST /calculatieblad/importeer); calculatie/calculatieblad.py se
   lees_calculatieblad() doet het eigenlijke werk en levert een staat +
   waarschuwingen terug (bijv. "installaties zijn alleen als totaal per
   systeemsoort te herleiden") die hier ongewijzigd aan de gebruiker worden
   getoond -- zie CLAUDE.md voor de volledige uitleg van wat wel en niet uit
   zo'n bestand is te herleiden. */
function bindCalculatiebladImporterenKnop() {
  const knop = document.getElementById('btnCalculatiebladImporteren');
  const input = document.getElementById('calculatiebladInput');
  knop.addEventListener('click', () => {
    if (CB.heeftInhoud() && !confirm('Er staat al iets ingevuld. Dit overschrijven met het geïmporteerde calculatieblad?')) return;
    input.value = '';
    input.click();
  });
  input.addEventListener('change', async () => {
    const bestand = input.files[0];
    if (!bestand) return;
    const oud = knop.textContent;
    knop.disabled = true; knop.textContent = 'Bezig…';
    try {
      const bytes = new Uint8Array(await bestand.arrayBuffer());
      let binair = ''; for (const b of bytes) binair += String.fromCharCode(b);
      const resultaat = await CB.postJSON('/calculatieblad/importeer', { inhoud: btoa(binair) });
      if (resultaat.fout) { CB.toast('Kon het calculatieblad niet importeren: ' + resultaat.fout); return; }
      CB.calc.vulOpties([{ naam: 'Optie A', staat: resultaat.staat }], 0);
      CB.toast(resultaat.waarschuwingen && resultaat.waarschuwingen.length
        ? 'Calculatieblad geïmporteerd — ' + resultaat.waarschuwingen.join(' ')
        : 'Calculatieblad geïmporteerd.');
    } catch (fout) {
      CB.toast('Kon het calculatieblad niet importeren: ' + fout.message);
    } finally {
      knop.disabled = false; knop.textContent = oud;
    }
  });
}

function bindCalculatiebladKnop() {
  const knop = document.getElementById('btnCalculatieblad');
  knop.addEventListener('click', async () => {
    const oud = knop.textContent;
    knop.disabled = true; knop.textContent = 'Bezig…';
    try {
      const antwoord = await fetch('/calculatieblad', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(state),
      });
      const soort = antwoord.headers.get('Content-Type') || '';
      if (soort.includes('json')) throw new Error((await antwoord.json()).fout || 'onbekende fout');
      const blob = await antwoord.blob();
      const naam = calculatiebladBestandsnaam();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = naam;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 4000);
      CB.toast('Calculatieblad gedownload als ' + naam);
    } catch (fout) {
      CB.toast('Het calculatieblad kon niet gemaakt worden: ' + fout.message);
    } finally {
      knop.disabled = false; knop.textContent = oud;
    }
  });
}

/* ==================================== INIT ==================================== */
async function laadData() {
  const [materiaal_catalogus, yimm, parkeertarieven, omzetbonus, systemen, panasoncRac, panasonicPac, daikin] = await Promise.all([
    CB.getJSON('/data/materiaal_catalogus.json'), CB.getJSON('/data/yimm.json'),
    CB.getJSON('/data/parkeertarieven.json'), CB.getJSON('/data/omzetbonus_provisie.json'),
    CB.getJSON('/data/systemen.json'),
    CB.getJSON('/data/panasonic/rac.json'), CB.getJSON('/data/panasonic/pac.json'),
    CB.getJSON('/data/daikin/split_sky_air_multi.json'),
  ]);
  DATA = {
    materiaal_catalogus, yimm, parkeertarieven, omzetbonus, systemen,
    panasonic: [
      ...panasoncRac.artikelen.map((a, i) => ({ ...a, catalogus: 'RAC', panasonic_id: 'RAC-' + i })),
      ...panasonicPac.artikelen.map((a, i) => ({ ...a, catalogus: 'PAC', panasonic_id: 'PAC-' + i })),
    ],
    daikin: [
      ...daikin.artikelen.map((a, i) => ({ ...a, daikin_soort: 'artikel', daikin_id: 'ART-' + i })),
      ...daikin.accessoires.map((a, i) => ({ ...a, daikin_soort: 'accessoire', daikin_id: 'ACC-' + i })),
    ],
  };
  for (const c of DATA.materiaal_catalogus) CATALOGUS_BY_ROW[c.row] = c;
}

async function initCalculatie() {
  CB.laadscherm.zetStatus('Materiaal- en prijsgegevens laden…');
  await laadData();
  const bewaard = CB.leesAutosaveOpties();
  if (bewaard) {
    opties = bewaard.opties.map(o => ({ naam: o.naam, staat: o.staat }));
    actieveOptieIndex = Math.min(Math.max(bewaard.actieveOptie || 0, 0), opties.length - 1);
    hersynchroniseerIdTeller(opties);
  } else {
    opties = [{ naam: 'Optie A', staat: nieuweStaat() }];
    actieveOptieIndex = 0;
  }
  state = opties[actieveOptieIndex].staat;
  bindMeta(); bindInstallaties(); bindMateriaal(); bindUren();
  bindLijst('uitbestedingBody', 'uitbesteding'); bindLijst('equipmentBody', 'equipment');
  bindToevoegKnoppen(); bindBestellijst(); bindCollapsibles(); bindOpties(); bindCalculatiebladKnop();
  bindCalculatiebladImporterenKnop();
  renderOptieBalk();
  CB.laadscherm.zetStatus('Rekenkern voorbereiden…');
  await herbereken();
}

CB.calc = {
  get staat() { return state; },
  nieuweStaat,
  // Vervangt de HELE lijst opties (bijv. bij "Nieuw project" of het openen
  // van een bestand) -- voor een enkele optie tussentijds bijwerken (Openen/
  // Nieuw binnen dezelfde sessie), niet voor het wisselen tussen bestaande
  // opties (zie wisselOptie hierboven, via de tabbalk).
  vulOpties(nieuweOpties, actieveIndex) {
    opties = nieuweOpties.map(o => ({ naam: o.naam || 'Optie', staat: o.staat }));
    actieveOptieIndex = Math.min(Math.max(actieveIndex || 0, 0), opties.length - 1);
    hersynchroniseerIdTeller(opties);
    state = opties[actieveOptieIndex].staat;
    berekening = null; laatstVerzonden = null;
    renderOptieBalk();
    renderAll();
  },
  // Voor CB.huidigProject()/autosave: alle opties, met de actieve staat
  // gesynchroniseerd (zie bewaarActieveOptie).
  alleOpties() {
    bewaarActieveOptie();
    return opties.map(o => ({ naam: o.naam, staat: o.staat }));
  },
  get actieveOptieIndex() { return actieveOptieIndex; },
  heeftInhoud,
  render: () => renderAll(),
  klaar: null,
};

document.addEventListener('DOMContentLoaded', () => { CB.calc.klaar = initCalculatie(); });

})();
