"""
Enhanced Kubectl Manager with comprehensive kubectl API coverage
Matches and exceeds capabilities from Flux159/mcp-server-kubernetes
"""

import json
import subprocess
import asyncio
from typing import Dict, List, Optional, Any
import re

try:
    from logger import get_logger
except ImportError:
    from logger import get_logger

logger = get_logger(__name__)


class KubectlManager:
    """
    Comprehensive kubectl management with all operations from Flux159 plus enhancements
    """
    
    def __init__(self, non_destructive_mode: bool = False):
        """Initialize kubectl manager with optional non-destructive mode"""
        self.non_destructive_mode = non_destructive_mode
        self.port_forwards = {}  # Track active port forwards
        
        # Check if kubectl is available
        if not self._check_kubectl():
            raise RuntimeError("kubectl not found in PATH")
    
    def _check_kubectl(self) -> bool:
        """Check if kubectl is available"""
        try:
            result = subprocess.run(['kubectl', 'version', '--client'], 
                                  capture_output=True, text=True, timeout=10)
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def _run_kubectl(self, args: List[str], input_data: Optional[str] = None) -> Dict[str, Any]:
        """Run kubectl command and return structured result"""
        try:
            cmd = ['kubectl'] + args
            logger.info(f"Running kubectl command: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                input=input_data,
                capture_output=True,
                text=True,
                timeout=60
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
                'stderr': 'Command timed out after 60 seconds',
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
    
    def _mask_secrets(self, output: str) -> str:
        """Mask sensitive data in kubectl output"""
        if 'secret' in output.lower():
            # Mask base64 encoded values
            output = re.sub(r'(\s+)(data:\s*\n(?:\s+\w+:\s+)[A-Za-z0-9+/=]+)', 
                          r'\1data:\n    <MASKED>', output)
            # Mask token values
            output = re.sub(r'(token:\s+)[A-Za-z0-9._-]+', r'\1<MASKED>', output)
        return output
    
    def _check_destructive_operation(self, operation: str) -> bool:
        """Check if operation is destructive and should be blocked in non-destructive mode"""
        if not self.non_destructive_mode:
            return False
            
        destructive_ops = [
            'delete', 'destroy', 'remove', 'terminate', 
            'kill', 'drain', 'cordon', 'evict'
        ]
        return any(op in operation.lower() for op in destructive_ops)
    
    # Core kubectl operations (matching Flux159)
    
    async def kubectl_get(self, resource: str, name: Optional[str] = None, 
                         namespace: Optional[str] = None, 
                         output_format: str = 'yaml') -> Dict[str, Any]:
        """Get or list Kubernetes resources"""
        args = ['get', resource]
        
        if name:
            args.append(name)
        if namespace:
            args.extend(['-n', namespace])
        if output_format:
            args.extend(['-o', output_format])
        
        result = self._run_kubectl(args)
        if result['success'] and output_format in ['json', 'yaml']:
            result['stdout'] = self._mask_secrets(result['stdout'])
        
        return result
    
    async def kubectl_describe(self, resource: str, name: str, 
                              namespace: Optional[str] = None) -> Dict[str, Any]:
        """Describe a Kubernetes resource"""
        args = ['describe', resource, name]
        if namespace:
            args.extend(['-n', namespace])
        
        return self._run_kubectl(args)
    
    async def kubectl_create(self, resource_yaml: str, 
                            namespace: Optional[str] = None) -> Dict[str, Any]:
        """Create resources from YAML"""
        args = ['create', '-f', '-']
        if namespace:
            args.extend(['-n', namespace])
        
        return self._run_kubectl(args, input_data=resource_yaml)
    
    async def kubectl_apply(self, resource_yaml: str, 
                           namespace: Optional[str] = None) -> Dict[str, Any]:
        """Apply resources from YAML"""
        args = ['apply', '-f', '-']
        if namespace:
            args.extend(['-n', namespace])
        
        return self._run_kubectl(args, input_data=resource_yaml)
    
    async def kubectl_delete(self, resource: str, name: str, 
                            namespace: Optional[str] = None) -> Dict[str, Any]:
        """Delete a Kubernetes resource"""
        if self._check_destructive_operation('delete'):
            return {
                'success': False,
                'stdout': '',
                'stderr': 'Delete operations disabled in non-destructive mode',
                'returncode': 1,
                'command': f'kubectl delete {resource} {name}'
            }
        
        args = ['delete', resource, name]
        if namespace:
            args.extend(['-n', namespace])
        
        return self._run_kubectl(args)
    
    async def kubectl_logs(self, pod_name: str, namespace: Optional[str] = None,
                          container: Optional[str] = None, follow: bool = False,
                          tail: Optional[int] = None) -> Dict[str, Any]:
        """Get logs from a pod"""
        args = ['logs', pod_name]
        
        if namespace:
            args.extend(['-n', namespace])
        if container:
            args.extend(['-c', container])
        if follow:
            args.append('-f')
        if tail:
            args.extend(['--tail', str(tail)])
        
        return self._run_kubectl(args)
    
    async def kubectl_scale(self, resource: str, name: str, replicas: int,
                           namespace: Optional[str] = None) -> Dict[str, Any]:
        """Scale a resource"""
        args = ['scale', resource, name, f'--replicas={replicas}']
        if namespace:
            args.extend(['-n', namespace])
        
        return self._run_kubectl(args)
    
    async def kubectl_patch(self, resource: str, name: str, patch: str,
                           patch_type: str = 'strategic',
                           namespace: Optional[str] = None) -> Dict[str, Any]:
        """Patch a resource"""
        args = ['patch', resource, name, '--patch', patch]
        args.extend(['--type', patch_type])
        
        if namespace:
            args.extend(['-n', namespace])
        
        return self._run_kubectl(args)
    
    async def kubectl_rollout(self, action: str, resource: str, name: str,
                             namespace: Optional[str] = None) -> Dict[str, Any]:
        """Manage rollouts (status, history, undo, restart)"""
        args = ['rollout', action, f'{resource}/{name}']
        if namespace:
            args.extend(['-n', namespace])
        
        return self._run_kubectl(args)
    
    async def kubectl_context(self, action: str = 'current', 
                             context_name: Optional[str] = None) -> Dict[str, Any]:
        """Manage kubectl contexts"""
        if action == 'current':
            args = ['config', 'current-context']
        elif action == 'list':
            args = ['config', 'get-contexts']
        elif action == 'use' and context_name:
            args = ['config', 'use-context', context_name]
        else:
            return {
                'success': False,
                'stdout': '',
                'stderr': 'Invalid context action or missing context name',
                'returncode': 1,
                'command': f'kubectl config {action}'
            }
        
        return self._run_kubectl(args)
    
    async def explain_resource(self, resource: str, 
                              field: Optional[str] = None) -> Dict[str, Any]:
        """Explain Kubernetes resource documentation"""
        args = ['explain', resource]
        if field:
            args.append(f'{resource}.{field}')
        
        return self._run_kubectl(args)
    
    async def list_api_resources(self, api_group: Optional[str] = None) -> Dict[str, Any]:
        """List available API resources"""
        args = ['api-resources']
        if api_group:
            args.extend(['--api-group', api_group])
        
        return self._run_kubectl(args)
    
    async def kubectl_generic(self, command: str) -> Dict[str, Any]:
        """Execute any kubectl command (disabled in non-destructive mode)"""
        if self._check_destructive_operation(command):
            return {
                'success': False,
                'stdout': '',
                'stderr': 'Generic kubectl commands disabled in non-destructive mode',
                'returncode': 1,
                'command': f'kubectl {command}'
            }
        
        # Parse command into args
        args = command.split()
        return self._run_kubectl(args)
    
    # Port forwarding functionality
    
    async def port_forward(self, resource: str, ports: str,
                          namespace: Optional[str] = None) -> Dict[str, Any]:
        """Start port forwarding to a resource"""
        args = ['port-forward', resource, ports]
        if namespace:
            args.extend(['-n', namespace])
        
        try:
            # Start port-forward in background
            process = subprocess.Popen(
                ['kubectl'] + args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Store process for later cleanup
            forward_id = f"{resource}:{ports}"
            if namespace:
                forward_id = f"{namespace}/{forward_id}"
            
            self.port_forwards[forward_id] = process
            
            # Give it a moment to start
            await asyncio.sleep(2)
            
            if process.poll() is None:  # Process is still running
                return {
                    'success': True,
                    'stdout': f'Port forwarding started: {forward_id}',
                    'stderr': '',
                    'returncode': 0,
                    'command': ' '.join(['kubectl'] + args),
                    'forward_id': forward_id
                }
            else:
                stdout, stderr = process.communicate()
                return {
                    'success': False,
                    'stdout': stdout,
                    'stderr': stderr,
                    'returncode': process.returncode,
                    'command': ' '.join(['kubectl'] + args)
                }
        
        except Exception as e:
            return {
                'success': False,
                'stdout': '',
                'stderr': str(e),
                'returncode': 1,
                'command': ' '.join(['kubectl'] + args)
            }
    
    async def stop_port_forward(self, forward_id: str) -> Dict[str, Any]:
        """Stop a specific port forward"""
        if forward_id not in self.port_forwards:
            return {
                'success': False,
                'stdout': '',
                'stderr': f'Port forward {forward_id} not found',
                'returncode': 1,
                'command': f'stop port-forward {forward_id}'
            }
        
        process = self.port_forwards[forward_id]
        try:
            process.terminate()
            await asyncio.sleep(1)
            if process.poll() is None:
                process.kill()
            
            del self.port_forwards[forward_id]
            
            return {
                'success': True,
                'stdout': f'Port forward {forward_id} stopped',
                'stderr': '',
                'returncode': 0,
                'command': f'stop port-forward {forward_id}'
            }
        
        except Exception as e:
            return {
                'success': False,
                'stdout': '',
                'stderr': str(e),
                'returncode': 1,
                'command': f'stop port-forward {forward_id}'
            }
    
    async def list_port_forwards(self) -> Dict[str, Any]:
        """List active port forwards"""
        active_forwards = []
        to_remove = []
        
        for forward_id, process in self.port_forwards.items():
            if process.poll() is None:  # Still running
                active_forwards.append(forward_id)
            else:
                to_remove.append(forward_id)
        
        # Clean up dead processes
        for forward_id in to_remove:
            del self.port_forwards[forward_id]
        
        return {
            'success': True,
            'stdout': '\n'.join(active_forwards) if active_forwards else 'No active port forwards',
            'stderr': '',
            'returncode': 0,
            'command': 'list port-forwards',
            'active_forwards': active_forwards
        }
    
    # Health and connectivity
    
    async def ping(self) -> Dict[str, Any]:
        """Verify connection to Kubernetes cluster"""
        return await self.kubectl_get('nodes', output_format='json')
    
    # Enhanced troubleshooting
    
    async def diagnose_pod(self, keyword: str, namespace: Optional[str] = None) -> Dict[str, Any]:
        """Systematic pod troubleshooting similar to k8s-diagnose"""
        diagnosis = {
            'keyword': keyword,
            'namespace': namespace,
            'steps': [],
            'recommendations': []
        }
        
        try:
            # Step 1: Find pods matching keyword
            pods_result = await self.kubectl_get('pods', namespace=namespace, output_format='json')
            if not pods_result['success']:
                diagnosis['steps'].append({
                    'step': 'Find pods',
                    'status': 'failed',
                    'output': pods_result['stderr']
                })
                return {
                    'success': False,
                    'stdout': json.dumps(diagnosis, indent=2),
                    'stderr': 'Failed to list pods',
                    'returncode': 1,
                    'command': 'diagnose pod'
                }
            
            # Parse pod data
            pods_data = json.loads(pods_result['stdout']) if pods_result['stdout'] else {'items': []}
            matching_pods = [
                pod for pod in pods_data.get('items', [])
                if keyword.lower() in pod['metadata']['name'].lower()
            ]
            
            diagnosis['steps'].append({
                'step': 'Find pods',
                'status': 'success',
                'found_pods': len(matching_pods),
                'pod_names': [pod['metadata']['name'] for pod in matching_pods]
            })
            
            # Step 2: Analyze each pod
            for pod in matching_pods[:5]:  # Limit to 5 pods
                pod_name = pod['metadata']['name']
                pod_namespace = pod['metadata']['namespace']
                pod_status = pod['status']['phase']
                
                pod_analysis = {
                    'pod_name': pod_name,
                    'namespace': pod_namespace,
                    'status': pod_status,
                    'issues': [],
                    'suggestions': []
                }
                
                # Check pod status
                if pod_status != 'Running':
                    pod_analysis['issues'].append(f"Pod status is {pod_status}")
                    
                    if pod_status == 'Pending':
                        pod_analysis['suggestions'].append("Check resource quotas and node capacity")
                        pod_analysis['suggestions'].append("Check for scheduling constraints")
                    elif pod_status == 'Failed':
                        pod_analysis['suggestions'].append("Check pod logs for error details")
                        pod_analysis['suggestions'].append("Check resource limits and requests")
                
                # Check container statuses
                container_statuses = pod['status'].get('containerStatuses', [])
                for container_status in container_statuses:
                    if not container_status.get('ready', False):
                        pod_analysis['issues'].append(
                            f"Container {container_status['name']} not ready"
                        )
                        
                        # Check restart count
                        restart_count = container_status.get('restartCount', 0)
                        if restart_count > 0:
                            pod_analysis['issues'].append(
                                f"Container {container_status['name']} has restarted {restart_count} times"
                            )
                            pod_analysis['suggestions'].append("Check container logs for crash details")
                
                diagnosis['steps'].append({
                    'step': f'Analyze pod {pod_name}',
                    'status': 'completed',
                    'analysis': pod_analysis
                })
                
                # Get logs if there are issues
                if pod_analysis['issues']:
                    logs_result = await self.kubectl_logs(pod_name, namespace=pod_namespace, tail=50)
                    if logs_result['success']:
                        diagnosis['steps'].append({
                            'step': f'Get logs for {pod_name}',
                            'status': 'success',
                            'logs_preview': logs_result['stdout'][-500:]  # Last 500 chars
                        })
            
            # Overall recommendations
            if any('Pending' in step.get('analysis', {}).get('status', '') for step in diagnosis['steps']):
                diagnosis['recommendations'].append("Check cluster resource availability with 'kubectl top nodes'")
                diagnosis['recommendations'].append("Check for PodDisruptionBudgets that might prevent scheduling")
            
            return {
                'success': True,
                'stdout': json.dumps(diagnosis, indent=2),
                'stderr': '',
                'returncode': 0,
                'command': f'diagnose pod {keyword}',
                'diagnosis': diagnosis
            }
        
        except Exception as e:
            return {
                'success': False,
                'stdout': json.dumps(diagnosis, indent=2),
                'stderr': str(e),
                'returncode': 1,
                'command': f'diagnose pod {keyword}'
            }
    
    # Cleanup method
    
    async def cleanup(self) -> Dict[str, Any]:
        """Clean up resources (disabled in non-destructive mode)"""
        if self.non_destructive_mode:
            return {
                'success': False,
                'stdout': '',
                'stderr': 'Cleanup disabled in non-destructive mode',
                'returncode': 1,
                'command': 'cleanup'
            }
        
        cleanup_results = []
        
        # Stop all port forwards
        for forward_id in list(self.port_forwards.keys()):
            result = await self.stop_port_forward(forward_id)
            cleanup_results.append(f"Port forward {forward_id}: {'stopped' if result['success'] else 'failed'}")
        
        return {
            'success': True,
            'stdout': '\n'.join(cleanup_results),
            'stderr': '',
            'returncode': 0,
            'command': 'cleanup'
        }
