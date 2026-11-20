"""Dinheiro que só muda de conta (de uma conta tua para outra tua) não é um custo.

Carregar a Revolut com 100 € todos os meses, ou mandar 150 € para outra conta no teu nome,
tem o padrão perfeito de uma subscrição: mesmo valor, mesmo dia. Reconhecemos estes
movimentos de três formas:

1. **Carregamentos de contas digitais** (Revolut, N26, Wise...): pelo catálogo, categoria
   "Entre contas" (ver catalogo.py).
2. **Transferências com o nome do titular** ("TRF P/ TIAGO RODRIGUES"), se a pessoa
   disser o nome. Exige o primeiro nome e um apelido, para "MB WAY PARA TIAGO" (um amigo
   com o mesmo nome) e "TRF DE MARIA RODRIGUES" (a mãe, com o mesmo apelido) não contarem.
3. **Pares entre extratos de contas diferentes**: sai X de uma conta e entra exatamente X
   noutra, no mesmo dia ou poucos dias depois.
"""

from __future__ import annotations

import re

import pandas as pd

from .texto import corrigir_texto_pdf, sem_acentos

_PARTICULAS = {"DE", "DA", "DO", "DAS", "DOS", "E", "DI", "DU", "VAN", "VON"}

# Palavras que mostram que um movimento é uma transferência ou um carregamento (e não uma compra).
_TRANSFERENCIA = re.compile(
    r"\b(?:TRF|TRANSF|TRANSFERENCIA|TRANSFER|SEPA|IMEDIATA|MB ?WAY|MBWAY|TOP ?UP|CARREG\w*|DEPOSITO|"
    r"DEPOSIT|PAYMENT FROM|PAYMENT TO|REVOLUT|N26|WISE|MOEY|BUNQ)\b"
)
_DIRECAO = re.compile(r"\b(?:PARA|DE|TO|FROM)\b|(?<![A-Z])P/")

# Dias entre a saída numa conta e a entrada na outra (a entrada pode aparecer até 1 dia antes,
# por causa de fusos horários e da hora a que cada banco regista o movimento).
_ANTES, _DEPOIS = 1, 3
# Duas contas diferentes têm extratos que se sobrepõem no tempo. Ficheiros do mesmo banco
# mês a mês quase não se sobrepõem (os dias repetidos já saíram em juntar_extratos).
_SOBREPOSICAO_MINIMA = 7


def tokens_nome(texto: str) -> list[str]:
    """'Tiago M. dos Santos' -> ['TIAGO', 'SANTOS'] (sem acentos, sem partículas nem iniciais)."""
    texto = sem_acentos(corrigir_texto_pdf(str(texto))).upper()
    return [t for t in re.sub(r"[^A-Z]+", " ", texto).split() if len(t) > 1 and t not in _PARTICULAS]


def _aparece(token: str, palavras: list[str]) -> bool:
    """O token do nome está na descrição, inteiro ou cortado pelo banco ('RODRIGU')."""
    return any(p == token or (len(p) >= 4 and token.startswith(p)) for p in palavras)


def menciona_titular(descricao: str, nome: str | None) -> bool:
    """A descrição é uma transferência com o nome do titular (primeiro nome + um apelido)."""
    partes = tokens_nome(nome or "")
    if len(partes) < 2:
        return False
    texto = sem_acentos(corrigir_texto_pdf(str(descricao))).upper()
    if not (_TRANSFERENCIA.search(texto) or _DIRECAO.search(texto)):
        return False
    palavras = tokens_nome(texto)
    primeiro, apelidos = partes[0], partes[1:]
    return _aparece(primeiro, palavras) and any(_aparece(a, palavras) for a in apelidos)


def partilha_apelido(remetente: str, nome: str | None) -> bool:
    """O remetente tem um apelido do titular (provavelmente família, não um colega de casa)."""
    partes = tokens_nome(nome or "")
    if len(partes) < 2:
        return False
    palavras = tokens_nome(remetente)
    return any(_aparece(a, palavras) for a in partes[1:])


def _contas_diferentes(extrato: pd.DataFrame) -> set[tuple]:
    """Pares de ficheiros que parecem ser de contas diferentes (sobrepõem-se no tempo)."""
    limites = extrato.groupby("origem")["data"].agg(["min", "max"])
    pares = set()
    origens = list(limites.index)
    for i, a in enumerate(origens):
        for b in origens[i + 1:]:
            inicio = max(limites.loc[a, "min"], limites.loc[b, "min"])
            fim = min(limites.loc[a, "max"], limites.loc[b, "max"])
            if (fim - inicio).days >= _SOBREPOSICAO_MINIMA:
                pares |= {(a, b), (b, a)}
    return pares


def marcar_pares(extrato: pd.DataFrame) -> pd.Series:
    """True nos movimentos que são as duas pontas de uma transferência entre contas tuas.

    Precisa da coluna "origem" (de que ficheiro veio cada movimento, ver juntar_extratos).
    Cada saída emparelha com no máximo uma entrada: primeiro os pares mais próximos no tempo.
    """
    marcados = pd.Series(False, index=extrato.index)
    if "origem" not in extrato or extrato["origem"].nunique() < 2:
        return marcados
    diferentes = _contas_diferentes(extrato)
    if not diferentes:
        return marcados

    texto = extrato["descricao"].map(lambda d: sem_acentos(corrigir_texto_pdf(str(d))).upper())
    parece = texto.str.contains(_TRANSFERENCIA).to_dict()
    dias = extrato["data"].dt.normalize().to_dict()
    origem = extrato["origem"].to_dict()
    centimos = (extrato["valor"].abs() * 100).round().astype("int64").to_dict()
    saidas = extrato.index[extrato["valor"] < 0]
    entradas = extrato.index[extrato["valor"] > 0]
    entradas_por_valor: dict[int, list] = {}
    for j in entradas:
        entradas_por_valor.setdefault(centimos[j], []).append(j)

    candidatos = []
    for i in saidas:
        for j in entradas_por_valor.get(centimos[i], []):
            if (origem[i], origem[j]) not in diferentes:
                continue
            atraso = (dias[j] - dias[i]).days
            if -_ANTES <= atraso <= _DEPOIS and (parece[i] or parece[j]):
                candidatos.append((abs(atraso), dias[i], i, j))

    usados: set = set()
    for _, _, i, j in sorted(candidatos, key=lambda c: (c[0], c[1])):
        if i in usados or j in usados:
            continue
        usados |= {i, j}
    marcados.loc[list(usados)] = True
    return marcados
