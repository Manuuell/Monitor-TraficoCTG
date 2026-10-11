"""
Script de autorizacion OAuth - ejecutar UNA SOLA VEZ desde tu PC local.

Que hace:
1. Lee oauth_client.json desde CREDENCIALES_DIR
2. Abre el navegador para que inicies sesion en Google
3. Te pide autorizar el acceso a Drive + Sheets
4. Guarda token.json con el refresh_token y permisos 0600

Uso:
    python src/autorizar_google.py

Luego puedes copiar token.json al CREDENCIALES_DIR del VPS.
"""
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

# Permitir importar config desde mismo directorio
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
import google_upload  # noqa: E402


def main():
    print("=" * 60)
    print("AUTORIZACION GOOGLE OAUTH - TomTom Cartagena")
    print("=" * 60)

    if not config.OAUTH_CLIENT_FILE.exists():
        print(f"\nERROR: No existe {config.OAUTH_CLIENT_FILE}")
        print("Descarga el JSON del OAuth Client desde Google Cloud Console")
        print(f"y guardalo en {config.OAUTH_CLIENT_FILE}")
        return 1

    print(f"\nUsando: {config.OAUTH_CLIENT_FILE}")
    print(f"Scopes: {config.GOOGLE_SCOPES}")
    print("\nSe abrira tu navegador para autorizar...")
    print("Inicia sesion con la cuenta Google que tiene acceso al Drive/Sheet.\n")

    flow = InstalledAppFlow.from_client_secrets_file(
        str(config.OAUTH_CLIENT_FILE),
        config.GOOGLE_SCOPES,
    )
    creds = flow.run_local_server(port=0, prompt="consent")

    google_upload.guardar_token_seguro(creds.to_json())

    print("\n" + "=" * 60)
    print(f"OK Token guardado en: {config.OAUTH_TOKEN_FILE}")
    print("=" * 60)
    print("\nProximos pasos:")
    print("  1. Probar localmente: python src/descargar_trafico.py")
    print(f"  2. Copiar {config.OAUTH_TOKEN_FILE.name} al VPS:")
    print(f"     scp -i llave.pem {config.OAUTH_TOKEN_FILE} \\")
    print("         ubuntu@<IP_VPS>:/home/ubuntu/.config/proyect_r/credenciales/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
