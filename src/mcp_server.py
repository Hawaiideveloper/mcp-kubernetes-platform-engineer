"""
Kubernetes Platform Engineer MCP Server

Main MCP server implementation for comprehensive Kubernetes platform engineering,
cluster troubleshooting, monitoring, and system administration.
"""

import json
from typing import Any, Dict, Optional

from mcp import ListToolsResult
from mcp.server import Server
from mcp.server.models import InitializationOptions

from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolResult,
    TextContent,
    Tool,
)

from config import ServerConfig
from k8s_manager import KubernetesManager
from diagnostics_manager import DiagnosticsManager
from monitoring_manager import MonitoringManager
from security_manager import SecurityManager
from documentation_manager import DocumentationManager
from github_issues_manager import GitHubIssuesManager
from kubectl_manager import KubectlManager
from helm_manager import HelmManager
from logger import get_logger


class KubernetesPlatformEngineerMCPServer:
    """
    Kubernetes Platform Engineer MCP Server
    
    Provides comprehensive tools for:
    - Kubernetes cluster management and troubleshooting
    - Container runtime diagnostics
    - Network and storage troubleshooting
    - Performance monitoring and optimization
    - Security scanning and compliance
    - Automated incident response
    """
    
    def __init__(self, config: ServerConfig):
        """Initialize the MCP server with configuration."""
        self.config = config
        self.logger = get_logger(__name__)
        
        # Initialize MCP server
        self.server = Server("kubernetes-platform-engineer")
        
        # Check for non-destructive mode
        import os
        self.non_destructive_mode = os.getenv('ALLOW_ONLY_NON_DESTRUCTIVE_TOOLS', 'false').lower() == 'true'
        if self.non_destructive_mode:
            self.logger.info("Running in NON-DESTRUCTIVE MODE - destructive operations disabled")
        
        # Initialize managers
        self.k8s_manager = KubernetesManager(config.kubernetes)
        self.diagnostics_manager = DiagnosticsManager(config.diagnostics)
        self.monitoring_manager = MonitoringManager(config.monitoring)
        self.security_manager = SecurityManager(config.security)
        self.documentation_manager = DocumentationManager(config)
        self.github_issues_manager = GitHubIssuesManager(config)
        
        # Initialize enhanced managers
        self.kubectl_manager = KubectlManager(non_destructive_mode=self.non_destructive_mode)
        self.helm_manager = HelmManager(non_destructive_mode=self.non_destructive_mode)
        
        # Register MCP handlers
        self._register_handlers()
    
    def _register_handlers(self):
        """Register MCP protocol handlers."""
        
        @self.server.list_tools()
        async def handle_list_tools() -> ListToolsResult:
            """List available tools for Kubernetes platform engineering."""
            return ListToolsResult(
                tools=[
                    # Cluster Management Tools
                    Tool(
                        name="get_cluster_info",
                        description="Get comprehensive cluster information including nodes, version, and health status",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "include_details": {
                                    "type": "boolean",
                                    "description": "Include detailed node and component information",
                                    "default": True
                                }
                            }
                        }
                    ),
                    Tool(
                        name="diagnose_cluster_health",
                        description="Perform comprehensive cluster health diagnostics",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "check_types": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Types of checks to perform: nodes, pods, services, networking, storage",
                                    "default": ["nodes", "pods", "services", "networking"]
                                },
                                "namespace": {
                                    "type": "string",
                                    "description": "Namespace to focus diagnostics on (optional)"
                                }
                            }
                        }
                    ),
                    Tool(
                        name="troubleshoot_pod_issues",
                        description="Diagnose and troubleshoot pod-related issues",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "pod_name": {
                                    "type": "string",
                                    "description": "Name of the pod to troubleshoot"
                                },
                                "namespace": {
                                    "type": "string",
                                    "description": "Namespace of the pod",
                                    "default": "default"
                                },
                                "include_logs": {
                                    "type": "boolean",
                                    "description": "Include recent pod logs in analysis",
                                    "default": True
                                },
                                "include_events": {
                                    "type": "boolean",
                                    "description": "Include cluster events related to the pod",
                                    "default": True
                                }
                            },
                            "required": ["pod_name"]
                        }
                    ),
                    Tool(
                        name="analyze_resource_usage",
                        description="Analyze resource usage across cluster, nodes, or specific workloads",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "scope": {
                                    "type": "string",
                                    "enum": ["cluster", "node", "namespace", "pod"],
                                    "description": "Scope of resource analysis"
                                },
                                "target": {
                                    "type": "string",
                                    "description": "Specific target (node name, namespace, or pod name) when scope is not cluster"
                                },
                                "metrics": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Metrics to analyze: cpu, memory, storage, network",
                                    "default": ["cpu", "memory"]
                                }
                            },
                            "required": ["scope"]
                        }
                    ),
                    Tool(
                        name="check_network_connectivity",
                        description="Diagnose network connectivity issues between pods, services, and external endpoints",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "source_pod": {
                                    "type": "string",
                                    "description": "Source pod for connectivity test"
                                },
                                "target": {
                                    "type": "string",
                                    "description": "Target (pod, service, or external URL) to test connectivity to"
                                },
                                "namespace": {
                                    "type": "string",
                                    "description": "Namespace for the source pod",
                                    "default": "default"
                                },
                                "test_types": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Types of tests: ping, dns, http, tcp",
                                    "default": ["ping", "dns"]
                                }
                            },
                            "required": ["source_pod", "target"]
                        }
                    ),
                    Tool(
                        name="analyze_logs",
                        description="Analyze and aggregate logs from pods, containers, or cluster components",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "target": {
                                    "type": "string",
                                    "description": "Target for log analysis (pod name, deployment, or 'cluster')"
                                },
                                "namespace": {
                                    "type": "string",
                                    "description": "Namespace to search in",
                                    "default": "default"
                                },
                                "time_range": {
                                    "type": "string",
                                    "description": "Time range for logs (e.g., '1h', '30m', '24h')",
                                    "default": "1h"
                                },
                                "log_level": {
                                    "type": "string",
                                    "enum": ["error", "warn", "info", "debug", "all"],
                                    "description": "Minimum log level to include",
                                    "default": "warn"
                                },
                                "search_pattern": {
                                    "type": "string",
                                    "description": "Pattern to search for in logs (optional)"
                                }
                            },
                            "required": ["target"]
                        }
                    ),
                    Tool(
                        name="security_scan",
                        description="Perform security scanning and compliance checks on cluster resources",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "scan_types": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Types of scans: rbac, pods, network-policies, secrets, images",
                                    "default": ["rbac", "pods", "secrets"]
                                },
                                "namespace": {
                                    "type": "string",
                                    "description": "Namespace to focus scan on (optional)"
                                },
                                "severity_threshold": {
                                    "type": "string",
                                    "enum": ["low", "medium", "high", "critical"],
                                    "description": "Minimum severity level to report",
                                    "default": "medium"
                                }
                            }
                        }
                    ),
                    Tool(
                        name="performance_analysis",
                        description="Perform detailed performance analysis and identify bottlenecks",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "analysis_type": {
                                    "type": "string",
                                    "enum": ["cluster", "node", "workload", "storage", "network"],
                                    "description": "Type of performance analysis to perform"
                                },
                                "target": {
                                    "type": "string",
                                    "description": "Specific target for analysis (when not cluster-wide)"
                                },
                                "duration": {
                                    "type": "string",
                                    "description": "Duration for performance monitoring (e.g., '5m', '30m')",
                                    "default": "5m"
                                }
                            },
                            "required": ["analysis_type"]
                        }
                    ),
                    Tool(
                        name="get_recommendations",
                        description="Get actionable recommendations for cluster optimization and best practices",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "focus_areas": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Areas to focus recommendations on: performance, security, cost, reliability",
                                    "default": ["performance", "security", "reliability"]
                                },
                                "cluster_context": {
                                    "type": "object",
                                    "description": "Additional context about cluster usage and requirements"
                                }
                            }
                        }
                    ),
                    Tool(
                        name="execute_remediation",
                        description="Execute automated remediation actions for common issues",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "issue_type": {
                                    "type": "string",
                                    "description": "Type of issue to remediate"
                                },
                                "target": {
                                    "type": "string",
                                    "description": "Target resource for remediation"
                                },
                                "dry_run": {
                                    "type": "boolean",
                                    "description": "Perform dry run without making changes",
                                    "default": True
                                }
                            },
                            "required": ["issue_type", "target"]
                        }
                    ),
                    # Documentation and Knowledge Base Tools
                    Tool(
                        name="search_documentation",
                        description="Search Kubernetes official documentation for best practices and solutions",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "Search query for documentation"
                                },
                                "max_results": {
                                    "type": "integer",
                                    "description": "Maximum number of results to return",
                                    "default": 10
                                }
                            },
                            "required": ["query"]
                        }
                    ),
                    Tool(
                        name="get_best_practices",
                        description="Get Kubernetes best practices for specific areas",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "category": {
                                    "type": "string",
                                    "enum": ["resource_management", "security", "reliability", "networking", "storage", "monitoring"],
                                    "description": "Category of best practices to retrieve"
                                }
                            }
                        }
                    ),
                    Tool(
                        name="find_kubectl_commands",
                        description="Find relevant kubectl commands from documentation",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "search_term": {
                                    "type": "string",
                                    "description": "Term to search for in commands"
                                },
                                "command_type": {
                                    "type": "string",
                                    "enum": ["kubectl", "helm", "kubeadm", "docker"],
                                    "description": "Type of command to search for"
                                }
                            }
                        }
                    ),
                    Tool(
                        name="get_troubleshooting_guide",
                        description="Get troubleshooting guides from official documentation",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "issue_type": {
                                    "type": "string",
                                    "description": "Type of issue to get troubleshooting guide for"
                                }
                            },
                            "required": ["issue_type"]
                        }
                    ),
                    # GitHub Issues Tools
                    Tool(
                        name="search_github_issues",
                        description="Search known GitHub issues for similar problems and solutions",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "Search query for GitHub issues"
                                },
                                "repo": {
                                    "type": "string",
                                    "description": "Specific repository to search (e.g., 'kubernetes/kubernetes')"
                                },
                                "state": {
                                    "type": "string",
                                    "enum": ["open", "closed", "all"],
                                    "description": "Issue state to filter by",
                                    "default": "all"
                                },
                                "component": {
                                    "type": "string",
                                    "description": "Kubernetes component to filter by"
                                },
                                "severity": {
                                    "type": "string",
                                    "enum": ["low", "medium", "high", "critical"],
                                    "description": "Severity level to filter by"
                                },
                                "max_results": {
                                    "type": "integer",
                                    "description": "Maximum number of results",
                                    "default": 20
                                }
                            },
                            "required": ["query"]
                        }
                    ),
                    Tool(
                        name="find_similar_issues",
                        description="Find similar GitHub issues based on error messages or symptoms",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "error_message": {
                                    "type": "string",
                                    "description": "Error message or symptom description"
                                },
                                "max_results": {
                                    "type": "integer",
                                    "description": "Maximum number of similar issues to return",
                                    "default": 10
                                }
                            },
                            "required": ["error_message"]
                        }
                    ),
                    Tool(
                        name="get_trending_issues",
                        description="Get trending GitHub issues to stay informed about current problems",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "days": {
                                    "type": "integer",
                                    "description": "Number of days to look back for trending issues",
                                    "default": 7
                                },
                                "max_results": {
                                    "type": "integer",
                                    "description": "Maximum number of trending issues",
                                    "default": 15
                                }
                            }
                        }
                    ),
                    Tool(
                        name="get_issue_statistics",
                        description="Get statistics about GitHub issues database for insights",
                        inputSchema={
                            "type": "object",
                            "properties": {}
                        }
                    )
                ]
            )
        
        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: Optional[Dict[str, Any]]) -> CallToolResult:
            """Handle tool calls for Kubernetes platform engineering operations."""
            try:
                self.logger.info(f"Tool called: {name} with arguments: {arguments}")
                
                if name == "get_cluster_info":
                    result = await self.k8s_manager.get_cluster_info(
                        include_details=arguments.get("include_details", True)
                    )
                
                elif name == "diagnose_cluster_health":
                    result = await self.diagnostics_manager.diagnose_cluster_health(
                        check_types=arguments.get("check_types", ["nodes", "pods", "services", "networking"]),
                        namespace=arguments.get("namespace")
                    )
                
                elif name == "troubleshoot_pod_issues":
                    result = await self.diagnostics_manager.troubleshoot_pod_issues(
                        pod_name=arguments["pod_name"],
                        namespace=arguments.get("namespace", "default"),
                        include_logs=arguments.get("include_logs", True),
                        include_events=arguments.get("include_events", True)
                    )
                
                elif name == "analyze_resource_usage":
                    result = await self.monitoring_manager.analyze_resource_usage(
                        scope=arguments["scope"],
                        target=arguments.get("target"),
                        metrics=arguments.get("metrics", ["cpu", "memory"])
                    )
                
                elif name == "check_network_connectivity":
                    result = await self.diagnostics_manager.check_network_connectivity(
                        source_pod=arguments["source_pod"],
                        target=arguments["target"],
                        namespace=arguments.get("namespace", "default"),
                        test_types=arguments.get("test_types", ["ping", "dns"])
                    )
                
                elif name == "analyze_logs":
                    result = await self.monitoring_manager.analyze_logs(
                        target=arguments["target"],
                        namespace=arguments.get("namespace", "default"),
                        time_range=arguments.get("time_range", "1h"),
                        log_level=arguments.get("log_level", "warn"),
                        search_pattern=arguments.get("search_pattern")
                    )
                
                elif name == "security_scan":
                    result = await self.security_manager.security_scan(
                        scan_types=arguments.get("scan_types", ["rbac", "pods", "secrets"]),
                        namespace=arguments.get("namespace"),
                        severity_threshold=arguments.get("severity_threshold", "medium")
                    )
                
                elif name == "performance_analysis":
                    result = await self.monitoring_manager.performance_analysis(
                        analysis_type=arguments["analysis_type"],
                        target=arguments.get("target"),
                        duration=arguments.get("duration", "5m")
                    )
                
                elif name == "get_recommendations":
                    result = await self.k8s_manager.get_recommendations(
                        focus_areas=arguments.get("focus_areas", ["performance", "security", "reliability"]),
                        cluster_context=arguments.get("cluster_context", {})
                    )
                
                elif name == "execute_remediation":
                    result = await self.k8s_manager.execute_remediation(
                        issue_type=arguments["issue_type"],
                        target=arguments["target"],
                        dry_run=arguments.get("dry_run", True)
                    )
                
                # Documentation Tools
                elif name == "search_documentation":
                    result = await self.documentation_manager.search_documentation(
                        query=arguments["query"],
                        max_results=arguments.get("max_results", 10)
                    )
                
                elif name == "get_best_practices":
                    result = await self.documentation_manager.get_best_practices(
                        category=arguments.get("category")
                    )
                
                elif name == "find_kubectl_commands":
                    result = await self.documentation_manager.find_commands(
                        command_type=arguments.get("command_type"),
                        search_term=arguments.get("search_term")
                    )
                
                elif name == "get_troubleshooting_guide":
                    result = await self.documentation_manager.get_troubleshooting_guide(
                        issue_type=arguments["issue_type"]
                    )
                
                # GitHub Issues Tools
                elif name == "search_github_issues":
                    result = await self.github_issues_manager.search_issues(
                        query=arguments["query"],
                        repo=arguments.get("repo"),
                        state=arguments.get("state", "all"),
                        component=arguments.get("component"),
                        severity=arguments.get("severity"),
                        max_results=arguments.get("max_results", 20)
                    )
                
                elif name == "find_similar_issues":
                    result = await self.github_issues_manager.find_similar_issues(
                        error_message=arguments["error_message"],
                        max_results=arguments.get("max_results", 10)
                    )
                
                elif name == "get_trending_issues":
                    result = await self.github_issues_manager.get_trending_issues(
                        days=arguments.get("days", 7),
                        max_results=arguments.get("max_results", 15)
                    )
                
                elif name == "get_issue_statistics":
                    result = await self.github_issues_manager.get_issue_statistics()
                
                else:
                    return CallToolResult(
                        content=[TextContent(type="text", text=f"Unknown tool: {name}")]
                    )
                
                return CallToolResult(
                    content=[TextContent(type="text", text=json.dumps(result, indent=2))]
                )
                
            except Exception as e:
                self.logger.error(f"Error in tool {name}: {e}", exc_info=True)
                return CallToolResult(
                    content=[TextContent(type="text", text=f"Error: {str(e)}")]
                )
    
    async def start(self):
        """Start the MCP server over stdio so editors like Cursor can connect."""
        try:
            self.logger.info(
                f"Starting Kubernetes Platform Engineer MCP Server (stdio) on {self.config.host}:{self.config.port}"
            )
            
            # Initialize managers
            await self.k8s_manager.initialize()
            await self.diagnostics_manager.initialize()
            await self.monitoring_manager.initialize()
            await self.security_manager.initialize()
            await self.documentation_manager.initialize()
            await self.github_issues_manager.initialize()
            
            # Serve MCP over stdio
            self.logger.info("MCP server initialized; waiting for stdio client...")
            async with stdio_server() as (read_stream, write_stream):
                await self.server.run(
                    read_stream, 
                    write_stream, 
                    InitializationOptions(
                        server_name="kubernetes-platform-engineer",
                        server_version=self.config.version,
                        capabilities=self.server.get_capabilities()
                    )
                )
            
        except Exception as e:
            self.logger.error(f"Failed to start server: {e}", exc_info=True)
            raise
