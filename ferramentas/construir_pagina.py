"""Gera a página que corre o BillWatch inteiro no browser, sem servidor (stlite + Pyodide).

A página leva lá dentro o código da app, os dados e o tema (com as letras). Quem a abre
descarrega o stlite e o Python da jsDelivr, e algumas bibliotecas do PyPI; os extratos que se
carregam na app são lidos no browser e não saem do computador.

    python ferramentas/construir_pagina.py [pasta]          (por omissão: _site)

Gera, prontos para o GitHub Pages:
  pasta/index.html   a app (também funciona aberta diretamente do disco)
  pasta/404.html     volta à página principal (ver mais abaixo)
  pasta/.nojekyll    para o GitHub Pages servir os ficheiros tal como estão
"""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from urllib.parse import urlparse

RAIZ = Path(__file__).resolve().parent.parent
MODELO = Path(__file__).with_name("pagina.html")

STLITE = "1.12.3"   # traz o Streamlit 1.65 e o Pyodide 314.0.3 (Python 3.14)
# Do Pyodide: pandas, numpy, altair, python-calamine (Excel) e lxml (".xls" que são HTML).
# Do PyPI: pdfminer.six, na versão exata que o pdfplumber pede.
REQUISITOS = ["pdfminer.six==20260107", "python-calamine", "lxml"]
# O pdfplumber pede o pypdfium2, que não existe para o browser e só serve para desenhar páginas
# como imagem (a app não usa). Instala-se sem dependências, depois de o Python carregar.
SEM_DEPENDENCIAS = ["pdfplumber==0.11.10"]

FICHEIROS = ["app.py", "contas/*.py", "ui/*.py", "paginas/*.py", "dados/ofertas_luz.csv",
             "static/logo.svg", "static/favicon.png", "static/fontes/LICENCA-*.txt"]
BINARIOS = (".png",)

# Aqui os ficheiros nem saem do computador, e os textos sobre privacidade passam a dizê-lo.
TEXTOS = {
    "paginas/subscricoes.py": [
        ('discreto("Os ficheiros são lidos em memória e nunca são guardados.")',
         'discreto("Os ficheiros são lidos neste browser e nunca saem do teu computador.")'),
    ],
    "ui/componentes.py": [
        ("f'em memória e nunca são guardados. <a href=",
         "f'neste browser e nunca saem do teu computador. <a href="),
    ],
    "paginas/sobre.py": [
        ('"Os ficheiros são lidos em memória, só para fazer as contas, e nunca são guardados. "',
         '"Esta versão corre toda no teu browser: os ficheiros são lidos aqui, só para fazer as contas, '
         'e nunca saem do teu computador. "'),
        ('"As fontes da app também são servidas pela própria app, sem pedidos a terceiros."',
         '"Da internet só vem o código da app (o Python e as bibliotecas, da jsDelivr e do PyPI); '
         'os teus extratos nunca são enviados."'),
    ],
}

DESCRICAO = ("Descobre quanto pagas todos os meses e onde estás a pagar a mais. "
             "A app corre no teu browser: os extratos não saem do computador.")

# O Streamlit põe o nome da página no endereço (…/billwatch/luz). Ao recarregar, o GitHub Pages
# não tem esse ficheiro e mostra o 404.html, que volta à página principal da app.
PAGINA_404 = """<!DOCTYPE html>
<html lang="pt">
<head>
<meta charset="utf-8">
<meta name="robots" content="noindex">
<title>BillWatch</title>
<script>if (location.pathname !== "__BASE__") location.replace("__BASE__");</script>
</head>
<body><p>Esta página não existe. <a href="__BASE__">Abrir o BillWatch</a></p></body>
</html>
"""


def repositorio() -> str:
    return os.environ.get("GITHUB_REPOSITORY", "tiagorodrigues04/billwatch")


def endereco() -> str:
    """Onde a página fica no GitHub Pages: https://<dono>.github.io/<repositório>/."""
    dono, nome = repositorio().split("/")
    return f"https://{dono.lower()}.github.io/{nome}/"


def versao() -> str:
    try:
        return subprocess.run(["git", "-C", str(RAIZ), "rev-parse", "--short", "HEAD"],
                              check=True, capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "local"


def tema() -> str:
    """O config.toml com as letras lá dentro: sem servidor, não há 'app/static/' para as servir."""
    config = (RAIZ / ".streamlit/config.toml").read_text(encoding="utf-8")

    def embutir(m: re.Match) -> str:
        dados = base64.b64encode((RAIZ / m.group(1).removeprefix("app/")).read_bytes()).decode("ascii")
        return f'url = "data:font/woff2;base64,{dados}"'

    config, n = re.subn(r'url = "(app/static/fontes/[^"]+\.woff2)"', embutir, config)
    if n == 0 or "app/static" in config:
        raise SystemExit("O tema mudou: confirma como as letras estão em .streamlit/config.toml")
    config = config.replace("enableStaticServing = true", "enableStaticServing = false")
    tomllib.loads(config)   # tem de continuar a ser TOML válido
    return config


def ficheiros_da_app() -> dict[str, object]:
    ficheiros: dict[str, object] = {}
    for padrao in FICHEIROS:
        caminhos = sorted(RAIZ.glob(padrao))
        if not caminhos:
            raise SystemExit(f"Não encontrei {padrao}")
        for caminho in caminhos:
            nome = caminho.relative_to(RAIZ).as_posix()
            if nome.endswith(BINARIOS):
                ficheiros[nome] = {"b64": base64.b64encode(caminho.read_bytes()).decode("ascii")}
                continue
            texto = caminho.read_text(encoding="utf-8")
            for antes, depois in TEXTOS.get(nome, []):
                if texto.count(antes) != 1:
                    raise SystemExit(f"{nome}: o texto sobre privacidade mudou; atualiza TEXTOS em {__file__}")
                texto = texto.replace(antes, depois)
            ficheiros[nome] = texto
    ficheiros[".streamlit/config.toml"] = tema()
    return ficheiros


def pagina() -> str:
    ficheiros = ficheiros_da_app()
    # Dentro de <script type="application/json"> nada pode parecer uma etiqueta HTML.
    embutidos = json.dumps(ficheiros, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    html = MODELO.read_text(encoding="utf-8")
    for marca, valor in {
        "__FICHEIROS__": embutidos,
        "__FAVICON__": ficheiros["static/favicon.png"]["b64"],
        "__STLITE__": STLITE,
        "__COMMIT__": versao(),
        "__REQUISITOS__": json.dumps(REQUISITOS),
        "__SEM_DEPENDENCIAS__": json.dumps(SEM_DEPENDENCIAS),
        "__DESCRICAO__": DESCRICAO,
        "__SITE__": endereco(),
        "__IMAGEM__": f"https://raw.githubusercontent.com/{repositorio()}/main/docs/talao.png",
    }.items():
        if marca not in html:
            raise SystemExit(f"{MODELO.name}: falta a marca {marca}")
        html = html.replace(marca, valor)
    return html


def construir(pasta: Path) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    html = pagina()
    (pasta / "index.html").write_text(html, encoding="utf-8")
    (pasta / "404.html").write_text(PAGINA_404.replace("__BASE__", urlparse(endereco()).path), encoding="utf-8")
    (pasta / ".nojekyll").write_text("", encoding="utf-8")
    return pasta / "index.html"


if __name__ == "__main__":
    indice = construir(Path(sys.argv[1] if len(sys.argv) > 1 else RAIZ / "_site"))
    print(f"{indice}: {indice.stat().st_size / 1024:.0f} KB, para {endereco()}")
