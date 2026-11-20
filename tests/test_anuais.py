"""Pagamentos que só aparecem uma vez num extrato longo (anuais) vão para "A confirmar"."""

import pandas as pd
import pytest

from cenarios import juntar, mensal, ruido, unico
from contas.recorrentes import (confirmados, detetar_recorrentes, juntar_linhas, linha_fixa,
                                possiveis_subscricoes, resumo)

# 4 meses de extrato (05/05 a 08/09), com a Netflix todos os meses.
NETFLIX = mensal("COMPRA NETFLIX.COM AMSTERDAM", -13.99, n=5)


def _a_confirmar(*partes):
    df = juntar(NETFLIX, ruido(fim="2026-09-02"), *partes)
    return possiveis_subscricoes(df, detetar_recorrentes(df)).set_index("comerciante")


def test_pagamento_anual_aparece_em_a_confirmar_com_renovacao_e_valor_por_mes():
    p = _a_confirmar(unico("2026-06-10", "AMAZON PRIME*AB12C", -49.90),
                     unico("2026-07-02", "DD LOGO SEGUROS AUTOMOVEL 77", -312.40))
    amazon = p.loc["Amazon Prime"]
    assert amazon["periodicidade"] == "Anual"
    assert "06/2027" in amazon["nota"] and "4,16 €" in amazon["nota"]
    assert p.loc["Logo", "periodicidade"] == "Anual"
    assert "Netflix" not in p.index                     # já está no talão


def test_pagamento_unico_recente_pode_ser_uma_subscricao_nova():
    p = _a_confirmar(unico("2026-08-25", "COMPRA DISNEY PLUS LONDON", -9.99))
    assert p.loc["Disney+", "periodicidade"] == "Mensal"
    assert "recente" in p.loc["Disney+", "nota"]


def test_fora_de_a_confirmar_compras_avulsas_consumos_e_repetidos():
    p = _a_confirmar(unico("2026-06-15", "COMPRA LOJA DO BAIRRO", -80.0),        # fora do catálogo
                     unico("2026-06-22", "DD EDP COMERCIAL REF 1", -61.30),       # consumo, não é anual
                     unico("2026-06-01", "APPLE.COM/BILL", -4.99),                # Apple 2 vezes: não é único
                     unico("2026-08-01", "APPLE.COM/BILL", -12.99))
    assert not ({"EDP", "Apple (iCloud/App Store)"} & set(p.index))
    assert not any("Loja" in c for c in p.index)


def test_confirmar_um_anual_conta_no_total_por_mes():
    df = juntar(NETFLIX, unico("2026-06-10", "AMAZON PRIME*AB12C", -49.90))
    rec = detetar_recorrentes(df)
    possiveis = possiveis_subscricoes(df, rec)
    linhas = confirmados(possiveis, {"Amazon Prime": "Anual"})
    assert len(linhas) == 1
    assert linhas[0]["custo_mensal"] == pytest.approx(4.16)
    assert linhas[0]["proximo_previsto"] == pd.Timestamp("2027-06-10")
    assert resumo(juntar_linhas(rec, linhas))["mensal"] == pytest.approx(13.99 + 4.16)


def test_pagamento_adicionado_a_mao():
    linha = linha_fixa("Seguro do carro", "Adicionado por ti", 90.0, "Trimestral")
    assert linha["custo_mensal"] == pytest.approx(30.0) and linha["origem"] == "manual"
    rec = juntar_linhas(detetar_recorrentes(NETFLIX), [linha])
    assert resumo(rec)["mensal"] == pytest.approx(43.99)
    assert resumo(juntar_linhas(pd.DataFrame(), [linha]))["mensal"] == pytest.approx(30.0)
