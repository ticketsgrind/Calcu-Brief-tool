"""Toetst de laag die het Word-bestand schrijft.

De nadruk ligt op het briefpapier. De brief moet niet alleen de juiste tekst
bevatten, maar ook de briefkop met de Schilt-gegevens rechtsboven op de eerste
pagina, de drie voetteksten en alle afbeeldingen. Dat gaat stil mis: een
Word-bestand dat een namespace kwijtraakt opent Word als beschadigd, en een
ontbrekende titlePg laat de hele eerste pagina anders opmaken.
"""

import re
import unittest
import zipfile
from pathlib import Path

import yaml

from brieventool import laad, stel_samen
from brieventool.sjabloon import (KOPSECTIES, PARAGRAAFTAG, context,
                                  schrijf_docx, tabs_naar_word)

WORTEL = Path(__file__).resolve().parent.parent
BRON = WORTEL / "bronbrieven" / "wand enkelvoud.dotx"
SJABLOON = WORTEL / "sjablonen" / "brief.docx"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def brief(naam="particulier-wand-enkelvoud.yaml"):
    offerte = yaml.safe_load((WORTEL / "voorbeelden" / naam).read_text(encoding="utf-8"))
    return stel_samen(offerte, laad(WORTEL))


def document_van(pad):
    with zipfile.ZipFile(pad) as z:
        return z.read("word/document.xml").decode("utf-8"), set(z.namelist())


class BriefpapierMixin:
    """De controles die voor het sjabloon én voor een gemaakte brief gelden."""

    def test_alle_namespaces_zijn_bewaard(self):
        # Een XML-lezer die het document opnieuw wegschrijft hernoemt prefixen
        # die hij niet kent. mc:Ignorable verwijst er dan naar prefixen die niet
        # meer bestaan en Word beschouwt het bestand als beschadigd.
        bron, _ = document_van(BRON)
        self.assertEqual(self._namespaces(self.xml), self._namespaces(bron))

    def test_ignorable_verwijst_naar_bestaande_prefixen(self):
        kop = re.search(r"<w:document\b[^>]*>", self.xml).group(0)
        genoemd = re.search(r'Ignorable="([^"]*)"', kop)
        self.assertIsNotNone(genoemd, "mc:Ignorable ontbreekt")
        ontbrekend = set(genoemd.group(1).split()) - self._namespaces(self.xml)
        self.assertEqual(ontbrekend, set(), f"niet gedeclareerd: {sorted(ontbrekend)}")

    def test_briefkop_rechtsboven_op_de_eerste_pagina(self):
        # headerReference type="first" wijst naar header1.xml met de
        # Schilt-gegevens; titlePg zet aan dat pagina 1 die kop gebruikt.
        self.assertIn('w:type="first"', self.xml)
        self.assertRegex(self.xml, r'<w:headerReference[^>]*w:type="first"')
        self.assertIn("<w:titlePg", self.xml,
                      "zonder titlePg krijgt pagina 1 de gewone kop en verdwijnt de briefkop")

    def test_alle_drie_de_voetteksten(self):
        soorten = set(re.findall(r'<w:footerReference[^>]*w:type="(\w+)"', self.xml))
        self.assertEqual(soorten, {"even", "default", "first"})

    def test_kop_en_voetteksten_zitten_in_het_bestand(self):
        onderdelen = {n for n in self.namen if re.match(r"word/(header|footer)\d*\.xml", n)}
        self.assertEqual(len(onderdelen), 4, f"gevonden: {sorted(onderdelen)}")

    def test_afbeeldingen_zijn_meegekomen(self):
        _, bronnamen = document_van(BRON)
        eigen = {n for n in self.namen if n.startswith("word/media/")}
        origineel = {n for n in bronnamen if n.startswith("word/media/")}
        self.assertEqual(eigen, origineel)

    def test_relaties_van_kop_en_voet_zijn_intact(self):
        # Zonder de rels-bestanden verwijst de briefkop naar niets en toont Word
        # een leeg kader in plaats van het logo.
        self.assertIn("word/_rels/document.xml.rels", self.namen)
        self.assertIn("word/_rels/header1.xml.rels", self.namen)

    def test_paginaformaat_en_marges_zijn_bewaard(self):
        self.assertIn("<w:sectPr", self.xml)
        self.assertIn("<w:pgSz", self.xml)
        self.assertIn("<w:pgMar", self.xml)

    def test_stijlen_en_nummering_zijn_meegekomen(self):
        self.assertIn("word/styles.xml", self.namen)
        self.assertIn("word/numbering.xml", self.namen)

    def test_is_een_document_en_geen_sjabloon(self):
        # Een .dotx opent Word als "nieuw document op basis van".
        with zipfile.ZipFile(self.pad) as z:
            types = z.read("[Content_Types].xml").decode("utf-8")
        self.assertIn("wordprocessingml.document.main+xml", types)
        self.assertNotIn("wordprocessingml.template.main+xml", types)

    @staticmethod
    def _namespaces(xml):
        kop = re.search(r"<w:document\b[^>]*>", xml)
        return set(re.findall(r"xmlns:([A-Za-z0-9]+)=", kop.group(0) if kop else ""))


