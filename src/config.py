"""
Configuration management for Kubernetes Platform Engineer MCP Server.
"""

import os
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class KubernetesConfig:
    """Kubernetes-specific configuration."""
    kubeconfig_path: Optional[str] = None
    default_namespace: str = "default"
    context: Optional[str] = None
    cluster_name: Optional[str] = None
    timeout: int = 30


@dataclass
class MonitoringConfig:
    """Monitoring and observability configuration."""
    prometheus_url: Optional[str] = None
    grafana_url: Optional[str] = None
    alert_manager_url: Optional[str] = None
    enable_metrics: bool = True
    metrics_port: int = 8080


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    file_path: Optional[str] = None
    max_size: str = "10MB"
    backup_count: int = 5


@dataclass
class SecurityConfig:
    """Security and authentication configuration."""
    rbac_enabled: bool = True
    pod_security_standards: bool = True
    network_policies: bool = True
    admission_controllers: List[str] = None
    
    def __post_init__(self):
        if self.admission_controllers is None:
            self.admission_controllers = [
                "NamespaceLifecycle",
                "LimitRanger", 
                "ServiceAccount",
                "DefaultStorageClass",
                "DefaultTolerationSeconds",
                "MutatingAdmissionWebhook",
                "ValidatingAdmissionWebhook",
                "ResourceQuota",
                "PodSecurityPolicy"
            ]


@dataclass
class DiagnosticsConfig:
    """Diagnostics and troubleshooting configuration."""
    enable_performance_monitoring: bool = True
    enable_network_diagnostics: bool = True
    enable_storage_diagnostics: bool = True
    enable_container_runtime_diagnostics: bool = True
    diagnostic_timeout: int = 60
    max_concurrent_diagnostics: int = 5


@dataclass
class ServerConfig:
    """Main server configuration."""
    name: str = "kubernetes-platform-engineer"
    version: str = "1.0.0"
    description: str = "Kubernetes Platform Engineer MCP Server"
    host: str = "0.0.0.0"
    port: int = 3000
    debug: bool = False
    
    # Sub-configurations
    kubernetes: KubernetesConfig = None
    monitoring: MonitoringConfig = None
    logging: LoggingConfig = None
    security: SecurityConfig = None
    diagnostics: DiagnosticsConfig = None
    
    def __post_init__(self):
        """Initialize sub-configurations with environment variables."""
        if self.kubernetes is None:
            self.kubernetes = KubernetesConfig(
                kubeconfig_path=os.getenv("KUBECONFIG", "~/.kube/config"),
                default_namespace=os.getenv("K8S_NAMESPACE", "default"),
                context=os.getenv("K8S_CONTEXT"),
                cluster_name=os.getenv("K8S_CLUSTER_NAME"),
                timeout=int(os.getenv("K8S_TIMEOUT", "30"))
            )
        
        if self.monitoring is None:
            self.monitoring = MonitoringConfig(
                prometheus_url=os.getenv("PROMETHEUS_URL"),
                grafana_url=os.getenv("GRAFANA_URL"),
                alert_manager_url=os.getenv("ALERTMANAGER_URL"),
                enable_metrics=os.getenv("ENABLE_METRICS", "true").lower() == "true",
                metrics_port=int(os.getenv("METRICS_PORT", "8080"))
            )
        
        if self.logging is None:
            self.logging = LoggingConfig(
                level=os.getenv("LOG_LEVEL", "INFO"),
                file_path=os.getenv("LOG_FILE"),
                max_size=os.getenv("LOG_MAX_SIZE", "10MB"),
                backup_count=int(os.getenv("LOG_BACKUP_COUNT", "5"))
            )
        
        if self.security is None:
            self.security = SecurityConfig(
                rbac_enabled=os.getenv("RBAC_ENABLED", "true").lower() == "true",
                pod_security_standards=os.getenv("POD_SECURITY_STANDARDS", "true").lower() == "true",
                network_policies=os.getenv("NETWORK_POLICIES", "true").lower() == "true"
            )
        
        if self.diagnostics is None:
            self.diagnostics = DiagnosticsConfig(
                enable_performance_monitoring=os.getenv("ENABLE_PERF_MONITORING", "true").lower() == "true",
                enable_network_diagnostics=os.getenv("ENABLE_NET_DIAGNOSTICS", "true").lower() == "true",
                enable_storage_diagnostics=os.getenv("ENABLE_STORAGE_DIAGNOSTICS", "true").lower() == "true",
                enable_container_runtime_diagnostics=os.getenv("ENABLE_RUNTIME_DIAGNOSTICS", "true").lower() == "true",
                diagnostic_timeout=int(os.getenv("DIAGNOSTIC_TIMEOUT", "60")),
                max_concurrent_diagnostics=int(os.getenv("MAX_CONCURRENT_DIAGNOSTICS", "5"))
            )
        
        # Override with environment variables
        self.host = os.getenv("MCP_HOST", self.host)
        self.port = int(os.getenv("MCP_PORT", str(self.port)))
        self.debug = os.getenv("DEBUG", "false").lower() == "true"


def load_config() -> ServerConfig:
    """Load configuration from environment variables and defaults."""
    return ServerConfig()


# Global configuration instance
config = load_config()
