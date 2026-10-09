"""Guardian may depend only on its domain and Python standard library."""
import ast
from pathlib import Path
import sys

def test_dependency_boundary():
    root=Path(__file__).resolve().parents[2]
    for filename in ('decision/models/guardian.py','decision/services/guardian_service.py'):
        tree=ast.parse((root/filename).read_text())
        imports=[]
        for node in ast.walk(tree):
            if isinstance(node,ast.Import): imports.extend(n.name for n in node.names)
            elif isinstance(node,ast.ImportFrom): imports.append(node.module or '')
        assert all(name.split('.')[0] in sys.stdlib_module_names or name=='decision.models.guardian' for name in imports)
        assert not any(isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in ('open','__import__','eval','exec') for node in ast.walk(tree))
