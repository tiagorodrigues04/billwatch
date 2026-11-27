"""Telemetria (ui/telemetria.py): o que sai para o PostHog é anónimo, só uma vez e só se a pessoa deixar.

Os testes usam um cliente PostHog verdadeiro com send=False: os eventos passam pelo before_send
(a limpeza que vai mesmo para produção), mas nada sai para a rede.
"""

from pathlib import Path

import pytest

AppTest = pytest.importorskip("streamlit.testing.v1").AppTest
posthog = pytest.importorskip("posthog")
APP = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture()
def enviados(monkeypatch):
    """Liga a telemetria com um cliente que guarda os eventos em vez de os enviar."""
    import ui.telemetria as telemetria
    eventos: list[dict] = []

    def guardar(evento):
        eventos.append(telemetria.limpar_evento(evento))
        return None   # None: o evento não segue para lado nenhum

    cliente = posthog.Posthog("phc_teste", host=telemetria.HOST_PADRAO, send=False, sync_mode=True,
                              before_send=guardar, disable_geoip=True)
    monkeypatch.setattr(telemetria, "_cliente", lambda: cliente)
    return eventos


def _ficheiro(texto: str, file_id: str = "id-1"):
    from ui.extratos import FicheiroGuardado
    dados = texto.encode()
    return FicheiroGuardado("Extrato do Tiago.csv", len(dados), file_id, dados)


def _nomes(eventos):
    return [e["event"] for e in eventos]


def test_limpar_evento_anonimiza_a_mensagem_e_tira_as_variaveis():
    from ui.telemetria import limpar_evento
    evento = {"event": "$exception", "properties": {"$exception_list": [
        {"type": "ValueError", "value": "could not convert string to float: 'NETFLIX 12,34 Tiago'",
         "stacktrace": {"frames": [{"function": "f", "vars": {"extrato": "dados"}}]}}]}}
    excecao = limpar_evento(evento)["properties"]["$exception_list"][0]
    assert "NETFLIX" not in excecao["value"] and "Tiago" not in excecao["value"] and "12,34" not in excecao["value"]
    assert excecao["type"] == "ValueError"
    assert "vars" not in excecao["stacktrace"]["frames"][0]


def test_sem_chave_nao_envia_nada():
    import ui.telemetria as telemetria
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    assert not telemetria.disponivel()


def test_paginas_contadas_so_quando_se_muda(enviados):
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.run()                                       # um clique qualquer: a mesma página
    at.switch_page("paginas/luz.py").run()
    assert not at.exception
    paginas = [e["properties"]["pagina"] for e in enviados if e["event"] == "pagina_aberta"]
    assert paginas == ["Contas fixas", "Luz"]
    assert all(e["properties"]["$process_person_profile"] is False for e in enviados)
    assert len({e["distinct_id"] for e in enviados}) == 1      # o mesmo código ao acaso na sessão


def test_ficheiros_lidos_so_formato_e_quantidade(enviados):
    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state["_extratos_guardados"] = [_ficheiro(
        "Data;Descrição;Montante\n01/03/2026;NETFLIX;-9,99\n01/04/2026;NETFLIX;-9,99\n")]
    at.run()
    at.run()
    assert not at.exception
    lidos = [e["properties"] for e in enviados if e["event"] == "extratos_lidos"]
    assert len(lidos) == 1                         # o segundo clique não volta a contar
    assert lidos[0]["ficheiros"] == 1 and lidos[0]["lidos"] == 1 and lidos[0]["formatos"] == ["csv"]
    assert "Tiago" not in str(enviados) and "NETFLIX" not in str(enviados)


def test_erro_inesperado_ao_ler_vai_anonimizado(enviados, monkeypatch):
    import ui.leitura

    def rebenta(conteudo, nome=""):
        raise RuntimeError("linha 'MB WAY PARA RITA COSTA 25,00' estranha")

    monkeypatch.setattr(ui.leitura, "ler_extrato", rebenta)
    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state["_extratos_guardados"] = [_ficheiro("Data;Descrição;Montante\n01/03/2026;X;-1\n")]
    at.run()
    at.run()
    assert not at.exception                        # a pessoa continua a ver só a mensagem simpática
    erros = [e for e in enviados if e["event"] == "$exception"]
    assert len(erros) == 1
    assert erros[0]["properties"]["onde"] == "ler_ficheiro" and erros[0]["properties"]["formato"] == "csv"
    excecao = erros[0]["properties"]["$exception_list"][0]
    assert excecao["type"] == "RuntimeError" and "RITA" not in excecao["value"] and "25,00" not in excecao["value"]
    motivos = [e["properties"]["motivo"] for e in enviados if e["event"] == "ficheiro_nao_lido"]
    assert motivos == ["erro_inesperado"]


def test_erro_numa_pagina_e_registado_e_continua_a_aparecer(enviados, monkeypatch):
    import ui.dados

    def rebenta(*args, **kwargs):
        raise ValueError("Tiago Rodrigues 123")

    monkeypatch.setattr(ui.dados, "analisar", rebenta)
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert at.exception                            # o Streamlit mostra o erro, como antes
    erros = [e for e in enviados if e["event"] == "$exception"]
    assert len(erros) == 1 and erros[0]["properties"]["onde"] == "pagina"
    assert erros[0]["properties"]["pagina"] == "Contas fixas"
    # A mensagem vai anonimizada; as linhas de código que acompanham o erro são o código da app, não dados.
    assert erros[0]["properties"]["$exception_list"][0]["value"] == "xxxxx xxxxxxxxx 999"


def test_desligar_na_pagina_como_funciona(enviados):
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.switch_page("paginas/sobre.py").run()
    assert not at.exception
    assert any("PostHog" in m.value for m in at.markdown)
    at.toggle(key="telemetria").set_value(False).run()
    antes = len(enviados)
    at.switch_page("paginas/luz.py").run()
    at.switch_page("paginas/subscricoes.py").run()
    assert not at.exception
    assert len(enviados) == antes                  # desligado: nada mais sai
    at.switch_page("paginas/sobre.py").run()
    assert at.toggle(key="telemetria").value is False   # e continua desligado ao voltar


def test_sem_o_pacote_posthog_como_no_browser_fica_desligada(monkeypatch):
    import sys

    import ui.telemetria as telemetria
    monkeypatch.setenv(telemetria.VARIAVEL_CHAVE, "phc_teste")
    monkeypatch.setitem(sys.modules, "posthog", None)     # "import posthog" falha, como no stlite
    telemetria._cliente.clear()
    try:
        assert telemetria._cliente() is None
    finally:
        telemetria._cliente.clear()
