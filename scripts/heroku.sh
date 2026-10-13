#!/bin/sh
# Arranque en Heroku. El mismo repositorio se despliega en dos apps de Heroku, que se
# distinguen por la variable de configuración ROL:
#   ROL=api        API FastAPI con Heroku Postgres; aplica las migraciones en cada despliegue.
#   ROL=streamlit  App Streamlit; se conecta a la API con VALORIZADOR_API_URL.
# Uso (desde el Procfile): sh scripts/heroku.sh release | web
set -e

case "$ROL:$1" in
  api:release)
    exec alembic upgrade head
    ;;
  streamlit:release)
    exit 0
    ;;
  api:web)
    exec uvicorn valorizador.main:app --host 0.0.0.0 --port "$PORT" --proxy-headers --forwarded-allow-ips="*"
    ;;
  streamlit:web)
    exec streamlit run app/inicio.py --server.port "$PORT" --server.address 0.0.0.0 --server.headless true
    ;;
  *)
    echo "Defina ROL=api o ROL=streamlit en la configuración de la app de Heroku (recibido: '$ROL', '$1')" >&2
    exit 1
    ;;
esac
