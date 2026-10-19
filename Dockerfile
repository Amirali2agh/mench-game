# Use the official lightweight Python image
FROM python:3.12-slim

# Set environment variables to optimize Python behavior inside the container
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

# Set the working directory inside the container
WORKDIR /code

# Package index used for the build. The default is the public PyPI; deployments
# in restricted networks (for example inside Iran) can opt in to a mirror:
#   docker build --build-arg PIP_INDEX_URL=https://mirror2.chabokan.net/pypi/simple/ .
# PIP_TRUSTED_HOST is only needed for a mirror served over plain HTTP.
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=

# Copy the pinned dependency file to the working directory
COPY ./requirements.txt /code/requirements.txt

# Install the runtime dependencies only (no pytest / test tooling)
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /code/requirements.txt \
        --index-url "${PIP_INDEX_URL}" \
        ${PIP_TRUSTED_HOST:+--trusted-host "${PIP_TRUSTED_HOST}"}

# Run as an unprivileged user so a container escape is not root on the host
RUN addgroup --system app && adduser --system --ingroup app --home /code app

# Copy the application code, owned by the unprivileged user
COPY --chown=app:app ./app /code/app

USER app

# Expose the port FastAPI runs on
EXPOSE 8000

# /health answers 503 while Redis is unreachable, so the container reports
# itself unhealthy exactly when it cannot serve game actions.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"

# Start the FastAPI application using Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
