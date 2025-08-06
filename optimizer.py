import pandas as pd
import math
import uuid
import time
from datetime import datetime
from ortools.sat.python import cp_model
 
from services.file_processor import read_file, process_dataframe
from config import get_client_config
from services.math_utils import format_dates
 
# ---------------------------------------------------------
# Constantes para capping
# ---------------------------------------------------------
MAX_CAMIONES_CP_SAT = 15   # nunca crear más de 15 camiones en CP-SAT
MAX_TIEMPO_POR_GRUPO = 30  # segundos máximo que permitimos a un solo CP-SAT
SCALE = 1000
 
# ---------------------------------------------------------
from typing import List, Dict, Any
 
# --- Helpers for timing ---
 
def calcular_tiempo_por_grupo(df, config, total_timeout: int, max_por_grupo: int):
    num_grupos = _contar_grupos(df, config)
    tiempo_total_disponible = total_timeout - 5
    if num_grupos > 0:
        tpg = tiempo_total_disponible // num_grupos
        return min(tpg, max_por_grupo)
    return min(1, max_por_grupo)
 
# --- Ejecución por modo ---
 
def run_optimizacion(df, raw_pedidos: List[Dict], config: Dict, modo: str, tpg: int, timeout: int) -> Dict[str, Any]:
    res = ejecutar_optimizacion(df.copy(), raw_pedidos, config, modo, tpg, timeout)
    res['camiones'] = postprocesar_camiones(res.get('camiones', []), config)
    return res
 
# --- Flujo principal ---
 
def optimizar_con_dos_fases(raw_df, client_config, cliente, venta, request_timeout, max_tpg):
    # 1) Preprocesamiento
    df_proc, pedidos = process_dataframe(raw_df, client_config, cliente, venta)
    pedidos = [
        {**p, 'Fecha preferente de entrega': format_dates(p['Fecha preferente de entrega'])}
        for p in pedidos
    ]
 
    # 2) Calcular tiempo por grupo
    tpg = calcular_tiempo_por_grupo(df_proc, client_config, request_timeout, max_tpg)
    # 3) Ejecutar VCU sobre TODOS los pedidos
    resultado_vcu = run_optimizacion(df_proc, pedidos, client_config, 'vcu', tpg, request_timeout)
    # 4) Ejecutar BinPacking sobre TODOS los pedidos (misma entrada)
    resultado_bp = run_optimizacion(df_proc, pedidos, client_config, 'binpacking', tpg, request_timeout)
 
    # 5) Etiquetado BH en BinPacking (como antes)
    if (client_config.PERMITE_BH):
        for cam in resultado_bp['camiones']:
            if (
                cam['cd'][0] in client_config.CD_CON_BH
                and cam['flujo_oc'] != 'MIX'
                and cam['vcu_max'] <= client_config.BH_VCU_MAX
                and cam['tipo_ruta'] == 'normal'
            ):
                cam['tipo_camion'] = 'bh'
 
    # 7) Estructura de salida
    return {
        'vcu': resultado_vcu,
        'binpacking': resultado_bp
    }
 
 
# --- Endpoint de procesamiento ---
 
def procesar(content, filename, client, venta, REQUEST_TIMEOUT):
    try:
        config = get_client_config(client)
        df_full = read_file(content, filename, config, venta)
        print("Excel leído correctamente")
        result = optimizar_con_dos_fases(df_full, config, client, venta, REQUEST_TIMEOUT, MAX_TIEMPO_POR_GRUPO)
 
        return result
    except Exception as e:
        import traceback
        tb_str = traceback.format_exc()
        return {
            "error": {
                "message": str(e),
                "traceback": tb_str[:5000]  # limitar largo
            }
        }
 
 
def _contar_grupos(df, config):
    """
    Recorre rápidamente todas las rutas posibles y cuenta
    cuántos grupos (sub-matrices) van a llegar al solver,
    de modo de distribuir el tiempo total.
    """
    total = 0
    tipos_ruta = ['normal', 'multi_ce', 'multi_cd', 'bh']
    fases = [(tipo, config.RUTAS_POSIBLES[tipo]) for tipo in tipos_ruta if tipo in config.RUTAS_POSIBLES]
 
    lo_ag = '6009 Lo Aguirre'
    total = 0
    mix_grupos = config.MIX_GRUPOS
 
    for tipo, rutas in fases:
        if tipo == 'normal':
            for cds, ces in rutas:
                if cds == [lo_ag]:
                    # En Lo Aguirre: primero uno por flujo, luego mixtos
                    df_cd = df[df['CD'] == lo_ag]
                    for ce in ces:
                        df_sub = df_cd[df_cd['CE'] == ce]
                        if (config.USA_OC):
                            oc_unique = df_sub['OC'].unique().tolist()
                            total += len(oc_unique)
 
                            for ocg in mix_grupos:
                                if all(o in oc_unique for o in ocg):
                                    total += 1
                        else:
                            total += 1
                else:
                    # Resto de CDs: un único grupo si hay pedidos
                    mask = df['CD'].isin(cds) & df['CE'].isin(ces)
                    if not df[mask].empty:
                        total += 1
 
        elif tipo == 'bh':
            # BH: sin mezcla, siempre un grupo por cada flujo
            for cds, ces in rutas:
                mask = df['CD'].isin(cds) & df['CE'].isin(ces)
                df_sub = df[mask]
                total += len(df_sub['OC'].unique()) if config.USA_OC else 1
 
 
        else:  # multi_ce y multi_cd
            for cds, ces in rutas:
                mask = df['CD'].isin(cds) & df['CE'].isin(ces)
                if cds == [lo_ag]:
                    # desglosar Lo Aguirre también por flujo individual
                    df_sub = df[mask]
                    total += len(df_sub['OC'].unique()) if config.USA_OC else 1
 
                else:
                    # igual que antes: un solo grupo si hay datos
                    if not df[mask].empty:
                        total += 1
 
    return total
 
