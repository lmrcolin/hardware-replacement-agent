from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from advisor.models import Category, CompatibilityLevel, RecommendationResponse

pytestmark = pytest.mark.integration
APP_DIR = Path(__file__).resolve().parents[2] / "app"
APP = APP_DIR / "streamlit_app.py"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "responses"
OFFICIAL = (
    "Necesito una tarjeta de red 100 Gigabit Ethernet con soporte RDMA y offload de IPsec. "
    "Usábamos la Intel E810 pero ya no la encuentro"
)


def search(at: AppTest, text: str) -> AppTest:
    at.text_input(key="q").set_value(text)
    at.button(key="search").click().run()
    assert not at.exception
    return at


def ask(text: str, agent: str = "Real (catálogo + datasheets)") -> AppTest:
    at = AppTest.from_file(str(APP), default_timeout=120).run()
    assert not at.exception
    at.radio(key="agent").set_value(agent).run()
    return search(at, text)


def markdown(at: AppTest) -> str:
    return " ".join(m.value for m in at.markdown)


def test_official_case_shows_ranked_substitutes_and_original_card() -> None:
    at = ask(OFFICIAL)
    assert [s.value for s in at.subheader][:2] == ["1. MCX75310AAS-NEAT", "2. BCM57508"]
    assert "Pieza original: E810-CQDA2" in markdown(at) and "DISCONTINUED" in markdown(at)
    assert "Mejor <span>compatibilidad</span>" in markdown(at)  # only on the first card
    assert markdown(at).count('class="choice"') == 1
    assert len(at.dataframe) == 2  # spec comparison per recommendation


def test_clarification_suggests_part_for_typo() -> None:
    at = ask("Reemplazo para la E81O-CQDA2")
    assert any("E810-CQDA2" in i.value for i in at.info)
    assert not at.subheader


def test_a100_explains_blocked_successor() -> None:
    at = ask("Necesito reemplazar la A100")
    assert "H100-SXM5 como sucesor" in markdown(at) and not at.subheader


def test_example_link_and_recent_searches() -> None:
    at = AppTest.from_file(str(APP), default_timeout=120).run()
    at.button(key="ex-DAQ descontinuada").click().run()
    assert at.text_input(key="q").value == "Necesito reemplazar la USB-2627"
    search(at, "Busco una GPU de 80GB")
    assert at.button(key="hist-0") and at.button(key="hist-1")  # both searches kept
    at.button(key="hist-0").click().run()  # back to the DAQ search
    assert not at.exception
    assert next(s.value for s in at.subheader) == "1. USB-2633"


def test_landing_tiles_search_a_replacement() -> None:
    at = AppTest.from_file(str(APP), default_timeout=120).run()
    assert "Piezas del catálogo que necesitan reemplazo" in markdown(at)
    part = "E810-CQDA2"
    at.button(key=f"pick-{part}").click().run()
    assert not at.exception
    assert next(s.value for s in at.subheader) == "1. MCX75310AAS-NEAT"


def test_mock_agent_still_available() -> None:
    at = ask("Necesito una NIC 100GbE con RDMA", agent="Simulado (fixtures)")
    assert any("SYN-NIC-200" in s.value for s in at.subheader)


def test_unknown_candidates_have_their_own_section() -> None:
    at = ask("Necesito reemplazar el Arm Cortex-A78")
    assert "Posibles, sin datos suficientes" in markdown(at)
    assert "Sustitutos recomendados" not in markdown(at)
    assert [s.value for s in at.subheader] == ["1. w9-3595X"]


def test_filters_only_hide_never_rerank() -> None:
    sys.path.insert(0, str(APP_DIR))
    from components.render import Filters, all_options

    response = RecommendationResponse.model_validate_json(
        (FIXTURES / "replacement_found.json").read_text(encoding="utf-8")
    )
    options = all_options(response)
    assert all(Filters().keep(o) for o in options)
    first = options[0]
    by_level = Filters(levels=frozenset({first.compatibility.level}))
    kept = [o for o in options if by_level.keep(o)]
    assert kept[0] is first and [o.rank for o in kept] == sorted(o.rank for o in kept)
    other = next(c for c in Category if c is not first.commercial.category)
    assert not Filters(category=other).keep(first)
    assert not Filters(levels=frozenset({CompatibilityLevel.INCOMPATIBLE})).keep(first)


def _images():  # type: ignore[no-untyped-def]
    sys.path.insert(0, str(APP_DIR))
    from components import images

    return images


def test_every_product_gets_an_illustration_matching_its_form_factor() -> None:
    import base64
    import xml.etree.ElementTree as ET

    from advisor.pipeline import load_or_build

    images = _images()
    products = {p.part_number: p for p in load_or_build().products}
    expected = {
        "A100-SXM4-80GB": "gpu_module",
        "RTX-4090": "gpu_card",
        "WUS4C6464DSP3X5": "ssd_u2",
        "MZ-V9P2T0": "ssd_m2",
        "Cortex-A78": "ip_die",
        "USB-2627": "daq",
        "AD7606": "qfp",
        "E810-CQDA2": "nic",
        "H3A8G32AMR": "hbm",
    }
    assert {pn: images.kind(products[pn]) for pn in expected} == expected
    for product in products.values():
        svg = images.illustration_svg(product)
        ET.fromstring(svg)  # well-formed
        assert product.part_number[:13] in svg
        src, is_photo = images.image_source(product)
        if is_photo:  # every bundled photo carries its attribution
            assert images.photo_credit(product.part_number) is not None
        else:
            assert base64.b64decode(src.split(",", 1)[1]).decode() == svg


def test_bundled_photos_are_free_licensed_and_attributed() -> None:
    images = _images()
    credits = json.loads((images.PHOTOS / "sources.json").read_text(encoding="utf-8"))
    assert credits, "expected bundled photos"
    for part_number, credit in credits.items():
        assert (images.PHOTOS / credit["file"]).is_file()
        assert credit["file"].startswith(part_number)
        assert credit["license"].startswith(("CC BY", "CC0", "Public domain"))
        assert credit["author"] and credit["source_url"].startswith(
            "https://commons.wikimedia.org/"
        )
    # PCIe photos must not stand in for SXM modules (form factor is a critical rule)
    assert not {"A100-SXM4-80GB", "H100-SXM5"} & credits.keys()


def test_real_photo_replaces_the_illustration(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from advisor.models import Product

    images = _images()
    product = Product(part_number="SYN-PHOTO-1", manufacturer="Synthetic", category=Category.GPU)
    (tmp_path / "SYN-PHOTO-1.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    monkeypatch.setattr(images, "PHOTOS", tmp_path)
    monkeypatch.setattr(images, "_CACHE", {})
    src, is_photo = images.image_source(product)
    assert is_photo and src.startswith("data:image/png;base64,")
    assert "Ilustración" not in images.image_html(product)


def test_images_show_on_landing_and_results() -> None:
    at = AppTest.from_file(str(APP), default_timeout=120).run()
    assert markdown(at).count('class="pimg pimg-tile"') == 11
    search(at, OFFICIAL)
    # original + 2 recommended substitutes
    assert markdown(at).count('<div class="pimg"><img src="data:image/svg+xml') == 3
