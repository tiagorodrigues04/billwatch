"""Deteção de pagamentos recorrentes (subscrições, contas fixas) num extrato.

Ideia do algoritmo, em 4 passos:
1. Ficar só com as saídas de dinheiro e dar a cada uma um "comerciante"
   (pelo catálogo de conhecidos ou, se não estiver lá, por uma chave limpa da descrição).
2. Agrupar por comerciante e medir o intervalo em dias entre pagamentos seguidos.
3. Um grupo é recorrente se os intervalos forem regulares (semanal, mensal,
   trimestral ou anual) e o valor for estável (ou variável, se for um consumo como a luz).
4. Para cada recorrente calcular custo mensal/anual, próximo pagamento previsto e alertas.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .catalogo import CATEGORIAS_VARIAVEIS, identificar
from .extrato import chave_comerciante

# nome, intervalo típico em dias, tolerância em dias, pagamentos por ano
PERIODICIDADES = [
    ("Semanal", 7, 2, 52),
    ("Mensal", 30.4, 5, 12),
    ("Bimestral", 61, 7, 6),
    ("Trimestral", 91, 10, 4),
    ("Semestral", 182, 15, 2),
    ("Anual", 365, 20, 1),
]


def euro(valor: float) -> str:
    """12345.6 -> '12 345,60 €' (formato português)."""
    return f"{valor:,.2f}".replace(",", " ").replace(".", ",") + " €"


@dataclass
class Parametros:
    min_pagamentos: int = 3                 # mínimo de pagamentos para um desconhecido
    min_pagamentos_conhecido: int = 2       # comerciantes do catálogo precisam de menos provas
    regularidade_minima: float = 0.7        # % de intervalos dentro da tolerância
    variacao_maxima_valor: float = 0.15     # coeficiente de variação máximo (valor fixo)
    aumento_alerta: float = 0.05            # subida de preço que gera alerta (5%)


def _classificar_intervalo(intervalos: np.ndarray, p: Parametros):
    """Devolve (periodicidade, regularidade) ou (None, 0) se não houver padrão."""
    mediana = float(np.median(intervalos))
    for nome, dias, tolerancia, por_ano in PERIODICIDADES:
        if abs(mediana - dias) <= tolerancia:
            dentro = np.abs(intervalos - dias) <= tolerancia * 1.5
            regularidade = float(dentro.mean())
            if regularidade >= p.regularidade_minima:
                return (nome, dias, por_ano), regularidade
    return None, 0.0


def preparar(extrato: pd.DataFrame) -> pd.DataFrame:
    """Passo 1: saídas de dinheiro com comerciante e categoria."""
    saidas = extrato[extrato["valor"] < 0].copy()
    saidas["montante"] = saidas["valor"].abs()
    identificados = saidas["descricao"].map(identificar)
    saidas["comerciante"] = [
        ident[0] if ident else chave_comerciante(desc).title()
        for ident, desc in zip(identificados, saidas["descricao"])
    ]
    saidas["categoria"] = [ident[1] if ident else "Outros" for ident in identificados]
    saidas["conhecido"] = identificados.notna()
    return saidas


def detetar_recorrentes(extrato: pd.DataFrame, parametros: Parametros | None = None,
                        hoje: pd.Timestamp | None = None) -> pd.DataFrame:
    """Devolve uma linha por pagamento recorrente encontrado."""
    p = parametros or Parametros()
    if extrato.empty:
        return pd.DataFrame()
    hoje = hoje if hoje is not None else extrato["data"].max()
    saidas = preparar(extrato)

    linhas = []
    for (comerciante, categoria), grupo in saidas.groupby(["comerciante", "categoria"]):
        conhecido = bool(grupo["conhecido"].iloc[0])
        minimo = p.min_pagamentos_conhecido if conhecido else p.min_pagamentos
        # Vários pagamentos no mesmo dia (ex.: duas compras na mesma loja) contam como um.
        por_dia = grupo.groupby(grupo["data"].dt.normalize())["montante"].sum().sort_index()
        if len(por_dia) < minimo:
            continue

        datas = por_dia.index
        intervalos = np.diff(datas.values).astype("timedelta64[D]").astype(float)
        # Para medir o ritmo, um pagamento extra poucos dias depois de outro (cobrança
        # duplicada, nova tentativa de débito) conta como o mesmo ciclo. Sem isto, uma
        # duplicação num extrato de 3 meses estragava a regularidade e a subscrição sumia.
        ciclos = [datas[0]]
        for d in datas[1:]:
            if (d - ciclos[-1]).days > 4:
                ciclos.append(d)
        if len(ciclos) < minimo:
            continue
        intervalos_ciclo = np.diff(pd.DatetimeIndex(ciclos).values).astype("timedelta64[D]").astype(float)
        periodo, regularidade = _classificar_intervalo(intervalos_ciclo, p)
        if periodo is None:
            continue
        nome_periodo, dias_periodo, por_ano = periodo

        valores = por_dia.values
        mediana = float(np.median(valores))
        variacao = float(np.std(valores) / mediana) if mediana else 0.0
        valor_variavel = categoria in CATEGORIAS_VARIAVEIS
        if not valor_variavel and variacao > p.variacao_maxima_valor:
            # Valores muito diferentes = provavelmente compras normais (supermercado, café...).
            # Exceção: subida de preço — os valores antigos são estáveis e os últimos também.
            antigos = valores[:-1]
            antigos_estaveis = np.std(antigos) / np.median(antigos) <= p.variacao_maxima_valor
            salto_plausivel = valores[-1] <= np.median(antigos) * 2  # subidas de preço reais não duplicam
            if not (antigos_estaveis and salto_plausivel):
                continue

        ultimo_valor = float(valores[-1])
        ultima_data = datas[-1]
        proxima = ultima_data + pd.Timedelta(days=round(dias_periodo))
        dias_desde_ultimo = (hoje.normalize() - ultima_data).days

        alertas = []
        if not valor_variavel:
            # Anda para trás enquanto o valor for igual ao atual: o valor antes disso é o preço antigo.
            i = len(valores) - 1
            while i > 0 and abs(valores[i - 1] - ultimo_valor) <= 0.01 * ultimo_valor:
                i -= 1
            if i > 0:
                antigo = float(valores[i - 1])
                if antigo * (1 + p.aumento_alerta) < ultimo_valor <= antigo * 2:
                    subida = (ultimo_valor / antigo - 1) * 100
                    quando = datas[i].strftime("%m/%Y")
                    alertas.append(
                        f"Preço subiu {subida:.0f}% em {quando} ({euro(antigo)} → {euro(ultimo_valor)})"
                    )
        ativa = dias_desde_ultimo <= dias_periodo * 1.5
        if not ativa:
            alertas.append("Sem pagamentos recentes — talvez já esteja cancelada")
        # Dois pagamentos muito próximos num serviço mensal = possível cobrança duplicada.
        if nome_periodo == "Mensal" and (intervalos < 10).any():
            alertas.append("Houve dois pagamentos com menos de 10 dias de diferença")

        valor_tipico = float(np.mean(valores[-3:])) if valor_variavel else ultimo_valor
        confianca = 0.5 * regularidade + 0.3 * (1 - min(variacao, 1)) + 0.2 * (1 if conhecido else 0)
        if valor_variavel:
            confianca = 0.6 * regularidade + 0.4 * (1 if conhecido else 0)

        linhas.append(
            {
                "comerciante": comerciante,
                "categoria": categoria,
                "periodicidade": nome_periodo,
                "valor_tipico": round(valor_tipico, 2),
                "valor_variavel": valor_variavel,
                "custo_mensal": round(valor_tipico * por_ano / 12, 2),
                "custo_anual": round(valor_tipico * por_ano, 2),
                "n_pagamentos": len(por_dia),
                "primeiro_pagamento": datas[0].date(),
                "ultimo_pagamento": ultima_data.date(),
                "proximo_previsto": proxima.date() if ativa else None,
                "ativa": ativa,
                "confianca": round(confianca, 2),
                "alertas": alertas,
            }
        )

    if not linhas:
        return pd.DataFrame()
    resultado = pd.DataFrame(linhas)
    return resultado.sort_values(["ativa", "custo_mensal"], ascending=[False, False]).reset_index(drop=True)


def possiveis_subscricoes(extrato: pd.DataFrame) -> pd.DataFrame:
    """Modo rápido para extratos curtos (ex.: 1 mês), onde ainda não há repetições.

    Não dá para provar que algo se repete, por isso mostramos só os pagamentos a
    comerciantes do catálogo (Netflix, MEO, ginásio...), que quase sempre são fixos.
    """
    saidas = preparar(extrato)
    conhecidos = saidas[saidas["conhecido"]]
    if conhecidos.empty:
        return pd.DataFrame()
    return (
        conhecidos.groupby(["comerciante", "categoria"], as_index=False)
        .agg(valor=("montante", "sum"), n_pagamentos=("montante", "size"), ultimo=("data", "max"))
        .sort_values("valor", ascending=False)
        .reset_index(drop=True)
    )


def resumo(recorrentes: pd.DataFrame) -> dict:
    """Números para o topo do painel (só subscrições ativas)."""
    if recorrentes.empty:
        return {"n_ativas": 0, "mensal": 0.0, "anual": 0.0, "n_alertas": 0}
    ativas = recorrentes[recorrentes["ativa"]]
    return {
        "n_ativas": int(len(ativas)),
        "mensal": round(float(ativas["custo_mensal"].sum()), 2),
        "anual": round(float(ativas["custo_anual"].sum()), 2),
        "n_alertas": int(recorrentes["alertas"].map(len).sum()),
    }
