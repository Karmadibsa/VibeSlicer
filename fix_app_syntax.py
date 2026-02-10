
import os

with open("app.py", "r", encoding="utf-8") as f:
    content = f.read()

# Le bloc fautif (copié-collé depuis view_file sauf l'indentation de première ligne)
bad_block = r'''        clean_title = title_text.replace("'", "").replace(":", "\:")
        poppins = os.path.join(ASSETS_DIR, "Poppins-Bold.ttf").replace("\", "/").replace(":", "\:")
        font_opt = f":fontfile='{poppins}'" if os.path.exists(os.path.join(ASSETS_DIR, "Poppins-Bold.ttf")) else ""'''

# Le bloc corrigé (avec double backslash pour échapper)
good_block = r'''        clean_title = title_text.replace("'", "").replace(":", "\\:")
        poppins = os.path.join(ASSETS_DIR, "Poppins-Bold.ttf").replace("\\", "/").replace(":", "\\:")
        font_opt = f":fontfile='{poppins}'" if os.path.exists(os.path.join(ASSETS_DIR, "Poppins-Bold.ttf")) else ""'''

if bad_block in content:
    content = content.replace(bad_block, good_block)
    print("Bloc 1 corrigé.")
else:
    print("Bloc 1 non trouvé (peut-être déjà corrigé ou indentation différente).")
    # Fallback: remplacement ligne par ligne simple
    content = content.replace(r'.replace("\", "/")', r'.replace("\\", "/")')
    content = content.replace(r'.replace(":", "\:")', r'.replace(":", "\\:")')
    print("Fallback simple replace appliqué.")

with open("app.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Fix terminé.")
