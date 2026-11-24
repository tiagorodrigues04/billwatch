"""Detalhes de UX: números tabulares, títulos equilibrados, talão a cinzento e cliques sem repetir contas."""

import re
import sys
import tomllib
from pathlib import Path

import pytest
from fontTools.ttLib import TTFont

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "ferramentas"))

import fonte_tabular  # noqa: E402
import ui.dados  # noqa: E402
from ui.componentes import talao_a_cinzento  # noqa: E402
from ui.estilo import CSS  # noqa: E402

CONFIG = tomllib.loads((RAIZ / ".streamlit" / "config.toml").read_text())


def _fonte_da_interface() -> Path:
    familia = CONFIG["theme"]["font"].split(",")[0].strip()
    face = next(f for f in CONFIG["theme"]["fontFaces"] if f["family"] == familia)
    return RAIZ / face["url"].removeprefix("app/")


def _larguras(fonte: TTFont, caracteres: str) -> list[int]:
    cmap, hmtx = fonte.getBestCmap(), fonte["hmtx"]
    return [hmtx[cmap[ord(c)]][0] for c in caracteres]


def test_os_algarismos_da_interface_tem_todos_a_mesma_largura():
    # As tabelas (st.dataframe) são desenhadas num canvas: só a própria fonte pode alinhar os valores.
    fonte = TTFont(_fonte_da_interface())
    assert len(set(_larguras(fonte, "0123456789"))) == 1
    original = TTFont(fonte_tabular.ORIGEM)
    assert _larguras(fonte, ".,:") == _larguras(original, ".,:")      # a pontuação não muda
    assert "Tabular" in fonte["name"].getDebugName(1)                    # versão modificada (OFL)


def test_a_fonte_tabular_e_reproduzivel(tmp_path):
    gerada = TTFont(fonte_tabular.gerar(destino=tmp_path / "f.woff2"))
    guardada = TTFont(fonte_tabular.DESTINO)
    algarismos = [ord(c) for c in "0123456789"]
    assert [gerada.getBestCmap()[c] for c in algarismos] == [guardada.getBestCmap()[c] for c in algarismos]


def test_os_titulos_partem_se_em_linhas_equilibradas():
    assert re.search(r"h1, h2, h3 \{ text-wrap: balance; \}", CSS)


class _Destino:
    def __init__(self):
        self.html_escrito = ""

    def html(self, texto: str) -> None:
        self.html_escrito = texto


def test_talao_a_cinzento():
    destino = _Destino()
    talao_a_cinzento(destino, "A ler 2 ficheiros <PDF>…")
    h = destino.html_escrito
    assert 'role="status"' in h and 'aria-busy="true"' in h       # leitores de ecrã ouvem "A ler..."
    assert h.count('class="bw-t-linha') == 7                       # 6 linhas e o total
    assert "A ler 2 ficheiros &lt;PDF&gt;…" in h
    assert ".bw-esq" in CSS and "prefers-reduced-motion: reduce) { .bw-esq { animation: none; }" in CSS


@pytest.fixture()
def contador(monkeypatch):
    """Conta quantas vezes a deteção corre de verdade (o resto vem da cache)."""
    vezes = {"n": 0}
    original = ui.dados.detetar_recorrentes

    def a_contar(*args, **kwargs):
        vezes["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(ui.dados, "detetar_recorrentes", a_contar)
    ui.dados.analisar.clear()
    yield vezes
    ui.dados.analisar.clear()


def test_a_analise_so_se_repete_quando_mudam_os_dados(contador):
    extrato = ui.dados.ler_extrato(ui.dados.csv_exemplo())
    primeira = ui.dados.analisar(extrato)
    segunda = ui.dados.analisar(extrato)
    assert contador["n"] == 1 and primeira[0].equals(segunda[0])
    ui.dados.analisar(extrato, nome="Ana Costa")       # outro nome: outra análise
    assert contador["n"] == 2


def test_cliques_no_corrigir_nao_repetem_a_detecao(contador):
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(RAIZ / "app.py"), default_timeout=60).run()
    assert not at.exception and contador["n"] == 1
    opcoes = at.multiselect(key="excluir").options
    at.multiselect(key="excluir").set_value([opcoes[0]]).run()
    at.multiselect(key="excluir").set_value([]).run()
    assert not at.exception and contador["n"] == 1
