FROM python:3.11-slim

WORKDIR /app

COPY requirements-web.txt .
RUN pip install --no-cache-dir -r requirements-web.txt

# Bake the segmentation model into the image so cold starts are instant
# and the container never needs outbound internet.
RUN python -c "from rembg import new_session; new_session('u2net_human_seg')"

COPY photoclaude/ photoclaude/
COPY webapp/ webapp/
COPY assets/ assets/

EXPOSE 8000
# $PORT is honored for PaaS hosts (Render, Railway, HF Spaces set it).
CMD ["sh", "-c", "uvicorn webapp.server:app --host 0.0.0.0 --port ${PORT:-8000}"]
