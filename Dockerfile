# Kubernetes Platform Engineer MCP Server
FROM python:3.11-slim

# Install system dependencies for Kubernetes tools and Linux administration
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    git \
    jq \
    vim \
    nano \
    net-tools \
    iproute2 \
    dnsutils \
    telnet \
    netcat-traditional \
    tcpdump \
    strace \
    htop \
    iotop \
    sysstat \
    lsof \
    procps \
    psmisc \
    tree \
    unzip \
    ca-certificates \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install kubectl
RUN curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" \
    && install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl \
    && rm kubectl

# Install helm
RUN curl https://baltocdn.com/helm/signing.asc | gpg --dearmor | tee /usr/share/keyrings/helm.gpg > /dev/null \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/helm.gpg] https://baltocdn.com/helm/stable/debian/ all main" | tee /etc/apt/sources.list.d/helm-stable-debian.list \
    && apt-get update \
    && apt-get install helm \
    && rm -rf /var/lib/apt/lists/*

# Install k9s for cluster management
RUN wget https://github.com/derailed/k9s/releases/latest/download/k9s_Linux_amd64.tar.gz \
    && tar -xzf k9s_Linux_amd64.tar.gz \
    && mv k9s /usr/local/bin/ \
    && rm k9s_Linux_amd64.tar.gz

# Install kubectx and kubens
RUN git clone https://github.com/ahmetb/kubectx /opt/kubectx \
    && ln -s /opt/kubectx/kubectx /usr/local/bin/kubectx \
    && ln -s /opt/kubectx/kubens /usr/local/bin/kubens

# Install stern for log aggregation
RUN wget https://github.com/stern/stern/releases/download/v1.32.0/stern_1.32.0_linux_amd64.tar.gz \
    && tar -xzf stern_1.32.0_linux_amd64.tar.gz \
    && mv stern /usr/local/bin/ \
    && rm stern_1.32.0_linux_amd64.tar.gz

# Install docker CLI for container runtime troubleshooting
RUN curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/debian bookworm stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null \
    && apt-get update \
    && apt-get install -y docker-ce-cli \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Ensure docs directory is included
COPY docs/ ./docs/

# Create directories for logs, configs, and data
RUN mkdir -p /app/logs /app/configs /app/data /root/.kube

# Set environment variables
ENV PYTHONPATH=/app
ENV KUBECONFIG=/root/.kube/config
ENV MCP_SERVER_NAME="kubernetes-platform-engineer"
ENV MCP_SERVER_VERSION="1.0.0"

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import src.health_check; src.health_check.check()" || exit 1

# Expose MCP server port
EXPOSE 3001

# Default command - start the HTTP server
CMD ["python", "src/main.py", "start", "--host", "0.0.0.0", "--port", "3001"]
