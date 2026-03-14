FROM public.ecr.aws/lambda/python:3.12

# Install uv for fast Python package management
RUN pip install uv

# Install ajna-cloud SDK from GitHub Release wheel
ARG SDK_VERSION=v0.2.2.0.15
RUN uv pip install --system --no-cache "https://github.com/ajnacloud-ksj/ajna-cloud-sdk/releases/download/${SDK_VERSION}/ajna_cloud-0.2.2.0-py3-none-any.whl"

# Copy and install remaining dependencies
COPY src/requirements.txt ${LAMBDA_TASK_ROOT}/
RUN uv pip install --system --no-cache -r ${LAMBDA_TASK_ROOT}/requirements.txt

# Copy ALL source code
COPY src/ ${LAMBDA_TASK_ROOT}/src/

# Copy app.py to root for Lambda entry point
COPY src/app.py ${LAMBDA_TASK_ROOT}/app.py

# Ensure schemas are available
COPY src/schemas ${LAMBDA_TASK_ROOT}/schemas

# Force Python to compile all modules to catch import errors at build time
RUN python -m compileall ${LAMBDA_TASK_ROOT}/src/

# Add src to PYTHONPATH so relative imports work
ENV PYTHONPATH="${LAMBDA_TASK_ROOT}/src:${PYTHONPATH}"

# Ensure correct permissions for Lambda execution
RUN chmod -R 755 ${LAMBDA_TASK_ROOT}

# Set the CMD to handler
CMD [ "app.lambda_handler" ]
