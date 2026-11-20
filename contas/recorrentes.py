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

import re
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .catalogo import CATEGORIAS_NAO_CUSTO, CATEGORIAS_POUPANCA, CATEGORIAS_VARIAVEIS, ENTRE_CONTAS, identificar
from .entre_contas import menciona_titular
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
PERIODO = {nome: (dias, por_ano) for nome, dias, _, por_ano in PERIODICIDADES}

# Menos dias do que isto: o extrato é curto demais para ver repetições (modo rápido).
DIAS_EXTRATO_CURTO = 55
NOTA_EXPERIMENTAL = "Valor muito baixo: pode ser um período experimental que passa a preço normal"

_SUFIXO_VALOR = re.compile(r" \(\d[\d ]*,\d{2} €\)$")


def sem_sufixo(comerciante: str) -> str:
    """"Apple (iCloud/App Store) (0,99 €)" -> "Apple (iCloud/App Store)" (subgrupo por valor)."""
    return _SUFIXO_VALOR.sub("", comerciante)


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


def preparar(extrato: pd.DataFrame, nome: str | None = None) -> pd.DataFrame:
    """Passo 1: saídas de dinheiro com comerciante e categoria.

    `nome` (opcional) é o nome do titular: as transferências com esse nome são para outra
    conta da própria pessoa e ficam na categoria "Entre contas", tal como os pares que
    juntar_extratos encontrou entre extratos de contas diferentes (coluna "entre_contas").
    """
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
    entre = saidas["categoria"] == ENTRE_CONTAS
    if "entre_contas" in saidas:
        entre |= saidas["entre_contas"].fillna(False).astype(bool)
    if nome:
        entre |= saidas["descricao"].map(lambda d: menciona_titular(d, nome))
    saidas["entre_contas"] = entre
    saidas.loc[entre, "categoria"] = ENTRE_CONTAS
    # Um débito direto (SDD) é quase sempre uma conta fixa: precisa de menos provas,
    # tal como um comerciante do catálogo.
    saidas["confiavel"] = saidas["conhecido"] | saidas["debito_direto"]
    # MB WAY para amigos com valores redondos (10 €, 20 €) repetem-se por acaso.
    saidas["para_pessoa"] = ~saidas["confiavel"] & saidas["descricao"].map(e_transferencia_para_pessoa)
    return saidas


def detetar_recorrentes(extrato: pd.DataFrame, parametros: Parametros | None = None,
                        hoje: pd.Timestamp | None = None, nome: str | None = None) -> pd.DataFrame:
    """Devolve uma linha por pagamento recorrente encontrado."""
    p = parametros or Parametros()
    if extrato.empty:
        return pd.DataFrame()
    hoje = hoje if hoje is not None else extrato["data"].max()
    saidas = preparar(extrato, nome)

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
                "entre_contas": categoria == ENTRE_CONTAS,
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
                "datas": list(datas),          # dias e valores dos pagamentos (para as contas divididas)
                "valores": [float(v) for v in valores],
                "origem": "detetado",
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


