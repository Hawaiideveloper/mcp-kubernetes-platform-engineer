"""
Enhanced Tools Integration for Kubernetes Platform Engineer MCP Server
Provides comprehensive kubectl and Helm tools matching and exceeding Flux159 capabilities
"""

from typing import List
from mcp.types import Tool


def get_enhanced_kubectl_tools() -> List[Tool]:
    """Get all enhanced kubectl tools"""
    return [
        # Core kubectl operations
        Tool(
            name="kubectl_get",
            description="Get or list Kubernetes resources with comprehensive options",
            inputSchema={
                "type": "object",
                "properties": {
                    "resource": {
                        "type": "string",
                        "description": "Resource type (pods, services, deployments, etc.)",
                        "required": True
                    },
                    "name": {
                        "type": "string",
                        "description": "Specific resource name (optional)"
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Namespace to search in"
                    },
                    "output_format": {
                        "type": "string",
                        "enum": ["yaml", "json", "table", "wide"],
                        "default": "yaml",
                        "description": "Output format"
                    }
                },
                "required": ["resource"]
            }
        ),
        Tool(
            name="kubectl_describe",
            description="Describe a specific Kubernetes resource with detailed information",
            inputSchema={
                "type": "object",
                "properties": {
                    "resource": {
                        "type": "string",
                        "description": "Resource type",
                        "required": True
                    },
                    "name": {
                        "type": "string",
                        "description": "Resource name",
                        "required": True
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Namespace"
                    }
                },
                "required": ["resource", "name"]
            }
        ),
        Tool(
            name="kubectl_create",
            description="Create Kubernetes resources from YAML manifest",
            inputSchema={
                "type": "object",
                "properties": {
                    "resource_yaml": {
                        "type": "string",
                        "description": "YAML manifest content",
                        "required": True
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Target namespace"
                    }
                },
                "required": ["resource_yaml"]
            }
        ),
        Tool(
            name="kubectl_apply",
            description="Apply Kubernetes resources from YAML manifest",
            inputSchema={
                "type": "object",
                "properties": {
                    "resource_yaml": {
                        "type": "string",
                        "description": "YAML manifest content",
                        "required": True
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Target namespace"
                    }
                },
                "required": ["resource_yaml"]
            }
        ),
        Tool(
            name="kubectl_delete",
            description="Delete a Kubernetes resource (disabled in non-destructive mode)",
            inputSchema={
                "type": "object",
                "properties": {
                    "resource": {
                        "type": "string",
                        "description": "Resource type",
                        "required": True
                    },
                    "name": {
                        "type": "string",
                        "description": "Resource name",
                        "required": True
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Namespace"
                    }
                },
                "required": ["resource", "name"]
            }
        ),
        Tool(
            name="kubectl_logs",
            description="Get logs from a pod with advanced filtering options",
            inputSchema={
                "type": "object",
                "properties": {
                    "pod_name": {
                        "type": "string",
                        "description": "Pod name",
                        "required": True
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Namespace"
                    },
                    "container": {
                        "type": "string",
                        "description": "Specific container name"
                    },
                    "follow": {
                        "type": "boolean",
                        "default": False,
                        "description": "Follow log output"
                    },
                    "tail": {
                        "type": "integer",
                        "description": "Number of lines to show from the end"
                    }
                },
                "required": ["pod_name"]
            }
        ),
        Tool(
            name="kubectl_scale",
            description="Scale a deployment, replicaset, or statefulset",
            inputSchema={
                "type": "object",
                "properties": {
                    "resource": {
                        "type": "string",
                        "enum": ["deployment", "replicaset", "statefulset"],
                        "description": "Resource type to scale",
                        "required": True
                    },
                    "name": {
                        "type": "string",
                        "description": "Resource name",
                        "required": True
                    },
                    "replicas": {
                        "type": "integer",
                        "minimum": 0,
                        "description": "Number of replicas",
                        "required": True
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Namespace"
                    }
                },
                "required": ["resource", "name", "replicas"]
            }
        ),
        Tool(
            name="kubectl_patch",
            description="Update field(s) of a resource using strategic merge patch",
            inputSchema={
                "type": "object",
                "properties": {
                    "resource": {
                        "type": "string",
                        "description": "Resource type",
                        "required": True
                    },
                    "name": {
                        "type": "string",
                        "description": "Resource name",
                        "required": True
                    },
                    "patch": {
                        "type": "string",
                        "description": "JSON patch content",
                        "required": True
                    },
                    "patch_type": {
                        "type": "string",
                        "enum": ["strategic", "merge", "json"],
                        "default": "strategic",
                        "description": "Patch type"
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Namespace"
                    }
                },
                "required": ["resource", "name", "patch"]
            }
        ),
        Tool(
            name="kubectl_rollout",
            description="Manage rollouts (status, history, undo, restart)",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["status", "history", "undo", "restart"],
                        "description": "Rollout action",
                        "required": True
                    },
                    "resource": {
                        "type": "string",
                        "enum": ["deployment", "daemonset", "statefulset"],
                        "description": "Resource type",
                        "required": True
                    },
                    "name": {
                        "type": "string",
                        "description": "Resource name",
                        "required": True
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Namespace"
                    }
                },
                "required": ["action", "resource", "name"]
            }
        ),
        Tool(
            name="kubectl_context",
            description="Manage kubectl contexts (current, list, switch)",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["current", "list", "use"],
                        "default": "current",
                        "description": "Context action"
                    },
                    "context_name": {
                        "type": "string",
                        "description": "Context name (required for 'use' action)"
                    }
                }
            }
        ),
        Tool(
            name="explain_resource",
            description="Explain Kubernetes resource documentation",
            inputSchema={
                "type": "object",
                "properties": {
                    "resource": {
                        "type": "string",
                        "description": "Resource type to explain",
                        "required": True
                    },
                    "field": {
                        "type": "string",
                        "description": "Specific field to explain"
                    }
                },
                "required": ["resource"]
            }
        ),
        Tool(
            name="list_api_resources",
            description="List available Kubernetes API resources",
            inputSchema={
                "type": "object",
                "properties": {
                    "api_group": {
                        "type": "string",
                        "description": "Filter by API group"
                    }
                }
            }
        ),
        Tool(
            name="kubectl_generic",
            description="Execute any kubectl command (disabled in non-destructive mode)",
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "kubectl command to execute (without 'kubectl')",
                        "required": True
                    }
                },
                "required": ["command"]
            }
        ),
        # Port forwarding
        Tool(
            name="port_forward",
            description="Start port forwarding to a pod or service",
            inputSchema={
                "type": "object",
                "properties": {
                    "resource": {
                        "type": "string",
                        "description": "Resource (pod/podname or service/servicename)",
                        "required": True
                    },
                    "ports": {
                        "type": "string",
                        "description": "Port mapping (e.g., '8080:80' or '8080')",
                        "required": True
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Namespace"
                    }
                },
                "required": ["resource", "ports"]
            }
        ),
        Tool(
            name="stop_port_forward",
            description="Stop a specific port forward",
            inputSchema={
                "type": "object",
                "properties": {
                    "forward_id": {
                        "type": "string",
                        "description": "Port forward ID to stop",
                        "required": True
                    }
                },
                "required": ["forward_id"]
            }
        ),
        Tool(
            name="list_port_forwards",
            description="List active port forwards",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        # Enhanced troubleshooting
        Tool(
            name="k8s_diagnose",
            description="Systematic Kubernetes pod troubleshooting similar to Flux159",
            inputSchema={
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "Keyword to identify relevant pods",
                        "required": True
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Namespace to search in"
                    }
                },
                "required": ["keyword"]
            }
        ),
        Tool(
            name="ping",
            description="Verify connection to Kubernetes cluster",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        )
    ]


