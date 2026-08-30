FROM python:3.13-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir a2a-sdk fastapi uvicorn httpx sse-starlette

# Copy agent files
COPY agent_a.py agent_b.py run_demo.py ./

# Expose ports
EXPOSE 41241 41242

# Default: run the demo
CMD ["python", "run_demo.py"]
