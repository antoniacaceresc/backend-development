import pandas as pd
from io import BytesIO
from typing import Tuple, List, Dict, Any
 
def read_file(content: bytes, filename: str, client_config, venta: str) -> pd.DataFrame:
    sheet_name = venta.upper()
    header_row = client_config.HEADER_ROW
    try:
        if filename.endswith((".xlsx", ".xlsm")):
            df = pd.read_excel(BytesIO(content), sheet_name=sheet_name, header=header_row, engine="openpyxl")
            print("Leyendo excel...")
            return df
        else:
            raise ValueError("Formato de archivo no soportado")
    except Exception as e:
        print(f"[ERROR] Al leer el Excel: {e}")
        raise
 
def build_column_mapping(client_config, venta: str) -> Dict[str, str]:
    # Prioriza col_map sobre extra_map
    col_map = client_config.COLUMN_MAPPING[venta]
    extra_map = client_config.EXTRA_MAPPING
    combined_map = {**extra_map, **col_map}
    return combined_map
 
def warn_missing_columns(df: pd.DataFrame, mapping: Dict[str, str]) -> List[str]:
    missing = [excel_name for excel_name in mapping.values() if excel_name not in df.columns]
    if missing:
        print(f"[WARN] Columnas en Excel no encontradas (se omiten): {missing}")
    return missing
 
def process_dataframe(df_full: pd.DataFrame, client_config, cliente:str, venta: str) -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
    mapping = build_column_mapping(client_config, venta)
    rename_map = {excel_name: internal_name for internal_name, excel_name in mapping.items() if excel_name in df_full.columns}
    warn_missing_columns(df_full, mapping)
   
    df_raw = df_full[list(rename_map.keys())].rename(columns=rename_map).copy()
    df_raw = df_raw.fillna("")
 
    raw_pedidos = df_raw.to_dict(orient="records")
    needed_cols = list(rename_map.values())
    missing_internal = [c for c in needed_cols if c not in df_raw.columns]
    if missing_internal:
        raise ValueError(f"[ERROR] En df_proc faltan columnas mapeadas: {missing_internal}")

    df_proc = df_raw[needed_cols].copy()
    if "CE" in df_proc.columns:
        df_proc["CE"] = df_proc["CE"].astype(str).str.zfill(4)
    # Cast categorical columns
    for col in ["CD", "CE", "OC"]:
        if col in df_proc.columns:
            df_proc[col] = df_proc[col].astype('category')
 
    # Validación y filtrado final
    df_proc["PESO"] = pd.to_numeric(df_proc["PESO"], errors="coerce")

 
    # Filtrar PEDIDO no vacío ni nulo ni duplicado
    df_proc = df_proc[(df_proc["PEDIDO"] != "") & (df_proc["PEDIDO"].notnull())]
    df_proc = df_proc.drop_duplicates(subset="PEDIDO", keep=False)

    # Pasar a numérico
    df_proc["BASE"]         = pd.to_numeric(df_proc["BASE"], errors="coerce")
    df_proc["SUPERIOR"]     = pd.to_numeric(df_proc["SUPERIOR"], errors="coerce")
    df_proc["FLEXIBLE"]     = pd.to_numeric(df_proc["FLEXIBLE"], errors="coerce")
    df_proc["NO_APILABLE"]  = pd.to_numeric(df_proc["NO_APILABLE"], errors="coerce")

    for flag in ["VALIOSO", "PDQ"]:
        if flag in df_proc.columns:
            df_proc[flag] = (pd.to_numeric(df_proc[flag], errors="coerce").fillna(0).astype(int).clip(0, 1))
        else:
            df_proc[flag] = 0
            
    return df_proc, raw_pedidos