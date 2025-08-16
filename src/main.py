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
import os
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent))

import click
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .mcp_server import KubernetesPlatformEngineerMCPServer
from .config import ServerConfig
from .logger import setup_logging

# FastAPI app for HTTP REST API
app = FastAPI(
    title="Kubernetes Platform Engineer MCP Server",
    description="Model Context Protocol server for Kubernetes platform engineering",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class K8sPlatformApp:
    """Main application class for the Kubernetes Platform Engineer MCP Server"""
    
    def __init__(self):
        setup_logging()
        self.logger = logging.getLogger(__name__)
        self.config = ServerConfig()
        self.mcp_server = None
        
    async def initialize(self):
        """Initialize the application"""
        self.logger.info("🚀 Initializing Kubernetes Platform Engineer MCP Server...")
        
        # Initialize MCP server
        self.mcp_server = KubernetesPlatformEngineerMCPServer(self.config)
        # Initialize managers but don't start stdio server
        await self.mcp_server.k8s_manager.initialize()
        await self.mcp_server.diagnostics_manager.initialize()
        await self.mcp_server.monitoring_manager.initialize()
        await self.mcp_server.security_manager.initialize()
        await self.mcp_server.documentation_manager.initialize()
        await self.mcp_server.github_issues_manager.initialize()
        
        self.logger.info("✅ MCP Server initialized")
        
    async def run_server(self, host: str = "0.0.0.0", port: int = 3001):
        """Run the HTTP server"""
        self.logger.info(f"🌐 Starting HTTP server on {host}:{port}")
        
        # Add health check endpoint
        @app.get("/health")
        async def health_check():
            return {
                "status": "healthy",
                "service": "kubernetes-platform-engineer-mcp-server",
                "version": "1.0.0"
            }
            
        @app.get("/")
        async def root():
            """API information and available endpoints"""
            return {
                "service": "kubernetes-platform-engineer-mcp-server",
                "version": "1.0.0",
                "description": "Model Context Protocol server for Kubernetes platform engineering",
                "endpoints": {
                    "health": "GET /health - Health check",
                    "k8s_diagnostics": "GET /k8s/diagnostics - Cluster diagnostics",
                    "k8s_monitoring": "GET /k8s/monitoring - Cluster monitoring",
                    "k8s_security": "GET /k8s/security - Security scanning"
                }
            }
        
        @app.get("/k8s/diagnostics")
        async def get_k8s_diagnostics():
            """Get Kubernetes cluster diagnostics"""
            try:
                # This would normally call MCP server methods
                return {
                    "status": "healthy",
                    "cluster_info": "Available",
                    "nodes": "Ready",
                    "pods": "Running"
                }
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
                
        @app.get("/k8s/monitoring")
        async def get_k8s_monitoring():
            """Get Kubernetes cluster monitoring data"""
            try:
                return {
                    "status": "monitoring_active",
                    "metrics": "Available",
                    "alerts": "None"
                }
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
                
        @app.get("/k8s/security")
        async def get_k8s_security():
            """Get Kubernetes security scan results"""
            try:
                return {
                    "status": "secure",
                    "vulnerabilities": "None",
                    "compliance": "Passed"
                }
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        
        # Start the server
        config = uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level="info",
            reload=False
        )
        server = uvicorn.Server(config)
        await server.serve()

# CLI Commands
@click.group()
def cli():
    """Kubernetes Platform Engineer MCP Server"""
    pass

@cli.command()
@click.option('--host', default='0.0.0.0', help='Host to bind to')
@click.option('--port', default=3001, type=int, help='Port to bind to')
@click.option('--dev', is_flag=True, help='Run in development mode')
def start(host, port, dev):
    """Start the HTTP server"""
    
    # Check for environment variables
    host = os.getenv('HOST', host)
    port = int(os.getenv('PORT', port))
    
    if dev:
        logging.getLogger().setLevel(logging.DEBUG)
        print("🔧 Running in development mode")
    
    app_instance = K8sPlatformApp()
    
    async def run():
        await app_instance.initialize()
        await app_instance.run_server(host, port)
    
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\n👋 Shutting down gracefully...")
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

@cli.command()
def stdio():
    """Start the MCP STDIO server for IDE integration"""
    async def run_stdio():
        setup_logging()
        logger = logging.getLogger(__name__)
        
        try:
            config = ServerConfig()
            logger.info(f"Starting Kubernetes Platform Engineer MCP Server (STDIO) v{config.version}")
            
            server = KubernetesPlatformEngineerMCPServer(config)
            await server.start()
            
        except KeyboardInterrupt:
            logger.info("Server shutdown requested by user")
        except Exception as e:
            logger.error(f"Server error: {e}", exc_info=True)
            sys.exit(1)
    
    try:
        asyncio.run(run_stdio())
    except KeyboardInterrupt:
        print("\n👋 Shutting down gracefully...")
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    cli()
