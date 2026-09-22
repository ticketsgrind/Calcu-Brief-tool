"""Toetst de voorgeselecteerde werkzaamheden tegen de bronbrieven.

De opsomming "De installatie is aangeboden inclusief" en "Niet tot onze
werkzaamheden behoren" staat woord voor woord in de sjablonen. Split,
multi-split, cassette en kanaal delen een lijst; VRF heeft een eigen lijst met
andere regels en een andere volgorde. Deze toets leest die lijsten uit de
bronbrieven zelf, zodat de tool niet stilletjes van de brief af gaat lopen.
"""

import re
import unittest
import zipfile
from pathlib import Path

import yaml

from brieventool import laad
from brieventool.samenstellen import stel_samen
from brieventool.sjabloon import schrijf_docx

WORTEL = Path(__file__).resolve().parent.parent

# De sets die het scherm voorselecteert; ze staan ook in ontwerp/prototype.html.
STANDAARD = {
    "inclusief": ["demontage", "montage", "bekabeling", "transport", "inbedrijfstelling"],
    "exclusief": ["bouwkundig", "sparingen", "betonboringen", "elektra_stopcontact",
                  "elektra_voeding", "elektra_voedingskabel", "regeltechniek",
                  "condensafvoerleiding", "plakplaat", "beplating"],
}
VRF = {
    "inclusief": ["demontage", "montage", "sturingsbekabeling", "flexibele_leidingen",
                  "starre_leidingen", "inbedrijfstelling"],
    "exclusief": ["koellast", "bouwkundig", "sparingen_uitgebreid", "elektra_alles",
                  "regeltechniek_bedraden", "kabelgoot", "waterzijdig", "luchttechniek",
                  "inregelen", "condensafvoerleiding_meervoud", "plakplaten",
                  "beplating_stucco", "transport_vergunningen", "hoogwerker"],
}


def uit_bronbrief(bestand):
    """De twee opsommingen uit een sjabloon, in de volgorde van de brief."""
    xml = zipfile.ZipFile(WORTEL / "bronbrieven" / bestand).read("word/document.xml").decode("utf-8")
    body = xml[xml.index("<w:body"):]
    # In de sjablonen staat hier en daar een vaste spatie waar een gewone hoort;
    # dat is een typefout in Word en geen verschil in de tekst.
    regels = ["".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p)).replace("\u00a0", " ").strip()
              for p in re.findall(r"<w:p\b[^>]*(?:/>|>.*?</w:p>)", body, re.S)]
    begin = next(n for n, r in enumerate(regels) if r.startswith("De installatie is aangeboden"))
    eind = next(n for n, r in enumerate(regels) if r.startswith("Totaalprijs"))
    return [r for r in regels[begin:eind] if r]


def brief_met(werk, systeemsoort):
    offerte = yaml.safe_load((WORTEL / "voorbeelden" / "zakelijk-cassette-meervoud.yaml")
                             .read_text(encoding="utf-8"))
    offerte["briefdatum"] = str(offerte["briefdatum"])
    offerte["werk_inclusief"] = werk["inclusief"]
    offerte["werk_exclusief"] = werk["exclusief"]
    offerte["installaties"] = [dict(offerte["installaties"][0], systeemsoort=systeemsoort)]
    brief = stel_samen(offerte, laad(WORTEL))
    return [a.tekst for sectie in ("werkzaamheden_inclusief", "werkzaamheden_exclusief")
            for a in brief.secties[sectie] if a.tekst.strip()]


def cursief_uit_bronbrief(bestand):
    """De schuingedrukte regels uit een sjabloon."""
    xml = zipfile.ZipFile(WORTEL / "bronbrieven" / bestand).read("word/document.xml").decode("utf-8")
    body = xml[xml.index("<w:body"):]
    uit = []
    for alinea in re.findall(r"<w:p\b[^>]*(?:/>|>.*?</w:p>)", body, re.S):
        for run in re.findall(r"<w:r\b.*?</w:r>", alinea, re.S):
            if re.search(r"<w:i/>|<w:i ", run):
                tekst = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", run)).replace("\u00a0", " ").strip()
                if tekst:
                    uit.append(tekst)
    return uit


