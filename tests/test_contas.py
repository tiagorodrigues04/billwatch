from pathlib import Path

import pandas as pd
import pytest

from contas.catalogo import identificar
from contas.energia import carregar_ofertas, comparar, extrair_dados_texto, ler_fatura_pdf
from contas.exemplo import extrato_csv_banco, gerar_extrato
from contas.extrato import carregar_extrato, chave_comerciante, converter_numero
from contas.recorrentes import detetar_recorrentes, resumo

RAIZ = Path(__file__).resolve().parent.parent


# --- extrato ---------------------------------------------------------------

@pytest.mark.parametrize("texto, esperado", [
    ("1.234,56", 1234.56), ("-12,99", -12.99), ("12.99", 12.99), ("€ 7,99", 7.99),
    ("1,234.56", 1234.56), ("", None), ("abc", None),
])
def test_converter_numero(texto, esperado):
    assert converter_numero(texto) == esperado


def test_le_formato_banco_com_cabecalho_e_debito_credito():
    df = carregar_extrato(extrato_csv_banco(gerar_extrato()))
    assert list(df.columns) == ["data", "descricao", "valor"]
    assert (df["valor"] < 0).any() and (df["valor"] > 0).any()
    assert df["data"].is_monotonic_increasing


def test_le_formato_simples_com_montante():
    csv = "Date,Description,Amount\n2026-01-05,NETFLIX.COM,-7.99\n2026-02-05,NETFLIX.COM,-7.99\n"
    df = carregar_extrato(csv.encode())
    assert df["valor"].tolist() == [-7.99, -7.99]


def test_chave_comerciante_remove_ruido():
    assert chave_comerciante("COMPRA 4521 NETFLIX.COM 866-579 12/03") == "NETFLIX"
    assert chave_comerciante("TRF RENDA QUARTO REF 770487") == "RENDA QUARTO"


def test_catalogo():
    assert identificar("DD MEO SA ENT 12345") == ("MEO", "Telecomunicações")
    assert identificar("GOOGLE *YOUTUBEPREMIUM") == ("YouTube Premium", "Streaming")
    assert identificar("COMPRA HOMEOPATIA") is None  # "MEO" dentro de outra palavra não conta


# --- recorrentes -------------------------------------------------------------

@pytest.fixture(scope="module")
def recorrentes():
    return detetar_recorrentes(gerar_extrato()).set_index("comerciante")


def test_encontra_subscricoes_e_ignora_ruido(recorrentes):
    for nome in ["Netflix", "Spotify", "ChatGPT", "Fitness Hut", "MEO", "EDP", "Fidelidade", "Renda"]:
        assert nome in recorrentes.index, nome
    for ruido in ["Continente", "Cafe Santa", "Uber"]:
        assert not any(ruido in c for c in recorrentes.index), ruido


def test_periodicidades(recorrentes):
    assert recorrentes.loc["Netflix", "periodicidade"] == "Mensal"
    assert recorrentes.loc["Fidelidade", "periodicidade"] == "Semestral"
    assert recorrentes.loc["Fidelidade", "custo_mensal"] == pytest.approx(84.50 * 2 / 12, abs=0.01)


def test_alertas(recorrentes):
    assert any("subiu 25%" in a for a in recorrentes.loc["Netflix", "alertas"])
    assert not recorrentes.loc["Disney+", "ativa"]
    assert any("duplic" in a or "10 dias" in a for a in recorrentes.loc["Spotify", "alertas"])
    assert recorrentes.loc["EDP", "valor_variavel"]


def test_resumo_so_conta_ativas(recorrentes):
    r = resumo(recorrentes.reset_index())
    ativas = recorrentes[recorrentes["ativa"]]
    assert r["mensal"] == pytest.approx(ativas["custo_mensal"].sum(), abs=0.01)
    assert r["n_ativas"] == len(ativas)


def test_extrato_sem_recorrentes():
    df = pd.DataFrame({"data": pd.to_datetime(["2026-01-01", "2026-03-17"]),
                       "descricao": ["LOJA A", "LOJA B"], "valor": [-10.0, -55.0]})
    assert detetar_recorrentes(df).empty


# --- energia -----------------------------------------------------------------

def test_le_fatura_pdf_exemplo():
    dados, _ = ler_fatura_pdf((RAIZ / "dados" / "fatura_exemplo.pdf").read_bytes())
    assert dados.consumo_kwh == 185
    assert dados.potencia_kva == 4.6
    assert dados.preco_kwh == pytest.approx(0.158)
    assert dados.termo_fixo_dia == pytest.approx(0.265)
    assert dados.dias == 31
    assert dados.total == pytest.approx(47.61)


def test_extrair_texto_vazio():
    assert extrair_dados_texto("sem números aqui").campos_encontrados() == []


def test_comparar_ordena_e_calcula_poupanca():
    res = comparar(200, 6.9, carregar_ofertas(), custo_atual=60.0, dias=30)
    assert res["custo_mensal"].is_monotonic_increasing
    linha = res.iloc[0]
    esperado = (linha["termo_fixo_eur_dia"] * 30 + linha["preco_kwh"] * 200) * 30.4 / 30
    assert linha["custo_mensal"] == pytest.approx(esperado, abs=0.01)
    assert linha["poupanca_anual"] == pytest.approx((60 * 30.4 / 30 - linha["custo_mensal"]) * 12, abs=0.05)
