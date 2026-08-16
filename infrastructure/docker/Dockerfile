ARG PROJECT_PIPELINE_BASE_IMAGE
FROM ${PROJECT_PIPELINE_BASE_IMAGE}
WORKDIR /opt/project-pipeline
COPY pyproject.toml README.md LICENSE ./
COPY requirements/runtime.txt requirements/runtime.txt
COPY src/ src/
COPY scripts/run_command_center_service.py scripts/run_command_center_service.py
RUN python -m pip install --no-cache-dir -r requirements/runtime.txt && python -m pip install --no-deps . \
    && useradd --system --home /opt/project-pipeline --uid 10001 projectpipeline \
    && chown -R projectpipeline:projectpipeline /opt/project-pipeline
USER projectpipeline
EXPOSE 8765
CMD ["python", "scripts/run_command_center_service.py", "--root", ".", "--host", "0.0.0.0", "--port", "8765"]