class TestSjabloon(BriefpapierMixin, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pad = SJABLOON
        cls.xml, cls.namen = document_van(cls.pad)

    def test_sjabloon_bestaat(self):
        self.assertTrue(self.pad.is_file(), "draai eerst: python3 tools/maak_sjabloon.py")

    def test_elke_lus_is_gesloten(self):
        tekst = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", self.xml))
        self.assertEqual(tekst.count("{%p for"), tekst.count("{%p endfor %}"))
        self.assertEqual(tekst.count("{%p if"), tekst.count("{%p endif %}"))

    def test_verwijst_alleen_naar_bestaande_secties(self):
        tekst = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", self.xml))
        genoemd = set(re.findall(r"secties\.(\w+)", tekst))
        bestaand = {b.sectie for b in laad(WORTEL).blokken}
        self.assertTrue(genoemd <= bestaand, f"onbekende secties: {genoemd - bestaand}")


class TestGemaakteBrief(BriefpapierMixin, unittest.TestCase):
    """Schrijft echt een .docx en leest hem terug."""

    voorbeeld = "zakelijk-cassette-meervoud.yaml"

    @classmethod
    def setUpClass(cls):
        import tempfile
        cls.map = tempfile.TemporaryDirectory()
        cls.pad = schrijf_docx(brief(cls.voorbeeld),
                               SJABLOON, Path(cls.map.name) / "brief.docx")
        cls.xml, cls.namen = document_van(cls.pad)

    @classmethod
    def tearDownClass(cls):
        cls.map.cleanup()

    def regels(self):
        uit = []
        for alinea in re.findall(r"<w:p\b[^>]*/>|<w:p\b.*?</w:p>", self.xml, re.S):
            delen = re.findall(r"<w:t[^>]*>([^<]*)</w:t>|(<w:tab/>)", alinea)
            uit.append("".join(t or "\t" for t, _ in
                               [(a, b) for a, b in delen]))
        return uit

    def test_geen_sjabloontags_meer_over(self):
        tekst = "".join(self.regels())
        self.assertNotIn("{{", tekst)
        self.assertNotIn("{%", tekst)

    def test_witregels_tussen_de_secties(self):
        # Een zelfsluitende <w:p /> werd eerder door het tagpatroon opgeslokt,
        # waardoor de brief één doorlopend blok tekst werd.
        self.assertGreater(len([r for r in self.regels() if not r.strip()]), 10)

    def test_tabs_zijn_word_tabs_geworden(self):
        losse = [t for t in re.findall(r"<w:t[^>]*>([^<]*)</w:t>", self.xml) if "\t" in t]
        self.assertEqual(losse, [], "er staan nog tabtekens in de tekst")
        self.assertIn("<w:tab/>", self.xml)

    def test_betreft_en_termijnen_zijn_uitgelijnd(self):
        regels = self.regels()
        self.assertTrue(any(r.startswith("Betreft\t") for r in regels))
        self.assertTrue(any(r.startswith("\t\t") for r in regels), "termijnen niet ingesprongen")

    def test_opsommingen_hebben_een_streepje(self):
        # De stijl Lijstalinea zorgt alleen voor inspringing; het streepje komt
        # uit de verwijzing naar een lijstdefinitie in numbering.xml.
        for alinea in re.findall(r"<w:p\b.*?</w:p>", self.xml, re.S):
            if "betonboringen, hak-" in alinea:
                self.assertIn('w:val="Lijstalinea"', alinea)
                self.assertIn("<w:numPr>", alinea,
                              "zonder numPr staat de regel ingesprongen maar zonder streepje")
                return
        self.fail("de opsommingsregel is niet gevonden")

    def test_evenveel_opsommingstekens_als_opsommingsregels(self):
        verwacht = sum(1 for a in brief("zakelijk-cassette-meervoud.yaml").alle_alineas
                       if a.stijl == "opsomming")
        self.assertEqual(self.xml.count("<w:numPr>"), verwacht)
        self.assertGreater(verwacht, 5)

    def _blokken(self, hoeveel):
        """De eerste gevulde regels met het aantal lege regels erachter."""
        regels = self.regels()
        uit, nummer = [], 0
        while nummer < len(regels) and len(uit) < hoeveel:
            if regels[nummer].strip():
                volgende = nummer + 1
                while volgende < len(regels) and not regels[volgende].strip():
                    volgende += 1
                uit.append((regels[nummer].split("\t")[0].strip(), volgende - nummer - 1))
                nummer = volgende
            else:
                nummer += 1
        return uit

    def test_de_briefkop_heeft_de_nagemeten_witruimte(self):
        """Het adresblok aaneengesloten, zes lege regels, dan de betreft-regel.

        Daarna een lege regel, "Meerkerk <datum>", een lege regel, en project
        no. en Ref. weer tegen elkaar aan. Deze telling staat in het sjabloon en
        wordt door de voorvertoning nagetekend; ze is nagemeten aan de
        bronbrieven.
        """
        blokken = self._blokken(8)
        betreft = next(n for n, (tekst, _) in enumerate(blokken) if tekst == "Betreft")
        adres = blokken[:betreft]
        self.assertGreater(len(adres), 2, "geen adresblok gevonden")
        self.assertEqual([leeg for _, leeg in adres], [0] * (len(adres) - 1) + [6])
        self.assertEqual([leeg for _, leeg in blokken[betreft:betreft + 4]], [1, 1, 0, 3])
        self.assertEqual(blokken[betreft + 1][0], "Meerkerk")
        self.assertTrue(blokken[betreft + 2][0].startswith("Ons project no."))
        self.assertTrue(blokken[betreft + 3][0].startswith("Ref."))

    def test_vier_lege_regels_boven_het_adres(self):
        regels = self.regels()
        eerste = next(n for n, r in enumerate(regels) if r.strip())
        self.assertEqual(eerste, 4, "het adresblok staat niet op de nagemeten hoogte")

    def test_witregel_tussen_de_alineas(self):
        """Na elke gewone alinea hoort een lege alinea.

        Vier uitzonderingen, alle vier uit de bronbrieven: opsommingsregels
        staan tegen elkaar aan, een met tabs uitgelijnde vervolgregel staat
        direct onder de regel waar hij bij hoort, tekst met stijl "letterlijk"
        -- de ondertekening en de technische specificaties -- bepaalt zijn eigen
        witruimte, en de werkzaamhedenlijst staat als een blok tegen elkaar aan.
        De briefkop telt niet mee: het adresblok en de regels met project no. en
        Ref. horen aaneengesloten.
        """
        alineas = brief(self.voorbeeld).alle_alineas
        letterlijk = {a.tekst for a in alineas if a.letterlijk}
        werkzaamheden = {a.tekst for naam in ("werkzaamheden_inclusief",
                                              "werkzaamheden_exclusief")
                         for a in brief(self.voorbeeld).secties[naam]}
        paren = self._opeenvolgende_gevulde_alineas()
        self.assertGreater(len(paren), 3, "geen aaneengesloten alinea's gevonden")
        for huidige, volgende in paren:
            vervolgregel = volgende["tekst"].startswith("\t")
            beide_opsomming = huidige["opsomming"] and volgende["opsomming"]
            eigen_witruimte = huidige["tekst"] in letterlijk
            in_de_lijst = huidige["tekst"] in werkzaamheden
            self.assertTrue(
                vervolgregel or beide_opsomming or eigen_witruimte or in_de_lijst,
                f"geen witregel tussen {huidige['tekst'][:44]!r} en {volgende['tekst'][:44]!r}",
            )

    def _opeenvolgende_gevulde_alineas(self):
        alineas = []
        for xml in re.findall(r"<w:p\b[^>]*/>|<w:p\b.*?</w:p>", self.xml, re.S):
            delen = re.findall(r"<w:t[^>]*>([^<]*)</w:t>|(<w:tab/>)", xml)
            alineas.append({"tekst": "".join(t or "\t" for t, _ in delen),
                            "opsomming": "<w:numPr>" in xml})
        begin = next(n for n, a in enumerate(alineas) if a["tekst"].startswith("Geachte"))
        alineas = alineas[begin:]
        return [(a, b) for a, b in zip(alineas, alineas[1:])
                if a["tekst"].strip() and b["tekst"].strip()]

    def test_cursief_staat_waar_de_bronbrief_hem_zet(self):
        """De schuingedrukte regels zijn die van de bronbrief.

        Nagemeten in alle sjablonen en de verstuurde brieven: de uitgangspunten
        voor de prijsvorming, de garantietekst en de functie onder de
        ondertekening. Koppen zijn nergens cursief -- die zijn onderstreept of
        vet -- en de rest van de brief staat recht.
        """
        cursief, recht = [], []
        for alinea in re.findall(r"<w:p\b[^>]*(?:/>|>.*?</w:p>)", self.xml, re.S):
            tekst = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", alinea)).strip()
            if not tekst:
                continue
            (cursief if "<w:i/>" in alinea else recht).append(tekst)

        self.assertTrue(any(t.startswith("Voor de prijsvorming") for t in cursief), cursief)
        self.assertTrue(any(t.startswith("de (werk)locatie") for t in cursief), cursief)
        self.assertTrue(any(t.startswith("De garantietermijn") for t in cursief), cursief)
        self.assertTrue(any(t == "Technisch Commercieel Manager" for t in cursief), cursief)
        self.assertIn("Zie bijlage.", cursief)
        # De kop erboven blijft onderstreept resp. vet, niet cursief.
        self.assertIn("Garantietermijn:", recht)
        self.assertIn("TECHNISCHE SPECIFICATIES", recht)
        self.assertTrue(any(t.startswith("De totaalprijs") for t in recht), recht)

    def test_geen_enkele_kop_is_cursief(self):
        for alinea in re.findall(r"<w:p\b[^>]*(?:/>|>.*?</w:p>)", self.xml, re.S):
            tekst = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", alinea)).strip()
            if "<w:i/>" in alinea:
                self.assertNotIn('<w:u w:val="single"/>', alinea, tekst)
                self.assertNotIn("<w:b/>", alinea, tekst)

    def test_het_bedrag_staat_vet_en_de_zin_niet(self):
        for alinea in re.findall(r"<w:p\b.*?</w:p>", self.xml, re.S):
            if "De totaalprijs compleet" not in alinea:
                continue
            delen = re.findall(r"<w:r\b.*?</w:r>", alinea, re.S)
            vet = [d for d in delen if "<w:b/>" in d]
            gewoon = [d for d in delen if "<w:b/>" not in d and "<w:t" in d]
            self.assertTrue(vet, "het bedrag staat niet vet")
            self.assertTrue(gewoon, "de hele regel staat vet")
            self.assertIn("netto.", "".join(vet))
            self.assertIn("De totaalprijs", "".join(gewoon))
            self.assertNotIn("€", "".join(gewoon))
            return
        self.fail("de totaalprijsregel is niet gevonden")

    def test_de_condenswaterpompregel_staat_niet_vet(self):
        for alinea in re.findall(r"<w:p\b.*?</w:p>", self.xml, re.S):
            if "condenswater" in alinea:
                self.assertNotIn("<w:b/>", alinea)
                return
        self.fail("de condenswaterpompregel is niet gevonden")

    # Nagemeten in bronbrieven/wand enkelvoud.dotx en de uitgewerkte brieven.
    OPMAAK = {
        "Wij specificeren onze aanbieding als volgt:": "onderstreept",
        "De installatie is aangeboden inclusief:": "onderstreept",
        "Niet tot onze werkzaamheden behoren:": "onderstreept",
        "Totaalprijs:": "onderstreept",
        "Levering:": "onderstreept",
        "Facturering en betaling:": "onderstreept",
        "Kredietwaardigheid:": "onderstreept",
        "Algemene voorwaarden:": "onderstreept",
        "Garantietermijn:": "onderstreept",
        "Aansprakelijkheid:": "onderstreept",
        "Aanbieding": "vet",
        "Tot slot": "vet",
        "TECHNISCHE SPECIFICATIES": "vet",
        # "Zie bijlage." staat sindsdien cursief, niet vet; zie
        # test_cursief_staat_waar_de_bronbrief_hem_zet hieronder.
        # Een aanloopzin, geen kopje: die blijft gewoon.
        "Voor de prijsvorming zijn wij ervan uitgegaan dat:": "gewoon",
    }

    def test_kopjes_hebben_de_opmaak_uit_de_bronbrief(self):
        gevonden = {}
        for alinea in re.findall(r"<w:p\b.*?</w:p>", self.xml, re.S):
            tekst = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", alinea)).strip()
            if tekst not in self.OPMAAK:
                continue
            gevonden[tekst] = ("vet" if "<w:b/>" in alinea else
                               "onderstreept" if "<w:u " in alinea else "gewoon")
        ontbreekt = set(self.OPMAAK) - set(gevonden) - {"Zie bijlage.", "TECHNISCHE SPECIFICATIES"}
        self.assertEqual(ontbreekt, set(), f"niet in de brief: {sorted(ontbreekt)}")
        for tekst, verwacht in gevonden.items():
            with self.subTest(tekst):
                self.assertEqual(verwacht, self.OPMAAK[tekst])

    def test_kopjes_met_dubbele_punt_zijn_niet_vet(self):
        # De opdrachtgever wil ze onderstreept, niet vet.
        for alinea in re.findall(r"<w:p\b.*?</w:p>", self.xml, re.S):
            tekst = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", alinea)).strip()
            if self.OPMAAK.get(tekst) == "onderstreept":
                self.assertNotIn("<w:b/>", alinea, tekst)

    def test_betreft_label_is_klein_en_de_inhoud_vet(self):
        for alinea in re.findall(r"<w:p\b.*?</w:p>", self.xml, re.S):
            if not "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", alinea)).startswith("Betreft"):
                continue
            runs = re.findall(r"<w:r\b.*?</w:r>", alinea, re.S)
            label = next(r for r in runs if "Betreft" in r)
            inhoud = next(r for r in runs if "Airconditioning" in r)
            self.assertIn('<w:sz w:val="14"/>', label, "het label staat niet op 7 punten")
            self.assertNotIn("<w:b/>", label, "het label hoort niet vet te zijn")
            self.assertIn("<w:b/>", inhoud, "de inhoud hoort vet te zijn")
            self.assertIn("<w:tab/>", alinea)
            return
        self.fail("de betreft-regel is niet gevonden")

    def test_meerkerk_label_is_klein_en_de_datum_niet_vet(self):
        for alinea in re.findall(r"<w:p\b.*?</w:p>", self.xml, re.S):
            if not "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", alinea)).startswith("Meerkerk"):
                continue
            self.assertIn('<w:sz w:val="14"/>', alinea)
            self.assertNotIn("<w:b/>", alinea)
            self.assertIn("<w:tab/>", alinea)
            return
        self.fail("de regel met plaats en datum is niet gevonden")

    def test_de_brief_bevat_de_juiste_inhoud(self):
        tekst = "\n".join(self.regels())
        for verwacht in ["Voorbeeld Vastgoed B.V.", "exclusief 21% btw", "€ 24.750,- netto",
                         "Kredietwaardigheid:", "De binnenunits zijn", "John van de Weetering"]:
            self.assertIn(verwacht, tekst)


