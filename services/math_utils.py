import pandas as pd
from datetime import datetime

def format_dates(fecha):
    """
    Recibe:
      - pd.Timestamp o datetime
      - string (por ejemplo '03/04/2025' o '2025-04-03')
      - None / NaN
    Devuelve:
      - String 'DD/MM/YYYY'
      - None si no se pudo interpretar la fecha
    """
    if pd.isna(fecha):
        return None

    if isinstance(fecha, (pd.Timestamp, datetime)):
        dt = fecha
    else:
        dt = pd.to_datetime(fecha, dayfirst=True, errors='coerce')
    if pd.isna(dt):
        return None
    return dt.strftime('%d-%m-%Y')
