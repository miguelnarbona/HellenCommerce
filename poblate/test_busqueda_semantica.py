from core.pipeline.BusinessLogic import BusinessLogic
from core.pipeline.InfoExtractor import InfoExtractor
from adapters.db.SQLiteAdapter import SQLiteAdapter

def main():
    # Inicializa tus componentes
    db = SQLiteAdapter("ruta_a_tu_db.sqlite")
    extractor = InfoExtractor()
    logic = BusinessLogic(db=db, extractor=extractor)

    # Prompt de prueba: comprador pide detergente líquido Brillo
    message = "Hola, compro detergente líquido marca Brillo, si es posible con entrega a domicilio"
    role = "comprador"
    user_id = "test_user_detergente"

    # Procesa el mensaje
    resultado = logic.process(message, role, user_id)

    # Imprime salida para verificar
    print("\n=== CONTEXTO BASE ===")
    for k, v in resultado.items():
        print(f"{k}: {v}")

if __name__ == "__main__":
    main()