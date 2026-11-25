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


# --- os três casos: entre contas, anuais e contas divididas --------------------

@pytest.fixture()
def app_tres_casos(monkeypatch):
    """A página principal a abrir com um extrato que tem os três casos (ver tests/cenarios.py)."""
    import ui.dados
    from cenarios import csv_tres_casos
    monkeypatch.setattr(ui.dados, "csv_exemplo", csv_tres_casos)
    return AppTest.from_file(APP, default_timeout=60).run()


def _talao(at) -> str:
    import html
    import re
    corpo = next(e.proto.body for e in at.get("html") if "bw-talao" in e.proto.body)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", corpo)))


def test_talao_mostra_entre_contas_anuais_e_partes_de_colegas(app_tres_casos):
    at = app_tres_casos
    assert not at.exception
    t = _talao(at)
    assert "Entre contas tuas, não conta como custo Revolut 100,00 €/mês" in t
    assert "A confirmar: pagamentos que só apareceram uma vez Amazon Prime 49,90 €" in t
    assert "Partes pagas por outros −20,00 €" in t
    assert "a tua parte é 20,00 €" in t


def test_o_teu_nome_tira_a_transferencia_para_ti_do_total(app_tres_casos):
    at = app_tres_casos
    assert "Total por mês 183,99 €" in _talao(at)            # 13,99 + 150 + 40 − 20
    at.text_input(key="nome_titular").set_value("Tiago Rodrigues").run()
    assert not at.exception
    t = _talao(at)
    assert "Total por mês 33,99 €" in t
    assert "Tiago Rodrigues 150,00 €/mês" in t                 # agora no bloco "Entre contas tuas"


def test_confirmar_o_anual_e_adicionar_a_mao_contam_no_total(app_tres_casos):
    at = app_tres_casos
    at.selectbox(key="confirmar_qual").set_value("Amazon Prime").run()
    assert at.selectbox(key="confirmar_freq_Amazon Prime").value == "Anual"
    at.button(key="confirmar_botao").click().run()
    assert not at.exception
    t = _talao(at)
    assert "Total por mês 188,15 €" in t and "confirmado por ti" in t
    assert "Amazon Prime 4,16 €" in t and "A confirmar" not in t
    at.text_input(key="manual_servico").set_value("Seguro do carro")
    at.number_input(key="manual_valor").set_value(90.0)
    at.selectbox(key="manual_freq").set_value("Trimestral")
    at.button(key="manual_adicionar").click().run()
    assert not at.exception
    t = _talao(at)
    assert "Seguro do carro 30,00 €" in t and "Total por mês 218,15 €" in t


def test_dividir_a_mao_e_recusar_uma_parte_detetada(app_tres_casos):
    at = app_tres_casos
    at.checkbox(key="partilha::Ana Costa::MEO").uncheck().run()
    assert "Partes pagas por outros −10,00 €" in _talao(at)
    at.selectbox(key="dividir_qual").set_value("MEO").run()
    at.number_input(key="dividir_pessoas").set_value(4).run()
    at.button(key="dividir_botao").click().run()
    assert not at.exception
    t = _talao(at)
    assert "dividida por 4: a tua parte é 10,00 €" in t and "Partes pagas por outros −30,00 €" in t


# --- supermercado e extratos partilhados entre as páginas ------------------------------

def test_pagina_do_supermercado_com_o_exemplo(app):
    app.switch_page("paginas/supermercado.py").run()
    assert not app.exception
    assert app.title[0].value == "Quanto gastas no supermercado?"
    assert {"O talão do exemplo", "Mês a mês", "Mudar de cadeia compensa?"} <= {s.value for s in app.subheader}
    t = _talao(app)
    assert "Total por mês 240,17 €" in t and "Idas pequenas, abaixo de 10 €" in t
    assert any(m.value.startswith("Quase nada.") for m in app.markdown)


def test_supermercado_usa_o_extrato_carregado_em_contas_fixas(app):
    import pandas as pd
    from ui.extratos import ExtratoPublicado
    extrato = pd.DataFrame({"data": pd.to_datetime(["2026-03-01", "2026-03-20", "2026-04-28"]),
                            "descricao": ["COMPRA PINGO DOCE", "COMPRA MINIPRECO", "COMPRA LIDL"],
                            "valor": [-5.0, -52.0, -40.0]})
    app.session_state["_extrato_publicado"] = ExtratoPublicado(extrato, exemplo=False, ficheiros=2)
    app.switch_page("paginas/supermercado.py").run()
    assert not app.exception
    assert "O teu talão" in [s.value for s in app.subheader]
    t = _talao(app)
    assert "3 compras" in t and "Minipreço" in t and "Exemplo" not in t


def test_ao_voltar_de_outra_pagina_os_ficheiros_continuam(app):
    """O carregador esvazia-se ao mudar de página, mas os ficheiros guardados na sessão continuam a contar."""
    from contas.exemplo import extrato_csv_banco, gerar_extrato
    from ui.extratos import FicheiroGuardado
    dados = extrato_csv_banco(gerar_extrato(meses=4))
    app.session_state["_extratos_guardados"] = [FicheiroGuardado("extrato.csv", len(dados), "id-1", dados)]
    app.switch_page("paginas/luz.py").run()
    app.switch_page("paginas/subscricoes.py").run()
    assert not app.exception
    assert "O teu talão" in [s.value for s in app.subheader]
    assert any("A usar extrato.csv, que carregaste antes." in c.value for c in app.caption)
    next(b for b in app.button if b.label == "Tirar").click().run()
    assert "O talão do exemplo" in [s.value for s in app.subheader]
