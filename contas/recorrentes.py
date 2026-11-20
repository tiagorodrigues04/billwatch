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

from .catalogo import CATEGORIAS_POUPANCA, CATEGORIAS_VARIAVEIS, identificar
from .extrato import chave_comerciante, e_debito_direto, e_transferencia_para_pessoa

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
    extra_para_pessoa: int = 1              # MB WAY para uma pessoa precisa de mais 1 pagamento


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


def _subida_de_preco(valores: np.ndarray, aumento_minimo: float, ruido: float = 0.05):
    """Procura a subida de preço mais recente: devolve (índice, preço antigo, preço novo) ou None.

    Divide os pagamentos em "antes" e "depois" em cada ponto possível, do mais recente para
    trás, e para no primeiro ponto em que os dois lados são estáveis (variam menos de 5%, o
    que tolera o câmbio de serviços cobrados em dólares) e têm preços diferentes.
    Compara medianas, por isso um mês com um valor estranho não cria um alerta falso.
    """
    for i in range(len(valores) - 1, 0, -1):
        antes, depois = valores[:i][-6:], valores[i:]
        m_antes, m_depois = float(np.median(antes)), float(np.median(depois))
        # Com um só pagamento no preço novo, o antigo tem de ser fixo ao cêntimo (1%):
        # senão a oscilação do câmbio passava por uma subida.
        tolerancia_antes = ruido if len(depois) >= 2 else 0.01
        estaveis = (np.abs(antes - m_antes) <= tolerancia_antes * m_antes).all() and \
                   (np.abs(depois - m_depois) <= ruido * m_depois).all()
        if not estaveis:
            continue
        # Preços fixos ao cêntimo: basta subir 5%. Preços que oscilam (câmbio): tem de subir 10%.
        fixos = (np.abs(antes - m_antes) <= 0.01 * m_antes).all() and \
                (np.abs(depois - m_depois) <= 0.01 * m_depois).all()
        minimo = aumento_minimo if fixos else max(aumento_minimo, 0.10)
        if m_antes * (1 + minimo) < m_depois <= m_antes * 1.6:
            return i, m_antes, m_depois
        if abs(m_depois - m_antes) > ruido * m_antes:
            return None   # a mudança mais recente não é uma subida (desceu, ou subiu demais)
        # mesmo preço dos dois lados: a mudança, se houver, está mais para trás
    return None


def preparar(extrato: pd.DataFrame) -> pd.DataFrame:
    """Passo 1: saídas de dinheiro com comerciante e categoria."""
    saidas = extrato[extrato["valor"] < 0].copy()
    saidas["montante"] = saidas["valor"].abs()
    identificados = saidas["descricao"].map(identificar)
    saidas["comerciante"] = [
        ident[0] if ident else chave_comerciante(desc).title()
        for ident, desc in zip(identificados, saidas["descricao"])
    ]
    saidas["debito_direto"] = saidas["descricao"].map(e_debito_direto)
    saidas["categoria"] = [
        ident[1] if ident else ("Débito direto" if dd else "Outros")
        for ident, dd in zip(identificados, saidas["debito_direto"])
    ]
    saidas["conhecido"] = identificados.notna()
    # Um débito direto (SDD) é quase sempre uma conta fixa: precisa de menos provas,
    # tal como um comerciante do catálogo.
    saidas["confiavel"] = saidas["conhecido"] | saidas["debito_direto"]
    # MB WAY para amigos com valores redondos (10 €, 20 €) repetem-se por acaso.
    saidas["para_pessoa"] = ~saidas["confiavel"] & saidas["descricao"].map(e_transferencia_para_pessoa)
    return saidas