def possiveis_subscricoes(extrato: pd.DataFrame, recorrentes: pd.DataFrame | None = None,
                          nome: str | None = None) -> pd.DataFrame:
    """Pagamentos "a confirmar": quase de certeza fixos, mas ainda sem provas de que se repetem.

    - **Extrato curto** (menos de 55 dias): ainda não há repetições, por isso mostramos os
      pagamentos a comerciantes do catálogo (Netflix, MEO, ginásio...), que quase sempre são fixos.
    - **Extrato longo**: os pagamentos que apareceram **uma só vez** a um comerciante do catálogo
      ou por débito direto. Ao fim de vários meses uma conta mensal já se teria repetido, por
      isso pode ser anual (seguro, Amazon Prime, propinas pagas de uma vez...). Sem isto, os
      pagamentos anuais desapareciam do talão, e são precisamente os que mais se esquecem.

    Os comerciantes que já estão em `recorrentes` ficam de fora. Nada disto entra nos totais
    até a pessoa confirmar (ver confirmados()).
    """
    colunas = ["comerciante", "categoria", "valor", "valor_tipico", "n_pagamentos", "ultimo", "nota",
               "periodicidade", "renovacao"]
    if extrato.empty:
        return pd.DataFrame(columns=colunas)
    saidas = preparar(extrato, nome)
    conhecidos = saidas[saidas["confiavel"] & ~saidas["categoria"].isin(CATEGORIAS_NAO_CUSTO)]
    if recorrentes is not None and not recorrentes.empty:
        confirmados_ = set(recorrentes["comerciante"].map(sem_sufixo))
        conhecidos = conhecidos[~conhecidos["comerciante"].isin(confirmados_)]
    if conhecidos.empty:
        return pd.DataFrame(columns=colunas)

    inicio, fim = extrato["data"].min().normalize(), extrato["data"].max().normalize()
    curto = (fim - inicio).days < DIAS_EXTRATO_CURTO
    meses = max(1, round((fim - inicio).days / 30.4))
    linhas = []
    for (comerciante, categoria), grupo in conhecidos.groupby(["comerciante", "categoria"]):
        por_dia = grupo.groupby(grupo["data"].dt.normalize())["montante"].sum()
        if not curto and (len(por_dia) != 1 or categoria in CATEGORIAS_VARIAVEIS):
            continue   # num extrato longo só interessam os pagamentos únicos (e não os consumos)
        ultimo, valor = por_dia.index.max(), float(por_dia.sum())
        tipico = float(np.median(por_dia.values))
        periodicidade, renovacao, nota = "Mensal", pd.NaT, ""
        if len(grupo) == 1 and tipico <= 1.0:
            nota = NOTA_EXPERIMENTAL   # 1 € ou menos uma só vez: costuma ser um período experimental
        elif not curto and (fim - ultimo).days < 40:
            nota = "Pagamento recente: pode ser uma subscrição nova ou um pagamento anual"
        elif not curto:
            periodicidade, renovacao = "Anual", ultimo + pd.Timedelta(days=365)
            nota = (f"Só 1 pagamento em {meses} meses: se for anual, renova por volta de "
                    f"{renovacao:%m/%Y} ({euro(tipico / 12)} por mês)")
        linhas.append({"comerciante": comerciante, "categoria": categoria, "valor": round(valor, 2),
                       "valor_tipico": round(tipico, 2), "n_pagamentos": len(grupo), "ultimo": ultimo,
                       "nota": nota, "periodicidade": periodicidade, "renovacao": renovacao})
    if not linhas:
        return pd.DataFrame(columns=colunas)
    return pd.DataFrame(linhas, columns=colunas).sort_values("valor", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Linhas que a pessoa confirma ou acrescenta à mão
# ---------------------------------------------------------------------------

def linha_fixa(comerciante: str, categoria: str, valor: float, periodicidade: str = "Mensal",
               ultimo: pd.Timestamp | None = None, origem: str = "manual", n_pagamentos: int = 0) -> dict:
    """Uma linha no formato de detetar_recorrentes, para um pagamento que a pessoa garante que é fixo."""
    dias, por_ano = PERIODO[periodicidade]
    ultimo = pd.Timestamp(ultimo).normalize() if ultimo is not None and pd.notna(ultimo) else None
    return {
        "comerciante": comerciante, "categoria": categoria, "poupanca": False, "entre_contas": False,
        "periodicidade": periodicidade, "valor_tipico": round(float(valor), 2), "valor_variavel": False,
        "custo_mensal": round(float(valor) * por_ano / 12, 2), "custo_anual": round(float(valor) * por_ano, 2),
        "n_pagamentos": n_pagamentos,
        "primeiro_pagamento": ultimo.date() if ultimo is not None else None,
        "ultimo_pagamento": ultimo.date() if ultimo is not None else None,
        "proximo_previsto": ultimo + pd.Timedelta(days=round(dias)) if ultimo is not None else pd.NaT,
        "ativa": True, "confianca": 1.0, "alertas": [], "datas": [ultimo] if ultimo is not None else [],
        "valores": [round(float(valor), 2)] if ultimo is not None else [], "origem": origem,
    }


def confirmados(possiveis: pd.DataFrame, escolhas: dict[str, str]) -> list[dict]:
    """Os pagamentos "a confirmar" que a pessoa confirmou, prontos a entrar no talão e nos totais.

    `escolhas` = {comerciante: periodicidade escolhida pela pessoa ("Mensal", "Anual"...)}.
    """
    return [linha_fixa(r.comerciante, r.categoria, r.valor_tipico, escolhas[r.comerciante], r.ultimo,
                       origem="confirmado", n_pagamentos=r.n_pagamentos)
            for r in possiveis.itertuples() if r.comerciante in escolhas]


def juntar_linhas(recorrentes: pd.DataFrame, extra: list[dict]) -> pd.DataFrame:
    """Acrescenta linhas confirmadas/manuais às detetadas, com a mesma ordem do talão."""
    if not extra:
        return recorrentes
    junto = pd.concat([recorrentes, pd.DataFrame(extra)], ignore_index=True) if not recorrentes.empty \
        else pd.DataFrame(extra)
    junto["proximo_previsto"] = pd.to_datetime(junto["proximo_previsto"])
    for coluna in ("poupanca", "entre_contas", "ativa", "valor_variavel"):
        junto[coluna] = junto[coluna].fillna(False).astype(bool)
    return junto.sort_values(["ativa", "custo_mensal"], ascending=[False, False]).reset_index(drop=True)


def _coluna(df: pd.DataFrame, nome: str) -> pd.Series:
    return df[nome].fillna(False).astype(bool) if nome in df else pd.Series(False, index=df.index)


def resumo(recorrentes: pd.DataFrame) -> dict:
    """Números para o topo do painel (só pagamentos ativos).

    Poupança e investimento (cofres, cripto, PPR...) e movimentos entre contas tuas são
    recorrentes mas não são custos: contam à parte. Se houver contas divididas
    (aplicar_partilhas), "mensal" e "anual" já são a tua parte; "mensal_bruto" é sem descontos.
    """
    if recorrentes.empty:
        return {"n_ativas": 0, "mensal": 0.0, "anual": 0.0, "n_alertas": 0, "poupanca_mensal": 0.0,
                "entre_contas_mensal": 0.0, "partilhado_mensal": 0.0, "mensal_bruto": 0.0}
    ativas = recorrentes[recorrentes["ativa"]]
    poupanca, entre = _coluna(ativas, "poupanca"), _coluna(ativas, "entre_contas")
    custos = ativas[~poupanca & ~entre]
    partilhado = float(custos["partilhado_mensal"].sum()) if "partilhado_mensal" in custos else 0.0
    bruto = float(custos["custo_mensal"].sum())
    return {
        "n_ativas": int(len(custos)),
        "mensal": round(bruto - partilhado, 2),
        "anual": round(float(custos["custo_anual"].sum()) - 12 * partilhado, 2),
        "n_alertas": int(recorrentes["alertas"].map(len).sum()),
        "poupanca_mensal": round(float(ativas[poupanca]["custo_mensal"].sum()), 2),
        "entre_contas_mensal": round(float(ativas[entre]["custo_mensal"].sum()), 2),
        "partilhado_mensal": round(partilhado, 2),
        "mensal_bruto": round(bruto, 2),
    }
