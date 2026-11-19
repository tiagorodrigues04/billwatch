"""Fatura da luz: leitura do PDF e comparação com outras ofertas.

Custo mensal de eletricidade (simplificado, antes de impostos):
    custo = termo_fixo (€/dia) × dias  +  preço da energia (€/kWh) × consumo (kWh)

O IVA, o IEC, a taxa DGEG e a contribuição audiovisual são iguais (ou quase) em
todas as comercializadoras, por isso não mudam qual é a oferta mais barata.
Comparamos tudo antes de impostos para ser justo e simples.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from .extrato import converter_numero

PASTA_DADOS = Path(__file__).resolve().parent.parent / "dados"
POTENCIAS_PADRAO = [1.15, 2.3, 3.45, 4.6, 5.75, 6.9, 10.35, 13.8, 17.25, 20.7]


@dataclass
class DadosFatura:
    consumo_kwh: float | None = None
    potencia_kva: float | None = None
    preco_kwh: float | None = None
    termo_fixo_dia: float | None = None
    dias: int | None = None
    total: float | None = None

    def campos_encontrados(self) -> list[str]:
        return [nome for nome, valor in self.__dict__.items() if valor is not None]


# ---------------------------------------------------------------------------
# Leitura do PDF (melhor esforço: cada comercializadora tem o seu layout)
# ---------------------------------------------------------------------------

_NUM = r"(\d{1,5}(?:[.,]\d{1,6})?)"


def _primeiro(padrao: str, texto: str) -> float | None:
    m = re.search(padrao, texto, flags=re.IGNORECASE)
    return converter_numero(m.group(1)) if m else None


def extrair_dados_texto(texto: str) -> DadosFatura:
    """Procura os números importantes no texto de uma fatura."""
    d = DadosFatura()
    texto = texto.replace(" ", " ")

    d.potencia_kva = _primeiro(r"(\d{1,2}[.,]\d{1,2})\s*kVA", texto)

    # Consumo: preferir uma linha que diga "consumo"; senão, o maior valor em kWh plausível.
    d.consumo_kwh = _primeiro(r"consumo[^\n\d]{0,60}" + _NUM + r"\s*kWh", texto)
    if d.consumo_kwh is None:
        candidatos = [converter_numero(x) for x in re.findall(_NUM + r"\s*kWh(?!\s*/)", texto)]
        candidatos = [c for c in candidatos if c and 5 <= c <= 5000]
        d.consumo_kwh = max(candidatos) if candidatos else None

    d.preco_kwh = _primeiro(r"(0[.,]\d{3,6})\s*€?\s*/\s*kWh", texto)
    d.termo_fixo_dia = _primeiro(r"(0[.,]\d{3,6})\s*€?\s*/\s*dia", texto)
    d.total = _primeiro(r"total\s*(?:a\s*pagar)?[^\n\d]{0,30}(\d{1,4}[.,]\d{2})\s*€?", texto)

    datas = re.findall(r"(\d{2}[/-]\d{2}[/-]\d{4})", texto)
    m = re.search(r"per[ií]odo[^\n]{0,40}?(\d{2}[/-]\d{2}[/-]\d{4})[^\n\d]{1,10}(\d{2}[/-]\d{2}[/-]\d{4})",
                  texto, flags=re.IGNORECASE)
    if m:
        datas = [m.group(1), m.group(2)]
    if len(datas) >= 2:
        try:
            ini, fim = (datetime.strptime(x.replace("-", "/"), "%d/%m/%Y") for x in datas[:2])
            dias = (fim - ini).days + 1
            if 20 <= dias <= 70:
                d.dias = dias
        except ValueError:
            pass
    return d


def ler_fatura_pdf(conteudo: bytes) -> tuple[DadosFatura, str]:
    """Devolve os dados encontrados e o texto bruto (útil para depurar)."""
    import pdfplumber

    with pdfplumber.open(io.BytesIO(conteudo)) as pdf:
        texto = "\n".join(pagina.extract_text() or "" for pagina in pdf.pages)
    return extrair_dados_texto(texto), texto


# ---------------------------------------------------------------------------
# Comparação de ofertas
# ---------------------------------------------------------------------------

def carregar_ofertas(caminho: Path | None = None) -> pd.DataFrame:
    caminho = caminho or PASTA_DADOS / "ofertas_luz.csv"
    return pd.read_csv(caminho)


def custo_periodo(consumo_kwh: float, dias: int, termo_fixo_dia: float, preco_kwh: float) -> float:
    return termo_fixo_dia * dias + preco_kwh * consumo_kwh


def comparar(consumo_kwh: float, potencia_kva: float, ofertas: pd.DataFrame,
             custo_atual: float | None = None, dias: int = 30) -> pd.DataFrame:
    """Ordena as ofertas para a potência indicada, da mais barata para a mais cara.

    O custo é sempre convertido para um mês médio (30,4 dias) para dar para comparar
    faturas com períodos diferentes.
    """
    disponiveis = ofertas[(ofertas["potencia_kva"] - potencia_kva).abs() < 0.01].copy()
    if disponiveis.empty:
        return disponiveis
    fator_mes = 30.4 / dias
    disponiveis["custo_mensal"] = [
        round(custo_periodo(consumo_kwh, dias, r.termo_fixo_eur_dia, r.preco_kwh) * fator_mes, 2)
        for r in disponiveis.itertuples()
    ]
    disponiveis["custo_anual"] = (disponiveis["custo_mensal"] * 12).round(2)
    if custo_atual is not None:
        atual_mensal = custo_atual * fator_mes
        disponiveis["poupanca_anual"] = ((atual_mensal - disponiveis["custo_mensal"]) * 12).round(2)
    return disponiveis.sort_values("custo_mensal").reset_index(drop=True)
