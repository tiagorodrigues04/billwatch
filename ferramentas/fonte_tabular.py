"""Gera a "Schibsted Grotesk Tabular": a fonte da app com algarismos tabulares por omissão.

Porquê: com algarismos proporcionais, um "1" é mais estreito do que um "8", e os valores
numa coluna não alinham (1.111,11 € fica mais curto do que 8.888,88 €). No HTML resolve-se
com `font-variant-numeric: tabular-nums` (ver ui/estilo.py), mas as tabelas do Streamlit
(st.dataframe) são desenhadas num canvas, onde o CSS não chega. A solução é a própria fonte
usar, por omissão, os algarismos tabulares que já traz (a feature OpenType "tnum").

Só mudam os 10 algarismos. A feature "tnum" desta fonte também alarga o ponto, a vírgula e
os dois pontos, o que no texto corrido ficaria estranho, e para os valores alinharem chega
que os algarismos tenham todos a mesma largura.

Licença: a Schibsted Grotesk é SIL OFL 1.1 sem nome reservado, por isso pode ser modificada
e redistribuída com a mesma licença (static/fontes/LICENCA-schibsted-grotesk.txt). O nome
interno passa a "Schibsted Grotesk Tabular", para se ver que é uma versão modificada.

Uso (na raiz do projeto):  python ferramentas/fonte_tabular.py
"""

from __future__ import annotations

from pathlib import Path

from fontTools.ttLib import TTFont

PASTA = Path(__file__).resolve().parent.parent / "static" / "fontes"
ORIGEM = PASTA / "schibsted-grotesk-latin-wght-normal.woff2"
DESTINO = PASTA / "schibsted-grotesk-tabular-latin-wght-normal.woff2"
ALGARISMOS = "0123456789"
FAMILIA = "Schibsted Grotesk Tabular"


def formas_tabulares(fonte: TTFont) -> dict[str, str]:
    """{glifo: glifo tabular}, a partir das substituições da feature "tnum"."""
    gsub = fonte["GSUB"].table
    indices = {i for registo in gsub.FeatureList.FeatureRecord if registo.FeatureTag == "tnum"
               for i in registo.Feature.LookupListIndex}
    mapa: dict[str, str] = {}
    for i in indices:
        lookup = gsub.LookupList.Lookup[i]
        for sub in lookup.SubTable:
            if lookup.LookupType == 7:          # lookup "extension": a substituição está lá dentro
                sub = sub.ExtSubTable
            mapa.update(getattr(sub, "mapping", None) or {})
    return mapa


def gerar(origem: Path = ORIGEM, destino: Path = DESTINO) -> Path:
    fonte = TTFont(origem)
    tabulares = formas_tabulares(fonte)
    cmap = fonte.getBestCmap()
    trocas = {ord(c): tabulares[cmap[ord(c)]] for c in ALGARISMOS if cmap[ord(c)] in tabulares}
    if len(trocas) != len(ALGARISMOS):
        raise SystemExit("A fonte não tem forma tabular para todos os algarismos.")
    for tabela in fonte["cmap"].tables:
        for codigo, glifo in trocas.items():
            if codigo in tabela.cmap:
                tabela.cmap[codigo] = glifo

    nome = fonte["name"]
    familia_ps = FAMILIA.replace(" ", "")
    for registo in nome.names:
        texto = registo.toUnicode()
        if registo.nameID in (1, 16):
            registo.string = FAMILIA
        elif registo.nameID in (3, 4):
            registo.string = texto.replace("Schibsted Grotesk", FAMILIA)
        elif registo.nameID in (6, 25):
            registo.string = texto.replace("SchibstedGrotesk", familia_ps)
    nome.setName("Schibsted Grotesk com algarismos tabulares por omissão (gerada por ferramentas/fonte_tabular.py)",
                 10, 3, 1, 0x409)

    fonte.flavor = "woff2"
    fonte.save(destino)
    return destino


if __name__ == "__main__":
    print(f"Gerada: {gerar()}")
