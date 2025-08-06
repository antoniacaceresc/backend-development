
class DisvetConfig:
    HEADER_ROW = 0

    # Configuraciones algoritmo
    USA_OC = False
    AGRUPAR_POR_PO = False

    # Parámetros de Optimización
    VCU_MIN = 0.8
    MAX_ORDENES = 50
    MAX_PALLETS_CONF = 60
    MAX_PALLETS_REAL = 120

    # BH
    PERMITE_BH = True
    CD_CON_BH = ['Cerro Grande', 'Kameid']
    BH_MAX_POSICIONES = 28
    BH_VCU_MAX = 1
    BH_VCU_MIN = 0.55
    BH_MAX_PALLETS = 56

    # MIX Flujo
    MIX_GRUPOS = []

    # Mapeo de columnas
    COLUMN_MAPPING = {
        "Secos": {   
            "CD": "CD",
            "PO": "Número PO",
            "PEDIDO": "N° Pedido",
            "CE": "Ce.",
            "PALLETS": "Pal. Conf.",
            "PESO": "Peso Conf.",
            "VOL": "Vol. Conf.",
            "VALOR": "$$ Conf.",
            "CHOCOLATES": "Chocolates",
            "VALOR_CAFE": "Valor Cafe",
            "BASE": "Base",
            "SUPERIOR": "Superior",
            "FLEXIBLE": "Flexible",
            "NO_APILABLE": "No Apilable"
        },
    }

    EXTRA_MAPPING = {
        "Solic.":   "Solic.",
        "Cant. Sol.": "Cj. Solic.",
        "CJ Conf.": "Cj. Conf.",
        "Suma de Conf (Pallet)": "Pal. Conf.",
        "Suma de Valor neto CONF": "$$ Conf.",
        "%NS": "%NS",
        "Fecha preferente de entrega": "Fecha prefer/entrega", 
    }

    # Tipos de camiones
    TRUCK_TYPES = [{'type':'normal','cap_weight':23000,'cap_volume':70000, 'max_positions': 30, 'levels': 2}]

    # Configuración agrupamiento especial

    RUTAS_POSIBLES = {
        "normal": [
            
            (["Bioñuble"],["0088"]),
            (["Bioñuble"],["0097"]),
            (["Bioñuble"],["0103"]),

            (["Cerro Grande"],["0088"]),
            (["Cerro Grande"],["0097"]),
            (["Cerro Grande"],["0103"]),
            
            (["Comech"],["0088"]),
            (["Comech"],["0097"]),
            (["Comech"],["0103"]),
            
            (["Ferrbest"],["0088"]),
            (["Ferrbest"],["0097"]),
            (["Ferrbest"],["0103"]),

            (["Friex"],["0088"]),
            (["Friex"],["0097"]),
            (["Friex"],["0103"]),

            (["HN"],["0088"]),
            (["HN"],["0097"]),
            (["HN"],["0103"]),
            
            (["Jama"],["0088"]),
            (["Jama"],["0097"]),
            (["Jama"],["0103"]),

            (["Kameid"],["0088"]),
            (["Kameid"],["0097"]),
            (["Kameid"],["0103"]),

            (["Maxima"],["0088"]),
            (["Maxima"],["0097"]),
            (["Maxima"],["0103"]),

            (["Norkoshe"],["0088"]),
            (["Norkoshe"],["0097"]),
            (["Norkoshe"],["0103"]),
            
            (["Pan de Azucar"],["0088"]),
            (["Pan de Azucar"],["0097"]),
            (["Pan de Azucar"],["0103"]),

            (["Relun"],["0088"]),
            (["Relun"],["0097"]),
            (["Relun"],["0103"]),

            (["Vivancos SPA"],["0088"]),
            (["Vivancos SPA"],["0097"]),
            (["Vivancos SPA"],["0103"]),
        ],

        "multi_ce": [
            
            # Ces: Quilicura y Maipú
            (["Bioñuble"],["0088", "0103"]),
            (["Cerro Grande"],["0088", "0103"]),
            (["Comech"],["0088", "0103"]),
            (["Ferrbest"],["0088", "0103"]),
            (["Friex"],["0088", "0103"]),
            (["HN"],["0088", "0103"]),
            (["Jama"],["0088", "0103"]),
            (["Kameid"],["0088", "0103"]),
            (["Norkoshe"],["0088", "0103"]),
            (["Pan de Azucar"],["0088", "0103"]),
            (["PDA"],["0088", "0103"]),
            (["Relun"],["0088", "0103"]),
            (["Vivancos SPA"],["0088", "0103"]),

        ],
        "multi_cd": [
            # Desde Quilicura
            (["Bioñuble","Relun"],["0088"]),
            (["Norkoshe", "HN"],["0088"]),
            (["PDA", "Jama"],["0088"]),
            (["Ferrbest", "Comech"],["0088"]),

            # Desde Maipú
            (["Bioñuble","Relun"],["0103"]),
            (["Norkoshe", "HN"],["0103"]),
            (["PDA", "Jama"],["0103"]),
            (["Ferrbest", "Comech"],["0103"]),

        ],
        
        "bh": [
            #estas igua estan incluidas en  noramles y multi
            (["Cerro Grande"],["0088"]),
            (["Cerro Grande"],["0097"]),
            (["Cerro Grande"],["0103"]),
            (["Cerro Grande"],["0088", "0103"]),
            (["Kameid"],["0088"]),
            (["Kameid"],["0097"]),
            (["Kameid"],["0103"]),
            (["Kameid"],["0088", "0103"]),
        ]

    }