def postprocesar_camiones(camiones, config):
    """
    Añade flujo OC, chocolates.
    """
    for cam in camiones:
        if config.USA_OC:
            ocs = {p.get('OC') for p in cam['pedidos'] if 'OC' in p and p.get('OC')}
            cam['flujo_oc'] = ocs.pop() if len(ocs) == 1 else 'MIX'
        else:
            cam['flujo_oc'] = None
        cam['chocolates'] = 'SI' if any(p.get('CHOCOLATES') == 'SI' for p in cam['pedidos']) else 'NO'
 
    return camiones
 
 
def ejecutar_optimizacion(df, raw_pedidos, config, modo, tiempo_por_grupo, REQUEST_TIMEOUT):
    """
    Ejecuta optimización en fases según modo.
    """
    # Precalculamos raw_map y métricas globales
    raw_map = {r['PEDIDO']: r.copy() for r in raw_pedidos}
    pedidos_all = df['PEDIDO'].tolist()
    vol_raw_all = dict(zip(pedidos_all, df['VOL']))
    peso_raw_all = dict(zip(pedidos_all, df['PESO']))
    # Precalculamos fracciones VCU escaladas
    vcu_vol_int_all = {}
    vcu_peso_int_all = {}
    truck = config.TRUCK_TYPES[0]
    cap_vol = truck['cap_volume']
    cap_peso = truck['cap_weight']
    for i in pedidos_all:
        frac_vol = vol_raw_all[i] / cap_vol if cap_vol else 0.0
        frac_peso = peso_raw_all[i] / cap_peso if cap_peso else 0.0
        vcu_vol_int_all[i] = max(0, min(SCALE, int(math.ceil(frac_vol * SCALE))))
        vcu_peso_int_all[i] = max(0, min(SCALE, int(math.ceil(frac_peso * SCALE))))
 
    pedidos_rest = df.copy()
    resultados = []
    start_total = time.time()
 
    # Selección de fases según modo
    tipos_ruta = ['normal'] if modo == 'binpacking' else ['normal', 'multi_ce', 'multi_cd', 'bh']
    fases = [(tipo, config.RUTAS_POSIBLES[tipo]) for tipo in tipos_ruta if tipo in config.RUTAS_POSIBLES]
 
    total_orders = len(pedidos_all)
    mix_grupos = config.MIX_GRUPOS
    for tipo, rutas in fases:
        rutas_iter = generar_rutas(tipo, rutas, pedidos_rest, mix_grupos, config.USA_OC)
        for cds, ces, oc in rutas_iter:
            df_g = pedidos_rest[ (pedidos_rest['CD'].isin(cds)) & (pedidos_rest['CE'].isin(ces)) ]
            if oc:
                if isinstance(oc, list):
                    df_g = df_g[df_g['OC'].isin(oc)]
                else:
                    df_g = df_g[df_g['OC'] == oc]
            if df_g.empty:
                continue
            # calcular tiempo dinámico por grupo
            group_orders = len(df_g)
            print(tiempo_por_grupo, group_orders, total_orders)
            tiempo_group = max(1, (tiempo_por_grupo * group_orders / 10))
            cfg = {'id': f"{tipo}__{'-'.join(cds)}__{'-'.join(map(str, ces))}" + (f"__{oc}" if oc else ''),
                   'tipo': tipo, 'ce': ces, 'cd': cds, 'oc': oc}
            elapsed = time.time() - start_total
            if elapsed + tiempo_group > (REQUEST_TIMEOUT - 2):
                break
            if modo == 'vcu':
                res = optimizar_vcu(
                    df_g, raw_pedidos, cfg, config,
                    tiempo_group, vol_raw_all, peso_raw_all,
                    vcu_vol_int_all, vcu_peso_int_all
                )
            else:
                res = optimizar_bin(
                    df_g, raw_pedidos, cfg, config,
                    tiempo_group, vol_raw_all, peso_raw_all
                )
            if res['status'] in ('OPTIMAL', 'FEASIBLE') and res.get('camiones'):
                resultados.append(res)
                pedidos_rest = pedidos_rest[~pedidos_rest['PEDIDO'].isin(res['pedidos_asignados_ids'])]
        if time.time() - start_total > (REQUEST_TIMEOUT - 2):
            break
 
    # Reconstruir camiones y no incluidos
    all_cam = [c for r in resultados for c in r['camiones']]
    pedidos_no_incl = []
    for pid in pedidos_rest['PEDIDO'].tolist():
        if pid not in raw_map:
            continue
        raw = raw_map[pid]
        pedido = {'PEDIDO': pid, 'CE': raw.get('CE'), 'CD': raw.get('CD'), 'OC': raw.get('OC') if 'OC' in raw else None,
                  'VCU_VOL': vol_raw_all[pid] / float(cap_vol), 'VCU_PESO': peso_raw_all[pid] / float(cap_peso),
                 'PO': raw.get('PO'),
                  'CHOCOLATES': raw.get('CHOCOLATES'), 'Fecha preferente de entrega': raw.get('Fecha preferente de entrega')}
        pedidos_no_incl.append(completar_metadata_pedido(pedido, raw_map))
 
    return {'camiones': all_cam, 'pedidos_no_incluidos': pedidos_no_incl}
 
 
# ---------------------------------------------------------
# Heurística First-Fit Decreasing (FFD) para estimar n_cam
# ---------------------------------------------------------
def heuristica_ffd(pedidos, peso_raw, vol_raw, truck_caps):
    """
    Igual que antes, ordenamos por recurso más crítico.
    """
    cap_peso = truck_caps['cap_weight']
    cap_vol = truck_caps['cap_volume']
    pedidos_orden = sorted(
        pedidos,
        key=lambda i: max(peso_raw[i] / cap_peso, vol_raw[i] / cap_vol),
        reverse=True
    )
    camiones = []  # cada elemento: (peso_ocupado, vol_ocupado)
    for i in pedidos_orden:
        asignado = False
        for idx in range(len(camiones)):
            if (camiones[idx][0] + peso_raw[i] <= cap_peso
                and camiones[idx][1] + vol_raw[i] <= cap_vol):
                camiones[idx] = (camiones[idx][0] + peso_raw[i], camiones[idx][1] + vol_raw[i])
                asignado = True
                break
        if not asignado:
            camiones.append((peso_raw[i], vol_raw[i]))
    return len(camiones)
 
 
