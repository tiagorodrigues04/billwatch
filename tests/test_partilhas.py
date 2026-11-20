"""Contas divididas: quem te paga parte de uma conta baixa o teu custo real."""

import random

import pandas as pd
import pytest

from cenarios import extrato_tres_casos, juntar, mensal, ruido
from contas.partilhas import aplicar_partilhas, detetar_partilhas, remetente
from contas.recorrentes import detetar_recorrentes, resumo

MEO = mensal("DD MEO SA ENT 12345 REF 99", -40.0, inicio="2026-05-08")


def _partilhas(*partes, nome=None):
    df = juntar(MEO, ruido(), *partes)
    rec = detetar_recorrentes(df, nome=nome)
    return rec, detetar_partilhas(df, rec, nome=nome)


def test_colegas_de_casa_baixam_o_custo_real():
    rec, part = _partilhas(mensal("MB WAY DE JOAO SILVA", 10.0, inicio="2026-05-09"),
                           mensal("TRF DE ANA COSTA", 10.0, inicio="2026-05-11"))
    assert sorted(part["remetente"]) == ["Ana Costa", "Joao Silva"] and set(part["conta"]) == {"MEO"}
    final = aplicar_partilhas(rec, part)
    meo = final.set_index("comerciante").loc["MEO"]
    assert meo["custo_real_mensal"] == pytest.approx(20.0)
    s = resumo(final)
    assert (s["mensal_bruto"], s["partilhado_mensal"], s["mensal"]) == pytest.approx((40.0, 20.0, 20.0))


def test_familia_com_o_teu_apelido_nao_e_colega_de_casa():
    mae = mensal("TRF DE MARIA RODRIGUES", 15.0, inicio="2026-05-07")
    assert list(_partilhas(mae)[1]["remetente"]) == ["Maria Rodrigues"]          # sem nome: não dá para saber
    assert _partilhas(mae, nome="Tiago Rodrigues")[1].empty


def test_transferencias_tuas_nao_contam_como_partes():
    rec, part = _partilhas(mensal("TRF IMEDIATA DE TIAGO RODRIGUES", 10.0, inicio="2026-05-09"),
                           nome="Tiago Rodrigues")
    assert part.empty


def test_nao_contam_reembolsos_irregulares_nem_partes_grandes_demais():
    rng = random.Random(3)
    datas = sorted(pd.Timestamp("2026-05-01") + pd.Timedelta(days=rng.randint(0, 150)) for _ in range(6))
    amigos = pd.DataFrame({"data": datas, "descricao": "MB WAY DE RITA", "valor": [5, 20, 7.5, 12, 20, 9]})
    grande = mensal("TRF DE PEDRO NUNES", 35.0, inicio="2026-05-08")        # 35 € de uma conta de 40 €
    assert _partilhas(amigos, grande)[1].empty


def test_as_partes_nunca_passam_o_valor_da_conta():
    amigos = [mensal(f"MB WAY DE {nome}", 20.0, inicio="2026-05-09") for nome in ("ANA", "BRUNO", "CARLA")]
    rec, part = _partilhas(*amigos)
    assert len(part) == 2 and part["valor_mensal"].sum() == pytest.approx(40.0)


def test_prefere_uma_conta_que_se_costuma_dividir():
    # Um pagamento fixo a um desconhecido no dia a seguir à MEO: a Ana paga parte da MEO, não disso.
    rec, part = _partilhas(mensal("DD CLUBE NATACAO 12", -36.20, inicio="2026-05-10"),
                           mensal("MB WAY DE ANA COSTA", 10.0, inicio="2026-05-10"))
    assert list(part["conta"]) == ["MEO"]


def test_dividir_a_mao_substitui_o_que_foi_detetado():
    df = extrato_tres_casos()
    rec = detetar_recorrentes(df, nome="Tiago Rodrigues")
    final = aplicar_partilhas(rec, detetar_partilhas(df, rec, nome="Tiago Rodrigues"), divisoes={"MEO": 4})
    meo = final.set_index("comerciante").loc["MEO"]
    assert meo["dividida_por"] == 4 and meo["custo_real_mensal"] == pytest.approx(10.0)
    assert final.loc[final["entre_contas"], "partilhado_mensal"].eq(0).all()


@pytest.mark.parametrize("descricao, esperado", [
    ("MB WAY DE ANA COSTA", "ANA COSTA"),
    ("TRF MB WAY DE AMIGO", "AMIGO"),
    ("Transferência de Ana Costa", "ANA COSTA"),
    ("Payment from Joao Silva", "JOAO SILVA"),
    ("TRF IMEDIATA SEPA+ DE: RUI PINTO REF 123", "RUI PINTO"),
    ("MB WAY DE 912345678", "912345678"),
    ("TRF DE EMPRESA XPTO LDA", None),          # empresa
    ("TRF DE SALARIO NOVEMBRO", None),          # rendimento
    ("TRF MESADA FAMILIA", None),               # sem remetente
    ("COMPRA CONTINENTE", None),
])
def test_remetente(descricao, esperado):
    assert remetente(descricao) == esperado
