"""Todos os formatos bancários da coleção (tests/formatos) têm de dar exatamente os mesmos movimentos;
os ficheiros especiais (cripto, ilegíveis) têm de ficar de fora com aviso.

Para acrescentar um formato novo: imitá-lo em tests/gerar_formatos.py e correr esse script.
"""

import io
import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd
import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from contas.extrato import (FormatoDesconhecido, carregar_extrato, chave_comerciante,  # noqa: E402
                            ler_tabela, normalizar_com_mapa, sugerir_mapa)
from contas.recorrentes import detetar_recorrentes, resumo  # noqa: E402

PASTA = RAIZ / "tests" / "formatos"
ESPERADO = json.loads((PASTA / "esperado.json").read_text())
FIXOS = {"Netflix", "Spotify", "MEO", "Fitness Hut", "ChatGPT", "EDP", "Renda", "Apple (iCloud/App Store)"}


@pytest.fixture(scope="module")
def geradores():
    sys.path.insert(0, str(RAIZ / "tests"))
    pytest.importorskip("reportlab")
    import gerar_formatos
    return gerar_formatos


@pytest.mark.parametrize("nome", sorted(ESPERADO))
def test_formato_le_todos_os_movimentos(nome):
    df = carregar_extrato((PASTA / nome).read_bytes(), nome)
    e = ESPERADO[nome]
    assert len(df) == e["n"]
    assert df["valor"].sum() == pytest.approx(e["total"], abs=0.01)
    assert int((df["valor"] > 0).sum()) == e["entradas"]


@pytest.mark.parametrize("nome", sorted(ESPERADO))
def test_formato_datas_valores_e_comerciantes_exatos(nome, geradores):
    _, esperado = geradores.GERADORES[nome](geradores.base())
    lido = carregar_extrato((PASTA / nome).read_bytes(), nome)
    par = lambda df: Counter((d.date(), round(v, 2)) for d, v in zip(df["data"], df["valor"]))  # noqa: E731
    assert par(lido) == par(esperado)
    primeira = lambda textos: Counter((chave_comerciante(t[:38]).split() or [""])[0] for t in textos)  # noqa: E731
    assert primeira(lido["descricao"]) == primeira(esperado["descricao"])


@pytest.mark.parametrize("nome", sorted(ESPERADO))
def test_formato_mesmo_resultado_final(nome):
    rec = detetar_recorrentes(carregar_extrato((PASTA / nome).read_bytes(), nome))
    assert set(rec["comerciante"]) >= FIXOS
    r = resumo(rec)
    assert r["n_ativas"] == 8 and r["mensal"] == pytest.approx(442.06)


@pytest.mark.parametrize("nome", ["c07_revolut_extrato_pt.csv", "p03_revolut.pdf"])
def test_cripto_conta_como_poupanca_e_nao_como_custo(nome):
    rec = detetar_recorrentes(carregar_extrato((PASTA / nome).read_bytes(), nome))
    r = resumo(rec)
    assert r["poupanca_mensal"] == pytest.approx(25 * 52 / 12, abs=0.01)
    assert r["mensal"] == pytest.approx(442.06)


# --- ficheiros que não são extratos de conta, ou ilegíveis -------------------------

ESPECIAIS = json.loads((PASTA / "especiais.json").read_text())


@pytest.mark.parametrize("nome", sorted(ESPECIAIS))
def test_ficheiros_especiais_nao_dao_numeros_absurdos(nome):
    from contas.extrato import ExtratoNaoBancario, LeituraDuvidosa
    esperado = {"nao_bancario": ExtratoNaoBancario, "duvidosa": LeituraDuvidosa}[ESPECIAIS[nome]]
    with pytest.raises(esperado) as erro:
        carregar_extrato((PASTA / nome).read_bytes(), nome)
    if ESPECIAIS[nome] == "duvidosa":
        assert erro.value.problemas and not erro.value.extrato.empty   # dá para "usar mesmo assim"


def test_problemas_de_leitura():
    from contas.extrato import problemas_de_leitura
    bom = carregar_extrato((PASTA / "c02_montante_virgula.csv").read_bytes(), "c02.csv")
    assert problemas_de_leitura(bom) == []
    mau = pd.DataFrame({"data": pd.to_datetime(["2025-03-13"] * 6), "descricao": [""] * 6,
                        "valor": [-115.77, -115.77, -79350.12, -0.79, -0.79, 10.0]})
    problemas = problemas_de_leitura(mau)
    assert any("descrição" in p for p in problemas) and any("10 vezes" in p for p in problemas)


# --- casos-limite --------------------------------------------------------------

def test_colunas_desconhecidas_pedem_ajuda_e_o_mapa_manual_funciona():
    csv = "Dt;Txt;Q\n05-08-2026;NETFLIX.COM;-9,99\n05-09-2026;NETFLIX.COM;-9,99\n05-10-2026;NETFLIX.COM;-9,99\n"
    with pytest.raises(FormatoDesconhecido) as erro:
        carregar_extrato(csv.encode(), "x.csv")
    tabela = erro.value.tabela
    sugestao = sugerir_mapa(tabela)
    assert sugestao["data"] == "Dt" and sugestao["descricao"] == "Txt"   # adivinhou pelo conteúdo
    df = normalizar_com_mapa(tabela, {"data": "Dt", "descricao": "Txt", "valor": "Q"})
    assert df["valor"].tolist() == [-9.99] * 3
    assert normalizar_com_mapa(tabela, {"data": "Dt", "descricao": "Txt", "valor": "Q"}, inverter=True)["valor"].iloc[0] == 9.99


