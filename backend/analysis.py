"""Bounded, read-only repository inventory and starter static analysis.

Never imports or executes repository code. Pass repository-relative paths and
contents fetched by the caller to analyze_repository().
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import PurePosixPath
from typing import Any, Iterable, Mapping

MAX_TREE_FILES = 12_000
MAX_SOURCE_FILES = 3_000
MAX_FILE_BYTES = 256_000
MAX_TOTAL_BYTES = 8_000_000
MAX_RELATIONSHIPS = 15_000
SKIP_DIRS = {".git", "node_modules", "vendor", "dist", "build", "coverage", ".venv", "venv", "target", "__pycache__", ".next", "bin", "out", ".gradle", "generated"}
LANGUAGES = {".ts":"TypeScript", ".tsx":"TypeScript", ".js":"JavaScript", ".jsx":"JavaScript", ".mjs":"JavaScript", ".cjs":"JavaScript", ".java":"Java", ".py":"Python", ".html":"HTML", ".css":"CSS", ".scss":"SCSS", ".json":"JSON", ".yml":"YAML", ".yaml":"YAML", ".xml":"XML", ".md":"Markdown", ".sql":"SQL", ".sh":"Shell", ".go":"Go", ".rs":"Rust", ".kt":"Kotlin", ".gradle":"Gradle", ".toml":"TOML"}
MANIFEST_NAMES = {"package.json", "package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml", "pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts", "requirements.txt", "pyproject.toml", "Pipfile", "Pipfile.lock", "poetry.lock", "go.mod", "Cargo.toml", "Gemfile", "composer.json", "Dockerfile", "docker-compose.yml", "docker-compose.yaml", "angular.json", "tsconfig.json"}

def _safe(path: str) -> bool:
    p = PurePosixPath(path)
    return not p.is_absolute() and ".." not in p.parts and not any(x in SKIP_DIRS for x in p.parts)

def _manifest(path: str, source: str) -> dict[str, Any]:
    name = PurePosixPath(path).name
    out: dict[str, Any] = {"path": path, "type": name, "dependencies": []}
    if name == "package.json":
        try:
            data = json.loads(source)
            out.update(name=data.get("name"), version=data.get("version"), scripts=sorted((data.get("scripts") or {}).keys())[:40])
            deps = {}
            for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
                deps.update(data.get(key) or {})
            out["dependencies"] = [{"name": k, "version": v} for k, v in sorted(deps.items())[:300]]
        except (ValueError, TypeError):
            out["parse_error"] = "Invalid package.json"
    elif name in {"requirements.txt", "Pipfile"}:
        deps = []
        for line in source.splitlines():
            s = line.strip()
            m = re.match(r"([A-Za-z0-9_.-]+)\s*(.*)$", s) if s and not s.startswith(("#", "-", "[")) else None
            if m: deps.append({"name": m.group(1), "version": m.group(2).strip() or None})
        out["dependencies"] = deps[:300]
    elif name in {"pom.xml", "build.gradle", "build.gradle.kts", "Cargo.toml", "go.mod", "composer.json", "pyproject.toml"}:
        out["excerpt"] = "\n".join(source.splitlines()[:80])[:5000]
        if name == "composer.json":
            try:
                data = json.loads(source)
                deps = {**(data.get("require") or {}), **(data.get("require-dev") or {})}
                out["dependencies"] = [{"name": k, "version": v} for k, v in sorted(deps.items())[:300]]
            except (ValueError, TypeError): out["parse_error"] = "Invalid composer.json"
    else:
        out["excerpt"] = "\n".join(source.splitlines()[:40])[:3000]
    return out

def _stack(paths: list[str], manifests: list[dict[str, Any]]) -> list[dict[str, str]]:
    names = {PurePosixPath(p).name for p in paths}
    ext = Counter(PurePosixPath(p).suffix.lower() for p in paths)
    packages = {d["name"].lower() for m in manifests for d in m.get("dependencies", []) if d.get("name")}
    result: list[dict[str, str]] = []
    def add(name: str, evidence: str, kind: str = "language/framework") -> None:
        if not any(x["name"] == name for x in result): result.append({"name":name,"type":kind,"evidence":evidence})
    for suffix, label in ((".ts","TypeScript"),(".tsx","TypeScript"),(".js","JavaScript"),(".jsx","JavaScript"),(".java","Java"),(".py","Python")):
        if ext[suffix] and not any(x["name"] == label for x in result): add(label, f"{sum(ext[e] for e in ('.ts','.tsx') if label=='TypeScript') if label=='TypeScript' else ext[suffix]} source files", "language")
    if "angular.json" in names or "@angular/core" in packages: add("Angular", "angular.json or @angular/core dependency", "framework")
    for package, label in (("@nestjs/core","NestJS"),("react","React"),("vue","Vue")):
        if package in packages: add(label, f"{package} dependency", "framework")
    if any(n in names for n in ("pom.xml","build.gradle","build.gradle.kts")):
        add("Maven" if "pom.xml" in names else "Gradle", "Java build manifest", "build tool")
    if any(n in names for n in ("requirements.txt","pyproject.toml","Pipfile")): add("Python packaging", "Python dependency manifest", "build tool")
    for m in manifests:
        if "spring-boot" in m.get("excerpt", "").lower() or any("spring-boot" in d.get("name", "").lower() for d in m.get("dependencies", [])):
            add("Spring Boot", f"Spring Boot declaration in {m['path']}", "framework"); break
    return result

def _relationships(contents: dict[str, str], paths: list[str]) -> list[dict[str, str]]:
    available = set(paths); java_types: dict[str, str] = {}; java_imports = []; edges = []
    for path, text in list(contents.items())[:MAX_SOURCE_FILES]:
        if path.endswith(".java"):
            pkg = re.search(r"(?m)^\s*package\s+([\w.]+)\s*;", text)
            type_match = re.search(r"\b(?:class|interface|enum|record)\s+(\w+)", text)
            if pkg and type_match:
                java_types[f"{pkg.group(1)}.{type_match.group(1)}"] = path
            java_imports.extend((path, x) for x in re.findall(r"(?m)^\s*import\s+(?:static\s+)?([\w.]+)\s*;", text))
    for path, text in list(contents.items())[:MAX_SOURCE_FILES]:
        if path.endswith((".ts",".tsx",".js",".jsx",".mjs",".cjs")):
            refs = re.findall(r"(?:import\s+(?:[^\n;]*?\s+from\s+)?|export\s+[^\n;]*?\s+from\s+|require\s*\()\s*[\"']([^\"']+)[\"']", text)
            for spec in refs:
                if not spec.startswith("."): continue
                base = str(PurePosixPath(path).parent / spec); base = str(PurePosixPath(base))
                candidates = [base] + [base+x for x in (".ts",".tsx",".js",".jsx",".mjs")] + [base+"/index"+x for x in (".ts",".tsx",".js",".jsx")]
                target = next((p for p in candidates if p in available), None)
                if target: edges.append({"from":path,"to":target,"kind":"imports","reference":spec})
                if len(edges) >= MAX_RELATIONSHIPS: return edges
        elif path.endswith(".java"):
            for source_path, fqcn in java_imports:
                if source_path != path: continue
                target = java_types.get(fqcn)
                if not target and fqcn.count(".") >= 2:
                    target = java_types.get(fqcn.rsplit(".", 1)[0])
                if target: edges.append({"from":path,"to":target,"kind":"java-import","reference":fqcn})
                if len(edges) >= MAX_RELATIONSHIPS: return edges
    return edges

RULES = [
    ("ts.inner-html", (".ts",".tsx",".js",".jsx"), re.compile(r"\b(?:innerHTML|outerHTML)\s*="), "high", "Potential unsafe HTML assignment", "Direct HTML assignment can create cross-site scripting when the value contains untrusted input."),
    ("ts.eval", (".ts",".tsx",".js",".jsx"), re.compile(r"\beval\s*\("), "high", "Dynamic code evaluation", "eval executes a string as code and can turn untrusted input into script execution."),
    ("ts.hardcoded-secret", (".ts",".tsx",".js",".jsx"), re.compile(r"(?i)\b(?:api[_-]?key|secret|password|access[_-]?token)\b\s*[:=]\s*[\"'][A-Za-z0-9_\-/.+=]{12,}[\"']"), "high", "Possible hard-coded credential", "A credential-like literal appears in source. Confirm whether it is real and rotate it if exposed."),
    ("java.runtime-exec", (".java",), re.compile(r"\bRuntime\s*\.\s*getRuntime\s*\(\s*\)\s*\.\s*exec\s*\("), "high", "Process execution from Java", "Runtime.exec launches an operating-system process; validate and constrain command inputs."),
    ("java.string-sql", (".java",), re.compile(r"(?i)\b(?:executeQuery|executeUpdate|execute)\s*\(\s*[\"'][^\n\"']*(?:\+|\{)"), "medium", "Possible dynamically concatenated SQL", "SQL appears assembled in an execute call. Prefer prepared statements with bound parameters."),
    ("python.eval", (".py",), re.compile(r"\b(?:eval|exec)\s*\("), "high", "Dynamic code evaluation", "eval/exec executes dynamically supplied Python code; ensure all inputs are trusted and constrained."),
    ("python.hardcoded-secret", (".py",), re.compile(r"(?i)\b(?:api[_-]?key|secret|password|access[_-]?token)\b\s*=\s*[\"'][A-Za-z0-9_\-/.+=]{12,}[\"']"), "high", "Possible hard-coded credential", "A credential-like literal appears in source. Confirm whether it is real and rotate it if exposed."),
]

def _findings(contents: dict[str, str]) -> list[dict[str, Any]]:
    findings = []
    for path, source in list(contents.items())[:MAX_SOURCE_FILES]:
        ext = PurePosixPath(path).suffix.lower()
        for number, line in enumerate(source.splitlines(), 1):
            for rule, extensions, pattern, severity, title, description in RULES:
                if ext in extensions and pattern.search(line):
                    findings.append({"category":"security","severity":severity,"rule_id":rule,"title":title,"description":description,"path":path,"line":number,"evidence":line.strip()[:500]})
                    if len(findings) >= 500: return findings
    return findings

def analyze_repository(file_contents: Mapping[str, Any], *, tree_paths: Iterable[str] | None = None, repository: str | None = None) -> dict[str, Any]:
    """Return report-ready inventory, tech stack, dependency, import and finding data.

    file_contents maps repository-relative paths to fetched UTF-8 text. tree_paths
    optionally includes the complete repository tree (even files not fetched).
    No code is run. Bounds: 12k paths, 3k sources, 256KB/file, 8MB total.
    """
    input_paths = [str(x) for x in (tree_paths if tree_paths is not None else file_contents.keys())]
    paths = sorted({p for p in input_paths if _safe(p)})[:MAX_TREE_FILES]
    content: dict[str, str] = {}; bytes_used = 0
    for raw_path, raw in file_contents.items():
        path = str(raw_path)
        if path not in paths or len(content) >= MAX_SOURCE_FILES: continue
        text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw if isinstance(raw, str) else ""
        size = len(text.encode("utf-8", "replace"))
        if size > MAX_FILE_BYTES or bytes_used + size > MAX_TOTAL_BYTES: continue
        content[path] = text; bytes_used += size
    languages = Counter(LANGUAGES[PurePosixPath(p).suffix.lower()] for p in paths if PurePosixPath(p).suffix.lower() in LANGUAGES)
    extensions = Counter(PurePosixPath(p).suffix.lower() or "[no extension]" for p in paths)
    manifests = [_manifest(p, content[p]) for p in paths if PurePosixPath(p).name in MANIFEST_NAMES and p in content]
    relationships = _relationships(content, paths); findings = _findings(content)
    directories = Counter(str(PurePosixPath(p).parent) for p in paths)
    return {
        "repository": repository,
        "tech_stack": _stack(paths, manifests),
        "inventory": {"files_total":len(paths),"files_analyzed":len(content),"bytes_analyzed":bytes_used,
                      "languages":[{"name":k,"files":v} for k,v in languages.most_common()],
                      "extensions":[{"extension":k,"files":v} for k,v in extensions.most_common(30)],
                      "top_directories":[{"path":k or ".","files":v} for k,v in directories.most_common(30)],
                      "truncated":len(input_paths)>MAX_TREE_FILES or len(content)<min(len(paths),len(file_contents))},
        "manifests":manifests,
        "dependencies":[{"manifest":m["path"],**d} for m in manifests for d in m.get("dependencies",[])],
        "relationships":relationships,"findings":findings,
        "summary":{"files_scanned":len(content),"findings":len(findings),"relationships":len(relationships),"manifests":len(manifests),"source":"bounded-static-starter-analysis"},
        "limitations":["Static heuristics can miss defects and may report false positives.","Relationships cover local TypeScript/JavaScript imports and Java package imports only.","Dependency versions are inventoried; vulnerability advisories are not checked.","No repository code, build scripts, tests, or package managers are executed."],
    }
