"""
Documentation Manager for fetching and indexing Kubernetes documentation and best practices.
"""

import asyncio
import aiohttp
import json
import re
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import hashlib
from datetime import datetime

from config import ServerConfig
from logger import get_logger


class DocumentationManager:
    """
    Manages Kubernetes documentation fetching, indexing, and search capabilities.
    """
    
    def __init__(self, config: ServerConfig):
        """Initialize documentation manager."""
        self.config = config
        self.logger = get_logger(__name__)
        self.base_urls = [
            "https://kubernetes.io/docs/",
            "https://kubernetes.io/docs/concepts/",
            "https://kubernetes.io/docs/tasks/",
            "https://kubernetes.io/docs/tutorials/",
            "https://kubernetes.io/docs/reference/",
            "https://kubernetes.io/docs/setup/",
        ]
        self.documentation_db = {}
        self.indexed_urls = set()
        self.best_practices = {}
        
    async def initialize(self):
        """Initialize documentation fetching and indexing."""
        try:
            self.logger.info("Initializing documentation manager...")
            await self._build_documentation_index()
            await self._load_best_practices()
            self.logger.info("Documentation manager initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize documentation manager: {e}")
            raise
    
    async def _build_documentation_index(self):
        """Build comprehensive documentation index from Kubernetes docs."""
        self.logger.info("Building Kubernetes documentation index...")
        
        connector = aiohttp.TCPConnector(limit=10)
        timeout = aiohttp.ClientTimeout(total=30)
        
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            # Fetch main documentation sections
            tasks = []
            for base_url in self.base_urls:
                tasks.append(self._fetch_documentation_section(session, base_url))
            
            await asyncio.gather(*tasks, return_exceptions=True)
        
        self.logger.info(f"Documentation index built with {len(self.documentation_db)} entries")
    
    async def _fetch_documentation_section(self, session: aiohttp.ClientSession, base_url: str):
        """Fetch and index a documentation section."""
        try:
            async with session.get(base_url) as response:
                if response.status == 200:
                    content = await response.text()
                    soup = BeautifulSoup(content, 'html.parser')
                    
                    # Extract main content
                    main_content = soup.find('main') or soup.find('div', class_='main-content')
                    if main_content:
                        doc_entry = await self._extract_documentation_content(main_content, base_url)
                        if doc_entry:
                            url_hash = hashlib.md5(base_url.encode()).hexdigest()
                            self.documentation_db[url_hash] = doc_entry
                    
                    # Find and index linked pages
                    await self._index_linked_pages(session, soup, base_url)
                    
        except Exception as e:
            self.logger.error(f"Error fetching documentation from {base_url}: {e}")
    
    async def _extract_documentation_content(self, content_element, url: str) -> Dict[str, Any]:
        """Extract structured content from documentation page."""
        try:
            # Extract title
            title_elem = content_element.find('h1')
            title = title_elem.get_text().strip() if title_elem else "Unknown"
            
            # Extract sections and subsections
            sections = []
            current_section = None
            
            for elem in content_element.find_all(['h1', 'h2', 'h3', 'h4', 'p', 'code', 'pre']):
                if elem.name in ['h1', 'h2', 'h3', 'h4']:
                    if current_section:
                        sections.append(current_section)
                    current_section = {
                        'level': int(elem.name[1]),
                        'title': elem.get_text().strip(),
                        'content': [],
                        'code_examples': []
                    }
                elif current_section:
                    if elem.name in ['code', 'pre']:
                        current_section['code_examples'].append(elem.get_text().strip())
                    else:
                        current_section['content'].append(elem.get_text().strip())
            
            if current_section:
                sections.append(current_section)
            
            # Extract commands and best practices
            commands = self._extract_commands(content_element)
            best_practices = self._extract_best_practices(content_element)
            troubleshooting = self._extract_troubleshooting_info(content_element)
            
            return {
                'url': url,
                'title': title,
                'sections': sections,
                'commands': commands,
                'best_practices': best_practices,
                'troubleshooting': troubleshooting,
                'indexed_at': datetime.utcnow().isoformat(),
                'tags': self._extract_tags(title, sections)
            }
            
        except Exception as e:
            self.logger.error(f"Error extracting content from {url}: {e}")
            return None
    
    def _extract_commands(self, content_element) -> List[Dict[str, str]]:
        """Extract kubectl and other commands from documentation."""
        commands = []
        
        # Find code blocks that look like commands
        code_blocks = content_element.find_all(['code', 'pre'])
        for block in code_blocks:
            text = block.get_text().strip()
            
            # Look for kubectl commands
            if 'kubectl' in text:
                lines = text.split('\n')
                for line in lines:
                    line = line.strip()
                    if line.startswith('kubectl'):
                        commands.append({
                            'command': line,
                            'type': 'kubectl',
                            'description': self._get_command_description(block)
                        })
            
            # Look for other common commands
            for cmd_type in ['helm', 'kubeadm', 'docker', 'crictl']:
                if cmd_type in text:
                    lines = text.split('\n')
                    for line in lines:
                        line = line.strip()
                        if line.startswith(cmd_type):
                            commands.append({
                                'command': line,
                                'type': cmd_type,
                                'description': self._get_command_description(block)
                            })
        
        return commands
    
    def _extract_best_practices(self, content_element) -> List[str]:
        """Extract best practices from documentation."""
        best_practices = []
        
        # Look for sections with best practice indicators
        indicators = ['best practice', 'recommendation', 'should', 'avoid', 'prefer', 'important']
        
        for elem in content_element.find_all(['p', 'li', 'div']):
            text = elem.get_text().lower()
            if any(indicator in text for indicator in indicators):
                practice = elem.get_text().strip()
                if len(practice) > 20 and len(practice) < 500:  # Reasonable length
                    best_practices.append(practice)
        
        return best_practices
    
    def _extract_troubleshooting_info(self, content_element) -> List[Dict[str, str]]:
        """Extract troubleshooting information from documentation."""
        troubleshooting = []
        
        # Look for troubleshooting sections
        trouble_indicators = ['troubleshoot', 'debug', 'error', 'issue', 'problem', 'solution']
        
        for elem in content_element.find_all(['div', 'section'], class_=lambda x: x and any(ind in str(x).lower() for ind in trouble_indicators)):
            title_elem = elem.find(['h1', 'h2', 'h3', 'h4'])
            title = title_elem.get_text().strip() if title_elem else "Troubleshooting"
            
            content = []
            for p in elem.find_all('p'):
                content.append(p.get_text().strip())
            
            if content:
                troubleshooting.append({
                    'title': title,
                    'content': ' '.join(content),
                    'type': 'troubleshooting'
                })
        
        return troubleshooting
    
    def _extract_tags(self, title: str, sections: List[Dict]) -> List[str]:
        """Extract relevant tags for categorization."""
        tags = set()
        
        # Add tags based on title
        title_lower = title.lower()
        if 'pod' in title_lower:
            tags.add('pods')
        if 'service' in title_lower:
            tags.add('services')
        if 'deployment' in title_lower:
            tags.add('deployments')
        if 'network' in title_lower:
            tags.add('networking')
        if 'storage' in title_lower:
            tags.add('storage')
        if 'security' in title_lower:
            tags.add('security')
        if 'monitor' in title_lower:
            tags.add('monitoring')
        
        # Add tags based on section content
        for section in sections:
            section_text = section.get('title', '').lower()
            if 'rbac' in section_text:
                tags.add('rbac')
            if 'ingress' in section_text:
                tags.add('ingress')
            if 'configmap' in section_text:
                tags.add('configmaps')
            if 'secret' in section_text:
                tags.add('secrets')
        
        return list(tags)
    
    def _get_command_description(self, block_element) -> str:
        """Get description for a command from surrounding context."""
        # Look for description in previous or next siblings
        description = ""
        
        prev_elem = block_element.find_previous_sibling(['p', 'div'])
        if prev_elem:
            text = prev_elem.get_text().strip()
            if len(text) < 200:  # Reasonable description length
                description = text
        
        return description
    
    async def _index_linked_pages(self, session: aiohttp.ClientSession, soup: BeautifulSoup, base_url: str):
        """Index linked documentation pages."""
        links = soup.find_all('a', href=True)
        tasks = []
        
        for link in links[:10]:  # Limit to avoid overwhelming
            href = link['href']
            if href.startswith('/docs/') and href not in self.indexed_urls:
                full_url = urljoin(base_url, href)
                if full_url not in self.indexed_urls:
                    self.indexed_urls.add(full_url)
                    tasks.append(self._fetch_documentation_section(session, full_url))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _load_best_practices(self):
        """Load comprehensive Kubernetes best practices."""
        self.best_practices = {
            'resource_management': [
                "Always set resource requests and limits for containers",
                "Use appropriate CPU and memory values based on actual usage",
                "Implement horizontal pod autoscaling for variable workloads",
                "Monitor resource utilization regularly",
                "Use resource quotas to prevent resource exhaustion"
            ],
            'security': [
                "Never run containers as root user",
                "Use Pod Security Standards to enforce security policies",
                "Implement network policies for micro-segmentation",
                "Scan container images for vulnerabilities",
                "Use secrets management for sensitive data",
                "Enable RBAC and follow least privilege principle"
            ],
            'reliability': [
                "Configure liveness and readiness probes",
                "Set up pod disruption budgets",
                "Use multiple replicas for high availability",
                "Implement proper graceful shutdown handling",
                "Use rolling updates for zero-downtime deployments"
            ],
            'networking': [
                "Use services for pod-to-pod communication",
                "Implement ingress controllers for external access",
                "Configure DNS policies appropriately",
                "Use headless services when needed",
                "Monitor network policies effectiveness"
            ],
            'storage': [
                "Use appropriate storage classes for workloads",
                "Implement backup strategies for persistent volumes",
                "Monitor storage usage and performance",
                "Use volume snapshots for data protection",
                "Consider storage locality for performance"
            ],
            'monitoring': [
                "Implement comprehensive logging strategy",
                "Monitor cluster and application metrics",
                "Set up alerting for critical issues",
                "Use distributed tracing for complex applications",
                "Monitor resource usage trends"
            ]
        }
    
    async def search_documentation(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Search documentation for relevant information."""
        try:
            self.logger.info(f"Searching documentation for: {query}")
            
            results = []
            query_lower = query.lower()
            
            for doc_id, doc in self.documentation_db.items():
                score = 0
                
                # Score based on title match
                if query_lower in doc['title'].lower():
                    score += 10
                
                # Score based on section content
                for section in doc['sections']:
                    if query_lower in section['title'].lower():
                        score += 5
                    for content in section['content']:
                        if query_lower in content.lower():
                            score += 1
                
                # Score based on commands
                for command in doc['commands']:
                    if query_lower in command['command'].lower():
                        score += 8
                
                # Score based on tags
                for tag in doc['tags']:
                    if query_lower in tag:
                        score += 3
                
                if score > 0:
                    results.append({
                        'score': score,
                        'doc': doc,
                        'doc_id': doc_id
                    })
            
            # Sort by score and return top results
            results.sort(key=lambda x: x['score'], reverse=True)
            return [r['doc'] for r in results[:max_results]]
            
        except Exception as e:
            self.logger.error(f"Error searching documentation: {e}")
            return []
    
    async def get_best_practices(self, category: str = None) -> Dict[str, List[str]]:
        """Get best practices for a specific category or all categories."""
        if category and category in self.best_practices:
            return {category: self.best_practices[category]}
        return self.best_practices
    
    async def find_commands(self, command_type: str = None, search_term: str = None) -> List[Dict[str, str]]:
        """Find commands from documentation."""
        commands = []
        
        for doc in self.documentation_db.values():
            for command in doc['commands']:
                include = True
                
                if command_type and command['type'] != command_type:
                    include = False
                
                if search_term and search_term.lower() not in command['command'].lower():
                    include = False
                
                if include:
                    commands.append(command)
        
        return commands[:50]  # Limit results
    
    async def get_troubleshooting_guide(self, issue_type: str) -> List[Dict[str, Any]]:
        """Get troubleshooting guides for specific issue types."""
        guides = []
        
        for doc in self.documentation_db.values():
            for trouble in doc['troubleshooting']:
                if issue_type.lower() in trouble['title'].lower() or issue_type.lower() in trouble['content'].lower():
                    guides.append({
                        'source': doc['title'],
                        'url': doc['url'],
                        'guide': trouble
                    })
        
        return guides
