#!/usr/bin/env python3
"""
Enhanced startup script for Kubernetes Platform Engineer MCP Server
Simplified startup to test the enhanced capabilities
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.config import ServerConfig
from src.mcp_server import KubernetesPlatformEngineerMCPServer
from src.logger import setup_logging

async def main():
    """Main entry point"""
    setup_logging()
    logger = logging.getLogger(__name__)
    
    try:
        # Create a minimal config
        config = ServerConfig()
        config.host = "0.0.0.0"
        config.port = 3001
        
        logger.info("Starting Enhanced Kubernetes Platform Engineer MCP Server")
        logger.info(f"Host: {config.host}, Port: {config.port}")
        
        # Check for non-destructive mode
        non_destructive = os.getenv('ALLOW_ONLY_NON_DESTRUCTIVE_TOOLS', 'false').lower() == 'true'
        if non_destructive:
            logger.info("Running in NON-DESTRUCTIVE MODE")
        
        # Create and start server
        server = KubernetesPlatformEngineerMCPServer(config)
        await server.start()
        
    except KeyboardInterrupt:
        logger.info("Server shutdown requested by user")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