class TestCursiefVolgtDeBronbrief(unittest.TestCase):
    """Wat in de bronbrief schuingedrukt staat, staat dat in onze brief ook."""

    def test_dezelfde_regels_zijn_cursief(self):
        offerte = yaml.safe_load((WORTEL / "voorbeelden" / "particulier-wand-enkelvoud.yaml")
                                 .read_text(encoding="utf-8"))
        offerte["briefdatum"] = str(offerte["briefdatum"])
        brief = stel_samen(offerte, laad(WORTEL))
        onze = {a.tekst for alineas in brief.secties.values() for a in alineas if a.cursief}
        alle = {a.tekst for alineas in brief.secties.values() for a in alineas if a.tekst.strip()}

        bron = cursief_uit_bronbrief("wand enkelvoud.dotx")
        # Wat de bronbrief cursief zet en in onze brief voorkomt, hoort bij ons
        # ook cursief te zijn. De functieregels vallen af omdat het sjabloon er
        # drie toont en onze brief er een kiest; de aanloopzin "Voor de
        # prijsvorming zijn wij er van uitgegaan dat:" valt af omdat de
        # spelling op verzoek van Lars is rechtgezet naar "ervan" (17 september
        # 2026) en daardoor niet meer letterlijk gelijk is aan de bronbrief.
        gedeeld = [r for r in bron if r in alle]
        self.assertEqual(len(gedeeld), 3, gedeeld)
        self.assertTrue(gedeeld[0].startswith("de (werk)locatie"), gedeeld)
        for regel in gedeeld:
            self.assertIn(regel, onze, f"in de bronbrief cursief, bij ons niet: {regel!r}")
        # En de functie van de gekozen ondertekenaar, die de bronbrief ook
        # schuingedrukt zet.
        self.assertIn("Technisch Commercieel Adviseur", onze)


class TestWitruimteVolgtDeBronbrief(unittest.TestCase):
    """Elke regel die in allebei voorkomt heeft evenveel lege regels erachter.

    Zo loopt de opmaak niet stilletjes weg van de brief die Schilt al jaren
    verstuurt. Een paar plekken wijken bewust af: het sjabloon zet twee lege
    regels voor "Levering:" en voor "Aansprakelijkheid:" waar overal elders er
    een staat, de functieregels van de drie ondertekenaars staan in het
    sjabloon onder elkaar terwijl onze brief er een kiest, en de twee koppen
    van de werkzaamhedenlijst krijgen sinds 17 september 2026 op verzoek van
    Lars een lege regel eronder terwijl de bronbrief daar niets zet.
    """

    UITZONDERINGEN = {
        "de werkzaamheden tijdens normale werktijden (kantooruren) kunnen worden uitgevoerd.",
        "De garantietermijn binnen Nederland is 12 maanden op geleverde materialen en door ons "
        "uitgevoerde werkzaamheden na inbedrijfstellen. Op geleverde onderdelen geldt een "
        "aanvullende fabrieksgarantie. Defecten welke te wijten zijn aan derden vallen buiten "
        "de garantie.",
        "Technisch Commercieel Adviseur",
        "De installatie is aangeboden inclusief:",
        "Niet tot onze werkzaamheden behoren:",
    }

    def witregels(self, paragrafen):
        uit = {}
        for nummer, tekst in enumerate(paragrafen):
            if not tekst:
                continue
            leeg, volgende = 0, nummer + 1
            while volgende < len(paragrafen) and not paragrafen[volgende]:
                leeg += 1
                volgende += 1
            uit[tekst] = leeg
        return uit

    def paragrafen(self, pad):
        xml = zipfile.ZipFile(pad).read("word/document.xml").decode("utf-8")
        body = xml[xml.index("<w:body"):]
        return ["".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p)).replace("\u00a0", " ").strip()
                for p in re.findall(r"<w:p\b[^>]*(?:/>|>.*?</w:p>)", body, re.S)]

    def test_zelfde_witruimte_als_wand_enkelvoud(self):
        import tempfile
        offerte = yaml.safe_load((WORTEL / "voorbeelden" / "particulier-wand-enkelvoud.yaml")
                                 .read_text(encoding="utf-8"))
        offerte["briefdatum"] = str(offerte["briefdatum"])
        with tempfile.TemporaryDirectory() as tijdelijk:
            doel = Path(tijdelijk) / "brief.docx"
            schrijf_docx(stel_samen(offerte, laad(WORTEL)),
                         WORTEL / "sjablonen" / "brief.docx", doel)
            onze = self.witregels(self.paragrafen(doel))
        bron = self.witregels(self.paragrafen(WORTEL / "bronbrieven" / "wand enkelvoud.dotx"))

        gedeeld = [t for t in onze if t in bron]
        self.assertGreater(len(gedeeld), 40, "te weinig gedeelde regels om iets te toetsen")
        anders = [(t, bron[t], onze[t]) for t in gedeeld
                  if bron[t] != onze[t] and t not in self.UITZONDERINGEN]
        self.assertEqual(anders, [], "witruimte wijkt af van de bronbrief")


