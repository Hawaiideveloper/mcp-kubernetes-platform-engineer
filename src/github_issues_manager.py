"""
GitHub Issues Manager for fetching and indexing Kubernetes GitHub issues for rapid troubleshooting.
"""

import asyncio
import aiohttp
import json
import aiosqlite
from typing import Any, Dict, List, Tuple
from datetime import datetime, timedelta
import re

from config import ServerConfig
from logger import get_logger


class GitHubIssuesManager:
    """
    Manages GitHub issues fetching, indexing, and search capabilities for Kubernetes troubleshooting.
    """
    
    def __init__(self, config: ServerConfig):
        """Initialize GitHub issues manager."""
        self.config = config
        self.logger = get_logger(__name__)
        # Use relative path that works both in development and production
        import tempfile
        import os
        try:
            data_dir = "./data"
            os.makedirs(data_dir, exist_ok=True)
            self.db_path = f"{data_dir}/github_issues.db"
        except OSError:
            # Fallback to temp directory if we can't write to ./data
            self.db_path = os.path.join(tempfile.gettempdir(), "github_issues.db")
        self.github_repos = [
            "kubernetes/kubernetes",
            "kubernetes/kubectl",
            "kubernetes/kubeadm",
            "kubernetes/kubelet",
            "kubernetes/kube-proxy",
            "kubernetes/ingress-nginx",
            "kubernetes/dashboard",
            "kubernetes-sigs/metrics-server",
            "kubernetes-sigs/cluster-autoscaler",
            "kubernetes-sigs/aws-load-balancer-controller",
            "projectcalico/calico",
            "flannel-io/flannel",
            "cilium/cilium",
            "helm/helm",
            "istio/istio",
            "prometheus/prometheus",
            "grafana/grafana"
        ]
        self.github_token = None  # Add GitHub token for higher rate limits
        self.update_interval = 3600  # Update every hour (3600 seconds)
        self.update_task = None  # Background update task
        
    async def initialize(self):
        """Initialize GitHub issues database and start fetching."""
        try:
            self.logger.info("Initializing GitHub issues manager...")
            await self._setup_database()
            await self._fetch_recent_issues()
            
            # Start background update task
            self.update_task = asyncio.create_task(self._background_update_loop())
            
            self.logger.info("GitHub issues manager initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize GitHub issues manager: {e}")
            raise
    
    async def _setup_database(self):
        """Setup SQLite database for storing GitHub issues."""
        import os
        try:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        except OSError:
            # Directory creation handled in __init__, this is just a safety check
            pass
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS github_issues (
                    id INTEGER PRIMARY KEY,
                    repo TEXT NOT NULL,
                    issue_number INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT,
                    state TEXT NOT NULL,
                    labels TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    closed_at TEXT,
                    url TEXT NOT NULL,
                    author TEXT,
                    assignees TEXT,
                    comments_count INTEGER DEFAULT 0,
                    reactions_count INTEGER DEFAULT 0,
                    severity TEXT,
                    component TEXT,
                    resolution TEXT,
                    workaround TEXT,
                    indexed_at TEXT NOT NULL,
                    UNIQUE(repo, issue_number)
                )
            """)
            
            await db.execute("""
                CREATE TABLE IF NOT EXISTS issue_comments (
                    id INTEGER PRIMARY KEY,
                    issue_id INTEGER,
                    comment_id INTEGER UNIQUE,
                    body TEXT,
                    author TEXT,
                    created_at TEXT,
                    helpful_score INTEGER DEFAULT 0,
                    FOREIGN KEY(issue_id) REFERENCES github_issues(id)
                )
            """)
            
            await db.execute("""
                CREATE TABLE IF NOT EXISTS issue_solutions (
                    id INTEGER PRIMARY KEY,
                    issue_id INTEGER,
                    solution_type TEXT,
                    description TEXT,
                    commands TEXT,
                    verification TEXT,
                    confidence_score REAL DEFAULT 0.0,
                    FOREIGN KEY(issue_id) REFERENCES github_issues(id)
                )
            """)
            
            # Create indexes for faster searches
            await db.execute("CREATE INDEX IF NOT EXISTS idx_repo_state ON github_issues(repo, state)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_labels ON github_issues(labels)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON github_issues(created_at)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_title_body ON github_issues(title, body)")
            
            await db.commit()
    
    async def _fetch_recent_issues(self):
        """Fetch recent issues from GitHub repositories."""
        self.logger.info("Fetching recent GitHub issues...")
        
        headers = {
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'K8s-Platform-Engineer-MCP/1.0'
        }
        
        if self.github_token:
            headers['Authorization'] = f'token {self.github_token}'
        
        connector = aiohttp.TCPConnector(limit=10)
        timeout = aiohttp.ClientTimeout(total=60)
        
        async with aiohttp.ClientSession(connector=connector, timeout=timeout, headers=headers) as session:
            tasks = []
            for repo in self.github_repos:
                tasks.append(self._fetch_repo_issues(session, repo))
            
            await asyncio.gather(*tasks, return_exceptions=True)
        
        self.logger.info("GitHub issues fetching completed")
    
    async def _background_update_loop(self):
        """Background task to continuously update GitHub issues."""
        self.logger.info(f"Starting background GitHub issues update loop (interval: {self.update_interval}s)")
        
        while True:
            try:
                await asyncio.sleep(self.update_interval)
                self.logger.info("Running scheduled GitHub issues update...")
                await self._fetch_recent_issues()
                
                # Clean up old issues (older than 1 year)
                await self._cleanup_old_issues()
                
                self.logger.info("Scheduled GitHub issues update completed")
            except asyncio.CancelledError:
                self.logger.info("Background update loop cancelled")
                break
            except Exception as e:
                self.logger.error(f"Error in background update loop: {e}")
                # Continue the loop despite errors
    
    async def _cleanup_old_issues(self):
        """Remove issues older than 1 year to keep database size manageable."""
        try:
            cutoff_date = (datetime.utcnow() - timedelta(days=365)).isoformat()
            
            async with aiosqlite.connect(self.db_path) as db:
                # Remove old issues
                await db.execute("""
                    DELETE FROM github_issues 
                    WHERE created_at < ? AND state = 'closed'
                """, (cutoff_date,))
                
                # Remove orphaned comments and solutions
                await db.execute("""
                    DELETE FROM issue_comments 
                    WHERE issue_id NOT IN (SELECT id FROM github_issues)
                """)
                
                await db.execute("""
                    DELETE FROM issue_solutions 
                    WHERE issue_id NOT IN (SELECT id FROM github_issues)
                """)
                
                await db.commit()
                
                # Get cleanup stats
                async with db.execute("SELECT changes()") as cursor:
                    deleted_count = (await cursor.fetchone())[0]
                
                if deleted_count > 0:
                    self.logger.info(f"Cleaned up {deleted_count} old GitHub issues")
                    
        except Exception as e:
            self.logger.error(f"Error cleaning up old issues: {e}")
    
    async def stop(self):
        """Stop the background update task."""
        if self.update_task and not self.update_task.done():
            self.update_task.cancel()
            try:
                await self.update_task
            except asyncio.CancelledError:
                pass
            self.logger.info("GitHub issues manager stopped")
    
    async def _fetch_repo_issues(self, session: aiohttp.ClientSession, repo: str):
        """Fetch issues for a specific repository."""
        try:
            # Fetch open issues
            await self._fetch_issues_page(session, repo, "open")
            
            # Fetch recently closed issues (last 30 days)
            since_date = (datetime.utcnow() - timedelta(days=30)).isoformat()
            await self._fetch_issues_page(session, repo, "closed", since=since_date)
            
        except Exception as e:
            self.logger.error(f"Error fetching issues for {repo}: {e}")
    
    async def _fetch_issues_page(self, session: aiohttp.ClientSession, repo: str, state: str, since: str = None):
        """Fetch a page of issues from GitHub API."""
        url = f"https://api.github.com/repos/{repo}/issues"
        params = {
            'state': state,
            'per_page': 100,
            'sort': 'updated',
            'direction': 'desc'
        }
        
        if since:
            params['since'] = since
        
        try:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    issues = await response.json()
                    await self._process_issues(repo, issues)
                elif response.status == 403:
                    self.logger.warning(f"Rate limited for {repo}")
                else:
                    self.logger.warning(f"Failed to fetch issues for {repo}: {response.status}")
                    
        except Exception as e:
            self.logger.error(f"Error fetching issues page for {repo}: {e}")
    
    async def _process_issues(self, repo: str, issues: List[Dict]):
        """Process and store issues in database."""
        async with aiosqlite.connect(self.db_path) as db:
            for issue in issues:
                # Skip pull requests
                if 'pull_request' in issue:
                    continue
                
                # Extract relevant information
                issue_data = await self._extract_issue_data(repo, issue)
                
                # Insert or update issue
                await db.execute("""
                    INSERT OR REPLACE INTO github_issues 
                    (repo, issue_number, title, body, state, labels, created_at, updated_at, 
                     closed_at, url, author, assignees, comments_count, reactions_count, 
                     severity, component, resolution, workaround, indexed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, issue_data)
            
            await db.commit()
    
    async def _extract_issue_data(self, repo: str, issue: Dict) -> Tuple:
        """Extract and process issue data."""
        labels = json.dumps([label['name'] for label in issue.get('labels', [])])
        assignees = json.dumps([assignee['login'] for assignee in issue.get('assignees', [])])
        
        # Analyze issue for severity and component
        severity = self._analyze_severity(issue)
        component = self._analyze_component(issue)
        resolution, workaround = self._extract_solution_info(issue)
        
        return (
            repo,
            issue['number'],
            issue['title'],
            issue.get('body', ''),
            issue['state'],
            labels,
            issue['created_at'],
            issue['updated_at'],
            issue.get('closed_at'),
            issue['html_url'],
            issue['user']['login'],
            assignees,
            issue['comments'],
            issue['reactions']['total_count'],
            severity,
            component,
            resolution,
            workaround,
            datetime.utcnow().isoformat()
        )
    
    def _analyze_severity(self, issue: Dict) -> str:
        """Analyze issue severity based on labels and content."""
        labels = [label['name'].lower() for label in issue.get('labels', [])]
        title = issue['title'].lower()
        body = issue.get('body', '').lower()
        
        # Check labels first
        if any(label in ['critical', 'p0', 'severity/critical'] for label in labels):
            return 'critical'
        elif any(label in ['high', 'p1', 'severity/high'] for label in labels):
            return 'high'
        elif any(label in ['medium', 'p2', 'severity/medium'] for label in labels):
            return 'medium'
        elif any(label in ['low', 'p3', 'severity/low'] for label in labels):
            return 'low'
        
        # Analyze content for severity indicators
        critical_keywords = ['crash', 'panic', 'deadlock', 'data loss', 'security']
        high_keywords = ['fail', 'error', 'broken', 'regression', 'performance']
        
        content = f"{title} {body}"
        
        if any(keyword in content for keyword in critical_keywords):
            return 'high'  # Conservative estimate
        elif any(keyword in content for keyword in high_keywords):
            return 'medium'
        
        return 'low'
    
    def _analyze_component(self, issue: Dict) -> str:
        """Analyze which Kubernetes component the issue relates to."""
        [label['name'].lower() for label in issue.get('labels', [])]
        title = issue['title'].lower()
        body = issue.get('body', '').lower()
        
        content = f"{title} {body}"
        
        # Component mapping
        components = {
            'kubelet': ['kubelet', 'node', 'container runtime'],
            'kube-proxy': ['kube-proxy', 'networking', 'iptables'],
            'api-server': ['api-server', 'apiserver', 'etcd'],
            'scheduler': ['scheduler', 'scheduling', 'pod placement'],
            'controller-manager': ['controller', 'manager', 'reconcile'],
            'kubectl': ['kubectl', 'cli', 'command line'],
            'kubeadm': ['kubeadm', 'cluster init', 'bootstrap'],
            'networking': ['network', 'cni', 'dns', 'ingress'],
            'storage': ['storage', 'volume', 'pv', 'pvc'],
            'security': ['rbac', 'security', 'auth', 'admission'],
            'monitoring': ['metrics', 'monitoring', 'prometheus'],
        }
        
        for component, keywords in components.items():
            if any(keyword in content for keyword in keywords):
                return component
        
        return 'general'
    
    def _extract_solution_info(self, issue: Dict) -> Tuple[str, str]:
        """Extract resolution and workaround information from issue."""
        body = issue.get('body', '')
        
        resolution = ""
        workaround = ""
        
        # Look for solution patterns in the body
        solution_patterns = [
            r'(?:solution|fix|resolved?):?\s*(.{1,500})',
            r'(?:workaround):?\s*(.{1,300})',
            r'(?:to fix|to resolve):?\s*(.{1,300})'
        ]
        
        for pattern in solution_patterns:
            matches = re.findall(pattern, body, re.IGNORECASE | re.DOTALL)
            if matches:
                if 'workaround' in pattern:
                    workaround = matches[0].strip()
                else:
                    resolution = matches[0].strip()
        
        return resolution, workaround
    
    async def search_issues(self, query: str, repo: str = None, state: str = None, 
                           component: str = None, severity: str = None, max_results: int = 20) -> List[Dict[str, Any]]:
        """Search GitHub issues based on various criteria."""
        try:
            self.logger.info(f"Searching GitHub issues for: {query}")
            
            sql = """
                SELECT * FROM github_issues 
                WHERE (title LIKE ? OR body LIKE ?)
            """
            params: list[object] = [f"%{query}%", f"%{query}%"]
            
            if repo:
                sql += " AND repo = ?"
                params.append(repo)
            
            if state:
                sql += " AND state = ?"
                params.append(state)
            
            if component:
                sql += " AND component = ?"
                params.append(component)
            
            if severity:
                sql += " AND severity = ?"
                params.append(severity)
            
            sql += " ORDER BY reactions_count DESC, comments_count DESC LIMIT ?"
            params.append(max_results)
            
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(sql, params) as cursor:
                    rows = await cursor.fetchall()
                    
                    # Convert to dictionaries
                    columns = [description[0] for description in cursor.description]
                    issues = []
                    
                    for row in rows:
                        issue_dict = dict(zip(columns, row))
                        # Parse JSON fields
                        issue_dict['labels'] = json.loads(issue_dict.get('labels', '[]'))
                        issue_dict['assignees'] = json.loads(issue_dict.get('assignees', '[]'))
                        issues.append(issue_dict)
                    
                    return issues
        
        except Exception as e:
            self.logger.error(f"Error searching GitHub issues: {e}")
            return []
    
    async def get_issue_solutions(self, issue_id: int) -> List[Dict[str, Any]]:
        """Get stored solutions for a specific issue."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute("""
                    SELECT * FROM issue_solutions 
                    WHERE issue_id = ? 
                    ORDER BY confidence_score DESC
                """, (issue_id,)) as cursor:
                    rows = await cursor.fetchall()
                    columns = [description[0] for description in cursor.description]
                    return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            self.logger.error(f"Error getting issue solutions: {e}")
            return []
    
    async def find_similar_issues(self, error_message: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Find similar issues based on error message or symptoms."""
        try:
            # Extract key terms from error message
            key_terms = self._extract_key_terms(error_message)
            
            if not key_terms:
                return []
            
            # Build search query - parameterized to prevent SQL injection
            clauses = ["(title LIKE ? OR body LIKE ?)"] * len(key_terms)
            params: list[object] = [v for t in key_terms for v in (f"%{t}%", f"%{t}%")]

            sql = (
                "SELECT *, (reactions_count + comments_count) as relevance_score "
                "FROM github_issues "
                "WHERE " + " OR ".join(clauses) + " "
                "AND state = 'closed' "
                "ORDER BY relevance_score DESC, updated_at DESC "
                "LIMIT ?"
            )
            params.append(max_results)

            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(sql, params) as cursor:
                    rows = await cursor.fetchall()
                    columns = [description[0] for description in cursor.description]
                    
                    issues = []
                    for row in rows:
                        issue_dict = dict(zip(columns, row))
                        issue_dict['labels'] = json.loads(issue_dict.get('labels', '[]'))
                        issue_dict['assignees'] = json.loads(issue_dict.get('assignees', '[]'))
                        issues.append(issue_dict)
                    
                    return issues
        
        except Exception as e:
            self.logger.error(f"Error finding similar issues: {e}")
            return []
    
    def _extract_key_terms(self, error_message: str) -> List[str]:
        """Extract key terms from error message for searching."""
        # Remove common noise words
        noise_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
        
        # Extract meaningful terms
        words = re.findall(r'\b\w{3,}\b', error_message.lower())
        key_terms = [word for word in words if word not in noise_words]
        
        # Also look for specific patterns
        patterns = [
            r'[A-Z][a-z]+Error',  # CamelCaseError
            r'\b\w+Exception\b',   # Exceptions
            r'\b[a-z]+-[a-z]+\b',  # hyphenated-terms
            r'\bv?\d+\.\d+\b',     # version numbers
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, error_message)
            key_terms.extend(matches)
        
        return list(set(key_terms))[:10]  # Limit and deduplicate
    
    async def get_trending_issues(self, days: int = 7, max_results: int = 15) -> List[Dict[str, Any]]:
        """Get trending issues from the last N days."""
        try:
            since_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
            
            sql = """
                SELECT *, 
                       (reactions_count * 2 + comments_count) as trend_score
                FROM github_issues 
                WHERE created_at >= ?
                ORDER BY trend_score DESC, created_at DESC
                LIMIT ?
            """
            
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(sql, (since_date, max_results)) as cursor:
                    rows = await cursor.fetchall()
                    columns = [description[0] for description in cursor.description]
                    
                    issues = []
                    for row in rows:
                        issue_dict = dict(zip(columns, row))
                        issue_dict['labels'] = json.loads(issue_dict.get('labels', '[]'))
                        issue_dict['assignees'] = json.loads(issue_dict.get('assignees', '[]'))
                        issues.append(issue_dict)
                    
                    return issues
        
        except Exception as e:
            self.logger.error(f"Error getting trending issues: {e}")
            return []
    
    async def get_issue_statistics(self) -> Dict[str, Any]:
        """Get statistics about the GitHub issues database."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                stats = {}
                
                # Total issues
                async with db.execute("SELECT COUNT(*) FROM github_issues") as cursor:
                    total = await cursor.fetchone()
                    stats['total_issues'] = total[0]
                
                # Issues by state
                async with db.execute("""
                    SELECT state, COUNT(*) FROM github_issues GROUP BY state
                """) as cursor:
                    by_state = await cursor.fetchall()
                    stats['by_state'] = dict(by_state)
                
                # Issues by severity
                async with db.execute("""
                    SELECT severity, COUNT(*) FROM github_issues GROUP BY severity
                """) as cursor:
                    by_severity = await cursor.fetchall()
                    stats['by_severity'] = dict(by_severity)
                
                # Issues by component
                async with db.execute("""
                    SELECT component, COUNT(*) FROM github_issues GROUP BY component
                    ORDER BY COUNT(*) DESC LIMIT 10
                """) as cursor:
                    by_component = await cursor.fetchall()
                    stats['top_components'] = dict(by_component)
                
                # Recent activity
                since_date = (datetime.utcnow() - timedelta(days=7)).isoformat()
                async with db.execute("""
                    SELECT COUNT(*) FROM github_issues WHERE created_at >= ?
                """, (since_date,)) as cursor:
                    recent = await cursor.fetchone()
                    stats['recent_issues'] = recent[0]
                
                return stats
        
        except Exception as e:
            self.logger.error(f"Error getting issue statistics: {e}")
            return {}
