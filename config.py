from pathlib import Path

#Ubicacion Carpetas 
RAIZ = Path(__file__).parent
DATA_RAW = RAIZ / "data" / "raw"
DATA_PROCCESED = RAIZ / "data" / "proccesed"

#Descarga 
FECHA_INICIO = "2010-01-01"
INDICE_REFERENCIA = "^NDX"

#Indicador
VENTANA_MAXIMO = 252
UMBRAL_MAXIMO = 0.98
N_GRUPOS = 3