def generar_rutas(tipo, rutas, df, mix_grupos, usa_oc):
    lo_ag = '6009 Lo Aguirre'
    rutas_iter = []
 
    if tipo == 'normal':
        for cds, ces in rutas:
            if cds == [lo_ag]:
                df_cd = df[df['CD'] == lo_ag]
                for ce in ces:
                    df_sub = df_cd[df_cd['CE'] == ce]
                    if usa_oc:
                        oc_unique = df_sub['OC'].unique().tolist()
                        for oc in oc_unique:
                            rutas_iter.append(([lo_ag], [ce], oc))
                        for ocg in mix_grupos:
                            if all(o in oc_unique for o in ocg):
                                rutas_iter.append(([lo_ag], [ce], ocg))
                    else:
                        rutas_iter.append(([lo_ag], [ce], None))
            else:
                mask = df['CD'].isin(cds) & df['CE'].isin(ces)
                if not df[mask].empty:
                    rutas_iter.append((cds, ces, None))
 
    elif tipo == 'bh':
        for cds, ces in rutas:
            mask = df['CD'].isin(cds) & df['CE'].isin(ces)
            df_sub = df[mask]
            if usa_oc:
                for oc in df_sub['OC'].unique().tolist():
                    rutas_iter.append((cds, ces, oc))
            else:
                rutas_iter.append((cds, ces, None))
 
    else:  # multi_ce y multi_cd
        for cds, ces in rutas:
            df_sub = df[df['CD'].isin(cds) & df['CE'].isin(ces)]
            if df_sub.empty:
                continue
 
            ce_presentes = set(df_sub['CE'].unique())
            cd_presentes = set(df_sub['CD'].unique())
 
            if tipo == 'multi_ce' and not all(ce in ce_presentes for ce in ces):
                continue
            if tipo == 'multi_cd' and not all(cd in cd_presentes for cd in cds):
                continue
 
            if lo_ag in cds and usa_oc:
                for oc in df_sub['OC'].unique():
                    if not df_sub[df_sub['OC'] == oc].empty:
                        rutas_iter.append((cds, ces, oc))
            else:
                rutas_iter.append((cds, ces, None))
 
    return rutas_iter
 
 
def completar_metadata_pedido(pedido_minimal: dict, raw_map: dict) -> dict:
    """
    Sin cambios: combinamos el pedido minimal con raw_map.
    """
    p = pedido_minimal['PEDIDO']
    completo = pedido_minimal.copy()
    if p not in raw_map:
        return completo
    for clave, valor in raw_map[p].items():
        if clave not in completo:
            completo[clave] = valor
    return completo
 

