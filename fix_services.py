import os
import re

services_dir = r'c:\HellenCommerce\services'
for folder in os.listdir(services_dir):
    service_path = os.path.join(services_dir, folder)
    if os.path.isdir(service_path) and folder.endswith('_service'):
        main_py = os.path.join(service_path, 'main.py')
        if os.path.exists(main_py):
            with open(main_py, 'r', encoding='utf-8') as f:
                content = f.read()
            
            match = re.search(r'\"intent\":\s*\"([A-Z]+)\"', content)
            if not match:
                print(f'Intent not found in {folder}')
                continue
            intent = match.group(1)
            
            new_process = f'''@app.post("/process")
async def process_intent(req: ProcessRequest):
    \"\"\"
    Procesa intenciones de tipo {intent}.
    Recibe el prompt ya ensamblado por el orquestador y lo ejecuta en Mistral/HF.
    \"\"\"
    user_id = req.user_id
    prompt  = req.prompt

    try:
        partial_response = await call_mistral(
            prompt,
            fallback="No se pudo generar una respuesta en este momento."
        )

        await log_to_logging_service("INFO", f"Proceso {intent} completado para {{user_id}}", line_num=0)
        return {{"intent": "{intent}", "partial": partial_response}}

    except Exception as e:
        await log_to_logging_service("ERROR", f"Error procesando {intent} para {{user_id}}: {{e}}", line_num=0)
        return {{"intent": "{intent}", "partial": "Hubo un problema procesando tu solicitud."}}
'''
            
            pattern = re.compile(r'@app\.post\(\"/process\"\).*?(?=@app\.get\(\"/health\"\))', re.DOTALL)
            new_content = pattern.sub(new_process + '\n', content)
            
            if new_content != content:
                with open(main_py, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                print(f'Updated {folder} ({intent})')
            else:
                print(f'No changes for {folder}')
