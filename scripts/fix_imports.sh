#!/bin/bash
# Fix all relative imports to absolute imports in src directory

echo "Fixing relative imports to absolute imports..."

# Fix main.py
sed -i '' 's/from \.mcp_server import/from mcp_server import/g' src/main.py
sed -i '' 's/from \.config import/from config import/g' src/main.py  
sed -i '' 's/from \.logger import/from logger import/g' src/main.py

# Fix mcp_server.py
sed -i '' 's/from \.config import/from config import/g' src/mcp_server.py
sed -i '' 's/from \.k8s_manager import/from k8s_manager import/g' src/mcp_server.py
sed -i '' 's/from \.diagnostics_manager import/from diagnostics_manager import/g' src/mcp_server.py
sed -i '' 's/from \.monitoring_manager import/from monitoring_manager import/g' src/mcp_server.py
sed -i '' 's/from \.security_manager import/from security_manager import/g' src/mcp_server.py
sed -i '' 's/from \.documentation_manager import/from documentation_manager import/g' src/mcp_server.py
sed -i '' 's/from \.github_issues_manager import/from github_issues_manager import/g' src/mcp_server.py
sed -i '' 's/from \.kubectl_manager import/from kubectl_manager import/g' src/mcp_server.py
sed -i '' 's/from \.helm_manager import/from helm_manager import/g' src/mcp_server.py
sed -i '' 's/from \.logger import/from logger import/g' src/mcp_server.py

# Fix other files
sed -i '' 's/from \.config import/from config import/g' src/k8s_manager.py
sed -i '' 's/from \.logger import/from logger import/g' src/k8s_manager.py

sed -i '' 's/from \.config import/from config import/g' src/diagnostics_manager.py
sed -i '' 's/from \.logger import/from logger import/g' src/diagnostics_manager.py

sed -i '' 's/from \.config import/from config import/g' src/documentation_manager.py
sed -i '' 's/from \.logger import/from logger import/g' src/documentation_manager.py

sed -i '' 's/from \.config import/from config import/g' src/github_issues_manager.py
sed -i '' 's/from \.logger import/from logger import/g' src/github_issues_manager.py

sed -i '' 's/from \.logger import/from logger import/g' src/helm_manager.py

# Fix any other files
find src -name "*.py" -exec sed -i '' 's/from \.config import/from config import/g' {} \;
find src -name "*.py" -exec sed -i '' 's/from \.logger import/from logger import/g' {} \;

echo "Fixed all relative imports to absolute imports"