@pytest.mark.parametrize("conteudo, nome", [
    (b"", "vazio.csv"),
    (b"\x00\x01\x02\x03 lixo binario \xff\xfe", "lixo.xlsx"),
    (b"%PDF-1.4 isto nao e um pdf a serio", "falso.pdf"),
    (b"<html><body><p>sem tabela nenhuma</p></body></html>", "pagina.xls"),
])
def test_ficheiros_estragados_dao_erro_amigavel(conteudo, nome):
    with pytest.raises(ValueError) as erro:
        carregar_extrato(conteudo, nome)
    assert "Traceback" not in str(erro.value) and len(str(erro.value)) > 10


def test_pdf_digitalizado_e_protegido():
    canvas = pytest.importorskip("reportlab.pdfgen.canvas")
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.rect(50, 50, 300, 300, fill=1)       # só uma "imagem", sem texto
    c.save()
    with pytest.raises(ValueError, match="imagem"):
        carregar_extrato(buf.getvalue(), "digitalizado.pdf")
    buf = io.BytesIO()
    c = canvas.Canvas(buf, encrypt="segredo")
    c.drawString(50, 700, "05-10-2026 NETFLIX 9,99 100,00")
    c.save()
    with pytest.raises(ValueError, match="palavra-passe|imagem"):
        carregar_extrato(buf.getvalue(), "protegido.pdf")


def test_mesmo_ficheiro_carregado_duas_vezes_nao_duplica():
    from contas.extrato import juntar_extratos
    nome = "c02_montante_virgula.csv"
    df = carregar_extrato((PASTA / nome).read_bytes(), nome)
    assert len(juntar_extratos([df, df])) == len(df)


def test_ler_tabela_devolve_tabela_para_o_diagnostico():
    tabela = ler_tabela((PASTA / "c01_pt_debito_credito.csv").read_bytes(), "c01.csv")
    assert {"Descrição", "Débito", "Crédito"} <= set(tabela.columns)


# --- o mesmo extrato em formatos diferentes (ex.: o PDF e o CSV do mesmo mês) ---

@pytest.fixture(scope="module")
def todos_lidos():
    return {nome: carregar_extrato((PASTA / nome).read_bytes(), nome) for nome in sorted(ESPERADO)}


def test_o_mesmo_extrato_em_dois_formatos_da_o_mesmo_talao(todos_lidos):
    """Juntar o mesmo extrato em dois formatos quaisquer não pode duplicar movimentos.

    Cada formato escreve a descrição à sua maneira ("...STOCKHO" cortado num PDF, "· Cartão: ..."
    acrescentado noutro). Antes só se apagavam repetidos com a descrição exatamente igual, e
    os 3 primeiros PDFs juntos davam 2 contas fixas em vez de 8.
    """
    from itertools import combinations
    from contas.extrato import juntar_extratos

    diferentes = []
    for a, b in combinations(sorted(todos_lidos), 2):
        r = resumo(detetar_recorrentes(juntar_extratos([todos_lidos[a], todos_lidos[b]])))
        if (r["n_ativas"], r["mensal"]) != (8, 442.06):
            diferentes.append((a, b, r["n_ativas"], r["mensal"]))
    assert not diferentes
    tres = juntar_extratos([todos_lidos[n] for n in ("p01_grelha.pdf", "p02_texto_colunas.pdf", "p03_revolut.pdf")])
    assert len(tres) == ESPERADO["p03_revolut.pdf"]["n"]          # os 64 em comum só contam uma vez
    assert not tres["entre_contas"].any()


@pytest.mark.parametrize("a, b, esperado", [
    ("COMPRA 3442 SPOTIFY P685823118 STOCKHOLM", "COMPRA 3442 SPOTIFY P685823118 STOCKHO", True),   # cortada
    ("COMPRA 6000 SPOTIFY P98104 STOCKHOLM", "COMPRA 6000 SPOTIFY P98104 STOCKHOLM · Cartão: 535522******1234", True),
    ("COMPRA 3938 CAFE SANTA CRUZ", "COMPRA 3938 CAFE · SANTA CRUZ", True),            # linha partida no PDF
    ("Compra Café Central", "COMPRA CAFE CENTRAL", True),                             # acentos e maiúsculas
    ("COMPRA 3938 CAFE SANTA CRUZ", "COMPRA 1205 CAFE SANTA CRUZ", False),            # outro cartão/compra
    ("MB WAY", "MB WAY PARA ANA", False),                                             # curta demais para decidir
])
def test_mesma_descricao(a, b, esperado):
    from contas.extrato import mesma_descricao
    assert mesma_descricao(a, b) is esperado


def test_juntar_formatos_diferentes_conta_cada_copia_uma_vez():
    """Dois cafés iguais no mesmo dia são dois movimentos, mesmo com descrições diferentes por formato."""
    from contas.extrato import juntar_extratos
    dia = pd.Timestamp("2026-10-03")
    pdf = pd.DataFrame({"data": [dia] * 2, "descricao": ["COMPRA 3938 CAFE · SANTA CRUZ"] * 2, "valor": [-1.2] * 2})
    csv = pd.DataFrame({"data": [dia] * 3, "descricao": ["COMPRA 3938 CAFE SANTA CRUZ"] * 3, "valor": [-1.2] * 3})
    assert len(juntar_extratos([pdf, csv])) == 3          # 2 do PDF são os mesmos do CSV; o 3.º café fica
