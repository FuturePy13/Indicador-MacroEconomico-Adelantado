from pathlib import Path

#Ubicacion Carpetas 
RAIZ = Path(__file__).parent
DATA_RAW = RAIZ / "data" / "raw"
DATA_PROCCESED = RAIZ / "data" / "proccesed"
CARPETA_DE_REPORTES = RAIZ / "outputs" / "reportes"

#Parametros de maximos y minimos
ARCHIVO_CIERRE = DATA_RAW / "cierre.parquet"
ARCHIVO_MAXIMO_DIA = DATA_RAW / "maximo_dia.parquet"
ARCHIVO_MINIMO_DIA = DATA_RAW / "minimo_dia.parquet"
ARCHIVO_PESOS = DATA_RAW / "pesos.csv"
ARCHIVO_HISTORIAL = DATA_RAW / "historial.csv"

#Datos 
DIAS_TOMADOS = 5
FUENTES_PESOS = ["invesco", "capitalizacion"]
N_GRUPOS = 3
NOMBRE_GRUPOS = ["grandes, medianas, pequeñas"]

#252 dias de bolsa (52 semanas)
VENTANA_MAXIMO = 252
BASE_MAXIMO = "cierre"

PERIODO_POR_DEFECTO = "semanal"
