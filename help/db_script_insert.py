# Script para insertar datos en los campos de las tabla `usuarios` de la base de datos helllencommerce
# cada insercion esta formada por:

# un user_id, 
# tipo, 
# nombre, 
# mercancia, 
# tamaños, 
# precio, 
# ubicacion, 
# telefono, 
# correo, 
# contacto, 
# domicilio, 
# estado, 
# contexto

# ej: nuevos = [
#        ("60000011", "vendedor", "Raúl Medina", "Arroz brasileño", "saco de 25kg", 22.0,
#         "La Habana", "60000011", "raul.medina@ejemplo.com", "Raúl Medina", 1, "activo",
#         "USUARIO: Tengo arroz brasileño en sacos de 25kg, buena calidad.\nIA: Entendido, lo registro."),

# Tambien tenemos como ejemplo en la misma tabla `usuarios` otra inserccion en otros campos:
# INSERT INTO usuarios (
#        user_id, tipo, nombre, mercancia, precio, ubicacion,
#        telefono, correo, domicilio, estado
#    )
#    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
#    """, (
#        "60000031", "vendedor", "Juan Pérez",
#        "detergente líquido marca brillo",
#        5.5, "Santiago de Cuba",
#        "5551234", None, 0, "activo"

# Este ejemplo es para proporcionar la ubicacion actual:
# UPDATE marketplace
#            SET lat = ?, lon = ?
#            WHERE id = ?
#        """, (lat, lon, negocio_id))