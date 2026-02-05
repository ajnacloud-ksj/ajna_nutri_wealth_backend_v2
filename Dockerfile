FROM public.ecr.aws/lambda/python:3.12

# Install uv for faster dependency installation
RUN pip install uv

# Copy dependency files
COPY pyproject.toml ${LAMBDA_TASK_ROOT}
COPY src/requirements.txt ${LAMBDA_TASK_ROOT}

# Install dependencies using uv (faster than pip)
RUN uv pip install --system -r ${LAMBDA_TASK_ROOT}/requirements.txt

# Copy function code
COPY src/ ${LAMBDA_TASK_ROOT}/src/
COPY src/app.py ${LAMBDA_TASK_ROOT}/app.py
COPY local_server.py ${LAMBDA_TASK_ROOT}/

# Add src to PYTHONPATH so relative imports work
ENV PYTHONPATH="${LAMBDA_TASK_ROOT}/src:${PYTHONPATH}"

# Ensure correct permissions for Lambda execution
RUN chmod -R 755 ${LAMBDA_TASK_ROOT}

# Set the CMD to handler
CMD [ "app.lambda_handler" ]
