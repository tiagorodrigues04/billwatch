"""Contas divididas: quando alguém te paga parte de uma conta que sai da tua conta.

Exemplo: pagas a internet (40 €) e os dois colegas de casa mandam-te 10 € cada por MB WAY.
O talão mostrava 40 €, mas o teu custo real é 20 €.

Como se deteta:
1. **Entradas de pessoas** ("MB WAY DE ANA COSTA", "TRF DE JOAO SILVA", "Payment from ...").
2. Para cada conta fixa, cada pagamento da conta procura uma entrada dessa pessoa até 7 dias
   antes ou depois. A pessoa acompanha a conta se aparecer em pelo menos 60% dos meses em
   que esteve presente (quem divide às vezes atrasa-se ou falha um mês) e sempre com a
   **mesma fração** da conta (10 € de 40 € = 1/4; numa conta de luz a fração mantém-se mesmo
   que o valor mude). Uma pessoa paga no máximo 60% de uma conta.
3. Se uma pessoa encaixa em várias contas, ganha primeiro uma conta que se costuma dividir
   (casa, internet, luz, streaming), depois a que fecha uma divisão em partes iguais com as
   outras pessoas (2 pessoas com 1/3 cada, mais tu), e só depois a mais próxima no tempo.
   As frações de todas as pessoas juntas nunca passam a conta inteira.
4. **Nunca contam**: empresas e rendimentos (salário, bolsa...), transferências tuas (o teu
   nome, pares entre contas) e, se disseres o teu nome, pessoas com o teu apelido, que é mais
   provável serem família (uma mesada perto do dia da renda) do que um colega de casa.

Também se pode dividir uma conta à mão (ex.: a luz por 3), com aplicar_partilhas(divisoes=...).
"""

from __future__ import annotations

import re
from collections import defaultdict

import numpy as np
import pandas as pd

from .entre_contas import menciona_titular, partilha_apelido
from .recorrentes import Parametros
from .texto import corrigir_texto_pdf, sem_acentos

DISTANCIA_MAXIMA = 7     # dias entre o pagamento da conta e a entrada da pessoa
PRESENCA_MINIMA = 0.6    # a pessoa aparece em pelo menos 60% dos pagamentos da conta
PARTE_MAXIMA = 0.6       # uma pessoa paga no máximo 60% da conta
# Contas que se costumam dividir com quem vive contigo (ou com amigos, no streaming).
CATEGORIAS_PARTILHAVEIS = {"Casa", "Telecomunicações", "Energia", "Streaming"}
COLUNAS = ["conta", "remetente", "fracao", "valor_mensal", "n_pagamentos", "distancia_dias"]

_ENTRADA_DE_PESSOA = re.compile(r"\b(MB ?WAY|MBWAY|TRF|TRANSF|TRANSFERENCIA|TRANSFER|PAYMENT|SEPA)\b")
_DE = re.compile(r"\b(?:DE|FROM)\b[\s:]+(.+)")
_RUIDO = {"REF", "SEPA", "IMEDIATA", "MB", "WAY", "MBWAY", "TRF", "PARA", "CONTA", "PT", "EUR", "DO", "DA",
          "DE", "DOS", "DAS"}
# Quem envia não é uma pessoa a pagar a parte dela: empresas, Estado, rendimentos.
_NAO_PESSOA = {"LDA", "SA", "UNIPESSOAL", "LIMITADA", "LTD", "LIMITED", "INC", "GMBH", "BV", "SL", "SALARIO",
               "ORDENADO", "VENCIMENTO", "BOLSA", "MESADA", "PENSAO", "SUBSIDIO", "ABONO", "IRS", "FINANCAS",
               "SEGURANCA", "SOCIAL", "ESTADO", "UNIVERSIDADE", "INSTITUTO", "BANCO", "CAIXA", "REEMBOLSO",
               "DEVOLUCAO", "JUROS", "POUPANCA", "COFRE", "POCKET", "SAVINGS", "VAULT", "REVOLUT", "N26",
               "WISE", "MOEY", "BUNQ"}


