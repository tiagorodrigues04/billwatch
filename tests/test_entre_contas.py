"""Dinheiro que só muda de conta (carregar a Revolut, transferir para outra conta tua) não é um custo."""

import pandas as pd
import pytest

from cenarios import juntar, mensal, ruido, unico
from contas.catalogo import identificar
from contas.entre_contas import marcar_pares, menciona_titular
from contas.extrato import juntar_extratos
from contas.recorrentes import detetar_recorrentes, resumo

NETFLIX = mensal("COMPRA NETFLIX.COM AMSTERDAM", -13.99)


@pytest.mark.parametrize("descricao", [
    "TRF IMEDIATA P/ REVOLUT",
    "COMPRA 4521 REVOLUT**1234* DUBLIN",
    "WISE EUROPE SA BRUXELAS",
    "TRF P/ N26 BANK",
    "Trf Imediata Sepa+ MOEY",
])
def test_carregamentos_de_contas_digitais_nao_sao_custos(descricao):
    r = detetar_recorrentes(juntar(NETFLIX, mensal(descricao, -100.0, inicio="2026-05-06"), ruido()))
    s = resumo(r)
    assert s["mensal"] == pytest.approx(13.99)          # só a Netflix
    assert s["entre_contas_mensal"] == pytest.approx(100.0)
    assert r.loc[r["entre_contas"], "categoria"].eq("Entre contas").all()


def test_nomes_parecidos_e_planos_pagos_continuam_a_ser_custos():
    assert identificar("DD REVOLUTION FITNESS COIMBRA") is None       # "REVOLUT" no início de outra palavra
    assert identificar("REVOLUT PREMIUM PLAN") == ("Revolut Premium", "Bancos")
    assert identificar("TRADE REPUBLIC BANK") == ("Trade Republic", "Poupança e investimento")


def test_transferencia_para_outra_conta_tua_sai_do_total_quando_dizes_o_nome():
    df = juntar(NETFLIX, mensal("TRF P/ TIAGO RODRIGUES", -150.0, inicio="2026-05-07"), ruido())
    assert resumo(detetar_recorrentes(df))["mensal"] == pytest.approx(163.99)    # sem nome não dá para saber
    s = resumo(detetar_recorrentes(df, nome="Tiago Miguel dos Santos Rodrigues"))
    assert s["mensal"] == pytest.approx(13.99)
    assert s["entre_contas_mensal"] == pytest.approx(150.0)


@pytest.mark.parametrize("descricao, nome, esperado", [
    ("TRF P/ TIAGO RODRIGUES", "Tiago Rodrigues", True),
    ("TRF IMEDIATA PARA TIAGO M RODRIGUES", "Tiago Rodrigues", True),
    ("TRF P/ TIAGO RODRIGU", "Tiago Rodrigues", True),            # nome cortado pelo banco
    ("Transferência para Tiago Rodrigues", "tiago rodrigues", True),
    ("MB WAY PARA TIAGO", "Tiago Rodrigues", False),               # um amigo com o mesmo nome
    ("TRF DE MARIA RODRIGUES", "Tiago Rodrigues", False),          # a mãe: o mesmo apelido não chega
    ("COMPRA TIAGO RODRIGUES LDA", "Tiago Rodrigues", False),      # uma compra, não uma transferência
    ("TRF P/ TIAGO RODRIGUES", "Tiago", False),                    # só o primeiro nome não chega
    ("TRF P/ TIAGO RODRIGUES", "", False),
])
def test_menciona_titular(descricao, nome, esperado):
    assert menciona_titular(descricao, nome) is esperado


def _dois_bancos(atraso_dias=1, valor_entrada=100.0):
    banco = juntar(NETFLIX, mensal("TRF IMEDIATA 0033000045219999", -100.0, inicio="2026-05-06"))
    datas = pd.date_range("2026-05-06", periods=6, freq="30D") + pd.Timedelta(days=atraso_dias)
    revolut = juntar(pd.DataFrame({"data": datas, "descricao": "Top-up by *1234", "valor": valor_entrada}),
                     unico("2026-05-20", "Pingo Doce", -23.40), unico("2026-07-02", "Uber", -7.80))
    return juntar_extratos([banco, revolut])


def test_pares_entre_extratos_de_bancos_diferentes_nao_sao_custos():
    junto = _dois_bancos()
    assert junto["entre_contas"].sum() == 12          # 6 saídas no banco + 6 entradas na Revolut
    assert resumo(detetar_recorrentes(junto))["mensal"] == pytest.approx(13.99)


@pytest.mark.parametrize("atraso_dias, valor_entrada", [(6, 100.0), (1, 99.0)])
def test_pares_precisam_do_mesmo_valor_e_de_datas_proximas(atraso_dias, valor_entrada):
    assert not _dois_bancos(atraso_dias, valor_entrada)["entre_contas"].any()


def test_meses_seguidos_do_mesmo_banco_nao_fazem_pares():
    # Pagas 50 € a um amigo no fim de setembro e outro amigo paga-te 50 € a 1 de outubro: ficheiros
    # seguidos do mesmo banco não se sobrepõem no tempo, por isso não podem ser duas contas tuas.
    setembro = juntar(unico("2026-09-03", "COMPRA CAFE", -2.0), unico("2026-09-30", "MB WAY PARA RITA", -50.0))
    outubro = juntar(unico("2026-10-01", "MB WAY DE PEDRO", 50.0), unico("2026-10-20", "COMPRA CAFE", -2.0))
    assert not juntar_extratos([setembro, outubro])["entre_contas"].any()


def test_marcar_pares_sem_origem_nao_marca_nada():
    assert not marcar_pares(NETFLIX).any()