def optimizar_vcu( df_g, raw_pedidos, grupo_cfg, client_config, tiempo_max_seg,
    vol_raw, peso_raw, vcu_vol_int, vcu_peso_int, PESO_VCU=1000, PESO_CAMIONES=200, PESO_PEDIDOS=3000):
    """
    Se parametriza `tiempo_max_seg` como tiempo límite para este CP-SAT.
    Además, limitamos n_cam nunca por encima de MAX_CAMIONES_CP_SAT.
    """
    raw_map = { r['PEDIDO']: r.copy() for r in raw_pedidos }
    df = df_g.copy()
    pedidos    = df['PEDIDO'].tolist()
    po_map     = dict(zip(pedidos, df['PO']))
    ce_map     = dict(zip(pedidos, df['CE']))
    cd_map     = dict(zip(pedidos, df['CD']))
    valor_map = dict(zip(pedidos, df['VALOR']))
    cafe_map = dict(zip(pedidos, df['VALOR_CAFE']))
    if 'CHOCOLATES' in df.columns:
        chocolates_map = dict(zip(pedidos, df['CHOCOLATES']))
    else:
        chocolates_map = {i: "NO" for i in pedidos}
    if 'OC' in df.columns:
        oc_map = dict(zip(pedidos, df['OC']))
    else:
        oc_map = {i: None for i in pedidos}
    
    if 'VALIOSO' in df_g.columns:
        df_g['VALIOSO'] = (pd.to_numeric(df_g['VALIOSO'], errors='coerce').fillna(0).astype(int).clip(0,1))
    else:
        df_g['VALIOSO'] = 0
    valuable_map = dict(zip(pedidos, df_g['VALIOSO']))
 
    pallets_conf_map    = dict(zip(pedidos, df['PALLETS']))

    # MAPEOS DE APILABILIDAD
    base_map        = dict(zip(pedidos, df['BASE']))
    superior_map    = dict(zip(pedidos, df['SUPERIOR']))
    flexible_map    = dict(zip(pedidos, df['FLEXIBLE']))
    no_apil_map     = dict(zip(pedidos, df['NO_APILABLE']))

    # Escalamiento a enteros (igual que haces con pallets_conf)
    PALLETS_SCALE = 10
    base_int     = {i: int(base_map[i]      * PALLETS_SCALE) for i in pedidos}
    superior_int = {i: int(superior_map[i]  * PALLETS_SCALE) for i in pedidos}
    flex_int     = {i: int(flexible_map[i]  * PALLETS_SCALE) for i in pedidos}
    noap_int     = {i: int(no_apil_map[i]   * PALLETS_SCALE) for i in pedidos}
 
    # Información camión
    truck = client_config.TRUCK_TYPES[0]
    cap_volume   = truck['cap_volume']
    cap_weight   = truck['cap_weight']
 
    if grupo_cfg['tipo'] == 'bh':
        VCU_MIN = client_config.BH_VCU_MIN
        MAX_POSITIONS = client_config.BH_MAX_POSICIONES
        MAX_PALLETS_CONF = client_config.BH_MAX_PALLETS
    else:
        VCU_MIN = client_config.VCU_MIN
        MAX_POSITIONS = truck['max_positions']
        MAX_PALLETS_CONF = client_config.MAX_PALLETS_CONF
 
 
    # --- Escalamiento a enteros ---
    VCU_MIN_int     = int(round(VCU_MIN * SCALE))
    pallets_conf_int = { i: int(pallets_conf_map[i] * PALLETS_SCALE) for i in pedidos}
 
 
    # 1) Estimamos n_cam con heurística FFD
    n_cam_heur = heuristica_ffd( pedidos, peso_raw, vol_raw, {'cap_weight': cap_weight, 'cap_volume': cap_volume} )
    # 2) Limitamos a MAX_CAMIONES_CP_SAT
    n_cam      = min(len(pedidos), n_cam_heur, MAX_CAMIONES_CP_SAT)
 
    model = cp_model.CpModel()
 
    # Variables x[(i, j)]
    x = {}
    for i in pedidos:
        if vol_raw[i] <= cap_volume and peso_raw[i] <= cap_weight:
            for j in range(n_cam):
                x[(i, j)] = model.NewBoolVar(f"x_vcu_{i}_{j}")
 
    if client_config.AGRUPAR_POR_PO:
        agregar_restricciones_agrupacion_por_po(model, x, pedidos, po_map, n_cam)
 
    # Variables y_truck[j]
    y_truck = {j: model.NewBoolVar(f"y_vcu_truck_{j}") for j in range(n_cam)}
 
    # Acumulados (enteros)
    vol_cam_int  = {}
    peso_cam_int = {}
    for j in range(n_cam):
        lista_i = [i for i in pedidos if (i, j) in x]
        vol_cam_int[j]  = sum(vcu_vol_int[i]  * x[(i, j)] for i in lista_i)
        peso_cam_int[j] = sum(vcu_peso_int[i] * x[(i, j)] for i in lista_i)
 
    # vcu_max_int[j]
    vcu_max_int = {}
    for j in range(n_cam):
        v = model.NewIntVar(0, SCALE, f"vcu_max_int_{j}")
        model.AddMaxEquality(v, [vol_cam_int[j], peso_cam_int[j]])
        vcu_max_int[j] = v
 
 
    # 6) Restricciones
    for i in pedidos:
        vars_i = [x[(i, j)] for j in range(n_cam) if (i, j) in x]
        model.Add(sum(vars_i) <= 1)
 
    for (i, j), vx in x.items():
        model.Add(vx <= y_truck[j])
 
    for j in range(1, n_cam):
        model.Add(y_truck[j] <= y_truck[j - 1])
 
    # VCU mínimo: solo si y_truck[j] = 1
    for j in range(n_cam):
        model.Add(vcu_max_int[j] >= VCU_MIN_int).OnlyEnforceIf(y_truck[j])
 
    total_stack_vars = {}
    # Restricción de pallets y número de órdenes
    for j in range(n_cam):
        lista_i = [i for i in pedidos if (i, j) in x]
        model.Add(sum(pallets_conf_int[i] * x[(i,j)] for i in lista_i) <= MAX_PALLETS_CONF * PALLETS_SCALE * y_truck[j])
        model.Add(sum(x[(i, j)] for i in lista_i) <= client_config.MAX_ORDENES * y_truck[j])
        
        # —– NUEVAS RESTRICCIONES DE APILABILIDAD —–
        # 1) totales de cada tipo
        model.Add( sum(base_int[i]     * x[(i,j)] for i in lista_i)
                   <= MAX_POSITIONS * PALLETS_SCALE * y_truck[j] )
        model.Add( sum(superior_int[i] * x[(i,j)] for i in lista_i)
                   <= MAX_POSITIONS * PALLETS_SCALE * y_truck[j] )
        model.Add( sum(noap_int[i]     * x[(i,j)] for i in lista_i)
                   <= MAX_POSITIONS * PALLETS_SCALE * y_truck[j] )
        model.Add( sum(flex_int[i]     * x[(i,j)] for i in lista_i)
                   <= MAX_POSITIONS * truck['levels'] * PALLETS_SCALE * y_truck[j] )

        # 2) combinaciones
        model.Add( sum((base_int[i] + noap_int[i]) * x[(i,j)] for i in lista_i)
                   <= MAX_POSITIONS * PALLETS_SCALE * y_truck[j] )
        model.Add( sum((superior_int[i] + noap_int[i]) * x[(i,j)] for i in lista_i)
                   <= MAX_POSITIONS * PALLETS_SCALE * y_truck[j] )
        
        # —– CÁLCULO COMPONENTES DEL LÍMITE DE APILABILIDAD —–
        # suma por tipo
        base_sum     = sum(base_int[i]     * x[(i,j)] for i in lista_i)
        superior_sum = sum(superior_int[i] * x[(i,j)] for i in lista_i)
        flex_sum     = sum(flex_int[i]     * x[(i,j)] for i in lista_i)
        noap_sum     = sum(noap_int[i]     * x[(i,j)] for i in lista_i)

        # —– 0) diff = BASE − SUPERIOR; abs_diff = |diff| —–
        diff     = model.NewIntVar(-MAX_POSITIONS*PALLETS_SCALE,
                                MAX_POSITIONS*PALLETS_SCALE,
                                f"diff_{j}")
        abs_diff = model.NewIntVar(0,
                                MAX_POSITIONS*PALLETS_SCALE,
                                f"abs_diff_{j}")
        model.Add(diff == base_sum + (-1) * superior_sum)
        model.AddAbsEquality(abs_diff, diff)

        # —– 1) a = min(base_sum, superior_sum) —–
        m0 = model.NewIntVar(0,
                            MAX_POSITIONS*PALLETS_SCALE,
                            f"m0_{j}")
        b0 = model.NewBoolVar(f"b0_{j}")
        model.Add(base_sum <= superior_sum).OnlyEnforceIf(b0)
        model.Add(base_sum >  superior_sum).OnlyEnforceIf(b0.Not())
        model.Add(m0 == base_sum).OnlyEnforceIf(b0)
        model.Add(m0 == superior_sum).OnlyEnforceIf(b0.Not())

        # —– 2) b = min(abs_diff, flex_sum) —–
        m1 = model.NewIntVar(0,
                            MAX_POSITIONS*PALLETS_SCALE,
                            f"m1_{j}")
        b1 = model.NewBoolVar(f"b1_{j}")
        model.Add(abs_diff <= flex_sum).OnlyEnforceIf(b1)
        model.Add(abs_diff >  flex_sum).OnlyEnforceIf(b1.Not())
        model.Add(m1 == abs_diff).OnlyEnforceIf(b1)
        model.Add(m1 == flex_sum).OnlyEnforceIf(b1.Not())

        # —– 3) c = round((flex_sum − m1)/2) —–
        rem  = model.NewIntVar(0,
                            MAX_POSITIONS*PALLETS_SCALE,
                            f"rem_{j}")
        half = model.NewIntVar(0,
                            MAX_POSITIONS*PALLETS_SCALE,
                            f"half_{j}")
        model.Add(rem == flex_sum + (-1) * m1)
        # half = ceil(rem/2):
        model.Add(2 * half >= rem)
        model.Add(2 * half <= rem + 1)

        # —– 4) d = max(abs_diff − flex_sum, 0) —–
        m2 = model.NewIntVar(0,
                            MAX_POSITIONS*PALLETS_SCALE,
                            f"m2_{j}")
        b2 = model.NewBoolVar(f"b2_{j}")
        model.Add(abs_diff >= flex_sum).OnlyEnforceIf(b2)
        model.Add(abs_diff <  flex_sum).OnlyEnforceIf(b2.Not())
        model.Add(m2 == abs_diff + (-1) * flex_sum).OnlyEnforceIf(b2)
        model.Add(m2 == 0).OnlyEnforceIf(b2.Not())

        # 6) total_stack = m0 + m1 + half + m2
        total_stack = model.NewIntVar(
            -MAX_POSITIONS*PALLETS_SCALE*2,
            MAX_POSITIONS*PALLETS_SCALE*4,
            f"total_stack_{j}"
        )
        model.Add(total_stack == m0 + m1 + half + m2 + noap_sum)

        # 7) umbral: total_stack ≤ max_positions * PALLETS_SCALE  si el camión está usado
        model.Add(
            total_stack 
            <= (MAX_POSITIONS * PALLETS_SCALE) * y_truck[j]
        )
        total_stack_vars[j] = total_stack

 
    # 7) Función objetivo
    obj_terms = []
    for j in range(n_cam): #max vcu
        obj_terms.append(PESO_VCU * vcu_max_int[j])
    for vx in x.values(): #incluir más pedidos
        obj_terms.append(PESO_PEDIDOS * vx)
    for j in range(n_cam): #minim camiones
        obj_terms.append(- (PESO_CAMIONES * SCALE) * y_truck[j])
 
    model.Maximize(sum(obj_terms))
 
    # 8) Ejecución del solver con parámetro de tiempo
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(tiempo_max_seg)
    #solver.parameters.relative_gap_limit = 0.01
    solver.parameters.num_search_workers  = 1  # Para no usar CPU extra en Render
    t0 = time.time()
    resultado = solver.Solve(model)
    t1 = time.time()
    status_map = {cp_model.OPTIMAL: 'OPTIMAL', cp_model.FEASIBLE: 'FEASIBLE'}
    estado     = status_map.get(resultado, 'NO_SOLUTION')
    print(f"[TIMING] CP-SAT (VCU) grupo {grupo_cfg['id']}: {t1 - t0:.3f} s (límite: {tiempo_max_seg}s), estado: {estado}")
 
 
    # 9) Reconstruir salida
    pedidos_incluidos = []
    camiones = []
    idx_cam = 1
    if grupo_cfg['tipo'] == 'bh':
        tt = 'bh'
    else:
        tt = truck['type']

    for j, ts_var in total_stack_vars.items():
        # Sólo imprime si el camión j está usado (opcional)
        if solver.Value(y_truck[j]):
            print(f"Camión {j} → total_stack = {solver.Value(ts_var)}")
    
    for j in range(n_cam):
        if solver.Value(y_truck[j]) < 1:
            continue
        grp = []
        for (i2, j2), vx in x.items():
            if j2 == j and solver.Value(vx) == 1:
                grp.append(i2)
                pedidos_incluidos.append(i2)
 
        vol_sum   = sum(vol_raw[i]  for i in grp)
        peso_sum  = sum(peso_raw[i] for i in grp)
        vcu_vol_j  = (vol_sum  / float(cap_volume))  if cap_volume  else 0.0
        vcu_peso_j = (peso_sum / float(cap_weight))  if cap_weight  else 0.0
        vcu_max_j  = max(vcu_vol_j, vcu_peso_j)
 
        datos_asig = []
        for i in grp:
            vcu_vol_i  = (vol_raw[i]  / float(cap_volume))  if cap_volume  else 0.0
            vcu_peso_i = (peso_raw[i] / float(cap_weight))  if cap_weight  else 0.0
 
            pedido_min = {
                'PEDIDO':       i,
                'CAMION':       idx_cam,
                'GRUPO':        grupo_cfg['id'],
                'TIPO_RUTA':    grupo_cfg['tipo'],
                'TIPO_CAMION':  tt,
                'CE':           ce_map[i],
                'CD':           cd_map[i],
                'VCU_VOL':      vcu_vol_i,
                'VCU_PESO':     vcu_peso_i,
                'CHOCOLATES':   chocolates_map[i],
                'VALIOSO':      valuable_map[i],
                'PO':           po_map[i],
                'OC':           oc_map[i],
                'PALLETS':      pallets_conf_map[i],
                'VALOR': valor_map[i],
            }
 
            pedido_completo = completar_metadata_pedido(pedido_min, raw_map)
            datos_asig.append(pedido_completo)
       
        valor_total = sum(valor_map.get(i, 0) or 0 for i in grp)
        valor_cafe = sum(cafe_map.get(i, 0) or 0 for i in grp)
        tiene_chocolates = any(chocolates_map.get(i) == 'SI' for i in grp)
        pallets_conf = sum(pallets_conf_map[i] for i in grp)
        valioso = any(valuable_map.get(i) == 1 for i in grp)
       
        camiones.append({
            'id':         uuid.uuid4().hex,
            'grupo':      grupo_cfg['id'],
            'tipo_ruta':  grupo_cfg['tipo'],
            'ce':         grupo_cfg['ce'],
            'cd':         grupo_cfg['cd'],
            'tipo_camion': tt,
            'vcu_vol':    vcu_vol_j,
            'vcu_peso':   vcu_peso_j,
            'vcu_max':    vcu_max_j,
            'chocolates': tiene_chocolates,
            'skus_valiosos': valioso,
            'valor_total': valor_total,
            'valor_cafe': valor_cafe,
            'pallets_conf': pallets_conf,
            'pedidos':    datos_asig
        })
        idx_cam += 1
 
    pedidos_excluidos_ids = [i for i in pedidos if i not in pedidos_incluidos]
    pedidos_excluidos = []
    for i in pedidos_excluidos_ids:
        pedido_min = {
            'PEDIDO':       i,
            'CE':           ce_map[i],
            'CD':           cd_map[i],
            'OC':           oc_map[i],
            'VCU_VOL':      (vol_raw[i] / float(cap_volume)) if cap_volume else 0.0,
            'VCU_PESO':     (peso_raw[i] / float(cap_weight)) if cap_weight else 0.0,
            'PO':           po_map[i],
            'PALLETS':      pallets_conf_map[i],
            'VALOR':        valor_map[i],
        }
        pedido_ex_completo = completar_metadata_pedido(pedido_min, raw_map)
        pedidos_excluidos.append(pedido_ex_completo)
 
    return {
        'status':                estado,
        'pedidos_asignados_ids': pedidos_incluidos,
        'pedidos_asignados':     [pa for cam in camiones for pa in cam['pedidos']],
        'pedidos_excluidos':     pedidos_excluidos,
        'camiones':              camiones
    }
 