def remetente(descricao: str) -> str | None:
    """Quem enviou uma entrada de dinheiro, se for uma pessoa: 'MB WAY DE ANA COSTA' -> 'ANA COSTA'."""
    texto = sem_acentos(corrigir_texto_pdf(str(descricao))).upper()
    if not _ENTRADA_DE_PESSOA.search(texto):
        return None
    m = _DE.search(texto)
    if not m:
        return None
    resto = re.sub(r"[^A-Z0-9 ]", " ", m.group(1)).split()
    if any(t in _NAO_PESSOA for t in resto):
        return None
    nomes = [t for t in resto if not any(c.isdigit() for c in t) and t not in _RUIDO and len(t) > 1]
    if nomes:
        return " ".join(nomes[:3])
    telefone = [t for t in resto if t.isdigit() and len(t) >= 6]   # "MB WAY DE 912345678"
    return telefone[0] if telefone else None


def _partes_iguais(fracao: float) -> int | None:
    """Em quantas partes iguais está dividida a conta (2 a 6), se a fração for 1/k (±2%)."""
    for k in range(2, 7):
        if abs(fracao - 1 / k) <= 0.02 / k:
            return k
    return None


def _contas_que_se_podem_dividir(recorrentes: pd.DataFrame) -> pd.DataFrame:
    custos = recorrentes[recorrentes["ativa"]]
    for coluna in ("poupanca", "entre_contas"):
        if coluna in custos:
            custos = custos[~custos[coluna].fillna(False).astype(bool)]
    if "datas" not in custos or "valores" not in custos:
        return custos.iloc[0:0]
    return custos[custos["datas"].map(lambda d: isinstance(d, list) and len(d) >= 2)]


def _acompanha(datas_conta: list, valores_conta: list, entradas: pd.Series, minimo: int):
    """A pessoa paga a sua parte perto de cada pagamento da conta? Devolve (frações, distâncias) ou None.

    `entradas`: valores recebidos da pessoa, indexados pelo dia. Cada entrada serve um só pagamento.
    """
    dias = list(entradas.index)
    usados: set = set()
    fracoes, distancias = [], []
    for dia_conta, valor_conta in zip(datas_conta, valores_conta):
        perto = [(abs((d - dia_conta).days), d) for d in dias
                 if d not in usados and abs((d - dia_conta).days) <= DISTANCIA_MAXIMA]
        if not perto or valor_conta <= 0:
            continue
        distancia, d = min(perto)
        usados.add(d)
        fracoes.append(float(entradas[d]) / valor_conta)
        distancias.append(distancia)
    # Só conta o tempo em que a pessoa lá esteve (um colega que chegou a meio do ano).
    janela = [c for c in datas_conta if dias[0] - pd.Timedelta(days=DISTANCIA_MAXIMA) <= c
              <= dias[-1] + pd.Timedelta(days=DISTANCIA_MAXIMA)]
    if len(fracoes) < max(2, min(minimo, len(datas_conta))) or len(fracoes) < PRESENCA_MINIMA * len(janela):
        return None
    return fracoes, distancias


