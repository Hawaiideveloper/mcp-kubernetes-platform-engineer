"""
Kubernetes Platform Engineer MCP Server

A comprehensive Model Context Protocol server for Kubernetes platform engineering,
cluster troubleshooting, monitoring, and advanced system administration.

Features:
- Kubernetes cluster diagnostics and troubleshooting
- Container runtime management and debugging
- Network diagnostics and CNI troubleshooting
- Resource monitoring and performance analysis
- Log aggregation and analysis
- Security scanning and compliance checking
- Automated incident response and remediation
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent))

from src.mcp_server import KubernetesPlatformEngineerMCPServer
from src.config import ServerConfig
from src.logger import setup_logging


async def main():
    """Main entry point for the Kubernetes Platform Engineer MCP Server."""
    
    # Setup logging
    setup_logging()
    logger = logging.getLogger(__name__)
    
    try:
        # Load configuration
        config = ServerConfig()
        logger.info(f"Starting Kubernetes Platform Engineer MCP Server v{config.version}")
        
        # Initialize and start the MCP server
        server = KubernetesPlatformEngineerMCPServer(config)
        await server.start()
        
    except KeyboardInterrupt:
        logger.info("Server shutdown requested by user")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
