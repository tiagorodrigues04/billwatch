"""Mede a qualidade da deteção de subscrições em extratos rotulados.

    python -m avaliacao.avaliar            # 300 extratos, imprime a tabela de resultados
    python -m avaliacao.avaliar --n 1000   # mais extratos
    python -m avaliacao.avaliar --erros    # mostra também os erros, para os corrigir

Como se conta:
- Cada linha que a app põe no talão é comparada com os rótulos dos movimentos que a formam.
  Se a maioria desses movimentos pertence a uma subscrição verdadeira (ainda não encontrada),
  é um acerto. Senão é um falso positivo.
- Precisão = acertos / linhas que a app mostrou   ("quando diz que é subscrição, acerta?")
- Recall   = acertos / subscrições verdadeiras    ("das que existem, quantas encontra?")
- Erro no custo = diferença média entre o "por mês" da app e o verdadeiro, nos acertos.
"""

from __future__ import annotations

import argparse
import re
from collections import Counter
from dataclasses import dataclass, field

import pandas as pd

from avaliacao.gerar import gerar_pessoa
from contas.recorrentes import detetar_recorrentes, preparar

_SUFIXO = re.compile(r" \((\d[\d ]*,\d{2}) €\)$")   # "Apple (0,99 €)" = subgrupo por valor


@dataclass
class Resultado:
    verdadeiros_positivos: int = 0
    falsos_positivos: int = 0
    falsos_negativos: int = 0
    erros_custo: list[float] = field(default_factory=list)
    estado_certo: int = 0                 # ativa/cancelada bem identificada (nos acertos)
    subidas: int = 0
    subidas_avisadas: int = 0
    avisos_falsos: int = 0                # "preço subiu" numa subscrição cujo preço não mudou
    sem_subida: int = 0
    por_tipo: dict[str, Counter] = field(default_factory=lambda: {"catalogo": Counter(), "fora": Counter()})
    exemplos_fp: list[str] = field(default_factory=list)
    exemplos_fn: list[str] = field(default_factory=list)

    @property
    def precisao(self) -> float:
        total = self.verdadeiros_positivos + self.falsos_positivos
        return self.verdadeiros_positivos / total if total else 1.0

    @property
    def recall(self) -> float:
        total = self.verdadeiros_positivos + self.falsos_negativos
        return self.verdadeiros_positivos / total if total else 1.0

    @property
    def f1(self) -> float:
        p, r = self.precisao, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0


def _movimentos_da_linha(preparados: pd.DataFrame, comerciante: str, categoria: str) -> pd.DataFrame:
    mesma = preparados[preparados["categoria"] == categoria]
    m = _SUFIXO.search(comerciante)
    if not m:
        return mesma[mesma["comerciante"] == comerciante]
    base = comerciante[: m.start()]
    valor = float(m.group(1).replace(" ", "").replace(",", "."))
    return mesma[(mesma["comerciante"] == base) & (mesma["montante"].round(2) == valor)]


def avaliar(n: int = 300, semente: int = 0) -> Resultado:
    res = Resultado()
    for pessoa in range(n):
        extrato, verdades = gerar_pessoa(pessoa, semente)
        por_id = {v.id: v for v in verdades}
        encontradas: set[str] = set()
        recorrentes = detetar_recorrentes(extrato[["data", "descricao", "valor"]])
        preparados = preparar(extrato)   # mantém a coluna "rotulo"

        for linha in recorrentes.itertuples() if not recorrentes.empty else []:
            rotulos = _movimentos_da_linha(preparados, linha.comerciante, linha.categoria)["rotulo"]
            mais_comum, vezes = Counter(rotulos).most_common(1)[0] if len(rotulos) else ("", 0)
            if mais_comum and vezes / len(rotulos) >= 0.5 and mais_comum not in encontradas:
                encontradas.add(mais_comum)
                v = por_id[mais_comum]
                res.verdadeiros_positivos += 1
                res.erros_custo.append(abs(linha.custo_mensal - v.custo_mensal))
                res.estado_certo += int(linha.ativa == v.ativa)
                avisou = any("subiu" in a for a in linha.alertas)
                if v.subiu_preco:
                    res.subidas_avisadas += int(avisou)
                else:
                    res.sem_subida += 1
                    res.avisos_falsos += int(avisou)
            else:
                res.falsos_positivos += 1
                if len(res.exemplos_fp) < 40:
                    exemplo = rotulos.index[0] if len(rotulos) else None
                    desc = extrato.loc[exemplo, "descricao"] if exemplo is not None else "?"
                    res.exemplos_fp.append(f"{linha.comerciante} ({linha.periodicidade}, "
                                           f"{linha.custo_mensal:.2f} €/mês) ex.: {desc}")

        for v in verdades:
            tipo = "catalogo" if v.no_catalogo else "fora"
            res.por_tipo[tipo]["total"] += 1
            res.subidas += int(v.subiu_preco)
            if v.id in encontradas:
                res.por_tipo[tipo]["encontradas"] += 1
            else:
                res.falsos_negativos += 1
                if len(res.exemplos_fn) < 40:
                    res.exemplos_fn.append(f"{v.nome}: {v.n_pagamentos} pagamentos, {v.custo_mensal:.2f} €/mês")
    return res


def tabela(res: Resultado, n: int) -> str:
    """Tabela em Markdown, pronta para colar no README."""
    def pct(x: float) -> str:
        return f"{100 * x:.1f}%".replace(".", ",")

    cat, fora = res.por_tipo["catalogo"], res.por_tipo["fora"]
    mae = sum(res.erros_custo) / len(res.erros_custo) if res.erros_custo else 0.0
    linhas = [
        "| Métrica | Valor |",
        "|---|---|",
        f"| Extratos avaliados | {n} |",
        f"| Subscrições verdadeiras | {res.verdadeiros_positivos + res.falsos_negativos} |",
        f"| **Precisão** | **{pct(res.precisao)}** |",
        f"| **Recall** | **{pct(res.recall)}** |",
        f"| F1 | {pct(res.f1)} |",
        f"| Recall, comerciantes do catálogo | {pct(cat['encontradas'] / cat['total'] if cat['total'] else 1)} |",
        f"| Recall, comerciantes desconhecidos | {pct(fora['encontradas'] / fora['total'] if fora['total'] else 1)} |",
        f"| Erro médio no custo por mês | {mae:.2f} €".replace(".", ",") + " |",
        f"| Ativa / cancelada certa | {pct(res.estado_certo / res.verdadeiros_positivos if res.verdadeiros_positivos else 1)} |",
        f"| Subidas de preço avisadas | {pct(res.subidas_avisadas / res.subidas if res.subidas else 1)} |",
        f"| Avisos de subida falsos | {res.avisos_falsos} em {res.sem_subida} subscrições sem subida |",
    ]
    return "\n".join(linhas)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--n", type=int, default=300, help="número de extratos (default 300)")
    parser.add_argument("--semente", type=int, default=0)
    parser.add_argument("--erros", action="store_true", help="mostrar exemplos de erros")
    args = parser.parse_args()
    res = avaliar(args.n, args.semente)
    print(tabela(res, args.n))
    if args.erros:
        print("\nFalsos positivos (a app mostrou, mas não é subscrição):")
        print("\n".join(f"  - {e}" for e in res.exemplos_fp) or "  nenhum")
        print("\nFalsos negativos (era subscrição, a app não viu):")
        print("\n".join(f"  - {e}" for e in res.exemplos_fn) or "  nenhum")


if __name__ == "__main__":
    main()
