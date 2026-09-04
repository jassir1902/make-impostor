# --- Etapa 1: builder ---
# Instala las dependencias en un venv aislado para copiar solo lo
# necesario a la imagen final (sin cache de pip, sin herramientas de build).
FROM python:3.12-slim AS builder

WORKDIR /build

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Etapa 2: runtime ---
# Imagen final: solo el venv ya construido + el código de la aplicación.
# Sin pytest, black, mypy ni ninguna dependencia de desarrollo — ver
# 06_devops_and_ci_cd.md, sección 1.1.
FROM python:3.12-slim AS runtime

WORKDIR /app

# Usuario sin privilegios — el proceso de la aplicación nunca corre como root.
RUN useradd --create-home --shell /bin/bash appuser

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY app/ ./app/
COPY main.py .

RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