def optimizar_bin(df_g, raw_pedidos, grupo_cfg, client_config, tiempo_max_seg, vol_raw, peso_raw):
    """
    BinPacking (CP-SAT) con:
    - Solo camiones de tipo 'S'
    - FFD para acotar n_cam
    - índices categóricos y pre-indexado
    - eliminar rutas sin pedidos antes de llamar al solver
    """
    raw_map = { r['PEDIDO']: r.copy() for r in raw_pedidos }
 
    df_g = df_g.copy()
    df_g['CD'] = df_g['CD'].astype('category')
    df_g['CE'] = df_g['CE'].astype('category')
    pedidos = df_g['PEDIDO'].tolist()
    # Convertimos a enteros redondeando para CP-SAT
    vol_int  = {i: int(round(vol_raw[i]))  for i in pedidos}
    peso_int = {i: int(round(peso_raw[i])) for i in pedidos}
    po_map = dict(zip(pedidos, df_g['PO']))
    ce_map = dict(zip(pedidos, df_g['CE']))
    cd_map = dict(zip(pedidos, df_g['CD']))
    if 'OC' in df_g.columns:
        oc_map = dict(zip(pedidos, df_g['OC']))
    else:
        oc_map = {i: None for i in pedidos}
    valor_map = dict(zip(pedidos, df_g['VALOR']))
    cafe_map = dict(zip(pedidos, df_g['VALOR_CAFE']))
    pallets_conf_map    = dict(zip(pedidos, df_g['PALLETS']))
    if 'CHOCOLATES' in df_g.columns:
        chocolates_map = dict(zip(pedidos, df_g['CHOCOLATES']))
    else:
        chocolates_map = {i: "NO" for i in pedidos}
    
    if 'VALIOSO' in df_g.columns:
        df_g['VALIOSO'] = (pd.to_numeric(df_g['VALIOSO'], errors='coerce').fillna(0).astype(int).clip(0,1))
    else:
        df_g['VALIOSO'] = 0
    valuable_map = dict(zip(pedidos, df_g['VALIOSO']))
 
    # MAPEOS DE APILABILIDAD
    base_map        = dict(zip(pedidos, df_g['BASE']))
    superior_map    = dict(zip(pedidos, df_g['SUPERIOR']))
    flexible_map    = dict(zip(pedidos, df_g['FLEXIBLE']))
    no_apil_map     = dict(zip(pedidos, df_g['NO_APILABLE']))

    # Escalamiento a enteros (igual que haces con pallets_conf)
    PALLETS_SCALE = 10
    base_int     = {i: int(base_map[i]      * PALLETS_SCALE) for i in pedidos}
    superior_int = {i: int(superior_map[i]  * PALLETS_SCALE) for i in pedidos}
    flex_int     = {i: int(flexible_map[i]  * PALLETS_SCALE) for i in pedidos}
    noap_int     = {i: int(no_apil_map[i]   * PALLETS_SCALE) for i in pedidos}
 
    # Información camión
    truck       = client_config.TRUCK_TYPES[0]
    cap_peso    = int(round(truck['cap_weight']))
    cap_vol     = int(round(truck['cap_volume']))

    MAX_PALLETS_CONF = client_config.MAX_PALLETS_CONF
    pallets_conf_int = {i: int((pallets_conf_map[i]) * PALLETS_SCALE) for i in pedidos}
    MAX_POSITIONS = truck['max_positions']

    # 2) Heurística FFD para estimar n_cam
    n_cam_heur = heuristica_ffd(pedidos, peso_int, vol_int, {'cap_weight': cap_peso, 'cap_volume': cap_vol})
    n_cam = min(len(pedidos), n_cam_heur + 5)
 

    # 3) Construir modelo CP-SAT
    model = cp_model.CpModel()
    x = {}
    for i in pedidos:
        for j in range(n_cam):
            vid = str(i)
            x[(i, j)] = model.NewBoolVar(f"x_bin_{vid}_{j}")
 
    if client_config.AGRUPAR_POR_PO:
        agregar_restricciones_agrupacion_por_po(model, x, pedidos, po_map, n_cam)
 
    y = {j: model.NewBoolVar(f"y_bin_{j}") for j in range(n_cam)}
   
    # Cada pedido EXACTAMENTE en un camión
    for i in pedidos:
        model.Add(sum(x[(i, j2)] for j2 in range(n_cam)) == 1)
   
    total_stack_vars = {}
    # 4) Restricciones agrupadas
    for j in range(n_cam):
        for i in pedidos:
            model.Add(x[(i, j)] <= y[j])
        # Capacidad peso/vol
        suma_peso = sum(int(round(peso_int[i])) * x[(i, j)] for i in pedidos)
        suma_vol = sum(int(round(vol_int[i])) * x[(i, j)] for i in pedidos)
        model.Add(suma_peso <= cap_peso * y[j])
        model.Add(suma_vol <= cap_vol * y[j])
        # Posiciones y órdenes
        model.Add(sum(x[(i, j)] for i in pedidos) <= client_config.MAX_ORDENES * y[j])
        model.Add(sum( pallets_conf_int[i] * x[(i, j)] for i in pedidos ) <= MAX_PALLETS_CONF * PALLETS_SCALE * y[j] )
        # Monotonía y[j] <= y[j-1]
        if j >= 1:
            model.Add(y[j] <= y[j - 1])

        lista_i = [i for i in pedidos]  # o filtra los i con (i,j) si prefieres


        # —– NUEVAS RESTRICCIONES DE APILABILIDAD —–
        # 1) totales de cada tipo
        model.Add( sum(base_int[i]     * x[(i,j)] for i in lista_i)
                   <= MAX_POSITIONS * PALLETS_SCALE * y[j] )
        model.Add( sum(superior_int[i] * x[(i,j)] for i in lista_i)
                   <= MAX_POSITIONS * PALLETS_SCALE * y[j] )
        model.Add( sum(noap_int[i]     * x[(i,j)] for i in lista_i)
                   <= MAX_POSITIONS * PALLETS_SCALE * y[j] )
        model.Add( sum(flex_int[i]     * x[(i,j)] for i in lista_i)
                   <= MAX_POSITIONS * truck['levels'] * PALLETS_SCALE * y[j] )

        # 2) combinaciones
        model.Add( sum((base_int[i] + noap_int[i]) * x[(i,j)] for i in lista_i)
                   <= MAX_POSITIONS * PALLETS_SCALE * y[j] )
        model.Add( sum((superior_int[i] + noap_int[i]) * x[(i,j)] for i in lista_i)
                   <= MAX_POSITIONS * PALLETS_SCALE * y[j] )
        
        # —– CÁLCULO COMPONENTES DEL LÍMITE DE APILABILIDAD —–
        # suma por tipo
        base_sum     = sum(base_int[i]     * x[(i,j)] for i in lista_i)
        superior_sum = sum(superior_int[i] * x[(i,j)] for i in lista_i)
        flex_sum     = sum(flex_int[i]     * x[(i,j)] for i in lista_i)
        noap_sum     = sum(noap_int[i]     * x[(i,j)] for i in lista_i)

        # —– 0) diff = BASE − SUPERIOR; abs_diff = |diff| —–
        diff     = model.NewIntVar(-MAX_POSITIONS*PALLETS_SCALE,
                                MAX_POSITIONS*PALLETS_SCALE,
                                f"diff_{j}")
        abs_diff = model.NewIntVar(0,
                                MAX_POSITIONS*PALLETS_SCALE,
                                f"abs_diff_{j}")
        model.Add(diff == base_sum + (-1) * superior_sum)
        model.AddAbsEquality(abs_diff, diff)

        # —– 1) a = min(base_sum, superior_sum) —–
        m0 = model.NewIntVar(0,
                            MAX_POSITIONS*PALLETS_SCALE,
                            f"m0_{j}")
        b0 = model.NewBoolVar(f"b0_{j}")
        model.Add(base_sum <= superior_sum).OnlyEnforceIf(b0)
        model.Add(base_sum >  superior_sum).OnlyEnforceIf(b0.Not())
        model.Add(m0 == base_sum).OnlyEnforceIf(b0)
        model.Add(m0 == superior_sum).OnlyEnforceIf(b0.Not())

        # —– 2) b = min(abs_diff, flex_sum) —–
        m1 = model.NewIntVar(0,
                            MAX_POSITIONS*PALLETS_SCALE,
                            f"m1_{j}")
        b1 = model.NewBoolVar(f"b1_{j}")
        model.Add(abs_diff <= flex_sum).OnlyEnforceIf(b1)
        model.Add(abs_diff >  flex_sum).OnlyEnforceIf(b1.Not())
        model.Add(m1 == abs_diff).OnlyEnforceIf(b1)
        model.Add(m1 == flex_sum).OnlyEnforceIf(b1.Not())

        # —– 3) c = round((flex_sum − m1)/2) —–
        rem  = model.NewIntVar(0,
                            MAX_POSITIONS*PALLETS_SCALE,
                            f"rem_{j}")
        half = model.NewIntVar(0,
                            MAX_POSITIONS*PALLETS_SCALE,
                            f"half_{j}")
        model.Add(rem == flex_sum + (-1) * m1)
        # half = ceil(rem/2):
        model.Add(2 * half >= rem)
        model.Add(2 * half <= rem + 1)

        # —– 4) d = max(abs_diff − flex_sum, 0) —–
        m2 = model.NewIntVar(0,
                            MAX_POSITIONS*PALLETS_SCALE,
                            f"m2_{j}")
        b2 = model.NewBoolVar(f"b2_{j}")
        model.Add(abs_diff >= flex_sum).OnlyEnforceIf(b2)
        model.Add(abs_diff <  flex_sum).OnlyEnforceIf(b2.Not())
        model.Add(m2 == abs_diff + (-1) * flex_sum).OnlyEnforceIf(b2)
        model.Add(m2 == 0).OnlyEnforceIf(b2.Not())

        # 6) total_stack = m0 + m1 + half + m2
        total_stack = model.NewIntVar(
            -MAX_POSITIONS*PALLETS_SCALE*2,
            MAX_POSITIONS*PALLETS_SCALE*4,
            f"total_stack_{j}"
        )
        model.Add(total_stack == m0 + m1 + half + m2 + noap_sum)

        # 7) umbral: total_stack ≤ max_positions * PALLETS_SCALE  si el camión está usado
        model.Add(
            total_stack 
            <= (MAX_POSITIONS * PALLETS_SCALE) * y[j]
        )
        total_stack_vars[j] = total_stack

 
    # ---------------------------------------------
    # 5) Objetivo: minimizar número de camiones
    model.Minimize(sum(y[j] for j in range(n_cam)))
 
    # ---------------------------------------------
    # 6) Resolver
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(tiempo_max_seg)
    solver.parameters.num_search_workers = 1
    t0 = time.time()
    resultado = solver.Solve(model)
    t1 = time.time()
    print(f"[TIMING] CP-SAT (Bin) grupo {grupo_cfg['id']}: {t1 - t0:.3f} s (límite: {tiempo_max_seg}s)")
 
    status_map = {cp_model.OPTIMAL: 'OPTIMAL', cp_model.FEASIBLE: 'FEASIBLE'}
    estado = status_map.get(resultado, 'NO_SOLUTION')
 
    # ---------------------------------------------
    # 7) Reconstruir salida
    pedidos_incluidos = [i for i in pedidos if any(solver.Value(x[(i, j)]) == 1 for j in range(n_cam))]
    datos_asig = []
    camiones = []
    idx_cam = 1

    for j, ts_var in total_stack_vars.items():
        # Sólo imprime si el camión j está usado (opcional)
        if solver.Value(y[j]):
            print(f"Camión {j} → total_stack = {solver.Value(ts_var)}")
    
    for j in range(n_cam):
        if solver.Value(y[j]) < 1:
            continue
        grp = [i for i in pedidos if solver.Value(x[(i, j)]) == 1]
        vol_real = sum(vol_int[i] for i in grp)
        peso_real = sum(peso_int[i] for i in grp)
        vcu_vol_j = vol_real / float(cap_vol) if cap_vol else 0.0
        vcu_peso_j = peso_real / float(cap_peso) if cap_peso else 0.0
        vcu_max_j = max(vcu_vol_j, vcu_peso_j)
 
        for i in grp:
            vcu_vol_i  = (vol_raw[i] / float(cap_vol))  if cap_vol else 0.0
            vcu_peso_i = (peso_raw[i] / float(cap_peso)) if cap_peso else 0.0
       
            pedido_min = {
                'PEDIDO': i,
                'CAMION': idx_cam,
                'GRUPO': grupo_cfg['id'],
                'TIPO_RUTA': grupo_cfg['tipo'],
                'TIPO_CAMION': 'normal',
                'CE': ce_map[i],
                'CD': cd_map[i],
                'VCU_VOL': vcu_vol_i,
                'VCU_PESO': vcu_peso_i,
                'CHOCOLATES':   chocolates_map[i],
                'VALIOSO':      valuable_map[i],
                'PO': po_map[i],
                'OC': oc_map[i],
                'PALLETS':  pallets_conf_map[i],
                'VALOR': valor_map[i]
            }
            # 9.4) Completar con todas las columnas internas
            pedido_completo = completar_metadata_pedido(pedido_min, raw_map)
            datos_asig.append(pedido_completo)
       
        valor_total = sum(valor_map.get(i, 0) or 0 for i in grp)
        valor_cafe = sum(cafe_map.get(i, 0) or 0 for i in grp)
        tiene_chocolates = any(chocolates_map.get(i) == 'SI' for i in grp)
        pallets_conf = sum(pallets_conf_map[i] for i in grp)
        valioso = any(valuable_map.get(i) == 1 for i in grp)

        camiones.append({
            'id': uuid.uuid4().hex,
            'grupo': grupo_cfg['id'],
            'tipo_ruta': grupo_cfg['tipo'],
            'ce': grupo_cfg['ce'],
            'cd': grupo_cfg['cd'],
            'tipo_camion': 'normal',
            'vcu_vol': vcu_vol_j,
            'vcu_peso': vcu_peso_j,
            'vcu_max': vcu_max_j,
            'chocolates': tiene_chocolates,
            'skus_valiosos': valioso,
            'valor_total': valor_total,
            'valor_cafe': valor_cafe,
            'pallets_conf': pallets_conf,
            'pedidos': datos_asig[-len(grp):]
        })
        idx_cam += 1
 
    # ----------------------------
    # 8) Detectar pedidos excluidos
    pedidos_excluidos_ids = [i for i in pedidos if i not in pedidos_incluidos]
    pedidos_excluidos = []
    for i in pedidos_excluidos_ids:
        pedido_min = {
            'PEDIDO': i,
            'CE': ce_map[i],
            'CD': cd_map[i],
            'OC': oc_map[i],
            'VCU_VOL': (vol_raw[i] / float(cap_vol)) if cap_vol else 0.0,
            'VCU_PESO': (peso_raw[i] / float(cap_peso)) if cap_peso else 0.0,
            'PO': po_map[i],
            'PALLETS': pallets_conf_map[i],
            'VALOR': valor_map[i],
        }
        pedido_ex_completo = completar_metadata_pedido(pedido_min, raw_map)
        pedidos_excluidos.append(pedido_ex_completo)
 
    return {
        'status': estado,
        'pedidos_asignados_ids': pedidos_incluidos,
        'pedidos_asignados': datos_asig,
        'pedidos_excluidos': pedidos_excluidos,
        'camiones': camiones
    }


def agregar_restricciones_agrupacion_por_po(model, x, pedidos, po_map, n_cam):
    po_grupos = {}
    for i in pedidos:
        po = po_map[i]
        po_grupos.setdefault(po, []).append(i)
 
    for po, items in po_grupos.items():
        if len(items) <= 1:
            continue
        for j in range(n_cam):
            for idx in range(1, len(items)):
                i1, i2 = items[0], items[idx]
                if (i1, j) in x and (i2, j) in x:
                    model.Add(x[(i1, j)] == x[(i2, j)])