"""A deteção não pode piorar sem darmos por isso.

Corre a avaliação em extratos rotulados (avaliacao/gerar.py) e exige mínimos de qualidade.
Se uma alteração ao catálogo ou às regras baixar a precisão ou o recall, este teste falha.
Os números completos (1000 extratos) estão no README: python -m avaliacao.avaliar --n 1000
"""

import pytest

from avaliacao.avaliar import avaliar


@pytest.fixture(scope="module")
def res():
    return avaliar(n=60)


def test_qualidade_da_detecao(res):
    assert res.precisao >= 0.95, f"precisão {res.precisao:.1%}"
    assert res.recall >= 0.97, f"recall {res.recall:.1%}"
    assert sum(res.erros_custo) / len(res.erros_custo) < 0.5   # erro médio no custo por mês, em €


def test_casos_da_vida_real(res):
    """Entre contas, anuais e contas divididas (ver avaliacao/gerar.py e o README)."""
    assert res.pessoas_com_entre_contas > 0 and res.entre_contas_como_custo == 0
    assert res.anuais > 0 and res.anuais_a_confirmar == res.anuais
    assert res.contas_divididas > 0
    assert res.contas_divididas_descontadas / res.contas_divididas >= 0.9
    assert res.descontos_falsos <= 1
    assert sum(res.erros_custo_real) / len(res.erros_custo_real) < 1.0   # erro na tua parte, em €
