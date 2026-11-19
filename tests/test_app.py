"""A interface abre sem erros em todas as páginas (teste de fumo com o AppTest do Streamlit)."""

from pathlib import Path

import pytest

AppTest = pytest.importorskip("streamlit.testing.v1").AppTest
APP = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture()
def app():
    return AppTest.from_file(APP, default_timeout=60).run()


def test_pagina_principal_mostra_o_talao_do_exemplo(app):
    assert not app.exception
    assert app.title[0].value == "Quanto pagas, todos os meses?"
    assert "O talão do exemplo" in [s.value for s in app.subheader]


def test_pagina_da_luz_compara_ofertas(app):
    app.switch_page("paginas/luz.py").run()
    assert not app.exception
    app.number_input(key="consumo").set_value(185.0)
    app.number_input(key="preco_kwh").set_value(0.158)
    app.number_input(key="termo_fixo").set_value(0.265)
    app.run()
    assert not app.exception
    assert "A comparação" in [s.value for s in app.subheader]


def test_pagina_como_funciona(app):
    app.switch_page("paginas/sobre.py").run()
    assert not app.exception
    assert app.title[0].value == "Como funciona"