class TestContext(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = context(brief())

    def test_romp_slaat_de_briefkop_over(self):
        namen = [n for n, a in brief().secties.items() if a and n not in KOPSECTIES]
        self.assertEqual(len(self.c["romp"]), len(namen))

    def test_romp_bevat_geen_lege_secties(self):
        for sectie in self.c["romp"]:
            self.assertTrue(sectie)

    def test_romp_houdt_de_volgorde_aan(self):
        self.assertTrue(self.c["romp"][0][0].tekst.startswith("Naar aanleiding"))

    def test_geen_functies_in_de_context(self):
        for waarde in self.c.values():
            self.assertFalse(callable(waarde))

    def test_losse_velden_blijven_beschikbaar(self):
        self.assertEqual(self.c["referentie"], "NV/LH/SA35923")
        self.assertEqual(self.c["ondertekenaar"]["naam"], "Nick Vervoorn")


class TestParagraaftag(unittest.TestCase):
    def uitpakken(self, xml):
        return PARAGRAAFTAG.sub(lambda m: "{%" + m.group(1) + "%}", xml)

    def test_tagalinea_verdwijnt_de_tag_blijft(self):
        self.assertEqual(
            self.uitpakken("<w:p><w:r><w:t>{%p endfor %}</w:t></w:r></w:p>"), "{% endfor %}")

    def test_zelfsluitende_lege_alinea_blijft_staan(self):
        # <w:p /> heeft geen </w:p>; zonder uitsluiting zocht het patroon door
        # in de volgende alinea en verdween de witregel ertussen.
        xml = '<w:p /><w:p><w:r><w:t>{%p endfor %}</w:t></w:r></w:p>'
        self.assertEqual(self.uitpakken(xml), "<w:p />{% endfor %}")

    def test_gewone_alinea_blijft_ongemoeid(self):
        xml = "<w:p><w:r><w:t>Geachte heer Jansen,</w:t></w:r></w:p>"
        self.assertEqual(self.uitpakken(xml), xml)

    def test_alinea_met_gewone_plaatshouder_blijft_staan(self):
        xml = "<w:p><w:r><w:t>{{ a.tekst }}</w:t></w:r></w:p>"
        self.assertEqual(self.uitpakken(xml), xml)


class TestTabs(unittest.TestCase):
    def test_tab_wordt_een_word_tab(self):
        uit = tabs_naar_word('<w:t xml:space="preserve">Betreft\tAirconditioning</w:t>')
        self.assertEqual(
            uit, '<w:t xml:space="preserve">Betreft</w:t><w:tab/>'
                 '<w:t xml:space="preserve">Airconditioning</w:t>')

    def test_meerdere_tabs_achter_elkaar(self):
        uit = tabs_naar_word('<w:t>\t\t70% bij aanvang</w:t>')
        self.assertEqual(uit, '<w:tab/><w:tab/><w:t xml:space="preserve">70% bij aanvang</w:t>')

    def test_tekst_zonder_tabs_blijft_ongemoeid(self):
        xml = "<w:t>Geachte heer Jansen,</w:t>"
        self.assertEqual(tabs_naar_word(xml), xml)

    def test_spaties_blijven_behouden(self):
        uit = tabs_naar_word("<w:t>Facturering:\t30% bij opdracht </w:t>")
        self.assertIn('xml:space="preserve">30% bij opdracht </w:t>', uit)


if __name__ == "__main__":
    unittest.main()
