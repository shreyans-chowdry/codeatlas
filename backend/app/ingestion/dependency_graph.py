import ast
import os
from backend.app.ingestion.chunker import _get_parser_and_chunkable
from backend.app.db.session import SessionLocal
from backend.app.db.models import DependencyEdge

def extract_imports(file_path: str, content: str, language: str) -> list[str]:
    """
    Extract imported module/file identifiers from the given file content.
    For Python, uses the ast module.
    For JS/TS, uses tree-sitter.
    """
    imports = []
    
    if language == "python":
        try:
            tree = ast.parse(content, filename=file_path)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        module_path = node.module
                        if node.level > 0:
                            # Handle relative imports
                            prefix = "." * node.level
                            module_path = prefix + module_path
                        imports.append(module_path)
                    else:
                        if node.level > 0:
                            imports.append("." * node.level)
        except Exception:
            pass  # Ignore parse errors
            
    elif language in ("javascript", "typescript"):
        parser, _ = _get_parser_and_chunkable(language)
        if parser:
            try:
                tree = parser.parse(content.encode('utf-8'))
                
                def traverse(node):
                    if node.type == 'import_statement':
                        for child in node.children:
                            if child.type == 'string':
                                val = child.text.decode('utf-8').strip("'\"")
                                imports.append(val)
                    elif node.type == 'call_expression':
                        function_node = node.child_by_field_name('function')
                        if function_node and function_node.text.decode('utf-8') == 'require':
                            args = node.child_by_field_name('arguments')
                            if args:
                                for child in args.children:
                                    if child.type == 'string':
                                        val = child.text.decode('utf-8').strip("'\"")
                                        imports.append(val)
                                        
                    for child in node.children:
                        traverse(child)
                        
                traverse(tree.root_node)
            except Exception:
                pass
                
    return imports

def _resolve_import(import_path: str, source_file_path: str, all_files_by_path: dict[str, dict]) -> str | None:
    """
    Attempts to resolve an import path to an actual file path in the repository.
    Returns the resolved path if it exists in all_files_by_path, else None.
    """
    source_dir = os.path.dirname(source_file_path)
    candidates = []

    # JS/TS style relative import
    if import_path.startswith(".") and "/" in import_path:
        resolved = os.path.normpath(os.path.join(source_dir, import_path))
        candidates.extend([
            f"{resolved}.js", f"{resolved}.ts", f"{resolved}.jsx", f"{resolved}.tsx",
            f"{resolved}/index.js", f"{resolved}/index.ts", resolved
        ])
    # Python style relative import (.module or ..module)
    elif import_path.startswith("."):
        leading_dots = len(import_path) - len(import_path.lstrip("."))
        rel_base = source_dir
        for _ in range(leading_dots - 1):
            rel_base = os.path.dirname(rel_base)
        
        rest = import_path.lstrip(".").replace(".", "/")
        resolved = os.path.normpath(os.path.join(rel_base, rest)) if rest else rel_base
        
        candidates.extend([
            f"{resolved}.py", f"{resolved}/__init__.py"
        ])
    else:
        # Absolute imports or external packages
        # JS/TS aliases or absolute paths (src/utils)
        candidates.extend([
            import_path, f"{import_path}.js", f"{import_path}.ts", f"{import_path}.jsx", f"{import_path}.tsx",
            f"{import_path}/index.js", f"{import_path}/index.ts"
        ])
        
        # Python absolute imports (app.utils.helpers)
        py_path = import_path.replace(".", "/")
        candidates.extend([
            f"{py_path}.py", f"{py_path}/__init__.py"
        ])

    for candidate in candidates:
        # Clean up any leading slashes or `./` that normpath might leave
        c = candidate.lstrip("./")
        if c in all_files_by_path:
            return c

    return None

def build_dependency_graph(repo_id: str, files: list[dict]):
    """
    Extracts imports from all files, resolves them to internal files,
    and creates DependencyEdge records in the database.
    Expects files list elements to have keys: 'path', 'language', 'content', 'id'
    """
    all_files_by_path = {f["path"]: f for f in files}
    edges_to_create = []
    
    for f in files:
        imports = extract_imports(f["path"], f.get("content", ""), f.get("language", ""))
        for imp in set(imports):
            target_path = _resolve_import(imp, f["path"], all_files_by_path)
            if target_path:
                target_file = all_files_by_path[target_path]
                edges_to_create.append({
                    "repo_id": repo_id,
                    "source_file_id": f["id"],
                    "target_file_id": target_file["id"],
                    "edge_type": "imports"
                })
                
    if edges_to_create:
        with SessionLocal() as db:
            for edge_data in edges_to_create:
                edge = DependencyEdge(**edge_data)
                db.add(edge)
            db.commit()
