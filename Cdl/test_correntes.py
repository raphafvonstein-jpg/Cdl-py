import ast
from pathlib import Path

import numpy as np
import pandas as pd


def carregar_funcoes():
    arvore = ast.parse(Path(__file__).with_name("app.py").read_text(encoding="utf-8"))
    nomes = {
        "calcular_potencial_extracao",
        "interpolar_ia_ic",
        "extrair_ultimo_scan",
        "detectar_coluna_scan",
    }
    modulo = ast.Module(
        body=[no for no in arvore.body if isinstance(no, ast.FunctionDef) and no.name in nomes],
        type_ignores=[],
    )
    namespace = {"np": np, "pd": pd}
    exec(compile(modulo, "app.py", "exec"), namespace)
    return namespace


FUNCOES = carregar_funcoes()
calcular_potencial_extracao = FUNCOES["calcular_potencial_extracao"]
interpolar_ia_ic = FUNCOES["interpolar_ia_ic"]
extrair_ultimo_scan = FUNCOES["extrair_ultimo_scan"]
detectar_coluna_scan = FUNCOES["detectar_coluna_scan"]


def test_usa_correntes_medidas_no_potencial_central():
    x = np.array([-0.2, 0.0, 0.2, 0.0, -0.2])
    y = np.array([1.0, 4.0, 2.0, -3.0, -1.0])
    alvo, _, _ = calcular_potencial_extracao(x)

    assert alvo == 0.0
    assert interpolar_ia_ic(x, y, alvo) == (4.0, -3.0)


def test_interpola_cada_ramo_quando_o_central_nao_foi_medido():
    x = np.array([-0.2, -0.1, 0.1, 0.2, 0.1, -0.1, -0.2])
    y = np.array([0.0, 2.0, 6.0, 8.0, -2.0, -6.0, -8.0])
    alvo, _, _ = calcular_potencial_extracao(x)

    assert alvo == 0.0
    assert interpolar_ia_ic(x, y, alvo) == (4.0, -4.0)


def test_correntes_iguais_continuam_sendo_dois_ramos_validos():
    x = np.array([-1.0, 0.0, 1.0, 0.0, -1.0])
    y = np.array([0.0, 2.0, 0.0, 2.0, 0.0])

    assert interpolar_ia_ic(x, y, 0.0) == (2.0, 2.0)


def test_encontra_ambas_as_correntes_independentemente_da_ordem_da_varredura():
    x = np.array([0.2, 0.0, -0.2, 0.0, 0.2])
    y = np.array([1.0, -5.0, -1.0, 3.0, 1.0])

    assert interpolar_ia_ic(x, y, 0.0) == (3.0, -5.0)


def test_cada_arquivo_usa_seu_proprio_potencial_central():
    arquivo_1_x = np.array([-0.2, 0.0, 0.2, 0.0, -0.2])
    arquivo_1_y = np.array([0.0, 2.0, 0.0, -2.0, 0.0])
    arquivo_2_x = np.array([0.1, 0.3, 0.5, 0.3, 0.1])
    arquivo_2_y = np.array([0.0, 8.0, 0.0, -6.0, 0.0])

    alvo_1, _, _ = calcular_potencial_extracao(arquivo_1_x)
    alvo_2, _, _ = calcular_potencial_extracao(arquivo_2_x)

    assert np.isclose(alvo_1, 0.0)
    assert np.isclose(alvo_2, 0.3)
    assert interpolar_ia_ic(arquivo_1_x, arquivo_1_y, alvo_1) == (2.0, -2.0)
    assert interpolar_ia_ic(arquivo_2_x, arquivo_2_y, alvo_2) == (8.0, -6.0)


def test_ultimo_scan_e_delimitado_pelos_retornos_e_nao_por_linhas():
    # Três ciclos, com quantidades diferentes de pontos em cada ramo.
    potencial = [
        0.0, 1.0, 0.0, -1.0,
        0.0, 0.5, 1.0, 0.5, 0.0, -0.5, -1.0,
        -0.5, 0.0, 0.5, 1.0, 0.0, -1.0,
    ]
    df = pd.DataFrame({"E": potencial, "I": np.arange(len(potencial))})

    ultimo, info = extrair_ultimo_scan(df, col_potencial="E")

    assert np.isclose(ultimo["E"].min(), -1.0)
    assert np.isclose(ultimo["E"].max(), 1.0)
    assert len(ultimo) != len(df) // 3
    assert "inversões" in info


def test_segmento_nao_e_confundido_com_ciclo_completo():
    df = pd.DataFrame({"Segment": [1, 2], "Potential": [0.0, 1.0]})

    assert detectar_coluna_scan(df) is None


def test_completa_passagem_quando_scan_termina_logo_antes_do_centro():
    x = np.array([-0.03, 0.17, -0.24, -0.037])
    y = np.array([4.0, 10.0, -10.0, 1.0])
    alvo = -0.035

    ia, ic = interpolar_ia_ic(x, y, alvo)

    assert np.isfinite(ia)
    assert np.isfinite(ic)