def detetar_recorrentes(extrato: pd.DataFrame, parametros: Parametros | None = None,
                        hoje: pd.Timestamp | None = None) -> pd.DataFrame:
    """Devolve uma linha por pagamento recorrente encontrado."""
    p = parametros or Parametros()
    if extrato.empty:
        return pd.DataFrame()
    hoje = hoje if hoje is not None else extrato["data"].max()
    saidas = preparar(extrato)

    def avaliar(grupo: pd.DataFrame, comerciante: str, categoria: str) -> dict | None:
        """Decide se um grupo de pagamentos é recorrente; devolve a linha do resultado ou None."""
        conhecido = bool(grupo["confiavel"].iloc[0])
        minimo = p.min_pagamentos_conhecido if conhecido else p.min_pagamentos
        if bool(grupo["para_pessoa"].all()):
            minimo += p.extra_para_pessoa
        # Vários pagamentos no mesmo dia (ex.: duas compras na mesma loja) contam como um.
        por_dia = grupo.groupby(grupo["data"].dt.normalize())["montante"].sum().sort_index()
        if len(por_dia) < minimo:
            return None

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
            return None
        intervalos_ciclo = np.diff(pd.DatetimeIndex(ciclos).values).astype("timedelta64[D]").astype(float)
        periodo, regularidade = _classificar_intervalo(intervalos_ciclo, p)
        if periodo is None:
            return None
        nome_periodo, dias_periodo, por_ano = periodo

        valores = por_dia.values
        mediana = float(np.median(valores))
        variacao = float(np.std(valores) / mediana) if mediana else 0.0
        valor_variavel = categoria in CATEGORIAS_VARIAVEIS
        if not valor_variavel and variacao > p.variacao_maxima_valor:
            # Valores muito diferentes = provavelmente compras normais (supermercado, café...).
            # Exceção: subida de preço — os valores antigos são estáveis e o último é MAIOR.
            # Com poucos pagamentos, dois valores parecidos acontecem por acaso (viagens de Uber),
            # por isso um desconhecido precisa de pelo menos 3 valores antigos estáveis.
            antigos = valores[:-1]
            antigos_estaveis = np.std(antigos) / np.median(antigos) <= p.variacao_maxima_valor
            provas = conhecido or len(antigos) >= 3
            salto_plausivel = np.median(antigos) < valores[-1] <= np.median(antigos) * 1.6  # raramente passa de +60%
            if not (antigos_estaveis and provas and salto_plausivel):
                return None

        ultimo_valor = float(valores[-1])
        ultima_data = datas[-1]
        proxima = ultima_data + pd.Timedelta(days=round(dias_periodo))
        dias_desde_ultimo = (hoje.normalize() - ultima_data).days

        alertas = []
        if not valor_variavel:
            subida_preco = _subida_de_preco(valores, p.aumento_alerta)
            if subida_preco is not None:
                i, antigo, novo = subida_preco
                subida = (novo / antigo - 1) * 100
                alertas.append(
                    f"Preço subiu {subida:.0f}% em {datas[i].strftime('%m/%Y')} ({euro(antigo)} → {euro(novo)})"
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

        return (
            {
                "comerciante": comerciante,
                "categoria": categoria,
                "poupanca": categoria in CATEGORIAS_POUPANCA,
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

    linhas = []
    for (comerciante, categoria), grupo in saidas.groupby(["comerciante", "categoria"]):
        linha = avaliar(grupo, comerciante, categoria)
        if linha is not None:
            linhas.append(linha)
            continue
        # O mesmo comerciante pode misturar uma subscrição com compras avulsas
        # (ex.: Apple = iCloud 0,99 € todos os meses + apps compradas de vez em quando).
        # Se o grupo todo falhou, testamos cada valor exato à parte.
        # Só para comerciantes conhecidos: em desconhecidos (ex.: transferências para amigos)
        # valores redondos como 20 € repetem-se por acaso e davam falsos positivos.
        if not bool(grupo["confiavel"].iloc[0]):
            continue
        for valor, subgrupo in grupo.groupby(grupo["montante"].round(2)):
            if len(subgrupo) >= 2 and len(subgrupo) < len(grupo):
                linha = avaliar(subgrupo, f"{comerciante} ({euro(valor)})", categoria)
                if linha is not None:
                    linhas.append(linha)

    if not linhas:
        return pd.DataFrame()
    resultado = pd.DataFrame(linhas)
    resultado["proximo_previsto"] = pd.to_datetime(resultado["proximo_previsto"])  # None -> NaT (célula vazia)
    return resultado.sort_values(["ativa", "custo_mensal"], ascending=[False, False]).reset_index(drop=True)


def possiveis_subscricoes(extrato: pd.DataFrame) -> pd.DataFrame:
    """Modo rápido para extratos curtos (ex.: 1 mês), onde ainda não há repetições.

    Não dá para provar que algo se repete, por isso mostramos só os pagamentos a
    comerciantes do catálogo (Netflix, MEO, ginásio...), que quase sempre são fixos.
    """
    saidas = preparar(extrato)
    conhecidos = saidas[saidas["confiavel"] & ~saidas["categoria"].isin(CATEGORIAS_POUPANCA)]
    if conhecidos.empty:
        return pd.DataFrame()
    tabela = (
        conhecidos.groupby(["comerciante", "categoria"], as_index=False)
        .agg(valor=("montante", "sum"), n_pagamentos=("montante", "size"), ultimo=("data", "max"),
             minimo=("montante", "min"))
        .sort_values("valor", ascending=False)
        .reset_index(drop=True)
    )
    # Um pagamento único de 1 € ou menos a um serviço de subscrição costuma ser um
    # período experimental — que passa a preço normal se não for cancelado.
    tabela["nota"] = [
        "Valor muito baixo: pode ser um período experimental que passa a preço normal"
        if n == 1 and minimo <= 1.0 else ""
        for n, minimo in zip(tabela["n_pagamentos"], tabela["minimo"])
    ]
    return tabela.drop(columns="minimo")


def resumo(recorrentes: pd.DataFrame) -> dict:
    """Números para o topo do painel (só pagamentos ativos).

    Poupança e investimento (cofres, cripto, PPR...) são recorrentes mas não são custos:
    contam à parte, em "poupanca_mensal".
    """
    if recorrentes.empty:
        return {"n_ativas": 0, "mensal": 0.0, "anual": 0.0, "n_alertas": 0, "poupanca_mensal": 0.0}
    ativas = recorrentes[recorrentes["ativa"]]
    poupanca = ativas["poupanca"] if "poupanca" in ativas else pd.Series(False, index=ativas.index)
    custos = ativas[~poupanca]
    return {
        "n_ativas": int(len(custos)),
        "mensal": round(float(custos["custo_mensal"].sum()), 2),
        "anual": round(float(custos["custo_anual"].sum()), 2),
        "n_alertas": int(recorrentes["alertas"].map(len).sum()),
        "poupanca_mensal": round(float(ativas[poupanca]["custo_mensal"].sum()), 2),
    }
