"""
Helm Manager for comprehensive Helm operations
Provides all Helm functionality from Flux159 plus enhancements
"""

import subprocess
import json
import yaml
from typing import Dict, List, Optional, Any
from pathlib import Path

try:
    from logger import get_logger
except ImportError:
    from logger import get_logger

logger = get_logger(__name__)


class HelmManager:
    """
    Comprehensive Helm management with all operations
    """
    
    def __init__(self, non_destructive_mode: bool = False):
        """Initialize Helm manager with optional non-destructive mode"""
        self.non_destructive_mode = non_destructive_mode
        
        # Check if helm is available
        if not self._check_helm():
            logger.warning("Helm not found in PATH - Helm operations will not be available")
            self.helm_available = False
        else:
            self.helm_available = True
    
    def _check_helm(self) -> bool:
        """Check if helm is available"""
        try:
            result = subprocess.run(['helm', 'version', '--short'], 
                                  capture_output=True, text=True, timeout=10)
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def _run_helm(self, args: List[str], input_data: Optional[str] = None) -> Dict[str, Any]:
        """Run helm command and return structured result"""
        if not self.helm_available:
            return {
                'success': False,
                'stdout': '',
                'stderr': 'Helm is not available on this system',
                'returncode': 127,
                'command': f'helm {" ".join(args)}'
            }
        
        try:
            cmd = ['helm'] + args
            logger.info(f"Running helm command: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                input=input_data,
                capture_output=True,
                text=True,
                timeout=300  # Helm operations can take longer
            )
            
            return {
                'success': result.returncode == 0,
                'stdout': result.stdout.strip(),
                'stderr': result.stderr.strip(),
                'returncode': result.returncode,
                'command': ' '.join(cmd)
            }
        except subprocess.TimeoutExpired:
            return {
                'success': False,
                'stdout': '',
                'stderr': 'Helm command timed out after 5 minutes',
                'returncode': 124,
                'command': ' '.join(cmd)
            }
        except Exception as e:
            return {
                'success': False,
                'stdout': '',
                'stderr': str(e),
                'returncode': 1,
                'command': ' '.join(cmd)
            }
    
    def _check_destructive_operation(self, operation: str) -> bool:
        """Check if operation is destructive and should be blocked in non-destructive mode"""
        if not self.non_destructive_mode:
            return False
            
        destructive_ops = ['uninstall', 'delete', 'rollback']
        return any(op in operation.lower() for op in destructive_ops)
    
    # Core Helm operations
    
    async def install_helm_chart(self, release_name: str, chart: str,
                                namespace: Optional[str] = None,
                                values: Optional[Dict[str, Any]] = None,
                                values_file: Optional[str] = None,
                                chart_version: Optional[str] = None,
                                repository: Optional[str] = None,
                                create_namespace: bool = False,
                                dry_run: bool = False) -> Dict[str, Any]:
        """Install a Helm chart"""
        args = ['install', release_name, chart]
        
        if namespace:
            args.extend(['--namespace', namespace])
        if create_namespace:
            args.append('--create-namespace')
        if chart_version:
            args.extend(['--version', chart_version])
        if dry_run:
            args.append('--dry-run')
        
        # Handle repository
        if repository:
            # Add repository first
            repo_result = await self.add_helm_repository(repository, repository)
            if not repo_result['success']:
                return repo_result
        
        # Handle values
        values_input = None
        if values_file:
            args.extend(['--values', values_file])
        elif values:
            # Convert values dict to YAML and pass via stdin
            values_yaml = yaml.dump(values)
            args.extend(['--values', '-'])
            values_input = values_yaml
        
        return self._run_helm(args, input_data=values_input)
    
    async def upgrade_helm_chart(self, release_name: str, chart: str,
                                namespace: Optional[str] = None,
                                values: Optional[Dict[str, Any]] = None,
                                values_file: Optional[str] = None,
                                chart_version: Optional[str] = None,
                                install: bool = True,
                                dry_run: bool = False) -> Dict[str, Any]:
        """Upgrade a Helm release"""
        args = ['upgrade', release_name, chart]
        
        if namespace:
            args.extend(['--namespace', namespace])
        if chart_version:
            args.extend(['--version', chart_version])
        if install:
            args.append('--install')
        if dry_run:
            args.append('--dry-run')
        
        # Handle values
        values_input = None
        if values_file:
            args.extend(['--values', values_file])
        elif values:
            values_yaml = yaml.dump(values)
            args.extend(['--values', '-'])
            values_input = values_yaml
        
        return self._run_helm(args, input_data=values_input)
    
    async def uninstall_helm_chart(self, release_name: str,
                                  namespace: Optional[str] = None,
                                  keep_history: bool = False) -> Dict[str, Any]:
        """Uninstall a Helm release"""
        if self._check_destructive_operation('uninstall'):
            return {
                'success': False,
                'stdout': '',
                'stderr': 'Helm uninstall operations disabled in non-destructive mode',
                'returncode': 1,
                'command': f'helm uninstall {release_name}'
            }
        
        args = ['uninstall', release_name]
        
        if namespace:
            args.extend(['--namespace', namespace])
        if keep_history:
            args.append('--keep-history')
        
        return self._run_helm(args)
    
    async def list_helm_releases(self, namespace: Optional[str] = None,
                                all_namespaces: bool = False,
                                output_format: str = 'table') -> Dict[str, Any]:
        """List Helm releases"""
        args = ['list']
        
        if all_namespaces:
            args.append('--all-namespaces')
        elif namespace:
            args.extend(['--namespace', namespace])
        
        if output_format in ['json', 'yaml']:
            args.extend(['--output', output_format])
        
        return self._run_helm(args)
    
    async def get_helm_release(self, release_name: str,
                              namespace: Optional[str] = None,
                              revision: Optional[int] = None,
                              output_format: str = 'yaml') -> Dict[str, Any]:
        """Get Helm release manifest"""
        args = ['get', 'manifest', release_name]
        
        if namespace:
            args.extend(['--namespace', namespace])
        if revision:
            args.extend(['--revision', str(revision)])
        
        return self._run_helm(args)
    
    async def get_helm_values(self, release_name: str,
                             namespace: Optional[str] = None,
                             revision: Optional[int] = None,
                             output_format: str = 'yaml') -> Dict[str, Any]:
        """Get Helm release values"""
        args = ['get', 'values', release_name]
        
        if namespace:
            args.extend(['--namespace', namespace])
        if revision:
            args.extend(['--revision', str(revision)])
        if output_format in ['json', 'yaml']:
            args.extend(['--output', output_format])
        
        return self._run_helm(args)
    
    async def helm_status(self, release_name: str,
                         namespace: Optional[str] = None,
                         output_format: str = 'table') -> Dict[str, Any]:
        """Get Helm release status"""
        args = ['status', release_name]
        
        if namespace:
            args.extend(['--namespace', namespace])
        if output_format in ['json', 'yaml']:
            args.extend(['--output', output_format])
        
        return self._run_helm(args)
    
    async def helm_history(self, release_name: str,
                          namespace: Optional[str] = None,
                          max_revisions: Optional[int] = None,
                          output_format: str = 'table') -> Dict[str, Any]:
        """Get Helm release history"""
        args = ['history', release_name]
        
        if namespace:
            args.extend(['--namespace', namespace])
        if max_revisions:
            args.extend(['--max', str(max_revisions)])
        if output_format in ['json', 'yaml']:
            args.extend(['--output', output_format])
        
        return self._run_helm(args)
    
    async def helm_rollback(self, release_name: str, revision: int,
                           namespace: Optional[str] = None,
                           dry_run: bool = False) -> Dict[str, Any]:
        """Rollback Helm release to a previous revision"""
        if self._check_destructive_operation('rollback'):
            return {
                'success': False,
                'stdout': '',
                'stderr': 'Helm rollback operations disabled in non-destructive mode',
                'returncode': 1,
                'command': f'helm rollback {release_name} {revision}'
            }
        
        args = ['rollback', release_name, str(revision)]
        
        if namespace:
            args.extend(['--namespace', namespace])
        if dry_run:
            args.append('--dry-run')
        
        return self._run_helm(args)
    
    # Repository management
    
    async def add_helm_repository(self, name: str, url: str,
                                 username: Optional[str] = None,
                                 password: Optional[str] = None) -> Dict[str, Any]:
        """Add Helm repository"""
        args = ['repo', 'add', name, url]
        
        if username:
            args.extend(['--username', username])
        if password:
            args.extend(['--password', password])
        
        return self._run_helm(args)
    
    async def update_helm_repositories(self) -> Dict[str, Any]:
        """Update Helm repositories"""
        return self._run_helm(['repo', 'update'])
    
    async def list_helm_repositories(self, output_format: str = 'table') -> Dict[str, Any]:
        """List Helm repositories"""
        args = ['repo', 'list']
        
        if output_format in ['json', 'yaml']:
            args.extend(['--output', output_format])
        
        return self._run_helm(args)
    
    async def remove_helm_repository(self, name: str) -> Dict[str, Any]:
        """Remove Helm repository"""
        return self._run_helm(['repo', 'remove', name])
    
    # Chart operations
    
    async def search_helm_charts(self, keyword: str,
                                repository: Optional[str] = None,
                                version: Optional[str] = None,
                                max_results: Optional[int] = None) -> Dict[str, Any]:
        """Search for Helm charts"""
        args = ['search', 'repo', keyword]
        
        if version:
            args.extend(['--version', version])
        if max_results:
            args.extend(['--max-col-width', str(max_results)])
        
        return self._run_helm(args)
    
    async def show_helm_chart(self, chart: str,
                             chart_version: Optional[str] = None,
                             info_type: str = 'all') -> Dict[str, Any]:
        """Show Helm chart information"""
        args = ['show', info_type, chart]
        
        if chart_version:
            args.extend(['--version', chart_version])
        
        return self._run_helm(args)
    
    async def template_helm_chart(self, release_name: str, chart: str,
                                 namespace: Optional[str] = None,
                                 values: Optional[Dict[str, Any]] = None,
                                 values_file: Optional[str] = None,
                                 chart_version: Optional[str] = None) -> Dict[str, Any]:
        """Template a Helm chart (render without installing)"""
        args = ['template', release_name, chart]
        
        if namespace:
            args.extend(['--namespace', namespace])
        if chart_version:
            args.extend(['--version', chart_version])
        
        # Handle values
        values_input = None
        if values_file:
            args.extend(['--values', values_file])
        elif values:
            values_yaml = yaml.dump(values)
            args.extend(['--values', '-'])
            values_input = values_yaml
        
        return self._run_helm(args, input_data=values_input)
    
    # Enhanced functionality beyond Flux159
    
    async def lint_helm_chart(self, chart_path: str) -> Dict[str, Any]:
        """Lint a Helm chart for issues"""
        return self._run_helm(['lint', chart_path])
    
    async def package_helm_chart(self, chart_path: str,
                                destination: Optional[str] = None) -> Dict[str, Any]:
        """Package a Helm chart"""
        args = ['package', chart_path]
        
        if destination:
            args.extend(['--destination', destination])
        
        return self._run_helm(args)
    
    async def test_helm_release(self, release_name: str,
                               namespace: Optional[str] = None) -> Dict[str, Any]:
        """Run tests for a Helm release"""
        args = ['test', release_name]
        
        if namespace:
            args.extend(['--namespace', namespace])
        
        return self._run_helm(args)
    
    async def helm_plugin_list(self) -> Dict[str, Any]:
        """List installed Helm plugins"""
        return self._run_helm(['plugin', 'list'])
    
    async def helm_env(self) -> Dict[str, Any]:
        """Show Helm environment information"""
        return self._run_helm(['env'])
    
    async def get_helm_version(self) -> Dict[str, Any]:
        """Get Helm version information"""
        return self._run_helm(['version'])
    
    # Utility methods
    
    def is_available(self) -> bool:
        """Check if Helm is available"""
        return self.helm_available
    
    async def validate_release_name(self, release_name: str) -> Dict[str, Any]:
        """Validate if a release name is valid and available"""
        # Check if release already exists
        list_result = await self.list_helm_releases(output_format='json')
        if list_result['success'] and list_result['stdout']:
            try:
                releases = json.loads(list_result['stdout'])
                existing_names = [release['name'] for release in releases]
                if release_name in existing_names:
                    return {
                        'success': False,
                        'stdout': '',
                        'stderr': f'Release name {release_name} already exists',
                        'returncode': 1,
                        'command': f'validate release name {release_name}'
                    }
            except json.JSONDecodeError:
                pass
        
        # Check name format (Helm naming rules)
        import re
        if not re.match(r'^[a-z0-9]([a-z0-9\-]*[a-z0-9])?$', release_name):
            return {
                'success': False,
                'stdout': '',
                'stderr': 'Release name must consist of lowercase letters, numbers, and hyphens',
                'returncode': 1,
                'command': f'validate release name {release_name}'
            }
        
        return {
            'success': True,
            'stdout': f'Release name {release_name} is valid and available',
            'stderr': '',
            'returncode': 0,
            'command': f'validate release name {release_name}'
        }
