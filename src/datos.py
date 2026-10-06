import sys
from datetime import datetime

import pandas as pd 
import yfinance as yf 

import config

CAMPOS = {"cierre": "Close", "maximo":"High", "minimo":"Low"}
ARCHIVOS = {
    "cierre":config.ARCHIVO_CIERRE,
    "maximo":config.ARCHIVO_MAXIMO_DIA,
    "minimo":config.ARCHIVO_MINIMO_DIA
}

TOLERANCIA_AJUSTE = 0.001
INTENTOS = 3

#Lista de Empresas 

def _a_yahoo(ticker):
    return str(ticker).strip().replace(".","-")

def _tickers_wikipedia():
    from io import StringIO

    import requests

    html = requests.get(
        "https://en.wikipedia.org/wiki/Nasdaq-100",
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    ).text
    tablas = pd.read_html(StringIO(html))
    comp = [t for t in tablas if "Ticker" in t.columns][0]
    return comp["Ticker"].tolist()

def cargar_tickers():
    if config.ARCHIVO_PESOS.exists():
        return pd.read_csv(config.ARCHIVO_PESOS)["ticker"].dropna().tolist()
    print("Todavia no existe pesos.csv: uso la lista de wikipedia por ahora")
    return _tickers_wikipedia()

#Descarga
def _descargar(tickers, inicio=None):
    if not tickers:
        return {nombre: pd.DataFrame() for nombre in CAMPOS}
    pedido = {"start": inicio} if inicio else {"period": "max"}
    datos = None
    for intento in range(1, INTENTOS + 1):
        try:
            datos = yf.download(
                tickers, auto_adjust=True, progress=False, threads=True, **pedido
            )
        except Exception as error:
            print(f"Intento {intento} falló: {error}")
            datos = None
        if datos is None or datos.empty:
            break
    if datos is None or datos.empty:
        raise RuntimeError("Yahoo no devolvio datos")
        
    resultado = {}
    for nombre, campos in CAMPOS.items():
        if isinstance(datos.columns, pd.MultiIndex):
            df = datos[campos].copy()
        else:
            df = datos[[campos]].rename(columns={campos:tickers[0]})
        df.index = pd.to_datetime(df.index)
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        df.index = df.index.normalize()
        resultado[nombre] = df.dropna(how="all").dropna(axis=1, how="all")
    return resultado

#Lectura y Combinacion 
def _hay_datos_guardados():
    return all(archivo.exists() for archivo in ARCHIVOS.values())

def cargar_precios():
    return tuple(pd.read_parquet(ARCHIVOS[n] for n in ("cierre", "maximo", "minimo")))