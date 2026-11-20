"""Extratos pequenos e fictícios para os testes dos movimentos entre contas, anuais e contas divididas."""

from __future__ import annotations

import random

import pandas as pd

from contas.exemplo import extrato_csv_banco


def mensal(descricao: str, valor: float, inicio: str = "2026-05-05", n: int = 6, dias: int = 30) -> pd.DataFrame:
    """O mesmo movimento, n vezes, de `dias` em `dias`."""
    datas = pd.date_range(inicio, periods=n, freq=f"{dias}D")
    return pd.DataFrame({"data": datas, "descricao": [descricao] * n, "valor": [valor] * n})


def unico(data: str, descricao: str, valor: float) -> pd.DataFrame:
    return pd.DataFrame({"data": [pd.Timestamp(data)], "descricao": [descricao], "valor": [valor]})


def juntar(*partes: pd.DataFrame) -> pd.DataFrame:
    return pd.concat(partes, ignore_index=True).sort_values("data", kind="stable").reset_index(drop=True)


def ruido(inicio: str = "2026-05-01", fim: str = "2026-10-10", semente: int = 1) -> pd.DataFrame:
    """Compras do dia a dia, sem padrão (supermercado, cafés)."""
    rng = random.Random(semente)
    linhas = []
    for d in pd.date_range(inicio, fim, freq="D"):
        if rng.random() < 0.3:
            linhas.append((d, f"COMPRA {rng.randint(1000, 9999)} PINGO DOCE COIMBRA", -round(rng.uniform(5, 70), 2)))
        if rng.random() < 0.4:
            linhas.append((d, f"COMPRA {rng.randint(1000, 9999)} CAFE CENTRAL", -round(rng.uniform(0.8, 6), 2)))
    return pd.DataFrame(linhas, columns=["data", "descricao", "valor"])


def extrato_tres_casos() -> pd.DataFrame:
    """Um estudante com os três casos de uma vez:

    - carrega a Revolut com 100 € e manda 150 € para outra conta em nome dele (Tiago Rodrigues);
    - paga o Amazon Prime uma vez por ano (só aparece uma vez);
    - paga a MEO (40 €) e os dois colegas de casa mandam-lhe 10 € cada.
    """
    return juntar(
        mensal("COMPRA NETFLIX.COM AMSTERDAM", -13.99),
        mensal("TRF IMEDIATA P/ REVOLUT", -100.0, inicio="2026-05-06"),
        mensal("TRF P/ TIAGO RODRIGUES", -150.0, inicio="2026-05-07"),
        mensal("DD MEO SA ENT 12345 REF 99", -40.0, inicio="2026-05-08"),
        mensal("MB WAY DE JOAO SILVA", 10.0, inicio="2026-05-09"),
        mensal("MB WAY DE ANA COSTA", 10.0, inicio="2026-05-10"),
        unico("2026-06-10", "AMAZON PRIME*AB12C", -49.90),
        ruido(),
    )


def csv_tres_casos() -> bytes:
    return extrato_csv_banco(extrato_tres_casos())
