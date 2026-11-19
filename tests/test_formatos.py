"""Todos os formatos da coleção (tests/formatos) têm de dar exatamente os mesmos movimentos.

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
    assert FIXOS <= set(rec["comerciante"])
    r = resumo(rec)
    assert r["n_ativas"] == 8 and r["mensal"] == pytest.approx(442.06)


@pytest.mark.parametrize("nome", ["c07_revolut_extrato_pt.csv", "p03_revolut.pdf"])
def test_cripto_conta_como_poupanca_e_nao_como_custo(nome):
    rec = detetar_recorrentes(carregar_extrato((PASTA / nome).read_bytes(), nome))
    r = resumo(rec)
    assert r["poupanca_mensal"] == pytest.approx(25 * 52 / 12, abs=0.01)
    assert r["mensal"] == pytest.approx(442.06)


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
