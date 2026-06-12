from app.core.pipeline.BusinessLogic import BusinessLogic
from app.core.pipeline.InfoExtractor import InfoExtractor
from app.adapters.db.SQLiteAdapter import SQLiteAdapter

def main():
    # Inicializa tus componentes
    db = SQLiteAdapter("c:/Users/Miguel Narbona/Proyectos/Python/AzureProjects/HellenCommerce_1.0.2/app/hellencommerce.db")
    extractor = InfoExtractor()
    logic = BusinessLogic(db=db, extractor=extractor)

    info = extractor.extract("Hola, compro detergente líquido marca Brillo")
    print(info)

    vendedores = db.buscar_coincidencias("vendedor", "detergente líquido marca brillo")
    print(vendedores)

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