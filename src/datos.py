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

def detectar_ajustes(cierre_viejo, cierre_nuevo):
    comunes = cierre_nuevo.index.intersectionI(cierre_viejo.index)
    columnas = [c for c in cierre_nuevo.columns if c in cierre_viejo.columns]
    if len(comunes) == 0 or not columnas:
        return []
    dia = comunes.min()
    diferencia = (cierre_nuevo.loc[dia, columnas] / cierre_viejo.loc[dia, columnas] - 1).abs()
    return diferencia[diferencia > TOLERANCIA_AJUSTE].index.tolist()

def reemplazar_columnas(base, completo):
    if completo.empty:
        return base
    repetidas = [c for c in completo.columns if c in base.columns]
    return base.drop(columns=repetidas).join(completo, how='other')

def ordenar(df):
    df = df[~df.index.duplicated(keep="last")]
    return df.sort_index().sort_index(axis=1)

def actualizar(tickers=None, forzar_completo=False):
    config.DATA_RAW.mkdir(parents=True, exist_ok=True)
    tickers = list(dict.fromkeys(_a_yahoo(t) for t in (tickers or cargar_tickers())))

    if forzar_completo or not _hay_datos_guardados():
        print(f"Descarga completa de {len(tickers)} empresas...")
        guardados = _descargar(tickers)

    else:
        viejo = dict(zip(("cierre", "maximo", "minimo"), cargar_precios()))
        cierre_viejo = viejo["cierre"]
        ultimo = cierre_viejo.index.max()
        inicio = ultimo - pd.tseries.offsets.BDay(config.DIAS_TOMADOS)

        nuevas = [t for t in tickers if t not in cierre_viejo.columns]
        ultimo_por_empresa = cierre_viejo.apply(lambda s: s.last_valid_index())
        rezagadas = [
            t for t in tickers
            if t in cierre_viejo.columns and ultimo_por_empresa[t] < inicio
        ]
        incrementales = [t for t in tickers if t not in nuevas and t not in rezagadas]

        print(f"Actualizando desde {inicio.date()} ({len(incrementales)} empresas)...")
        nuevo = _descargar(incrementales, inicio.strftime("%Y-%m-%d"))

        ajustadas = detectar_ajustes(cierre_viejo, nuevo["cierre"])
        completas = list(dict.fromkeys(nuevas + rezagadas + ajustadas))

        guardados = {n: nuevo[n].combine_first(viejo[n]) for n in viejo}

        if completas:
            print(
                f"Historia completa de {len(completas)} empresa(s):"
                f"{len(nuevas)} nuevas(s), {len(rezagadas)} con huecos, "
                f"{len(ajustadas)} con ajuste por dividendo/split."
            )
            historia = _descargar(completas)
            guardados = {n: reemplazar_columnas(guardados[n], historia[n]) for n in guardados}

    guardados = {n: ordenar(df) for n, df in guardados.items()}
    for nombre, archivo in ARCHIVOS.items():
        guardados[nombre].to_parquet(archivo)

    _resumen(guardados["cierre"], tickers)
    return guardados

def avisar_dia_incompleto(ultimo):
    try:
        from zoneinfo import ZoneInfo
        ahora = datetime.now(ZoneInfo("America/New_York"))
    except Exception:
        return
    if ultimo.date() == ahora.date() and ahora.hour < 17:
        print(
            "AVISO: el ultimo dia puede estar incompleto (el mercado de EE.UU." \
            "aun no ha cerrado o Yahoo no ha publicado el dato final). "
            "Genera el reporte despues del cierre."
        )

def _resumen(cierre, tickers):
    ultimo = cierre.index.max()
    en_archivo = [t for t in tickers if t in cierre.columns]
    sin_datos = [t for t in tickers if t not in cierre.columns]
    ultimo_por_empresa = cierre[en_archivo].apply(lambda s: s.last_valid_index())
    atrasadas = ultimo_por_empresa[ultimo_por_empresa < ultimo].index.tolist()

    print("\n --Resumen--")
    print(f"Fechas: {cierre.index.min().date()} a {ultimo.date()} ({len(cierre)} dias de bolsa)")
    print(f"Empresas con datos: {len(en_archivo)} de {len(tickers)}")
    print("Sin ningun dato:", sin_datos if sin_datos else "ninguna")
    print("Con ultimo dato anterior al ultimo dia:", atrasadas if atrasadas else "ninguna")

    avisar_dia_incompleto(ultimo)

    if __name__ == "__main__":
        actualizar(forzar_completos="--completo" in sys.argv)