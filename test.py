def calcular_expresion(B, S, F, A):
    # Primer término: mínimo entre B y S
    termino1 = min(B, S)
    
    # Segundo término: mínimo entre |B–S| y F
    diff = abs(B - S)
    termino2 = min(diff, F)
    
    # Tercer término: round((F - min(diff, F)) / 2)
    resto = F - termino2
    termino3 = round(resto / 2)
    
    # Cuarto término: max(|B–S| - F, 0)
    termino4 = max(diff - F, 0)
    
    # Suma final con A
    return termino1 + termino2 + termino3 + termino4 + A

def main():
    # Lectura de inputs desde consola
    B = float(input("Ingrese el valor de PB: "))
    S = float(input("Ingrese el valor de PS: "))
    F = float(input("Ingrese el valor de PF: "))
    A = float(input("Ingrese el valor de PA: "))

    # Cálculo y presentación del resultado
    resultado = calcular_expresion(B, S, F, A)
    print(f"\nResultado: {resultado}")

if __name__ == "__main__":
    main()