def get_enhanced_helm_tools() -> List[Tool]:
    """Get all enhanced Helm tools"""
    return [
        # Core Helm operations
        Tool(
            name="install_helm_chart",
            description="Install a Helm chart with comprehensive options",
            inputSchema={
                "type": "object",
                "properties": {
                    "release_name": {
                        "type": "string",
                        "description": "Release name",
                        "required": True
                    },
                    "chart": {
                        "type": "string",
                        "description": "Chart name or path",
                        "required": True
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Target namespace"
                    },
                    "values": {
                        "type": "object",
                        "description": "Chart values as object"
                    },
                    "values_file": {
                        "type": "string",
                        "description": "Path to values file"
                    },
                    "chart_version": {
                        "type": "string",
                        "description": "Chart version"
                    },
                    "repository": {
                        "type": "string",
                        "description": "Helm repository URL"
                    },
                    "create_namespace": {
                        "type": "boolean",
                        "default": False,
                        "description": "Create namespace if it doesn't exist"
                    },
                    "dry_run": {
                        "type": "boolean",
                        "default": False,
                        "description": "Perform a dry run"
                    }
                },
                "required": ["release_name", "chart"]
            }
        ),
        Tool(
            name="upgrade_helm_chart",
            description="Upgrade a Helm release",
            inputSchema={
                "type": "object",
                "properties": {
                    "release_name": {
                        "type": "string",
                        "description": "Release name",
                        "required": True
                    },
                    "chart": {
                        "type": "string",
                        "description": "Chart name or path",
                        "required": True
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Target namespace"
                    },
                    "values": {
                        "type": "object",
                        "description": "Chart values as object"
                    },
                    "values_file": {
                        "type": "string",
                        "description": "Path to values file"
                    },
                    "chart_version": {
                        "type": "string",
                        "description": "Chart version"
                    },
                    "install": {
                        "type": "boolean",
                        "default": True,
                        "description": "Install if release doesn't exist"
                    },
                    "dry_run": {
                        "type": "boolean",
                        "default": False,
                        "description": "Perform a dry run"
                    }
                },
                "required": ["release_name", "chart"]
            }
        ),
        Tool(
            name="uninstall_helm_chart",
            description="Uninstall a Helm release (disabled in non-destructive mode)",
            inputSchema={
                "type": "object",
                "properties": {
                    "release_name": {
                        "type": "string",
                        "description": "Release name",
                        "required": True
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Target namespace"
                    },
                    "keep_history": {
                        "type": "boolean",
                        "default": False,
                        "description": "Keep release history"
                    }
                },
                "required": ["release_name"]
            }
        ),
        Tool(
            name="list_helm_releases",
            description="List Helm releases",
            inputSchema={
                "type": "object",
                "properties": {
                    "namespace": {
                        "type": "string",
                        "description": "Specific namespace"
                    },
                    "all_namespaces": {
                        "type": "boolean",
                        "default": False,
                        "description": "List releases from all namespaces"
                    },
                    "output_format": {
                        "type": "string",
                        "enum": ["table", "json", "yaml"],
                        "default": "table",
                        "description": "Output format"
                    }
                }
            }
        ),
        Tool(
            name="get_helm_release",
            description="Get Helm release manifest",
            inputSchema={
                "type": "object",
                "properties": {
                    "release_name": {
                        "type": "string",
                        "description": "Release name",
                        "required": True
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Target namespace"
                    },
                    "revision": {
                        "type": "integer",
                        "description": "Specific revision"
                    }
                },
                "required": ["release_name"]
            }
        ),
        Tool(
            name="get_helm_values",
            description="Get Helm release values",
            inputSchema={
                "type": "object",
                "properties": {
                    "release_name": {
                        "type": "string",
                        "description": "Release name",
                        "required": True
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Target namespace"
                    },
                    "revision": {
                        "type": "integer",
                        "description": "Specific revision"
                    },
                    "output_format": {
                        "type": "string",
                        "enum": ["yaml", "json"],
                        "default": "yaml",
                        "description": "Output format"
                    }
                },
                "required": ["release_name"]
            }
        ),
        Tool(
            name="helm_status",
            description="Get Helm release status",
            inputSchema={
                "type": "object",
                "properties": {
                    "release_name": {
                        "type": "string",
                        "description": "Release name",
                        "required": True
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Target namespace"
                    },
                    "output_format": {
                        "type": "string",
                        "enum": ["table", "json", "yaml"],
                        "default": "table",
                        "description": "Output format"
                    }
                },
                "required": ["release_name"]
            }
        ),
        Tool(
            name="helm_history",
            description="Get Helm release history",
            inputSchema={
                "type": "object",
                "properties": {
                    "release_name": {
                        "type": "string",
                        "description": "Release name",
                        "required": True
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Target namespace"
                    },
                    "max_revisions": {
                        "type": "integer",
                        "description": "Maximum number of revisions to show"
                    }
                },
                "required": ["release_name"]
            }
        ),
        Tool(
            name="helm_rollback",
            description="Rollback Helm release (disabled in non-destructive mode)",
            inputSchema={
                "type": "object",
                "properties": {
                    "release_name": {
                        "type": "string",
                        "description": "Release name",
                        "required": True
                    },
                    "revision": {
                        "type": "integer",
                        "description": "Revision to rollback to",
                        "required": True
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Target namespace"
                    },
                    "dry_run": {
                        "type": "boolean",
                        "default": False,
                        "description": "Perform a dry run"
                    }
                },
                "required": ["release_name", "revision"]
            }
        ),
        # Repository management
        Tool(
            name="add_helm_repository",
            description="Add a Helm repository",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Repository name",
                        "required": True
                    },
                    "url": {
                        "type": "string",
                        "description": "Repository URL",
                        "required": True
                    },
                    "username": {
                        "type": "string",
                        "description": "Username for authentication"
                    },
                    "password": {
                        "type": "string",
                        "description": "Password for authentication"
                    }
                },
                "required": ["name", "url"]
            }
        ),
        Tool(
            name="update_helm_repositories",
            description="Update all Helm repositories",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="list_helm_repositories",
            description="List Helm repositories",
            inputSchema={
                "type": "object",
                "properties": {
                    "output_format": {
                        "type": "string",
                        "enum": ["table", "json", "yaml"],
                        "default": "table",
                        "description": "Output format"
                    }
                }
            }
        ),
        Tool(
            name="search_helm_charts",
            description="Search for Helm charts",
            inputSchema={
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "Search keyword",
                        "required": True
                    },
                    "version": {
                        "type": "string",
                        "description": "Chart version"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results"
                    }
                },
                "required": ["keyword"]
            }
        ),
        Tool(
            name="show_helm_chart",
            description="Show Helm chart information",
            inputSchema={
                "type": "object",
                "properties": {
                    "chart": {
                        "type": "string",
                        "description": "Chart name",
                        "required": True
                    },
                    "chart_version": {
                        "type": "string",
                        "description": "Chart version"
                    },
                    "info_type": {
                        "type": "string",
                        "enum": ["all", "chart", "readme", "values"],
                        "default": "all",
                        "description": "Type of information to show"
                    }
                },
                "required": ["chart"]
            }
        ),
        Tool(
            name="template_helm_chart",
            description="Template a Helm chart (render without installing)",
            inputSchema={
                "type": "object",
                "properties": {
                    "release_name": {
                        "type": "string",
                        "description": "Release name",
                        "required": True
                    },
                    "chart": {
                        "type": "string",
                        "description": "Chart name",
                        "required": True
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Target namespace"
                    },
                    "values": {
                        "type": "object",
                        "description": "Chart values as object"
                    },
                    "values_file": {
                        "type": "string",
                        "description": "Path to values file"
                    },
                    "chart_version": {
                        "type": "string",
                        "description": "Chart version"
                    }
                },
                "required": ["release_name", "chart"]
            }
        ),
        # Enhanced Helm operations
        Tool(
            name="lint_helm_chart",
            description="Lint a Helm chart for issues",
            inputSchema={
                "type": "object",
                "properties": {
                    "chart_path": {
                        "type": "string",
                        "description": "Path to chart directory",
                        "required": True
                    }
                },
                "required": ["chart_path"]
            }
        ),
        Tool(
            name="test_helm_release",
            description="Run tests for a Helm release",
            inputSchema={
                "type": "object",
                "properties": {
                    "release_name": {
                        "type": "string",
                        "description": "Release name",
                        "required": True
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Target namespace"
                    }
                },
                "required": ["release_name"]
            }
        ),
        Tool(
            name="get_helm_version",
            description="Get Helm version information",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        )
    ]
