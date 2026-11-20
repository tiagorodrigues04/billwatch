"""A deteção não pode piorar sem darmos por isso.

Corre a avaliação em extratos rotulados (avaliacao/gerar.py) e exige mínimos de qualidade.
Se uma alteração ao catálogo ou às regras baixar a precisão ou o recall, este teste falha.
Os números completos (1000 extratos) estão no README: python -m avaliacao.avaliar --n 1000
"""

from avaliacao.avaliar import avaliar


def test_qualidade_da_detecao():
    res = avaliar(n=60)
    assert res.precisao >= 0.95, f"precisão {res.precisao:.1%}"
    assert res.recall >= 0.97, f"recall {res.recall:.1%}"
    assert sum(res.erros_custo) / len(res.erros_custo) < 0.5   # erro médio no custo por mês, em €
