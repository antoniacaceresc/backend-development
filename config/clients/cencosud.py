
class CencosudConfig:
    HEADER_ROW = 0

    # Configuraciones algoritmo
    USA_OC = False
    AGRUPAR_POR_PO = True
    MIX_GRUPOS = []

    # Parámetros de Optimización
    VCU_MIN = 0.8
    MAX_ORDENES = 100
    MAX_PALLETS_REAL = 60
    MAX_PALLETS_CONF = 60

    # BH
    PERMITE_BH = True
    CD_CON_BH = ['N725 Bodega Noviciado', 'N641 Bodega Noviciado PYP']
    BH_MAX_POSICIONES = 26
    BH_MAX_PALLETS = 26
    BH_VCU_MAX = 1
    BH_VCU_MIN = 0.55


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
            "NO_APILABLE": "No Apilable",
            "VALIOSO": "Valioso Cencosud",
        },
        "Purina": {
            "CD": "CD",
            "PO": "Número PO",
            "PEDIDO": "N° Pedido",
            "CE": "Ce.",
            "PESO": "Peso Conf.",
            "VOL": "Vol. Conf.",
            "VALOR": "$$ Conf."
        }
    }

    EXTRA_MAPPING = {
        "Solic.":   "Solic.",
        "Cant. Sol.": "Cj. Solic.",
        "CJ Conf.": "Cj. Conf.",
        "Suma de Sol (Pallet)": "Pal. Solic.",
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
            (["N725 Bodega Noviciado"],["0079"]),
            (["N725 Bodega Noviciado"],["0080"]),
            (["N725 Bodega Noviciado"],["0088"]),
            (["N725 Bodega Noviciado"],["0103"]),
            (["N725 Bodega Noviciado"],["3598"]),
            (["N725 Bodega Noviciado"],["8150"]),

            (["N641 Bodega Noviciado PYP"],["0079"]),
            (["N641 Bodega Noviciado PYP"],["0080"]),
            (["N641 Bodega Noviciado PYP"],["0088"]),
            (["N641 Bodega Noviciado PYP"],["0103"]),
            (["N641 Bodega Noviciado PYP"],["3598"]),
            (["N641 Bodega Noviciado PYP"],["8150"]),

            (["N794 Bodega Chillan"],["0079"]),
            (["N794 Bodega Chillan"],["0080"]),
            (["N794 Bodega Chillan"],["0088"]),
            (["N794 Bodega Chillan"],["0103"]),
            (["N794 Bodega Chillan"],["3598"]),
            (["N794 Bodega Chillan"],["8150"])
        ],

        "multi_ce": [

            (["N641 Bodega Noviciado PYP"],["0088", "0103"]),
            (["N725 Bodega Noviciado"],["0088", "0103"]),
            (["N794 Bodega Chillan"],["0088", "0103"]),

        ],

        "bh": [
            (["N725 Bodega Noviciado"],["0079"]),
            (["N725 Bodega Noviciado"],["0080"]),
            (["N725 Bodega Noviciado"],["0088"]),
            (["N725 Bodega Noviciado"],["0103"]),
            (["N725 Bodega Noviciado"],["3598"]),
            (["N725 Bodega Noviciado"],["8150"]),

            (["N641 Bodega Noviciado PYP"],["0079"]),
            (["N641 Bodega Noviciado PYP"],["0080"]),
            (["N641 Bodega Noviciado PYP"],["0088"]),
            (["N641 Bodega Noviciado PYP"],["0103"]),
            (["N641 Bodega Noviciado PYP"],["3598"]),
            (["N641 Bodega Noviciado PYP"],["8150"]),
        ]

    }