class TestWerkzaamheden(unittest.TestCase):
    def test_standaardlijst_is_die_van_de_bronbrief(self):
        self.assertEqual(brief_met(STANDAARD, "splitsystem"),
                         uit_bronbrief("wand enkelvoud.dotx"))

    def test_dezelfde_lijst_voor_cassette(self):
        # cassette, kanaal en multi-split hebben in de sjablonen dezelfde lijst
        self.assertEqual(uit_bronbrief("cassette meervoud.dotx"),
                         uit_bronbrief("wand enkelvoud.dotx"))
        self.assertEqual(brief_met(STANDAARD, "multi-splitsystem"),
                         uit_bronbrief("cassette meervoud.dotx"))

    def test_vrf_heeft_een_eigen_lijst(self):
        self.assertEqual(brief_met(VRF, "vrf"), uit_bronbrief("VRF.dotx"))

    def test_de_twee_lijsten_verschillen_echt(self):
        self.assertNotEqual(brief_met(VRF, "vrf"), brief_met(STANDAARD, "splitsystem"))

    def test_het_scherm_kan_elke_regel_aanbieden(self):
        # Het scherm (scherm/brief.js) hardcodeert geen eigen lijst en kiest
        # ook niets voor: het rendert een checkbox voor elke waarde die
        # bibliotheek.velden() teruggeeft voor werk_inclusief/werk_exclusief
        # (zie renderWerkzaamheden in scherm/brief.js). Het scherm kan dus
        # nooit achterlopen zolang elke regel hierboven ook echt in die
        # afgeleide vocabulaire zit -- dat toetst deze test.
        velden = laad(WORTEL).velden()
        aangeboden_inclusief = {w for w, _ in velden.meervoudige_keuze.get("werk_inclusief", [])}
        aangeboden_exclusief = {w for w, _ in velden.meervoudige_keuze.get("werk_exclusief", [])}
        for naam, set_ in [("STANDAARD", STANDAARD), ("VRF", VRF)]:
            for sleutel in set_["inclusief"]:
                self.assertIn(sleutel, aangeboden_inclusief, f"{sleutel} ({naam}) niet aanbiedbaar in het scherm")
            for sleutel in set_["exclusief"]:
                self.assertIn(sleutel, aangeboden_exclusief, f"{sleutel} ({naam}) niet aanbiedbaar in het scherm")


if __name__ == "__main__":
    unittest.main()
