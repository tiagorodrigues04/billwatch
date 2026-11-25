"""Supermercado: reconhecer as cadeias, médias por mês, idas pequenas e quanto se poupava a mudar de cadeia."""

import pandas as pd
import pytest

from contas.exemplo import gerar_extrato
from contas.recorrentes import detetar_recorrentes, resumo
from contas.supermercados import (cadeia, compras, indices_de_precos, mais_barata, meses_cobertos, mudar_de_cadeia,
                                  por_mes, resumir)


def _extrato(linhas) -> pd.DataFrame:
    df = pd.DataFrame(linhas, columns=["data", "descricao", "valor"])
    return df.assign(data=pd.to_datetime(df["data"]))


@pytest.mark.parametrize("descricao, esperado", [
    ("COMPRA 4521 CONTINENTE BOM DIA COIMBRA", "Continente"),
    ("COMPRA CONTINENTE MODELO LEIRIA", "Continente"),
    ("Compra Pingo Doce Coimbra", "Pingo Doce"),
    ("COMPRA 1234 LIDL AGRADECE", "Lidl"),
    ("MB WAY COMPRA MERCADONA PORTUGAL", "Mercadona"),
    ("COMPRA MINI PRECO COIMBRA", "Minipreço"),
    ("COMPRA MINIPREÇO COIMBRA", "Minipreço"),
    ("COMPRA INTERMARCHÉ COIMBRA", "Intermarché"),
    ("COMPRA MY AUCHAN LISBOA", "Auchan"),
    ("COMPRA JUMBO COIMBRA", "Auchan"),
    ("COMPRA INTERMARCHE COMBUSTIVEIS", None),       # a bomba de gasolina da cadeia
    ("COMPRA GALP COIMBRA", None),
    ("COMPRA EL CORTE INGLES LISBOA", None),          # a loja toda: não dá para separar o supermercado
    ("COMPRA ALDINHO RESTAURANTE", None),             # "ALDI" só como palavra inteira
    ("TRF MB WAY DE JOAO", None),
])
def test_reconhece_a_cadeia(descricao, esperado):
    assert cadeia(descricao) == esperado


def test_devolucoes_descontam_e_um_ordenado_nao_e_compra():
    tabela = compras(_extrato([
        ("2026-03-02", "COMPRA LIDL COIMBRA", -30.0),
        ("2026-03-05", "DEVOLUCAO LIDL COIMBRA", 5.0),
        ("2026-03-28", "TRF SALARIO PINGO DOCE", 600.0),
        ("2026-03-10", "COMPRA NETFLIX.COM", -9.99),
    ]))
    assert tabela["cadeia"].tolist() == ["Lidl", "Lidl"]
    assert tabela["montante"].tolist() == [30.0, -5.0]


def test_medias_por_mes_por_cadeia_e_idas_pequenas():
    tabela = compras(_extrato([
        ("2026-03-01", "COMPRA PINGO DOCE", -4.0), ("2026-03-02", "COMPRA PINGO DOCE", -6.0),
        ("2026-03-15", "COMPRA CONTINENTE", -50.0), ("2026-04-10", "COMPRA CONTINENTE", -70.0),
        ("2026-04-20", "COMPRA PINGO DOCE", -12.0),
    ]))
    r = resumir(tabela, meses=2.0)
    assert r.gasto_mensal == pytest.approx(71.0)          # 142 € em 2 meses
    assert r.idas_mensal == pytest.approx(2.5)
    assert r.valor_medio == pytest.approx(28.4)
    assert (r.pequenas_mensal, r.pequenas_gasto_mensal) == (pytest.approx(1.0), pytest.approx(5.0))   # 4 € e 6 €
    continente = r.por_cadeia.iloc[0]                     # a que pesa mais vem primeiro
    assert continente.cadeia == "Continente"
    assert (continente.gasto_mensal, continente.idas_mensal, continente.valor_medio) == (60.0, 1.0, 60.0)
    assert r.por_cadeia["parte"].sum() == pytest.approx(1.0)
    assert resumir(tabela, meses=2.0, limite=15).pequenas_mensal == pytest.approx(1.5)


def test_grafico_so_com_os_meses_completos():
    extrato = _extrato([("2026-01-20", "COMPRA LIDL", -10.0), ("2026-02-10", "COMPRA LIDL", -20.0),
                        ("2026-03-03", "COMPRA LIDL", -30.0), ("2026-04-05", "COMPRA LIDL", -40.0)])
    meses = por_mes(compras(extrato), extrato)
    # janeiro só tem 12 dias de extrato e abril só 5: ficam fevereiro e março
    assert meses["mes"].dt.month.tolist() == [2, 3]
    assert meses["gasto"].tolist() == [20.0, 30.0]


def test_indice_da_deco_e_poupanca_ao_preco_da_mais_barata():
    indices = indices_de_precos()
    assert mais_barata(indices) == "Continente" and indices["indice"].min() == 100
    assert {"Pingo Doce", "Auchan", "Intermarché", "Minipreço"} <= set(indices["cadeia"])
    por_cadeia = pd.DataFrame({"cadeia": ["Minipreço", "Lidl", "Continente"], "gasto_mensal": [104.0, 50.0, 80.0]})
    t = mudar_de_cadeia(por_cadeia, indices).set_index("cadeia")
    assert t.loc["Minipreço", "poupanca_mensal"] == pytest.approx(4.0)     # 104 € × (1 − 100/104)
    assert t.loc["Continente", "poupanca_mensal"] == 0
    assert pd.isna(t.loc["Lidl", "indice"]) and pd.isna(t.loc["Lidl", "poupanca_mensal"])


def test_as_compras_do_exemplo_nao_mudam_as_contas_fixas():
    sem, com = gerar_extrato(), gerar_extrato(supermercados=True)
    assert len(com) > len(sem)
    antes, depois = detetar_recorrentes(sem), detetar_recorrentes(com)
    assert antes["comerciante"].tolist() == depois["comerciante"].tolist()
    assert resumo(antes)["mensal"] == resumo(depois)["mensal"]
    # e o exemplo do supermercado tem várias cadeias e idas pequenas
    r = resumir(compras(com), meses_cobertos(com))
    assert set(r.por_cadeia["cadeia"]) == {"Continente", "Pingo Doce", "Lidl", "Mercadona", "Minipreço"}
    assert r.pequenas_mensal > 3
