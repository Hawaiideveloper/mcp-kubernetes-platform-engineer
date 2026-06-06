"""
Health check module for Kubernetes Platform Engineer MCP Server.
"""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def check() -> bool:
    """
    Simple health check for the MCP server.
    
    Returns:
        bool: True if server is healthy, False otherwise
    """
    try:
        # Basic health checks
        checks = [
            check_python_version(),
            check_imports(),
            check_file_permissions()
        ]
        
        return all(checks)
    except Exception:
        return False


def check_python_version() -> bool:
    """Check if Python version is compatible."""
    return sys.version_info >= (3, 8)


def check_imports() -> bool:
    """Check if critical imports are available."""
    try:
        import asyncio
        import json
        import logging
        return True
    except ImportError:
        return False


def check_file_permissions() -> bool:
    """Check if necessary file permissions are available."""
    try:
        app_dir = Path(__file__).parent.parent
        return app_dir.exists() and app_dir.is_dir()
    except Exception:
        return False


if __name__ == "__main__":
    if check():
        print("Health check passed")
        sys.exit(0)
    else:
        print("Health check failed")
        sys.exit(1)
