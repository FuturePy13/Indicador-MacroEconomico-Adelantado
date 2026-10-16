"""Prueba de src/datos.py con un Yahoo FALSO y una carpeta temporal.

No usa internet ni toca tus datos reales.
Ejecutar desde la raíz del proyecto:  python -m tests.test_datos
"""
import sys
import tempfile
import types
from pathlib import Path

import numpy as np
import pandas as pd

# --- 1) Carpeta temporal: se cambia ANTES de importar datos.py -------------
import config

TEMP = Path(tempfile.mkdtemp())
config.DATA_RAW = TEMP / "raw"
config.DATA_PROCESSED = TEMP / "processed"
config.ARCHIVO_CIERRE = config.DATA_RAW / "cierre.parquet"
config.ARCHIVO_MAXIMO_DIA = config.DATA_RAW / "maximo_dia.parquet"
config.ARCHIVO_MINIMO_DIA = config.DATA_RAW / "minimo_dia.parquet"
config.ARCHIVO_PESOS = config.DATA_RAW / "pesos.csv"

# --- 2) Si no hay pyarrow, se usa pickle solo para esta prueba -------------
try:
    import pyarrow  # noqa: F401
except ImportError:
    pd.read_parquet = lambda p, *a, **k: pd.read_pickle(p)
    pd.DataFrame.to_parquet = lambda self, p, *a, **k: self.to_pickle(p)

# --- 3) Yahoo falso -------------------------------------------------------
MUNDO = {"df": None, "hasta": None}


def construir_mundo(tickers, fin, semilla=0):
    rng = np.random.default_rng(semilla)
    dias = pd.bdate_range("2015-01-01", fin)
    cierre = pd.DataFrame(
        100 * np.exp(np.cumsum(rng.normal(0.0005, 0.015, (len(dias), len(tickers))), axis=0)),
        index=dias,
        columns=tickers,
    )
    return {"Close": cierre, "High": cierre * 1.01, "Low": cierre * 0.99}


def fake_download(tickers, start=None, period=None, auto_adjust=True, progress=False, threads=True):
    tickers = [tickers] if isinstance(tickers, str) else list(tickers)
    partes = {}
    for campo, tabla in MUNDO["df"].items():
        sub = tabla.loc[: MUNDO["hasta"]]
        if start:
            sub = sub.loc[start:]
        sub = sub.reindex(columns=tickers)  # empresa desconocida -> NaN, como Yahoo
        sub.index = sub.index.tz_localize("America/New_York")
        partes[campo] = sub
    return pd.concat(partes, axis=1)


yf_falso = types.ModuleType("yfinance")
yf_falso.download = fake_download
sys.modules["yfinance"] = yf_falso

from src import datos  # noqa: E402


def comprobar(condicion, mensaje):
    print(("OK   " if condicion else "FALLA"), mensaje)
    if not condicion:
        raise SystemExit(1)


# --- 4) Escenarios ----------------------------------------------------------
TICKERS = ["AAA", "BBB", "CCC", "DDD"]

# Corrida 1: descarga completa
MUNDO["df"] = construir_mundo(TICKERS + ["NUEVA"], "2026-10-30")
MUNDO["hasta"] = pd.Timestamp("2026-10-02")
r1 = datos.actualizar(TICKERS + ["ZZZZ"])  # ZZZZ no existe
c1 = r1["cierre"]
comprobar(set(c1.columns) == set(TICKERS), "corrida 1: guarda las 4 empresas y descarta la inexistente")
comprobar(c1.index.max() == pd.Timestamp("2026-10-02"), "corrida 1: llega hasta el 2 de octubre")
comprobar(c1.index.tz is None, "corrida 1: las fechas quedan sin zona horaria")

# Corrida 2: 7 días después, con datos corregidos, un ajuste, una empresa nueva y un hueco
MUNDO["hasta"] = pd.Timestamp("2026-10-09")
mundo2 = {k: v.copy() for k, v in MUNDO["df"].items()}
ultimo_dia = pd.Timestamp("2026-10-02")
for campo in mundo2:  # el último día guardado estaba provisional: ahora cambia
    mundo2[campo].loc[ultimo_dia, "AAA"] *= 1.02
for campo in mundo2:  # CCC paga un dividendo: se ajusta toda su historia anterior
    mundo2[campo].loc[:"2026-10-06", "CCC"] *= 0.99
MUNDO["df"] = mundo2
viejo_BBB = c1["BBB"].copy()
viejo_AAA = c1["AAA"].copy()

r2 = datos.actualizar(TICKERS + ["NUEVA"])
c2 = r2["cierre"]
comprobar(c2.index.max() == pd.Timestamp("2026-10-09"), "corrida 2: agrega los días nuevos hasta el 9 de octubre")
comprobar(set(c2.columns) == set(TICKERS + ["NUEVA"]), "corrida 2: incluye la empresa nueva")
comprobar(c2["NUEVA"].first_valid_index() == pd.Timestamp("2015-01-01"), "corrida 2: la empresa nueva trae toda su historia")
comprobar(np.isclose(c2.loc[ultimo_dia, "AAA"], viejo_AAA.loc[ultimo_dia] * 1.02), "corrida 2: el día provisional se corrigió con el solape")
comprobar(np.allclose(c2.loc[: "2026-09-01", "BBB"], viejo_BBB.loc[: "2026-09-01"]), "corrida 2: lo viejo sin cambios se conserva")
esperada_CCC = mundo2["Close"]["CCC"].loc[:"2026-10-09"]
comprobar(np.allclose(c2["CCC"].dropna(), esperada_CCC), "corrida 2: CCC se re-descargó completa por el ajuste de dividendo")
comprobar(len(r2["maximo"]) == len(c2) and len(r2["minimo"]) == len(c2), "corrida 2: máximo y mínimo tienen las mismas fechas que el cierre")
comprobar((r2["maximo"].fillna(0) >= c2.fillna(0) - 1e-9).all().all(), "corrida 2: el máximo del día nunca es menor al cierre")

# Corrida 3: sin cambios en el mundo, nada debería moverse
r3 = datos.actualizar(TICKERS + ["NUEVA"])
comprobar(r3["cierre"].equals(c2), "corrida 3: sin novedades, los datos quedan idénticos")

# Corrida 4: forzar descarga completa
r4 = datos.actualizar(TICKERS + ["NUEVA"], forzar_completo=True)
comprobar(r4["cierre"].shape == c2.shape, "corrida 4: la descarga completa forzada da la misma forma")

# Corrida 5: una empresa quedó con huecos (sus datos guardados se cortaron en agosto)
cierre_g, maximo_g, minimo_g = datos.cargar_precios()
for nombre, tabla in (("cierre", cierre_g), ("maximo", maximo_g), ("minimo", minimo_g)):
    tabla.loc["2026-08-01":, "DDD"] = np.nan
    tabla.to_parquet(datos.ARCHIVOS[nombre])
r5 = datos.actualizar(TICKERS + ["NUEVA"])
comprobar(r5["cierre"]["DDD"].last_valid_index() == pd.Timestamp("2026-10-09"), "corrida 5: la empresa con huecos se completó")
comprobar(r5["cierre"].shape == c2.shape, "corrida 5: no se perdió ni se duplicó nada")

print("\nTodas las pruebas pasaron. Carpeta temporal:", TEMP)
