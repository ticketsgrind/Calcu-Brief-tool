'use strict';
/* ============================================================================
   Briefstap — nieuw formulier voor de brieventool (die had er nog geen, zie
   brieventool/README.md: "Wat er nog niet is: het formulier"). De browser
   rekent hier niets uit en verzint geen tekst: elke wijziging gaat naar
   POST /brief en het scherm toont precies wat samenstellen.py teruggeeft,
   inclusief de "ontbreekt nog"-melding van controle.py. Facturering,
   betaling, condensafvoer e.d. hardcoderen hun mogelijke waarden niet: die
   komen van GET /keuzes, dat ze afleidt uit analyse/teksten.yaml (zie
   brieventool/bibliotheek.py:velden). Systeemsoort/montagewijze per
   installatie zijn wel hardcoded (regel.* condities, niet generiek af te
   leiden) en moeten in de pas blijven met analyse/teksten.yaml.
   ============================================================================ */
(function () {

const { eur } = CB;

const SYSTEEMSOORT_OPTIES = [
  ['splitsystem', 'Splitsysteem'], ['multi-splitsystem', 'Multi-splitsysteem'],
  ['vrf', 'VRF-systeem'], ['warmtepomp', 'Lucht-water warmtepomp'],
  ['vloeistofkoelmachine', 'Vloeistofkoelmachine'],
];
const MONTAGEWIJZE_OPTIES = [
  ['wandmontage', 'Wandmontage'], ['vloermontage', 'Vloermontage'], ['wand/vloermontage', 'Wand-/vloermontage'],
  ['plafondinbouwmontage', 'Plafondinbouwmontage'], ['plafondonderbouwmontage', 'Plafondonderbouwmontage'],
  ['montage boven het systeemplafond', 'Montage boven het systeemplafond'], ['buitenopstelling', 'Buitenopstelling'],
];
const INSTALLATIETYPE_OPTIES = [
  ['airconditioning', 'Airconditioning'], ['koelmachine', 'Koelmachine'],
  ['mechanische ventilatie', 'Mechanische ventilatie'], ['warmtepomp', 'Warmtepomp'],
  ['luchtslangsysteem', 'Luchtslangsysteem'],
];
// Deze twee tellen als "geld invullen", niet als "ja/nee" -- ook al gedraagt
// hun voorwaarde in teksten.yaml zich als vlag (elk bedrag > 0 is "waar").
const BEDRAG_VLAGGEN = new Set(['meerprijs_coating', 'meerprijs_ral']);

let antwoorden = {};
let keuzes = null;      // GET /keuzes: secties, ondertekenaars, velden
let controleInfo = [];  // laatste POST /overdracht: welke velden afgeleid/keuze_nodig zijn
let laatsteBrief = null; // laatste POST /brief-antwoord

let installatieTeller = 1;
const nieuweInstallatieId = () => 'inst' + (installatieTeller++);

function heeftInhoud() {
  return Object.keys(antwoorden).some(k => {
    const v = antwoorden[k];
    return Array.isArray(v) ? v.length > 0 : Boolean(v);
  });
}

function vindControle(pad) {
  return controleInfo.find(c => c.pad === pad) || null;
}

function controleBadge(pad) {
  const c = vindControle(pad);
  if (!c || c.status !== 'afgeleid') return '';
  return `<span class="badge controleer" title="${c.reden.replace(/"/g, '&quot;')}">afgeleid — controleer</span>`;
}

/* --------------------------- server-aanroepen --------------------------- */
let laatstVerzonden = null;
async function herbereken() {
  const lichaam = JSON.stringify(antwoorden);
  if (lichaam === laatstVerzonden) return;
  laatstVerzonden = lichaam;
  laatsteBrief = await CB.postJSON('/brief', antwoorden);
  renderVoorvertoning();
  renderOntbreekt();
}
const plannenHerberekening = CB.debounce(herbereken, 250);

async function vulVoorVanuitCalculatie() {
  const resultaat = await CB.postJSON('/overdracht', { calculatie: CB.calc.staat });
  if (resultaat.fout) { CB.toast(resultaat.fout); return; }
  const overgenomen = resultaat.offerte || {};
  controleInfo = resultaat.overdracht || [];
  // Expliciete, zichtbare actie -- overschrijft alleen de velden die de
  // calculatie ook echt aanlevert; alles daarbuiten (adres, aanhef,
  // facturering, ...) blijft gewoon staan zoals de gebruiker het had.
  Object.assign(antwoorden, overgenomen);
  if (overgenomen.installaties) {
    antwoorden.installaties = overgenomen.installaties.map(i => ({ id: nieuweInstallatieId(), ...i }));
  }
  render();
  CB.toast('Voorinvulling uit de calculatie toegepast — controleer de gemarkeerde velden.');
}

/* ------------------------------- rendering ------------------------------- */
function renderVoorvertoning() {
  const vel = document.getElementById('briefVel');
  if (!laatsteBrief || laatsteBrief.fout) {
    vel.innerHTML = `<p class="muted">${laatsteBrief && laatsteBrief.fout ? laatsteBrief.fout : 'Vul links de gegevens in om de brief te zien.'}</p>`;
    return;
  }
  vel.innerHTML = laatsteBrief.secties.map(sectie => sectie.alineas.map(a => {
    const klasse = ['alinea', a.stijl, a.witregel_erna !== false ? 'witregel-erna' : ''].filter(Boolean).join(' ');
    const tekst = (a.tekst || '') + (a.nadruk ? `<b>${a.nadruk}</b>` : '');
    return `<div class="${klasse}">${tekst || '&nbsp;'}</div>`;
  }).join('')).join('');
}

function renderOntbreekt() {
  const el = document.getElementById('briefOntbreekt');
  const ontbreekt = laatsteBrief && laatsteBrief.ontbreekt || [];
  const btn = document.getElementById('btnWordBestand');
  if (ontbreekt.length === 0) {
    el.style.display = 'none';
    btn.disabled = false;
    btn.title = '';
  } else {
    el.style.display = 'block';
    el.className = 'warn-banner fout';
    el.textContent = `Nog niet compleet: ${ontbreekt.join(', ')} ${ontbreekt.length === 1 ? 'ontbreekt' : 'ontbreken'} nog. Er komt pas een Word-bestand als dit is aangevuld.`;
    btn.disabled = true;
    btn.title = 'Vul eerst de ontbrekende gegevens in.';
  }
}

function veldWaarde(veld) { return antwoorden[veld] === undefined ? '' : antwoorden[veld]; }
function zetVeld(veld, waarde) { antwoorden[veld] = waarde; CB.autosave(); plannenHerberekening(); }

function bouwSelect(veld, opties, { leegLabel } = {}) {
  const huidig = veldWaarde(veld);
  const optionsHtml = opties.map(([w, l]) => `<option value="${w}" ${w === huidig ? 'selected' : ''}>${l}</option>`).join('');
  return `<select data-veld="${veld}">
    ${leegLabel ? `<option value="" ${!huidig ? 'selected' : ''}>${leegLabel}</option>` : ''}
    ${optionsHtml}
  </select>`;
}

function renderKlant() {
  const el = document.getElementById('briefKlant');
  const zakelijk = veldWaarde('klanttype') === 'zakelijk';
  el.innerHTML = `
    <div class="grid cols-4">
      <div class="field"><label>Klanttype</label>${bouwSelect('klanttype', [['particulier','Particulier'],['zakelijk','Zakelijk']], { leegLabel: '— kies —' })}</div>
      <div class="field" style="${zakelijk ? '' : 'display:none;'}"><label>Organisatie</label><input data-veld="organisatie" value="${veldWaarde('organisatie')}"></div>
      <div class="field"><label>Aanspreekvorm</label>${bouwSelect('aanspreekvorm', [['de heer','De heer'],['mevrouw','Mevrouw'],['de heer en mevrouw','De heer en mevrouw'],['Fam.','Familie (Fam.)']], { leegLabel: '— kies —' })}</div>
      <div class="field"><label>Voorletters</label><input data-veld="voorletters" value="${veldWaarde('voorletters')}" placeholder="bijv. P."></div>
      <div class="field"><label>Achternaam</label><input data-veld="achternaam" value="${veldWaarde('achternaam')}"></div>
      <div class="field"><label>E-mailadres klant</label><input data-veld="email_klant" value="${veldWaarde('email_klant')}"></div>
    </div>
    <div class="section-sub">Adres</div>
    <div class="grid cols-4">
      <div class="field"><label>Straat en huisnummer</label><input data-veld="straat_huisnummer" value="${veldWaarde('straat_huisnummer')}"></div>
      <div class="field"><label>Postcode</label><input data-veld="postcode" value="${veldWaarde('postcode')}" placeholder="1234 AB"></div>
      <div class="field"><label>Plaats</label><input data-veld="plaats" value="${veldWaarde('plaats')}"></div>
      <div class="field"><label>Land <span class="muted" style="font-weight:400;">(alleen bij buitenland)</span></label><input data-veld="land" value="${veldWaarde('land')}"></div>
    </div>`;
}

function renderKenmerken() {
  const el = document.getElementById('briefKenmerken');
  const aanleiding = veldWaarde('aanleiding');
  el.innerHTML = `
    <div class="grid cols-4">
      <div class="field"><label>Documentsoort</label>${bouwSelect('documentsoort', [['offerte','Offerte'],['opdrachtbevestiging','Opdrachtbevestiging']])}</div>
      <div class="field"><label>Briefdatum</label><input type="date" data-veld="briefdatum" value="${veldWaarde('briefdatum')}"></div>
      <div class="field"><label>Projectnummer</label><input data-veld="projectnummer" value="${veldWaarde('projectnummer')}" placeholder="Q.1234567.6.01"> ${controleBadge('projectnummer')}</div>
      <div class="field"><label>Installatietype</label>${bouwSelect('installatietype', INSTALLATIETYPE_OPTIES)}</div>
      <div class="field"><label>SA-nummer</label><input data-veld="sa_nummer" value="${veldWaarde('sa_nummer')}" placeholder="35950"></div>
      <div class="field"><label>Opsteller (initialen)</label><input data-veld="opsteller_initialen" value="${veldWaarde('opsteller_initialen')}"></div>
      <div class="field" style="grid-column:span 2;"><label>Betreft-regel (locatieaanduiding)</label><input data-veld="locatieaanduiding" value="${veldWaarde('locatieaanduiding')}" placeholder="uw woning / uw vestiging te Meerkerk / uw project ..."></div>
    </div>
    <div class="section-sub">Aanleiding</div>
    <div class="grid cols-3">
      <div class="field">${bouwSelect('aanleiding', (keuzes.velden.enkeleKeuze.aanleiding || []).map(o => [o.waarde, o.label]), { leegLabel: '— kies —' })}</div>
      <div class="field" style="${aanleiding === 'onderhoud' ? '' : 'display:none;'}"><label>Naam adviseur</label><input data-veld="adviseur" value="${veldWaarde('adviseur')}"></div>
      <div class="field"><label>Datum van de aanleiding</label><input data-veld="datum_aanleiding" value="${veldWaarde('datum_aanleiding')}" placeholder="18 augustus"></div>
      <div class="field" style="${aanleiding === 'opdrachtbevestiging' ? '' : 'display:none;'}"><label>Opdrachtnummer</label><input data-veld="opdrachtnummer" value="${veldWaarde('opdrachtnummer')}"></div>
    </div>`;
}

function renderInstallaties() {
  const wrap = document.getElementById('briefInstallaties');
  const lijst = antwoorden.installaties || [];
  wrap.innerHTML = lijst.map((inst, i) => {
    const pad = `installaties[${i}]`;
    const nodigTypeBuitendeel = inst.systeemsoort === 'multi-splitsystem' || inst.systeemsoort === 'vrf';
    return `
    <div class="installatie-card${vindControle(pad + '.systeemsoort') ? ' heeft-controle' : ''}">
      <div class="installatie-acties no-print">
        <button class="icon-btn" data-action="verwijder-installatie" data-i="${i}" title="Verwijderen">✕</button>
      </div>
      <div class="grid cols-4">
        <div class="field"><label>Ruimte <span class="muted" style="font-weight:400;">(kopregel, optioneel)</span></label><input data-inst="${i}" data-veld="ruimte" value="${inst.ruimte||''}"></div>
        <div class="field"><label>Aantal systemen</label><input type="number" min="1" data-inst="${i}" data-veld="aantal_systemen" value="${inst.aantal_systemen||1}"></div>
        <div class="field"><label>Systeemsoort ${controleBadge(pad + '.systeemsoort')}</label>
          <select data-inst="${i}" data-veld="systeemsoort">
            <option value="" ${!inst.systeemsoort?'selected':''}>— kies —</option>
            ${SYSTEEMSOORT_OPTIES.map(([w,l])=>`<option value="${w}" ${w===inst.systeemsoort?'selected':''}>${l}</option>`).join('')}
          </select>
        </div>
        <div class="field"><label>Montagewijze</label>
          <select data-inst="${i}" data-veld="montagewijze">
            <option value="" ${!inst.montagewijze?'selected':''}>— kies —</option>
            ${MONTAGEWIJZE_OPTIES.map(([w,l])=>`<option value="${w}" ${w===inst.montagewijze?'selected':''}>${l}</option>`).join('')}
          </select>
        </div>
        <div class="field"><label>Merk ${controleBadge(pad + '.merk')}</label><input data-inst="${i}" data-veld="merk" value="${inst.merk||''}"></div>
        <div class="field"><label>Type binnendeel ${controleBadge(pad + '.type_binnendeel')}</label><input data-inst="${i}" data-veld="type_binnendeel" value="${inst.type_binnendeel||''}"></div>
        <div class="field" style="${nodigTypeBuitendeel?'':'display:none;'}"><label>Type buitendeel</label><input data-inst="${i}" data-veld="type_buitendeel" value="${inst.type_buitendeel||''}"></div>
      </div>
    </div>`;
  }).join('') || '<p class="muted">Nog geen installaties — voeg er een toe, of gebruik "Vul voor vanuit de calculatie" hierboven.</p>';
}

function renderSysteemOpties() {
  const el = document.getElementById('briefSysteemOpties');
  const v = keuzes.velden;
  const enkeleVeld = (veld, label) => v.enkeleKeuze[veld]
    ? `<div class="field"><label>${label}</label>${bouwSelect(veld, v.enkeleKeuze[veld].map(o => [o.waarde, o.label]), { leegLabel: '— kies —' })}</div>` : '';
  const vinkje = ({ veld, label }) => `<label><input type="checkbox" data-vlag="${veld}" ${antwoorden[veld] ? 'checked' : ''}> ${label}</label>`;
  el.innerHTML = `
    <div class="grid cols-3">
      ${enkeleVeld('opstelling_buitenunit', 'Opstelling buitenunit')}
      ${enkeleVeld('condensafvoer', 'Condensafvoer')}
      ${enkeleVeld('bediening', 'Bediening')}
    </div>
    <div class="section-sub">Extra opties</div>
    <div class="vinkjes-lijst">
      ${v.vinkjes.filter(x => !BEDRAG_VLAGGEN.has(x.veld)).map(vinkje).join('')}
    </div>
    <div class="grid cols-3" style="margin-top:10px;">
      <div class="field"><label>Meerprijs coating (€, optioneel)</label><input type="number" min="0" step="1" data-veld="meerprijs_coating" value="${veldWaarde('meerprijs_coating')}"></div>
      <div class="field"><label>Meerprijs RAL-kleur (€, optioneel)</label><input type="number" min="0" step="1" data-veld="meerprijs_ral" value="${veldWaarde('meerprijs_ral')}"></div>
      <div class="field"><label>Meerprijs zwaardere unit (€, optioneel)</label><input type="number" min="0" step="1" data-veld="meerprijs_advies" value="${veldWaarde('meerprijs_advies')}"></div>
    </div>`;
}

function renderTechspec() {
  const el = document.getElementById('briefTechspec');
  const v = keuzes.velden;
  const soort = veldWaarde('technische_specificaties');
  el.innerHTML = `
    <div class="field">${bouwSelect('technische_specificaties', (v.enkeleKeuze.technische_specificaties||[]).map(o=>[o.waarde,o.label]), { leegLabel: '— geen —' })}</div>
    <div class="field" style="${soort === 'uitgeschreven' ? '' : 'display:none;'}">
      <label>Technische specificaties (tekst)</label>
      <textarea data-veld="technische_specificaties_tekst">${veldWaarde('technische_specificaties_tekst')}</textarea>
    </div>
    <div class="field" style="${soort === 'uitgeschreven' ? '' : 'display:none;'}">
      <label>Of: datablad aanleveren (Word, PDF of platte tekst) — vervangt bovenstaande tekst niet, tenzij die leeg is</label>
      <input type="file" id="techspecBestand">
      <div class="hint" id="techspecBestandStatus"></div>
    </div>`;
  const bestandInput = document.getElementById('techspecBestand');
  if (bestandInput) bestandInput.addEventListener('change', async () => {
    const bestand = bestandInput.files[0];
    if (!bestand) return;
    const status = document.getElementById('techspecBestandStatus');
    status.textContent = 'Bezig met uitlezen…';
    const inhoud = await bestandNaarBase64(bestand);
    const resultaat = await CB.postJSON('/datablad', { naam: bestand.name, inhoud });
    if (resultaat.fout) { status.textContent = resultaat.fout; return; }
    antwoorden.technische_specificaties_bestand = resultaat.tekst;
    status.textContent = `Uitgelezen uit ${bestand.name}.`;
    plannenHerberekening();
  });
}
function bestandNaarBase64(bestand) {
  return new Promise((resolve, reject) => {
    const lezer = new FileReader();
    lezer.onload = () => resolve(lezer.result.split(',')[1]);
    lezer.onerror = reject;
    lezer.readAsDataURL(bestand);
  });
}

function renderWerkzaamheden() {
  const el = document.getElementById('briefWerkzaamheden');
  const v = keuzes.velden.meervoudigeKeuze;
  const groep = (veld, titel) => `
    <div class="section-sub">${titel}</div>
    <div class="vinkjes-lijst">
      ${(v[veld]||[]).map(o => `<label><input type="checkbox" data-meervoudig="${veld}" data-waarde="${o.waarde}"
        ${(antwoorden[veld]||[]).includes(o.waarde) ? 'checked' : ''}> ${o.label}</label>`).join('')}
    </div>`;
  el.innerHTML = groep('werk_inclusief', 'Inbegrepen werkzaamheden') + groep('werk_exclusief', 'Niet-inbegrepen werkzaamheden');
}

function renderPrijs() {
  const el = document.getElementById('briefPrijs');
  const regels = antwoorden.prijsregels || [];
  el.innerHTML = `
    <div class="field"><label>Prijssoort</label>${bouwSelect('prijssoort', [['totaalprijs','Totaalprijs'],['raamprijs','Raamprijs']])}</div>
    <table>
      <thead><tr><th>Positie <span class="muted">(optioneel, bij meerdere regels)</span></th><th class="right">Bedrag (€)</th><th></th></tr></thead>
      <tbody>
        ${regels.map((r, i) => `<tr>
          <td><input data-prijsregel="${i}" data-veld="positie" value="${r.positie||''}" placeholder="pos. A"></td>
          <td class="right"><input type="number" min="0" step="0.01" class="price-input" data-prijsregel="${i}" data-veld="bedrag" value="${r.bedrag===undefined?'':r.bedrag}"> ${controleBadge('prijsregels[0].bedrag')}</td>
          <td><button class="icon-btn no-print" data-action="verwijder-prijsregel" data-i="${i}">✕</button></td>
        </tr>`).join('')}
      </tbody>
    </table>
    <button class="btn ghost small" id="btnPrijsregelToevoegen">+ Prijsregel toevoegen</button>
    <div class="hint">De verkoopprijs bij "Vul voor vanuit de calculatie" komt rechtstreeks uit de calculatie-stap; hier wordt niets herberekend.</div>`;
  document.getElementById('btnPrijsregelToevoegen').addEventListener('click', () => {
    antwoorden.prijsregels = antwoorden.prijsregels || [];
    antwoorden.prijsregels.push({ positie: '', bedrag: '' });
    render();
  });
}

function renderFactureringBetaling() {
  const el = document.getElementById('briefFacturering');
  const v = keuzes.velden.enkeleKeuze;
  el.innerHTML = `
    <div class="grid cols-2">
      <div class="field"><label>Facturering</label>${bouwSelect('facturering', (v.facturering||[]).map(o=>[o.waarde,o.label]), { leegLabel: '— kies —' })}</div>
      <div class="field"><label>Betaling</label>${bouwSelect('betaling', (v.betaling||[]).map(o=>[o.waarde,o.label]), { leegLabel: '— kies —' })}</div>
    </div>`;
}

function renderOndertekening() {
  const el = document.getElementById('briefOndertekening');
  el.innerHTML = `
    <div class="grid cols-2">
      <div class="field"><label>Ondertekenaar</label>${bouwSelect('ondertekenaar', keuzes.ondertekenaars.map(o => [o.id, o.naam]), { leegLabel: '— kies —' })}</div>
      <div class="field met-checkbox"><input type="checkbox" id="documentatie_bijgevoegd" ${antwoorden.documentatie_bijgevoegd?'checked':''}>
        <label for="documentatie_bijgevoegd" style="margin:0;">Documentatie van de apparatuur bijgevoegd</label></div>
    </div>`;
  document.getElementById('documentatie_bijgevoegd').addEventListener('change', e => zetVeld('documentatie_bijgevoegd', e.target.checked));
}

function render() {
  if (!keuzes) return;
  renderKlant(); renderKenmerken(); renderInstallaties(); renderSysteemOpties();
  renderTechspec(); renderWerkzaamheden(); renderPrijs(); renderFactureringBetaling(); renderOndertekening();
  CB.autosave();
  plannenHerberekening();
}

/* --------------------------------- events -------------------------------- */
function bindFormulier() {
  document.getElementById('stapBrief').addEventListener('input', e => {
    const t = e.target;
    if (t.dataset.veld && t.dataset.inst === undefined && t.dataset.prijsregel === undefined) {
      zetVeld(t.dataset.veld, t.value);
    } else if (t.dataset.inst !== undefined && t.dataset.veld) {
      const inst = antwoorden.installaties[Number(t.dataset.inst)];
      inst[t.dataset.veld] = t.value;
      if (t.dataset.veld === 'systeemsoort') render(); // type_buitendeel-veld moet in/uit beeld komen
      else { CB.autosave(); plannenHerberekening(); }
    } else if (t.dataset.prijsregel !== undefined && t.dataset.veld) {
      antwoorden.prijsregels[Number(t.dataset.prijsregel)][t.dataset.veld] = t.value === '' ? '' : t.value;
      CB.autosave(); plannenHerberekening();
    } else if (t.dataset.vlag) {
      zetVeld(t.dataset.vlag, t.checked);
    } else if (t.dataset.meervoudig) {
      const veld = t.dataset.meervoudig, waarde = t.dataset.waarde;
      const lijst = new Set(antwoorden[veld] || []);
      if (t.checked) lijst.add(waarde); else lijst.delete(waarde);
      zetVeld(veld, [...lijst]);
    }
  });
  document.getElementById('stapBrief').addEventListener('change', e => {
    if (e.target.tagName === 'SELECT' && e.target.dataset.veld && e.target.dataset.inst === undefined) {
      if (e.target.dataset.veld === 'klanttype') render(); // organisatieveld moet in/uit beeld komen
    }
  });
  document.getElementById('stapBrief').addEventListener('click', e => {
    if (e.target.dataset.action === 'verwijder-installatie') {
      antwoorden.installaties.splice(Number(e.target.dataset.i), 1);
      render();
    }
    if (e.target.dataset.action === 'verwijder-prijsregel') {
      antwoorden.prijsregels.splice(Number(e.target.dataset.i), 1);
      render();
    }
  });
  document.getElementById('btnInstallatieToevoegenBrief').addEventListener('click', () => {
    antwoorden.installaties = antwoorden.installaties || [];
    antwoorden.installaties.push({ id: nieuweInstallatieId() });
    render();
  });
  document.getElementById('btnVulVoorVanuitCalculatie').addEventListener('click', vulVoorVanuitCalculatie);
  document.getElementById('btnWordBestand').addEventListener('click', async () => {
    const respons = await fetch('/docx', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(antwoorden),
    });
    if (respons.headers.get('Content-Type').includes('json')) {
      const data = await respons.json();
      return CB.toast(data.fout || 'Kan geen Word-bestand maken.');
    }
    const blob = await respons.blob();
    const dispositie = respons.headers.get('Content-Disposition') || '';
    const naamMatch = dispositie.match(/filename="([^"]+)"/);
    const naam = naamMatch ? naamMatch[1] : 'brief.docx';
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = naam;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    CB.toast('Word-bestand gedownload: ' + naam);
  });
}

async function initBrief() {
  CB.laadscherm.zetStatus('Briefbibliotheek laden…');
  keuzes = await CB.getJSON('/keuzes');
  bindFormulier();
  render();
}

CB.brief = {
  get antwoorden() { return antwoorden; },
  heeftInhoud,
  vulAntwoorden(nieuw) {
    antwoorden = nieuw || {};
    if (antwoorden.installaties) {
      antwoorden.installaties = antwoorden.installaties.map(i => ({ id: i.id || nieuweInstallatieId(), ...i }));
    }
    controleInfo = [];
    laatstVerzonden = null;
    render();
  },
  klaar: null,
};

document.addEventListener('DOMContentLoaded', () => { CB.brief.klaar = initBrief(); });

})();
