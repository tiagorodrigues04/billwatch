"""A página que corre a app no browser (ferramentas/construir_pagina.py) leva tudo o que a app precisa."""

import base64
import json
import re
import sys
import tomllib
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "ferramentas"))

import construir_pagina  # noqa: E402


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    pasta = tmp_path_factory.mktemp("site")
    construir_pagina.construir(pasta)
    return pasta


@pytest.fixture(scope="module")
def html(site):
    return (site / "index.html").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def ficheiros(html):
    bloco = re.search(r'<script type="application/json" id="ficheiros">(.*?)</script>', html, re.S).group(1)
    return json.loads(bloco)


def test_leva_todo_o_codigo_da_app(ficheiros):
    esperados = {p.relative_to(RAIZ).as_posix() for pasta in ("contas", "ui", "paginas") for p in (RAIZ / pasta).glob("*.py")}
    assert esperados | {"app.py", "dados/ofertas_luz.csv", "static/logo.svg", ".streamlit/config.toml"} <= set(ficheiros)
    for nome in ("app.py", "contas/extrato.py", "paginas/subscricoes.py"):
        assert ficheiros[nome].splitlines()[0] == (RAIZ / nome).read_text(encoding="utf-8").splitlines()[0]


def test_binarios_vao_em_base64(ficheiros):
    assert base64.b64decode(ficheiros["static/favicon.png"]["b64"]) == (RAIZ / "static/favicon.png").read_bytes()


def test_tema_com_as_letras_la_dentro(ficheiros):
    config = ficheiros[".streamlit/config.toml"]
    tema = tomllib.loads(config)
    assert "app/static" not in config
    assert tema["server"]["enableStaticServing"] is False
    letras = tema["theme"]["fontFaces"]
    assert letras and all(f["url"].startswith("data:font/woff2;base64,") for f in letras)
    assert {f["family"] for f in letras} == {"Schibsted Grotesk Tabular", "IBM Plex Mono"}


def test_textos_de_privacidade_dizem_que_nada_sai_do_computador(ficheiros):
    assert "nunca saem do teu computador" in ficheiros["paginas/subscricoes.py"]
    assert "nunca saem do teu computador" in ficheiros["ui/componentes.py"]
    assert "Esta versão corre toda no teu browser" in ficheiros["paginas/sobre.py"]
    assert "nunca são guardados" not in ficheiros["paginas/subscricoes.py"]


def test_html_bem_fechado_e_com_as_versoes_fixas(html):
    bloco = re.search(r'id="ficheiros">(.*?)</script>', html, re.S).group(1)
    assert "<" not in bloco                                 # nada lá dentro fecha o <script> antes do tempo
    assert 'const STLITE = "1.12.3"' in html and "@stlite/browser@${STLITE}/build/stlite.js" in html
    assert '"pdfplumber==0.11.10"' in html and "deps: false" in html
    assert not re.search(r"__[A-Z]+__", html)               # todas as marcas do modelo foram trocadas


def test_404_volta_a_pagina_principal(site):
    pagina_404 = (site / "404.html").read_text(encoding="utf-8")
    assert 'location.replace("/billwatch/")' in pagina_404
    assert (site / ".nojekyll").exists()
