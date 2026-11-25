"""Gera um extrato bancário fictício (12 meses de um estudante) para demonstração e testes.

Inclui de propósito:
- subscrições normais (Spotify, iCloud, ChatGPT, ginásio, MEO)
- uma subida de preço (Netflix)
- uma subscrição cancelada há meses (Disney+)
- um consumo variável (luz EDP)
- um pagamento recorrente desconhecido (renda do quarto por transferência)
- um seguro semestral
- uma cobrança duplicada (Spotify)
- ruído: supermercado, cafés, Uber, rendimentos
Com supermercados=True junta as compras de uma casa de estudantes: idas pequenas ao Pingo Doce,
a compra da semana no Lidl e, de vez em quando, o Mercadona e o Minipreço (é o exemplo da app).
Tudo é inventado: nomes, valores e referências.
"""

from __future__ import annotations

import random

import pandas as pd


def _dia(ano: int, mes: int, dia: int) -> pd.Timestamp:
    ultimo = pd.Timestamp(year=ano, month=mes, day=1) + pd.offsets.MonthEnd(0)
    return pd.Timestamp(year=ano, month=mes, day=min(dia, ultimo.day))


def gerar_extrato(fim: str = "2026-11-15", meses: int = 12, semente: int = 42,
                  supermercados: bool = False) -> pd.DataFrame:
    rng = random.Random(semente)
    # As compras do supermercado têm o seu próprio sorteio: ligá-las não muda mais nenhum movimento.
    sorteio = random.Random(semente + 1)
    fim_ts = pd.Timestamp(fim)
    inicio = (fim_ts - pd.DateOffset(months=meses - 1)).replace(day=1)
    movimentos: list[tuple[pd.Timestamp, str, float]] = []

    meses_lista = pd.period_range(inicio, fim_ts, freq="M")
    for i, periodo in enumerate(meses_lista):
        a, m = periodo.year, periodo.month
        add = lambda d, desc, v: movimentos.append((_dia(a, m, d), desc, v))  # noqa: E731

        add(1, "TRF MESADA FAMILIA", 400.00)
        add(2, f"TRF RENDA QUARTO REF {rng.randint(100000, 999999)}", -280.00)
        add(5, f"COMPRA {rng.randint(1000, 9999)} NETFLIX.COM AMSTERDAM", -7.99 if i < 7 else -9.99)
        add(8, f"COMPRA {rng.randint(1000, 9999)} SPOTIFY P{rng.randint(10**8, 10**9)} STOCKHOLM", -4.99)
        add(12, "APPLE.COM/BILL ITUNES.COM", -0.99)
        add(15, "OPENAI *CHATGPT SUBSCR SAN FRANCISCO", -23.00)
        add(3, f"DD FITNESS HUT COIMBRA REF {rng.randint(10**8, 10**9)}", -29.99)
        add(20, f"DD MEO SA ENT 12345 REF {rng.randint(10**8, 10**9)}", -45.00)
        consumo = 38 + 18 * abs(6 - m) / 6 + rng.uniform(-4, 4)  # mais caro no inverno
        add(22, f"DD EDP COMERCIAL REF {rng.randint(10**8, 10**9)}", -round(consumo, 2))
        if i < 6:
            add(10, "COMPRA DISNEY PLUS LONDON", -5.99)
        if m in (3, 9):
            add(18, "DD FIDELIDADE SEGUROS APOLICE", -84.50)
        if i == 9:  # cobrança duplicada
            add(10, f"COMPRA {rng.randint(1000, 9999)} SPOTIFY P{rng.randint(10**8, 10**9)} STOCKHOLM", -4.99)

        # Ruído: compras do dia a dia
        for _ in range(rng.randint(3, 5)):
            add(rng.randint(1, 28), f"COMPRA {rng.randint(1000, 9999)} CONTINENTE COIMBRA",
                -round(rng.uniform(8, 65), 2))
        for _ in range(rng.randint(4, 9)):
            add(rng.randint(1, 28), f"COMPRA {rng.randint(1000, 9999)} CAFE SANTA CRUZ",
                -round(rng.uniform(0.8, 6.5), 2))
        for _ in range(rng.randint(0, 3)):
            add(rng.randint(1, 28), "COMPRA UBER *TRIP HELP.UBER.COM", -round(rng.uniform(4, 14), 2))
        if rng.random() < 0.3:
            add(rng.randint(1, 28), "TRF MB WAY DE AMIGO", round(rng.uniform(5, 30), 2))
        if supermercados:
            for _ in range(sorteio.randint(5, 9)):     # o Pingo Doce ao pé de casa: pão, leite, fruta
                add(sorteio.randint(1, 28), f"COMPRA {sorteio.randint(1000, 9999)} PINGO DOCE COIMBRA",
                    -round(sorteio.uniform(1.5, 8.5), 2))
            for _ in range(sorteio.randint(1, 3)):     # a compra da semana no Lidl
                add(sorteio.randint(1, 28), f"COMPRA {sorteio.randint(1000, 9999)} LIDL COIMBRA",
                    -round(sorteio.uniform(15, 38), 2))
            if sorteio.random() < 0.4:                 # o Mercadona, de vez em quando
                add(sorteio.randint(1, 28), f"COMPRA {sorteio.randint(1000, 9999)} MERCADONA COIMBRA",
                    -round(sorteio.uniform(20, 40), 2))
            for _ in range(sorteio.randint(0, 2)):     # o Minipreço da esquina
                add(sorteio.randint(1, 28), f"COMPRA {sorteio.randint(1000, 9999)} MINIPRECO COIMBRA",
                    -round(sorteio.uniform(4, 16), 2))

    df = pd.DataFrame(movimentos, columns=["data", "descricao", "valor"])
    df = df[df["data"] <= fim_ts]
    return df.sort_values("data").reset_index(drop=True)


def extrato_csv_banco(df: pd.DataFrame) -> bytes:
    """Exporta no formato típico de um banco português (';', vírgula decimal, Débito/Crédito)."""
    fmt = lambda v: f"{v:.2f}".replace(".", ",") if v else ""  # noqa: E731
    saldo = 1500.0
    linhas = ["Extrato de conta à ordem", "Conta: PT50 0000 0000 0000 0000 0000 0 (fictícia)", "",
              "Data Mov.;Data Valor;Descrição;Débito;Crédito;Saldo"]
    for _, r in df.iterrows():
        saldo += r["valor"]
        d = r["data"].strftime("%d-%m-%Y")
        deb = fmt(-r["valor"]) if r["valor"] < 0 else ""
        cred = fmt(r["valor"]) if r["valor"] > 0 else ""
        linhas.append(f"{d};{d};{r['descricao']};{deb};{cred};{fmt(saldo)}")
    return "\n".join(linhas).encode("utf-8")
