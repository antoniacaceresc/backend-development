from typing import List, Dict, Any, Optional
import uuid


def compute_stats(
    camiones: Optional[List[Dict[str, Any]]],
    pedidos_no: Optional[List[Dict[str, Any]]]
) -> Dict[str, Any]:
    print("camiones")
    print(camiones)
    print("pedidos no inlcuidos")
    print(pedidos_no)
    camiones = camiones or []
    pedidos_no = pedidos_no or []

    cantidad_camiones = len(camiones)
    cantidad_normal = sum(1 for c in camiones if (c.get("tipo_camion") or "") != "bh")
    cantidad_bh = cantidad_camiones - cantidad_normal

    cantidad_asig = sum(len(c.get("pedidos") or []) for c in camiones)
    total_pedidos = cantidad_asig + len(pedidos_no)

    vcu_vals = [(c.get("vcu_max") or 0) for c in camiones]
    promedio_vcu = (sum(vcu_vals) / cantidad_camiones) if cantidad_camiones else 0

    norm_vals = [v for c in camiones if (c.get("tipo_camion") or "") != "bh" for v in [(c.get("vcu_max") or 0)]]
    promedio_norm = (sum(norm_vals) / cantidad_normal) if cantidad_normal else 0

    bh_vals = [v for c in camiones if (c.get("tipo_camion") or "") == "bh" for v in [(c.get("vcu_max") or 0)]]
    promedio_bh = (sum(bh_vals) / cantidad_bh) if cantidad_bh else 0

    valorizado = sum((c.get("valor_total") or 0) for c in camiones)

    return {
        "cantidad_camiones": cantidad_camiones,
        "cantidad_camiones_normal": cantidad_normal,
        "cantidad_camiones_bh": cantidad_bh,
        "cantidad_pedidos_asignados": cantidad_asig,
        "total_pedidos": total_pedidos,
        "promedio_vcu": promedio_vcu,
        "promedio_vcu_normal": promedio_norm,
        "promedio_vcu_bh": promedio_bh,
        "valorizado": valorizado
    }


def move_orders(
    state: Dict[str, Any],
    pedidos: Optional[List[Dict[str, Any]]],
    target_truck_id: Optional[str]
) -> Dict[str, Any]:
    camiones = state.get("camiones") or []
    no_incl = state.get("pedidos_no_incluidos") or []

    ids = {p.get("PEDIDO") for p in (pedidos or [])}
    for cam in camiones:
        cam["pedidos"] = [p for p in cam.get("pedidos") or [] if p.get("PEDIDO") not in ids]

    no_incl = [p for p in no_incl if p.get("PEDIDO") not in ids]

    if target_truck_id:
        for cam in camiones:
            if cam.get("id") == target_truck_id:
                cam.setdefault("pedidos", []).extend(pedidos or [])
                break
    else:
        no_incl.extend(pedidos or [])

    for cam in camiones:
        vvol = sum(p.get("VCU_VOL") or 0 for p in cam.get("pedidos") or [])
        vpes = sum(p.get("VCU_PESO") or 0 for p in cam.get("pedidos") or [])
        cam["vcu_vol"] = vvol
        cam["vcu_peso"] = vpes
        cam["vcu_max"] = max([vvol, vpes], default=0)
        cam["pallets_conf"] = sum(p.get("PALLETS") or 0 for p in cam.get("pedidos") or [])
        cam["valor_total"] = sum(p.get("VALOR") or 0 for p in cam.get("pedidos") or [])
        cam["chocolates"] = "SI" if any(p.get("CHOCOLATES") == "SI" for p in cam.get("pedidos") or []) else "NO"

    for idx, cam in enumerate(camiones, start=1):
        cam["numero"] = idx

    stats = compute_stats(camiones, no_incl)
    return {"camiones": camiones, "pedidos_no_incluidos": no_incl, "estadisticas": stats}


def add_truck(
    state: Dict[str, Any],
    cd: Optional[List[str]],
    ce: Optional[List[str]],
    ruta: Optional[str]
) -> Dict[str, Any]:
    camiones = state.get("camiones") or []
    no_incl = state.get("pedidos_no_incluidos") or []

    new_cam = {
        "id": uuid.uuid4().hex,
        "numero": len(camiones) + 1,
        "grupo": f"{','.join(cd or [])}__{','.join(ce or [])}",
        "tipo_ruta": ruta or "",
        "cd": cd or [],
        "ce": ce or [],
        "pedidos": [],
        "vcu_vol": 0,
        "vcu_peso": 0,
        "vcu_max": 0,
        "pos_total": 0,
        "flujo_oc": "",
        "tipo_camion": "normal",
        "chocolates": "NO",
        "pallets_conf": 0,
        "valor_total": 0
    }
    camiones.append(new_cam)
    return move_orders({"camiones": camiones, "pedidos_no_incluidos": no_incl}, [], None)


def delete_truck(
    state: Dict[str, Any],
    truck_id: Optional[str]
) -> Dict[str, Any]:
    camiones = state.get("camiones") or []
    no_incl = state.get("pedidos_no_incluidos") or []

    if truck_id:
        eliminado = next((c for c in camiones if c.get("id") == truck_id), None)
        if eliminado:
            camiones = [c for c in camiones if c.get("id") != truck_id]
            no_incl.extend(eliminado.get("pedidos") or [])

    return move_orders({"camiones": camiones, "pedidos_no_incluidos": no_incl}, [], None)