def detetar_partilhas(extrato: pd.DataFrame, recorrentes: pd.DataFrame, nome: str | None = None,
                      parametros: Parametros | None = None) -> pd.DataFrame:
    """Uma linha por pessoa que te paga regularmente parte de uma conta fixa."""
    p = parametros or Parametros()
    if extrato.empty or recorrentes is None or recorrentes.empty:
        return pd.DataFrame(columns=COLUNAS)
    contas = _contas_que_se_podem_dividir(recorrentes)
    entradas = extrato[extrato["valor"] > 0].copy()
    if "entre_contas" in entradas:
        entradas = entradas[~entradas["entre_contas"].fillna(False).astype(bool)]
    if contas.empty or entradas.empty:
        return pd.DataFrame(columns=COLUNAS)
    entradas["remetente"] = entradas["descricao"].map(remetente)
    entradas = entradas.dropna(subset=["remetente"])
    if nome and not entradas.empty:
        tuas = entradas["descricao"].map(lambda d: menciona_titular(d, nome))
        familia = entradas["remetente"].map(lambda r: partilha_apelido(r, nome))
        entradas = entradas[~tuas & ~familia]

    pessoas = {quem: g.groupby(g["data"].dt.normalize())["valor"].sum().sort_index()
               for quem, g in entradas.groupby("remetente")}
    candidatos = []   # (pessoa, conta, fração, distância, n, categoria partilhável?)
    for conta in contas.itertuples():
        datas_conta = list(pd.DatetimeIndex(conta.datas).normalize())
        for quem, recebido in pessoas.items():
            acompanha = _acompanha(datas_conta, conta.valores, recebido, p.min_pagamentos)
            if acompanha is None:
                continue
            fracoes, distancias = np.array(acompanha[0]), acompanha[1]
            fracao = float(np.median(fracoes))

            def perto(tolerancia: float) -> float:
                """Parte dos meses em que a fração ficou perto da habitual (robusto a um mês pago a dobrar)."""
                return float(np.mean(np.abs(fracoes - fracao) <= tolerancia * fracao))

            # Numa conta de consumo (luz, água) há quem pague um valor fixo e não metade da conta.
            if fracao > PARTE_MAXIMA or perto(0.5 if conta.valor_variavel else p.variacao_maxima_valor) < 0.7:
                continue
            candidatos.append((quem, conta, fracao, float(np.median(distancias)), len(fracoes),
                               conta.categoria in CATEGORIAS_PARTILHAVEIS, perto(0.03) >= 0.7))

    def ordem(c):
        quem, conta, fracao, distancia, _, partilhavel, exata = c
        # Partes iguais só contam se a fração for a mesma todos os meses (e não uma coincidência).
        k = _partes_iguais(fracao) if exata else None
        if k is None:
            falta = 9
        else:   # quantas outras pessoas pagam a mesma fração desta conta, contra as k - 2 esperadas
            iguais = sum(1 for o in candidatos if o[0] != quem and o[1].comerciante == conta.comerciante
                         and o[6] and abs(o[2] - fracao) <= 0.02 / k)
            falta = abs(iguais - (k - 2))
        return (0 if partilhavel else 1, falta, distancia)

    melhor: dict[str, tuple] = {}
    for c in sorted(candidatos, key=ordem):   # cada pessoa fica com a conta que melhor encaixa
        melhor.setdefault(c[0], c)
    por_conta: dict[str, list] = defaultdict(list)
    for c in melhor.values():
        por_conta[c[1].comerciante].append(c)

    linhas = []
    for nome_conta, lista in por_conta.items():
        total = 0.0
        for quem, conta, fracao, distancia, n, _, _ in sorted(lista, key=ordem):
            if total + fracao > 1.005:   # as partes de todos não podem passar a conta inteira
                continue
            total += fracao
            linhas.append({"conta": nome_conta, "remetente": quem.title(), "fracao": round(fracao, 4),
                           "valor_mensal": round(fracao * conta.custo_mensal, 2), "n_pagamentos": n,
                           "distancia_dias": distancia})
    return pd.DataFrame(linhas, columns=COLUNAS)


def aplicar_partilhas(recorrentes: pd.DataFrame, partilhas: pd.DataFrame | None = None,
                      divisoes: dict[str, int] | None = None) -> pd.DataFrame:
    """Acrescenta a cada linha quanto pagam os outros e qual é a tua parte.

    - `partilhas`: o que detetar_partilhas encontrou (só as que a pessoa aceitou).
    - `divisoes`: contas divididas à mão, {comerciante: número de pessoas contigo incluído}.
      Uma divisão à mão substitui o que foi detetado para essa conta.

    Colunas novas: partilhado_mensal, partilhado_por (nomes), dividida_por (pessoas, 0 = não)
    e custo_real_mensal (a tua parte).
    """
    r = recorrentes.copy()
    if r.empty:
        return r
    r["partilhado_mensal"] = 0.0
    r["partilhado_por"] = [[] for _ in range(len(r))]
    r["dividida_por"] = 0
    if partilhas is not None and not partilhas.empty:
        for conta, grupo in partilhas.groupby("conta"):
            for i in r.index[r["comerciante"] == conta]:
                r.at[i, "partilhado_mensal"] = round(float(grupo["valor_mensal"].sum()), 2)
                r.at[i, "partilhado_por"] = grupo["remetente"].tolist()
    for conta, pessoas in (divisoes or {}).items():
        if not pessoas or pessoas < 2:
            continue
        for i in r.index[r["comerciante"] == conta]:
            r.at[i, "partilhado_mensal"] = round(float(r.at[i, "custo_mensal"]) * (1 - 1 / pessoas), 2)
            r.at[i, "partilhado_por"] = []
            r.at[i, "dividida_por"] = int(pessoas)
    nao_custo = pd.Series(False, index=r.index)
    for coluna in ("poupanca", "entre_contas"):
        if coluna in r:
            nao_custo |= r[coluna].fillna(False).astype(bool)
    r.loc[nao_custo, ["partilhado_mensal", "dividida_por"]] = 0
    r["custo_real_mensal"] = (r["custo_mensal"] - r["partilhado_mensal"]).clip(lower=0).round(2)
    return r
