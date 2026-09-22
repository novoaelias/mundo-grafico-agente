# Mundo Gráfico: el webhook de Chatwoot del AgentKit + el panel interno,
# en un servidor.
#
# Corre `servidor_mundografico.py`, no el `webhook_chatwoot.py` original del
# kit: es el mismo servidor (mismo webhook, mismo /salud) con el panel de
# pedidos/catálogo/taller sumado encima y las migraciones de Postgres
# aplicándose solas al arrancar. Ver ese archivo para el detalle.
#
# El bot de Telegram del kit también queda adentro de la imagen por las
# dudas, aunque acá Telegram entra por Chatwoot (un inbox más), no por
# `bot_telegram.py` directo.
#
# Toda la configuración entra por variables de entorno. El .env no se copia
# acá adentro: en el servidor las variables las pone Coolify.

FROM python:3.13-slim

# Sin esto, Python se guarda los logs en un buffer y en el panel del servidor
# no ves nada hasta que el proceso muere. Con un servidor que corre para
# siempre, eso es no ver nunca nada.
ENV PYTHONUNBUFFERED=1

# Que las tildes no rompan cuando se imprime un mensaje.
ENV PYTHONIOENCODING=utf-8

WORKDIR /app

# curl es para el health check del panel, no para la app.
#
# Coolify (y casi cualquier PaaS) revisa que el contenedor esté vivo pegándole
# a una URL con curl o wget DESDE ADENTRO del contenedor. La imagen `slim` no
# trae ninguno de los dos, así que sin esta línea el contenedor arranca bien,
# atiende bien, y el panel igual lo marca *unhealthy* y lo da de baja. El log
# que deja es "New container is not healthy, rolling back": no dice que falte
# curl, y se pierde un rato largo buscando el error en otro lado.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Las dependencias primero y el código después: así, mientras no toques los
# requirements, Docker reusa la capa ya instalada y el deploy tarda segundos
# en vez de minutos.
COPY requirements.txt requirements-produccion.txt requirements-mundografico.txt ./
RUN pip install --no-cache-dir -r requirements-mundografico.txt

COPY src/ ./src/
COPY prompts/ ./prompts/
COPY webhook_chatwoot.py bot_telegram.py servidor_mundografico.py ./

# Sin esto corre como root sin necesidad: el servidor no escribe nada en
# disco (la memoria va a Postgres).
RUN useradd --create-home agente && chown -R agente:agente /app
USER agente

# El puerto donde escucha. Coolify lee este número para saber a dónde
# mandarle el tráfico del dominio.
ENV PUERTO=8000
EXPOSE 8000

CMD ["python", "servidor_mundografico.py"]
