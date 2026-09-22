"""Bewaakt de bewoording van de juridisch en commercieel bindende alinea's.

Deze teksten staan letterlijk in offertes die naar klanten gaan. Ze horen te
veranderen wanneer Schilt dat besluit, en niet per ongeluk bij het opschonen van
teksten.yaml of bij een zoek-en-vervang.

Faalt een test hieronder, stel dan eerst vast of de wijziging bedoeld is. Zo ja,
neem de nieuwe tekst hier over en noteer in analyse/vragen.md wie erover besloot.
Zo nee, draai de wijziging in analyse/teksten.yaml terug.
"""

import unittest
from pathlib import Path

from brieventool import laad

WORTEL = Path(__file__).resolve().parent.parent

# blok-id -> de tekst zoals die in de brief hoort te staan
VASTGELEGD = {
    'garantie_standaard':
        "Garantietermijn:\nDe garantietermijn binnen Nederland is 12 maanden op geleverde materialen en door ons uitgevoerde werkzaamheden na inbedrijfstellen. Op geleverde onderdelen geldt een aanvullende fabrieksgarantie. Defecten welke te wijten zijn aan derden vallen buiten de garantie.",
    'garantie_koelmachine':
        "Garantietermijn:\nGedurende 12 maanden na inbedrijfstelling op materiaal en arbeidsloon met een maximum van 18 maanden na aflevering (de kortste termijn is doorslaggevend).\nOp de compressor en MCHE condensorbatterijen geldt een aanvullende 24 maanden garantie op materiaal.",
    'algemene_voorwaarden':
        "Algemene voorwaarden:\nWij leveren volgens de algemene leverings- en betalingsvoorwaarden van de Koninklijke Metaalunie (Metaalunievoorwaarden), gedeponeerd ter griffie van de rechtbank te Rotterdam, zoals deze luiden volgens de laatstelijk aldaar neergelegde tekst, met uitsluiting van (alle) andere algemene voorwaarden. De voorwaarden worden u op verzoek toegezonden.",
    'aansprakelijkheid':
        "Aansprakelijkheid:\n- Indien wij bij u betonboringen uitvoeren, zullen deze met de uiterste zorgvuldigheid worden uitgevoerd. Business Unit Schilt Airconditioning is echter niet aansprakelijk voor het eventueel – onverhoopt – beschadigen van (leidingen in) vloeren of wanden.\n- Wij willen u erop attenderen geen apparatuur onder de binnenunits te plaatsen. Indien er wel apparatuur onder de binnenunits wordt geplaatst, is Business Unit Schilt Airconditioning niet aansprakelijk voor eventuele schade als gevolg van - onverhoopte - condenslekkages.",
    'kredietwaardigheid':
        "Kredietwaardigheid:\nNa ontvangst van een opdracht wordt door ons de kredietwaardigheid van de opdrachtgever getoetst bij onze kredietadviseurs. Indien dit advies daartoe aanleiding geeft, is het mogelijk dat er t.o.v. de in de offerte c.q. opdrachtbevestiging genoemde betalingscondities afwijkende condities overeengekomen dienen te worden.",
    'btw_exclusief':
        "De genoemde prijzen zijn exclusief 21% btw.",
    'btw_inclusief':
        "De genoemde prijzen zijn inclusief 21% btw.",
    'geldigheidsduur':
        "Deze aanbieding wordt 30 dagen na heden gestand gedaan, daarna komt deze te vervallen.",
    'privacy':
        "Wij maken u erop attent dat wij de persoonsgegevens die u ons heeft verstrekt en eventueel nog zult verstrekken, zullen verwerken op de manier zoals wij die in onze privacyverklaring hebben omschreven. Wij verwijzen u graag naar www.schiltbedrijven.nl/privacyverklaring voor meer informatie over de verwerking van uw persoonsgegevens en de rechten die u heeft.",
    # Facturering en betaling zijn twee losse keuzes; de tekst is dezelfde als
    # toen ze nog in een blok stonden, alleen op de regelovergang gesplitst.
    'facturering_vijftig_vijftig':
        "Facturering:\t- 1e termijn, 50% voorafgaande uitvoering werkzaamheden.\n\t\t- laatste termijn, 50% na oplevering.",
    'betaling_termijnen_particulier':
        "Betaling:\t- 1e termijn 2 werkdagen voorafgaande uitvoering werkzaamheden.\n\t\t- laatste termijn binnen 30 dagen na factuurdatum.",
    'betaling_30_dagen':
        "Betaling: binnen 30 dagen na de factuurdatum.",
    'meerprijs_condenspomp_zakelijk':
        "Indien het condenswater niet onder natuurlijk verloop weg kan, zal er gebruik gemaakt worden van een condenswaterpomp. De meerprijs hiervoor bedraagt € 220,- per stuk.",
    'meerprijs_condenspomp_particulier':
        "Indien het condenswater niet onder natuurlijk verloop weg kan, zal er gebruik gemaakt worden van een condenswaterpomp. De meerprijs hiervoor bedraagt € 260,- per stuk.",
    # ontbindingsrecht_particulier is op 17 september 2026 op verzoek van Lars
    # uit de bibliotheek gehaald (verouderde tekst); zie analyse/vragen.md.
}


class TestJuridischeTeksten(unittest.TestCase):
    maxDiff = None      # bij een verschil de hele tekst tonen, niet inkorten

    @classmethod
    def setUpClass(cls):
        cls.blokken = {b.id: b for b in laad(WORTEL).blokken}

    def test_bewoording_ongewijzigd(self):
        for blok_id, verwacht in VASTGELEGD.items():
            with self.subTest(blok_id):
                self.assertIn(blok_id, self.blokken, f"blok {blok_id} bestaat niet meer")
                self.assertEqual(
                    self.blokken[blok_id].tekst, verwacht,
                    f"de tekst van {blok_id} is gewijzigd; zie de uitleg boven in dit bestand",
                )

    def test_btw_blijft_gekoppeld_aan_klanttype(self):
        # Deze koppeling is in alle zeven uitgewerkte brieven bevestigd en mag
        # niet stilletjes omdraaien: particulier inclusief, zakelijk exclusief.
        self.assertIn("klanttype == 'zakelijk'", self.blokken["btw_exclusief"].voorwaarde)
        self.assertIn("klanttype == 'particulier'", self.blokken["btw_inclusief"].voorwaarde)

    def test_geldigheidsduur_blijft_dertig_dagen(self):
        self.assertIn("30 dagen", self.blokken["geldigheidsduur"].tekst)


if __name__ == "__main__":
    unittest.main()
