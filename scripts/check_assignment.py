#!/usr/bin/env python3
"""自动验收检查脚本 —— 软件体系结构大作业

用法:
    python scripts/check_assignment.py [--project-root .] [--format both]

输出:
    docs/自动验收检查结果.md
    docs/自动验收检查结果.json
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ————————————————————————————————————————————
# 工具函数
# ————————————————————————————————————————————

def _find_files(root: Path, patterns: List[str], max_depth: int = 4) -> List[Path]:
    """在 root 下按 glob 模式查找文件, 返回匹配路径列表."""
    matches: List[Path] = []
    for depth in range(1, max_depth + 1):
        glob_expr = "/".join(["*"] * depth)
        for pattern in patterns:
            for p in root.glob(f"{glob_expr}/{pattern}"):
                if p.is_file():
                    matches.append(p)
    return list(dict.fromkeys(matches))  # 去重保序


def _read_file(path: Path) -> str:
    """读取文件内容, 编码容错."""
    for enc in ["utf-8", "gbk", "latin-1"]:
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return ""


def _grep_in_file(path: Path, pattern: str) -> bool:
    """检查文件内容是否匹配正则."""
    try:
        content = _read_file(path)
        return bool(re.search(pattern, content, re.IGNORECASE))
    except Exception:
        return False


def _count_files(root: Path, patterns: List[str], max_depth: int = 4) -> int:
    return len(_find_files(root, patterns, max_depth))


# ————————————————————————————————————————————
# 单项检查函数
# ————————————————————————————————————————————

class CheckResult:
    """单条检查结果."""
    def __init__(self, check_id: str, category: str, name: str,
                 status: str = "未检查", detail: str = "", fix: str = ""):
        self.check_id = check_id
        self.category = category
        self.name = name
        self.status = status      # 通过 / 失败 / 警告 / 未检查
        self.detail = detail
        self.fix = fix


def check_core_directories(root: Path) -> List[CheckResult]:
    """检查 1: 核心目录是否存在."""
    results = []
    categories = {
        "services/": ["services", "service", "src/services", "backend"],
        "frontend/": ["frontend", "web", "ui", "client", "src/frontend"],
        "docs/": ["docs", "doc", "documentation", "documents"],
        "tests/": ["tests", "test", "test_data", "specs"],
    }
    for label, candidates in categories.items():
        found = False
        found_dir = ""
        for c in candidates:
            p = root / c
            if p.is_dir():
                found = True
                found_dir = c
                break
        if found:
            results.append(CheckResult(
                f"DIR-{label.rstrip('/')}", "目录结构",
                f"核心目录: {label}",
                "通过",
                f"已定位到 '{found_dir}/'",
            ))
        else:
            results.append(CheckResult(
                f"DIR-{label.rstrip('/')}", "目录结构",
                f"核心目录: {label}",
                "失败",
                f"未找到匹配目录 (尝试: {', '.join(candidates)})",
                "请创建对应目录或确认命名",
            ))
    return results


def check_agent_modules(root: Path) -> List[CheckResult]:
    """检查 2: 至少 3 个 Agent 类/模块."""
    # Agent 命名模式
    agent_patterns = [
        r"class\s+\w*Agent\w*",           # class XxxAgent
        r"agent",                          # 文件名含 agent
        r"@app\.(post|get).*/(extract|match|evaluate|analyze|recommend)",
    ]

    # 收集所有可能有 Agent 的 Python 文件
    py_files: List[Path] = []
    for d in ["services", "agents", "src", "backend", "app"]:
        sd = root / d
        if sd.is_dir():
            py_files.extend(sd.rglob("*.py"))

    # 按文件路径去重
    py_files = list(dict.fromkeys(py_files))

    # 检测含 Agent 特征的文件
    agent_files: Dict[str, List[str]] = {}  # file_path -> [evidence]
    for f in py_files:
        rel = str(f.relative_to(root))
        # 跳过 __pycache__, __init__, test_
        if "__pycache__" in rel or rel.endswith("__init__.py") or "test" in rel.lower():
            continue
        content = _read_file(f)
        evidences = []
        for pat in agent_patterns:
            matches = re.findall(pat, content, re.IGNORECASE)
            for m in matches:
                # re.findall 有捕获组时返回 tuple, 无捕获组时返回 str
                text = m if isinstance(m, str) else str(m)
                evidences.append(text.strip()[:80])
        # 文件名含 agent
        if "agent" in f.name.lower():
            evidences.append(f"文件名含 agent: {f.name}")
        if evidences:
            agent_files[rel] = evidences

    count = len(agent_files)
    detail_lines = [f"检测到 {count} 个候选 Agent 文件:"]
    for fpath, ev in agent_files.items():
        detail_lines.append(f"  - {fpath} ({ev[0]})")

    if count >= 3:
        return [CheckResult(
            "AGT-COUNT", "智能体模块",
            f"Agent 数量 >= 3: 当前 {count} 个",
            "通过",
            "\n".join(detail_lines),
        )]
    elif count >= 1:
        return [CheckResult(
            "AGT-COUNT", "智能体模块",
            f"Agent 数量 >= 3: 当前仅 {count} 个",
            "警告",
            "\n".join(detail_lines),
            "需要至少 3 类 Agent (如需求解析Agent、架构匹配Agent、评估生成Agent)",
        )]
    else:
        return [CheckResult(
            "AGT-COUNT", "智能体模块",
            "Agent 数量 >= 3: 未检测到任何 Agent",
            "失败",
            "",
            "请创建 Agent 模块并在代码中暴露 /extract, /match, /evaluate 等接口",
        )]


def check_knowledge_base(root: Path) -> List[CheckResult]:
    """检查 3: 知识库 >= 10 种架构风格."""
    results = []
    # 查找架构风格数据文件
    candidates = _find_files(root, [
        "architecture_styles.json", "styles.json", "architectures.json",
        "knowledge.json", "styles.yaml", "architectures.yaml",
        "styles.py", "architectures.py", "knowledge_graph*",
    ])

    styles_found = 0
    styles_names: List[str] = []
    source_file = ""

    for f in candidates:
        rel = str(f.relative_to(root))
        content = _read_file(f)
        if not content:
            continue
        # JSON
        if f.suffix == ".json":
            try:
                data = json.loads(content)
                if isinstance(data, dict):
                    for key in ["styles", "architectures", "architectural_styles", "data"]:
                        if key in data and isinstance(data[key], list):
                            styles_found = len(data[key])
                            styles_names = [s.get("name", s if isinstance(s, str) else "?") for s in data[key]]
                            source_file = rel
                            break
                elif isinstance(data, list):
                    styles_found = len(data)
                    styles_names = [s.get("name", s if isinstance(s, str) else "?") for s in data]
                    source_file = rel
            except json.JSONDecodeError:
                pass
        # Python 模块
        elif f.suffix == ".py":
            # 找列表/字典中的风格定义
            name_matches = re.findall(r'"name"\s*:\s*"([^"]+)"', content)
            if len(name_matches) >= 5:
                styles_found = len(name_matches)
                styles_names = name_matches
                source_file = rel
        # YAML
        elif f.suffix in (".yaml", ".yml"):
            names = re.findall(r"name\s*:\s*(.+)", content)
            if len(names) >= 5:
                styles_found = len(names)
                styles_names = [n.strip().strip('"').strip("'") for n in names]
                source_file = rel

        if styles_found >= 5:
            break  # 找到足够数据即停止

    if styles_found >= 10:
        results.append(CheckResult(
            "KB-COUNT", "知识库模块",
            f"架构风格数量 >= 10: 当前 {styles_found} 种",
            "通过",
            f"来源: {source_file}\n风格列表: {', '.join(styles_names[:15])}",
        ))
    elif styles_found >= 5:
        results.append(CheckResult(
            "KB-COUNT", "知识库模块",
            f"架构风格数量 >= 10: 当前仅 {styles_found} 种",
            "警告",
            f"来源: {source_file}\n现有: {', '.join(styles_names)}",
            f"请补充至 10 种以上 (缺 {10 - styles_found} 种)",
        ))
    else:
        results.append(CheckResult(
            "KB-COUNT", "知识库模块",
            f"架构风格数量 >= 10: 未找到或数量不足 (找到 {styles_found} 种)",
            "失败",
            f"来源: {source_file or '无'}",
            "请创建 knowledge_base/data/architecture_styles.json 文件, 包含 >= 10 种架构风格",
        ))

    # 检查每种风格是否含必填字段
    if styles_found >= 10:
        required_fields = ["name", "pros", "cons", "best_for"]
        missing = []
        content = _read_file(root / source_file) if source_file else ""
        if content and source_file.endswith(".json"):
            try:
                data = json.loads(content)
                items = data.get("styles", data if isinstance(data, list) else [])
                for i, item in enumerate(items):
                    if isinstance(item, dict):
                        lacks = [f for f in required_fields if f not in item]
                        if lacks:
                            name = item.get("name", f"#{i}")
                            missing.append(f"  - {name}: 缺少 {'/'.join(lacks)}")
            except json.JSONDecodeError:
                pass
        if missing:
            results.append(CheckResult(
                "KB-FIELDS", "知识库模块",
                "每种风格包含必填字段 (name, pros, cons, best_for)",
                "警告",
                "\n".join(missing[:10]),
                "请为上述风格补充缺失字段",
            ))
        else:
            results.append(CheckResult(
                "KB-FIELDS", "知识库模块",
                "每种风格包含必填字段 (name, pros, cons, best_for)",
                "通过",
                f"{styles_found} 种风格字段完整",
            ))

    return results


def check_test_dataset(root: Path) -> List[CheckResult]:
    """检查 4: 测试数据集 >= 20 个需求场景."""
    candidates = _find_files(root, [
        "requirements_cases.json", "test_cases.json", "cases.json",
        "dataset.json", "scenarios.json", "test_data.json",
        "requirements*.json", "test*.json",
    ])

    results = []
    case_count = 0
    source_file = ""
    case_examples: List[str] = []

    for f in candidates:
        rel = str(f.relative_to(root))
        content = _read_file(f)
        if not content:
            continue
        try:
            data = json.loads(content)
            if isinstance(data, list):
                case_count = len(data)
                source_file = rel
                for item in data[:5]:
                    req = item.get("requirement", item.get("text", item.get("input", str(item))))
                    case_examples.append(str(req)[:80])
                break
            elif isinstance(data, dict):
                for key in ["cases", "scenarios", "requirements", "items", "data"]:
                    if key in data and isinstance(data[key], list):
                        case_count = len(data[key])
                        source_file = rel
                        for item in data[key][:5]:
                            req = item.get("requirement", item.get("text", str(item)))
                            case_examples.append(str(req)[:80])
                        break
                if case_count:
                    break
        except json.JSONDecodeError:
            pass

    if case_count >= 20:
        results.append(CheckResult(
            "TEST-COUNT", "测试数据集",
            f"测试用例数量 >= 20: 当前 {case_count} 条",
            "通过",
            f"来源: {source_file}\n示例:\n" + "\n".join(f"  - {e}" for e in case_examples),
        ))
    elif case_count >= 10:
        results.append(CheckResult(
            "TEST-COUNT", "测试数据集",
            f"测试用例数量 >= 20: 当前仅 {case_count} 条",
            "警告",
            f"来源: {source_file}",
            f"请补充至 20 条以上 (缺 {20 - case_count} 条)",
        ))
    else:
        results.append(CheckResult(
            "TEST-COUNT", "测试数据集",
            f"测试用例数量 >= 20: 未找到或数量不足 (找到 {case_count} 条)",
            "失败",
            f"来源: {source_file or '无'}",
            "请在 tests/datasets/ 下创建 requirements_cases.json, 包含 >= 20 个需求场景",
        ))
    return results


def check_llm_config(root: Path) -> List[CheckResult]:
    """检查 5: LLM 调用配置."""
    results = []
    llm_env_keys = [
        "LLM_API_BASE", "LLM_API_KEY", "LLM_MODEL",
        "DEEPSEEK_API_KEY", "OPENAI_API_KEY",
        "DASHSCOPE_API_KEY", "OLLAMA_BASE_URL",
        "ANTHROPIC_API_KEY", "QWEN_API_KEY",
        "LLM_PROVIDER",
    ]

    # 检查 .env / .env.example
    env_files = list(root.glob(".env*"))
    found_keys: Dict[str, str] = {}
    for ef in env_files:
        content = _read_file(ef)
        for key in llm_env_keys:
            if re.search(rf"^{key}\s*=", content, re.MULTILINE | re.IGNORECASE):
                found_keys[key] = ef.name

    # 检查环境变量
    for key in llm_env_keys:
        if os.getenv(key):
            found_keys[key] = "环境变量"

    # 检查代码中的 LLM 调用
    llm_code_patterns = [
        r"chat/completions",           # OpenAI 兼容 API
        r"anthropic\.",                # Anthropic SDK
        r"openai\.",                   # OpenAI SDK
        r"langchain",                  # LangChain
        r"llama",                      # LlamaIndex
        r"ollama",                     # Ollama
        r"deepseek",                   # DeepSeek
        r"dashscope",                  # 通义千问 DashScope
        r"llm",                        # 通用 LLM 引用
    ]
    code_evidence: List[str] = []
    for ext in ["*.py", "*.ts", "*.js", "*.java", "*.go"]:
        for f in root.rglob(ext):
            if "__pycache__" in str(f) or "node_modules" in str(f):
                continue
            for pat in llm_code_patterns:
                if _grep_in_file(f, pat):
                    rel = str(f.relative_to(root))
                    code_evidence.append(f"  - {rel}: 匹配 '{pat}'")
                    break
            if len(code_evidence) >= 10:
                break
        if len(code_evidence) >= 10:
            break

    if found_keys:
        key_list = "\n".join(f"  - {k} (来源: {v})" for k, v in found_keys.items())
        results.append(CheckResult(
            "LLM-CONFIG", "LLM 集成",
            f"LLM API 配置: 发现 {len(found_keys)} 个密钥/地址",
            "通过",
            f"发现的配置:\n{key_list}",
        ))
    elif code_evidence:
        results.append(CheckResult(
            "LLM-CONFIG", "LLM 集成",
            "LLM 调用代码存在, 但未检测到环境配置",
            "警告",
            "代码证据:\n" + "\n".join(code_evidence[:5]),
            "请在 .env 中配置 LLM_API_BASE/LLM_API_KEY/LLM_MODEL 或对应密钥",
        ))
    else:
        results.append(CheckResult(
            "LLM-CONFIG", "LLM 集成",
            "未检测到 LLM 配置或调用代码",
            "失败",
            "",
            "请集成至少一个大语言模型 (DeepSeek/通义千问/OpenAI/Ollama)",
        ))

    # 检查代码中是否有 LLM 调用实现
    if code_evidence:
        results.append(CheckResult(
            "LLM-CODE", "LLM 集成",
            f"LLM 调用代码: 发现 {len(code_evidence)} 处匹配",
            "通过",
            "\n".join(code_evidence[:8]),
        ))
    else:
        results.append(CheckResult(
            "LLM-CODE", "LLM 集成",
            "LLM 调用代码: 未发现",
            "失败",
            "",
            "请实现 LLM 调用逻辑 (如 POST /chat/completions)",
        ))

    return results


def check_web_api(root: Path) -> List[CheckResult]:
    """检查 6: Web API 入口."""
    results = []
    api_patterns = [
        ("FastAPI/Uvicorn", r"from fastapi|import fastapi|uvicorn\.run|FastAPI\(\)", ["*.py"]),
        ("Flask", r"from flask|import flask|Flask\(__name__\)|app\.run\(", ["*.py"]),
        ("Express.js", r"express\(\)|app\.listen\(|require\('express'\)", ["*.js", "*.ts"]),
        ("Spring Boot", r"@SpringBootApplication|@RestController", ["*.java"]),
        ("Gin (Go)", r"gin\.Default\(\)|gin\.New\(\)", ["*.go"]),
    ]

    found_frameworks = []
    for fw_name, pattern, exts in api_patterns:
        for ext in exts:
            for f in root.rglob(ext):
                if "__pycache__" in str(f) or "node_modules" in str(f):
                    continue
                if _grep_in_file(f, pattern):
                    rel = str(f.relative_to(root))
                    found_frameworks.append(f"{fw_name} ({rel})")
                    break
            if found_frameworks and fw_name in found_frameworks[-1]:
                break

    # 也检查 docker-compose 或启动脚本中暴露的端口
    port_evidence = []
    for f in _find_files(root, ["docker-compose*.yml", "docker-compose*.yaml", "Makefile", "start*"]):
        content = _read_file(f)
        ports = re.findall(r'["\']?(\d{4,5})["\']?\s*:', content)
        if ports:
            port_evidence.append(f"{f.relative_to(root)}: 端口 {', '.join(set(ports))}")

    if found_frameworks:
        results.append(CheckResult(
            "API-FRAMEWORK", "Web API",
            f"API 框架: 检测到 {len(found_frameworks)} 个框架",
            "通过",
            "\n".join(f"  - {fw}" for fw in found_frameworks),
        ))
    else:
        results.append(CheckResult(
            "API-FRAMEWORK", "Web API",
            "Web API 框架: 未检测到",
            "失败",
            "",
            "请使用 FastAPI/Flask/Express/Spring Boot 等框架实现 Web API",
        ))

    # 检查是否有 /api 路由
    api_routes = []
    for f in root.rglob("*.py"):
        if "__pycache__" in str(f):
            continue
        content = _read_file(f)
        for m in re.finditer(r'@app\.(get|post|put|delete|patch)\("([^"]+)"\)', content):
            route = m.group(2)
            api_routes.append(f"{str(f.relative_to(root))}: {m.group(1).upper()} {route}")

    if api_routes:
        results.append(CheckResult(
            "API-ROUTES", "Web API",
            f"API 路由: 发现 {len(api_routes)} 个端点",
            "通过",
            "\n".join(f"  - {r}" for r in api_routes[:12]),
        ))
    else:
        results.append(CheckResult(
            "API-ROUTES", "Web API",
            "API 路由: 未发现",
            "警告",
            "",
            "请确保有对外暴露的 Web API 端点",
        ))

    return results


def check_visualization(root: Path) -> List[CheckResult]:
    """检查 7: 可视化页面."""
    results = []
    viz_files = _find_files(root, [
        "index.html", "*.html", "*.jsx", "*.tsx", "*.vue",
        "App.js", "App.tsx", "main.js", "main.tsx",
    ])

    # 排除 node_modules
    viz_files = [f for f in viz_files if "node_modules" not in str(f)]

    if not viz_files:
        results.append(CheckResult(
            "VIZ-PAGE", "可视化模块",
            "前端页面文件: 未找到",
            "失败",
            "",
            "请创建前端页面展示对比矩阵和拓扑图",
        ))
        return results

    results.append(CheckResult(
        "VIZ-PAGE", "可视化模块",
        f"前端页面文件: 发现 {len(viz_files)} 个",
        "通过",
        "\n".join(f"  - {f.relative_to(root)}" for f in viz_files[:8]),
    ))

    # 检查可视化库
    viz_libs = [
        ("Mermaid.js", r"mermaid"),
        ("D3.js", r"d3\.js|d3@|from ['\"]d3['\"]"),
        ("ECharts", r"echarts"),
        ("React Flow", r"reactflow|react-flow"),
        ("Graphviz", r"graphviz|dot\s+languages?"),
        ("Chart.js", r"chart\.js|chartjs"),
        ("Cytoscape", r"cytoscape"),
    ]
    found_libs = []
    for f in viz_files + list(root.rglob("*.css")):
        content = _read_file(f)
        for lib_name, pattern in viz_libs:
            if lib_name not in found_libs and re.search(pattern, content, re.IGNORECASE):
                found_libs.append(lib_name)

    if found_libs:
        results.append(CheckResult(
            "VIZ-LIB", "可视化模块",
            f"图形库: 检测到 {', '.join(found_libs)}",
            "通过",
            f"使用的图形库: {', '.join(found_libs)}",
        ))
    else:
        results.append(CheckResult(
            "VIZ-LIB", "可视化模块",
            "图形库: 未检测到",
            "警告",
            "",
            "建议集成 Mermaid.js / D3.js / ECharts 等图形库渲染拓扑图",
        ))

    # 检查对比矩阵相关 UI: 遍历所有 HTML/JS/PY 文件
    matrix_matches = False
    topo_matches = False
    for f in list(root.rglob("*.html")) + list(root.rglob("*.js")) + list(root.rglob("*.py")):
        if "__pycache__" in str(f) or "node_modules" in str(f):
            continue
        content = _read_file(f)
        if re.search(r"对比矩阵|comparison.*matrix|matrix.*table|架构.*对比", content, re.IGNORECASE):
            matrix_matches = True
        if re.search(r"拓扑|topology|topo|架构图|architecture.*diagram", content, re.IGNORECASE):
            topo_matches = True

    if matrix_matches:
        results.append(CheckResult(
            "VIZ-MATRIX", "可视化模块",
            "对比矩阵界面: 已发现",
            "通过",
            "代码中含对比矩阵相关关键词",
        ))
    else:
        results.append(CheckResult(
            "VIZ-MATRIX", "可视化模块",
            "对比矩阵界面: 未发现",
            "警告",
            "",
            "请在前端增加架构风格对比矩阵展示",
        ))

    if topo_matches:
        results.append(CheckResult(
            "VIZ-TOPO", "可视化模块",
            "架构拓扑图渲染: 已发现",
            "通过",
            "代码中含拓扑图相关关键词",
        ))
    else:
        results.append(CheckResult(
            "VIZ-TOPO", "可视化模块",
            "架构拓扑图渲染: 未发现",
            "警告",
            "",
            "请在前端增加架构拓扑图渲染 (Mermaid/D3/ECharts)",
        ))

    return results


def check_neo4j_integration(root: Path) -> List[CheckResult]:
    """检查 9: Neo4j 知识图谱存储."""
    results = []
    dc_file = root / "docker-compose.yml"
    dc_content = _read_file(dc_file) if dc_file.exists() else ""

    neo4j_in_dc = "neo4j" in dc_content.lower() and "image:" in dc_content.lower()
    results.append(CheckResult(
        "NEO4J-DC", "Neo4j 图谱存储",
        "docker-compose.yml 中含 Neo4j 服务",
        "通过" if neo4j_in_dc else "失败",
        f"{'已' if neo4j_in_dc else '未'}检测到 neo4j 容器定义",
        "" if neo4j_in_dc else "请在 docker-compose.yml 中添加 neo4j 服务",
    ))

    neo4j_driver_ref = any(
        _grep_in_file(f, r"from neo4j|import neo4j|GraphDatabase\.driver")
        for f in root.rglob("*.py") if "__pycache__" not in str(f)
    )
    results.append(CheckResult(
        "NEO4J-CODE", "Neo4j 图谱存储",
        "代码中含 neo4j Python Driver 引用",
        "通过" if neo4j_driver_ref else "警告",
        f"{'已' if neo4j_driver_ref else '未'}在 Python 代码中检测到 neo4j 导入",
    ))

    neo4j_in_req = any(
        "neo4j" in _read_file(f).lower()
        for f in _find_files(root, ["requirements*.txt"])
    )
    results.append(CheckResult(
        "NEO4J-REQ", "Neo4j 图谱存储",
        "requirements.txt 中含 neo4j 依赖",
        "通过" if neo4j_in_req else "警告",
        f"{'已' if neo4j_in_req else '未'}检测到 neo4j 包依赖",
    ))

    has_init_script = any(
        "init_neo4j" in f.name.lower()
        for f in root.rglob("*.py")
    )
    results.append(CheckResult(
        "NEO4J-INIT", "Neo4j 图谱存储",
        "存在 Neo4j 初始化脚本",
        "通过" if has_init_script else "警告",
        f"{'已' if has_init_script else '未'}检测到 init_neo4j 脚本",
    ))

    has_json_fallback = any(
        _grep_in_file(f, r"json.*fallback|fallback.*json|KNOWLEDGE_BACKEND")
        for f in root.rglob("*.py") if "__pycache__" not in str(f)
    )
    results.append(CheckResult(
        "NEO4J-FALLBACK", "Neo4j 图谱存储",
        "存在 JSON fallback 机制",
        "通过" if has_json_fallback else "警告",
        f"{'已' if has_json_fallback else '未'}检测到 KNOWLEDGE_BACKEND 或 fallback 逻辑",
    ))

    return results


def check_langgraph_integration(root: Path) -> List[CheckResult]:
    """检查 10: LangChain/LangGraph Agent 协作."""
    results = []

    langgraph_req = any(
        "langgraph" in _read_file(f).lower() or "langchain" in _read_file(f).lower()
        for f in _find_files(root, ["requirements*.txt"])
    )
    results.append(CheckResult(
        "LANG-REQ", "LangGraph 编排",
        "requirements.txt 中含 langgraph/langchain 依赖",
        "通过" if langgraph_req else "警告",
        f"{'已' if langgraph_req else '未'}检测到 langgraph/langchain 包依赖",
    ))

    langgraph_code = any(
        _grep_in_file(f, r"from langgraph|import langgraph|StateGraph|langchain")
        for f in root.rglob("*.py") if "__pycache__" not in str(f)
    )
    results.append(CheckResult(
        "LANG-CODE", "LangGraph 编排",
        "代码中含 LangGraph/LangChain 引用",
        "通过" if langgraph_code else "警告",
        f"{'已' if langgraph_code else '未'}检测到 LangGraph StateGraph 或 langchain 导入",
    ))

    has_manual_fallback = any(
        _grep_in_file(f, r"manual.*fallback|_manual_orchestrate|build_workflow.*None")
        for f in root.rglob("*.py") if "__pycache__" not in str(f)
    )
    results.append(CheckResult(
        "LANG-FALLBACK", "LangGraph 编排",
        "存在手动编排 fallback",
        "通过" if has_manual_fallback else "警告",
        f"{'已' if has_manual_fallback else '未'}检测到 manual fallback 逻辑",
    ))

    return results


def check_few_shot_prompts(root: Path) -> List[CheckResult]:
    """检查 11: Few-shot Prompt Engineering."""
    results = []

    has_req_few_shot = bool(list(root.rglob("requirements_few_shot.py")))
    has_eval_few_shot = bool(list(root.rglob("evaluation_few_shot.py")))
    has_few_shot = has_req_few_shot or has_eval_few_shot

    results.append(CheckResult(
        "FEW-PROMPTS", "Few-shot Prompt",
        "存在 few-shot prompt 文件",
        "通过" if has_few_shot else "失败",
        f"需求: {'有' if has_req_few_shot else '无'}, 评估: {'有' if has_eval_few_shot else '无'}",
        "" if has_few_shot else "请创建 services/common/prompts/ 下的 few-shot 文件",
    ))

    # 检查 prompt 中是否含示例
    few_shot_examples = any(
        _grep_in_file(f, r"示例\d|EXAMPLE|few.shot|build_few_shot_prompt")
        for f in root.rglob("*.py") if "few_shot" in str(f).lower()
    )
    results.append(CheckResult(
        "FEW-EXAMPLES", "Few-shot Prompt",
        "few-shot 文件中含足够示例",
        "通过" if few_shot_examples else "警告",
        f"{'已' if few_shot_examples else '未'}检测到示例标记",
    ))

    # 检查 requirements 和 evaluation agent 是否引用 few-shot
    uses_few_shot = any(
        _grep_in_file(f, r"few_shot|build_few_shot_prompt")
        for f in root.rglob("*.py")
        if "main.py" in str(f) and ("requirements" in str(f) or "evaluation" in str(f))
        and "__pycache__" not in str(f)
    )
    results.append(CheckResult(
        "FEW-INTEGRATION", "Few-shot Prompt",
        "Agent 代码中集成了 few-shot prompt",
        "通过" if uses_few_shot else "警告",
        f"{'已' if uses_few_shot else '未'}在 Agent 主代码中检测到 few-shot 调用",
    ))

    return results


def check_cache_module(root: Path) -> List[CheckResult]:
    """检查 12: LLM 结果缓存."""
    results = []

    has_cache_code = any(
        _grep_in_file(f, r"cache_get|cache_set|cache_key|simple_cache|sqlite_cache|CACHE_ENABLED")
        for f in root.rglob("*.py") if "__pycache__" not in str(f)
    )
    results.append(CheckResult(
        "CACHE-CODE", "LLM 缓存",
        "存在缓存模块代码",
        "通过" if has_cache_code else "失败",
        f"{'已' if has_cache_code else '未'}检测到缓存实现",
    ))

    has_cache_endpoint = any(
        _grep_in_file(f, r"/cache/stats|/cache/clear")
        for f in root.rglob("*.py") if "__pycache__" not in str(f)
    )
    results.append(CheckResult(
        "CACHE-API", "LLM 缓存",
        "存在 /cache/stats 接口",
        "通过" if has_cache_endpoint else "警告",
        f"{'已' if has_cache_endpoint else '未'}检测到缓存管理端点",
    ))

    has_cache_hit = any(
        _grep_in_file(f, r"cache_hit")
        for f in root.rglob("*.py") if "__pycache__" not in str(f)
    )
    results.append(CheckResult(
        "CACHE-HIT", "LLM 缓存",
        "响应中含 cache_hit 字段",
        "通过" if has_cache_hit else "警告",
        f"{'已' if has_cache_hit else '未'}检测到 cache_hit 响应字段",
    ))

    return results


def check_adr_module(root: Path) -> List[CheckResult]:
    """检查 13: ADR 架构决策溯源."""
    results = []

    has_adr_code = any(
        _grep_in_file(f, r"ADRPayload|add_adr|get_adr|adr_records\.json")
        for f in root.rglob("*.py") if "__pycache__" not in str(f)
    )
    results.append(CheckResult(
        "ADR-CODE", "ADR 溯源",
        "存在 ADR 存储代码",
        "通过" if has_adr_code else "失败",
        f"{'已' if has_adr_code else '未'}检测到 ADR 实现",
    ))

    has_adr_endpoint = any(
        _grep_in_file(f, r"@app\.(get|post).*[\"']/adr")
        for f in root.rglob("*.py") if "__pycache__" not in str(f)
    )
    results.append(CheckResult(
        "ADR-API", "ADR 溯源",
        "存在 /adr 接口端点",
        "通过" if has_adr_endpoint else "警告",
        f"{'已' if has_adr_endpoint else '未'}检测到 ADR API 端点",
    ))

    has_adr_response = any(
        _grep_in_file(f, r"adr_id|adr_status|adr_summary")
        for f in root.rglob("*.py") if "__pycache__" not in str(f)
    )
    results.append(CheckResult(
        "ADR-RESP", "ADR 溯源",
        "推荐响应中含 adr 字段",
        "通过" if has_adr_response else "警告",
        f"{'已' if has_adr_response else '未'}检测到 adr_id/adr_status 响应字段",
    ))

    return results


def check_combination_recommendation(root: Path) -> List[CheckResult]:
    """检查 14: 架构模式组合推荐."""
    results = []

    has_combo_data = bool(list(root.rglob("architecture_combinations.json")))
    has_combo_code = any(
        _grep_in_file(f, r"combo_matcher|combination_candidates|score_combination|rank_combinations")
        for f in root.rglob("*.py") if "__pycache__" not in str(f)
    )
    has_combo = has_combo_data or has_combo_code

    results.append(CheckResult(
        "COMBO-DATA", "组合推荐",
        "存在组合模式数据/代码",
        "通过" if has_combo else "失败",
        f"数据: {'有' if has_combo_data else '无'}, 代码: {'有' if has_combo_code else '无'}",
    ))

    has_combo_response = any(
        _grep_in_file(f, r"recommended_combination|combination_candidates")
        for f in root.rglob("*.py") if "__pycache__" not in str(f)
    )
    results.append(CheckResult(
        "COMBO-RESP", "组合推荐",
        "响应中含 recommended_combination",
        "通过" if has_combo_response else "警告",
        f"{'已' if has_combo_response else '未'}检测到组合推荐响应字段",
    ))

    return results


def check_refactoring_agent(root: Path) -> List[CheckResult]:
    """检查 15: 架构重构建议模块."""
    results = []

    has_refactor_svc = (root / "services" / "refactoring_agent" / "app" / "main.py").exists()
    results.append(CheckResult(
        "REFAC-SVC", "重构建议",
        "存在 refactoring-agent 微服务",
        "通过" if has_refactor_svc else "失败",
        f"{'已' if has_refactor_svc else '未'}检测到 refactoring_agent/main.py",
    ))

    dc_file = root / "docker-compose.yml"
    dc_content = _read_file(dc_file) if dc_file.exists() else ""
    refactor_in_dc = "refactoring-agent" in dc_content.lower()
    results.append(CheckResult(
        "REFAC-DC", "重构建议",
        "docker-compose.yml 中含 refactoring-agent",
        "通过" if refactor_in_dc else "警告",
        f"{'已' if refactor_in_dc else '未'}在编排中检测到 refactoring-agent",
    ))

    has_refactor_code = any(
        _grep_in_file(f, r"refactoring_advice|refactoring_needed|migration_steps|detect_smells")
        for f in root.rglob("*.py") if "__pycache__" not in str(f)
    )
    results.append(CheckResult(
        "REFAC-CODE", "重构建议",
        "含重构检测和建议生成代码",
        "通过" if has_refactor_code else "警告",
        f"{'已' if has_refactor_code else '未'}检测到重构建议逻辑",
    ))

    return results


def build_tech_compliance_table(all_results: List[CheckResult]) -> str:
    """生成技术建议符合度表."""
    tech_checks = [
        ("LLM + 知识图谱双驱动", ["LLM-CONFIG", "LLM-CODE", "NEO4J-CODE", "NEO4J-DC"]),
        ("LangChain Agent 协作", ["LANG-REQ", "LANG-CODE", "LANG-FALLBACK"]),
        ("Neo4j 图谱存储", ["NEO4J-DC", "NEO4J-CODE", "NEO4J-REQ", "NEO4J-INIT", "NEO4J-FALLBACK"]),
        ("Few-shot Prompt", ["FEW-PROMPTS", "FEW-EXAMPLES", "FEW-INTEGRATION"]),
        ("规则引擎校验", ["AGT-COUNT"]),  # score_style 已在 Agent 检查中
        ("LLM 缓存", ["CACHE-CODE", "CACHE-API", "CACHE-HIT"]),
        ("ADR 溯源", ["ADR-CODE", "ADR-API", "ADR-RESP"]),
        ("组合推荐", ["COMBO-DATA", "COMBO-RESP"]),
        ("重构建议", ["REFAC-SVC", "REFAC-DC", "REFAC-CODE"]),
    ]

    status_map = {r.check_id: r.status for r in all_results}
    lines = [
        "",
        "## 技术建议符合度",
        "",
        "| 技术建议 | 状态 | 通过/总检查数 |",
        "|---|---|---|",
    ]

    all_ok = True
    for tech_name, check_ids in tech_checks:
        passed = sum(1 for cid in check_ids if status_map.get(cid) == "通过")
        failed = sum(1 for cid in check_ids if status_map.get(cid) == "失败")
        if failed > 0:
            status_text = "⚠ 部分缺失"
            all_ok = False
        elif passed == len(check_ids):
            status_text = "✅ 已实现"
        elif passed > 0:
            status_text = "🟡 部分实现"
        else:
            status_text = "❌ 未实现"
            all_ok = False
        lines.append(f"| {tech_name} | {status_text} | {passed}/{len(check_ids)} |")

    if all_ok:
        lines.append("")
        lines.append("**所有课程技术建议均已实现!**")

    return "\n".join(lines)


def check_documentation(root: Path) -> List[CheckResult]:
    """检查 8: 文档完整性."""
    results = []
    doc_checks = [
        ("需求规格说明书", ["需求规格", "需求分析", "requirement", "spec", "specification"],
         "需求规格说明书 (含 AI 系统特有需求分析)"),
        ("架构设计文档", ["架构设计", "architecture.*design", "design.*doc", "体系结构.*设计"],
         "架构设计文档 (含微服务划分、Agent 协作、LLM 集成)"),
        ("系统测试报告", ["测试报告", "test.*report", "测试结果"],
         "系统测试报告 (含典型场景测试案例)"),
        ("答辩材料", ["答辩", "defense", "presentation", "演示", "讲稿", "PPT"],
         "答辩材料 (演示脚本/PPT/问答)"),
    ]

    for label, keywords, requirement in doc_checks:
        found = False
        file_paths = []
        for f in root.rglob("*"):
            if f.is_file() and f.suffix.lower() in (".md", ".pdf", ".docx", ".pptx", ".txt", ".rst"):
                fname = f.name.lower()
                content_lower = _read_file(f).lower() if f.suffix == ".md" else fname
                for kw in keywords:
                    if kw.lower() in fname or kw.lower() in content_lower[:2000]:
                        found = True
                        file_paths.append(str(f.relative_to(root)))
                        break

        if found:
            results.append(CheckResult(
                f"DOC-{label[:4].upper()}",
                "文档与答辩",
                f"文档: {label}",
                "通过",
                f"匹配文件: {', '.join(file_paths[:5])}",
            ))
        else:
            results.append(CheckResult(
                f"DOC-{label[:4].upper()}",
                "文档与答辩",
                f"文档: {label}",
                "失败",
                f"未找到匹配 '{label}' 的文档 (关键词: {', '.join(keywords[:3])})",
                f"请创建 {requirement}",
            ))

    # 文档总数量
    all_docs = list(root.rglob("*"))
    doc_exts = {".md", ".pdf", ".docx", ".rst"}
    doc_count = sum(1 for f in all_docs if f.suffix.lower() in doc_exts and f.is_file())
    results.append(CheckResult(
        "DOC-COUNT", "文档与答辩",
        f"文档总数 (md/pdf/docx): {doc_count} 份",
        "通过" if doc_count >= 3 else "警告",
        f"找到 {doc_count} 份文档文件",
    ))

    return results


# ————————————————————————————————————————————
# 主流程
# ————————————————————————————————————————————

def run_all_checks(root: Path) -> List[CheckResult]:
    """运行全部检查并返回结果列表."""
    all_results: List[CheckResult] = []
    check_groups = [
        ("1. 核心目录", check_core_directories),
        ("2. Agent 模块", check_agent_modules),
        ("3. 知识库", check_knowledge_base),
        ("4. 测试数据集", check_test_dataset),
        ("5. LLM 集成", check_llm_config),
        ("6. Web API", check_web_api),
        ("7. 可视化", check_visualization),
        ("8. 文档与答辩", check_documentation),
        ("9. Neo4j 图谱", check_neo4j_integration),
        ("10. LangGraph 编排", check_langgraph_integration),
        ("11. Few-shot Prompt", check_few_shot_prompts),
        ("12. LLM 缓存", check_cache_module),
        ("13. ADR 溯源", check_adr_module),
        ("14. 组合推荐", check_combination_recommendation),
        ("15. 重构建议", check_refactoring_agent),
    ]
    for category, check_fn in check_groups:
        try:
            results = check_fn(root)
            for r in results:
                r.category = category
            all_results.extend(results)
        except Exception as exc:
            all_results.append(CheckResult(
                f"ERR-{category[:8]}", category,
                f"检查异常: {category}",
                "失败",
                f"执行 {check_fn.__name__} 时出错: {exc}",
                "请检查脚本逻辑或项目目录结构",
            ))
    return all_results


def compute_summary(results: List[CheckResult]) -> Dict[str, Any]:
    """汇总统计数据."""
    total = len(results)
    passed = sum(1 for r in results if r.status == "通过")
    failed = sum(1 for r in results if r.status == "失败")
    warnings = sum(1 for r in results if r.status == "警告")

    pass_rate = passed / total if total else 0

    # 评分预估 (与作业评分权重一致)
    category_weights = {
        "需求分析": 0.15,
        "架构设计": 0.30,
        "系统实现": 0.25,
        "测试验证": 0.15,
        "答辩表现": 0.15,
    }
    # 此处简化为: 核心功能 = 0.70, 文档 = 0.30
    core_categories = {"1. 核心目录", "2. Agent 模块", "3. 知识库", "5. LLM 集成", "6. Web API"}
    ext_categories = {"4. 测试数据集", "7. 可视化", "8. 文档与答辩"}

    core_passed = sum(1 for r in results if r.status == "通过" and r.category in core_categories)
    core_total = sum(1 for r in results if r.category in core_categories)
    ext_passed = sum(1 for r in results if r.status == "通过" and r.category in ext_categories)
    ext_total = sum(1 for r in results if r.category in ext_categories)

    core_score = (core_passed / core_total * 70) if core_total else 0
    ext_score = (ext_passed / ext_total * 30) if ext_total else 0

    return {
        "total_checks": total,
        "passed": passed,
        "failed": failed,
        "warnings": warnings,
        "pass_rate": round(pass_rate, 4),
        "estimated_score": round(core_score + ext_score, 1),
        "top_failures": [
            {"id": r.check_id, "name": r.name, "fix": r.fix}
            for r in results if r.status == "失败"
        ][:10],
    }


def render_markdown(results: List[CheckResult], summary: Dict[str, Any], root: Path) -> str:
    """渲染 Markdown 报告."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"# 自动验收检查结果",
        "",
        f"**检查时间:** {now}  ",
        f"**项目路径:** `{root.resolve()}`  ",
        f"**检查项数:** {summary['total_checks']}  ",
        "",
        "---",
        "",
        "## 总览",
        "",
        f"| 指标 | 数值 |",
        f"|---|---|",
        f"| 通过 | **{summary['passed']}** |",
        f"| 失败 | **{summary['failed']}** |",
        f"| 警告 | **{summary['warnings']}** |",
        f"| 通过率 | **{summary['pass_rate']:.1%}** |",
        f"| 估计得分 | **{summary['estimated_score']} / 100** |",
        "",
        "---",
        "",
    ]

    # 按类别分组输出
    current_category = ""
    for r in results:
        if r.category != current_category:
            current_category = r.category
            lines.append(f"## {current_category}")
            lines.append("")
            lines.append("| 状态 | 检查项 | 详情 |")
            lines.append("|---|---|---|")

        icon = {"通过": "[OK]", "失败": "[FAIL]", "警告": "[WARN]", "未检查": "[-]"}.get(r.status, "[-]")
        lines.append(f"| {icon} {r.status} | {r.name} | {r.detail[:200]} |")

    # 技术建议符合度表
    lines.append(build_tech_compliance_table(results))
    lines.append("")

    # 失败项汇总
    failures = [r for r in results if r.status == "失败"]
    if failures:
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## 需修复项")
        lines.append("")
        for i, f in enumerate(failures, 1):
            lines.append(f"### {i}. {f.name}")
            lines.append(f"**修复建议:** {f.fix}")
            if f.detail:
                lines.append(f"")
                lines.append(f"详情: {f.detail[:300]}")
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(f"*本报告由 `scripts/check_assignment.py` 自动生成*")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="软件体系结构大作业 —— 自动验收检查",
    )
    parser.add_argument(
        "--project-root", default=".",
        help="项目根目录 (默认当前目录)",
    )
    parser.add_argument(
        "--format", choices=["md", "json", "both"], default="both",
        help="输出格式 (默认 both)",
    )
    parser.add_argument(
        "--out-md", default="docs/自动验收检查结果.md",
        help="Markdown 输出路径",
    )
    parser.add_argument(
        "--out-json", default="docs/自动验收检查结果.json",
        help="JSON 输出路径",
    )
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    if not root.is_dir():
        print(f"错误: 项目根目录不存在: {root}")
        sys.exit(1)

    print(f"[*] 开始检查项目: {root}")
    print(f"    共 15 大检查类别 (含课程技术建议) ")
    print()

    # 运行所有检查
    results = run_all_checks(root)
    summary = compute_summary(results)

    # 终端输出
    for r in results:
        icon = {"通过": "[OK]", "失败": "[!!]", "警告": "[??]", "未检查": "[--]"}.get(r.status, "[--]")
        print(f"  {icon} {r.name}: {r.status}")

    print()
    print(f"  总计: {summary['total_checks']} 项")
    print(f"  通过: {summary['passed']} | 失败: {summary['failed']} | 警告: {summary['warnings']}")
    print(f"  通过率: {summary['pass_rate']:.1%}")
    print(f"  估计得分: {summary['estimated_score']}/100")
    print()

    # 写入输出文件
    if args.format in ("md", "both"):
        md_path = root / args.out_md
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_content = render_markdown(results, summary, root)
        md_path.write_text(md_content, encoding="utf-8")
        print(f"[MD] Markdown 报告: {md_path}")

    if args.format in ("json", "both"):
        json_path = root / args.out_json
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_output = {
            "check_time": datetime.now().isoformat(timespec="seconds"),
            "project_root": str(root),
            "summary": summary,
            "results": [
                {
                    "id": r.check_id,
                    "category": r.category,
                    "name": r.name,
                    "status": r.status,
                    "detail": r.detail,
                    "fix": r.fix,
                }
                for r in results
            ],
        }
        json_path.write_text(
            json.dumps(json_output, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[JSON] JSON 报告: {json_path}")

    # 如果有失败项, 退出码非零
    if summary["failed"] > 0:
        print(f"\n[WARN] 有 {summary['failed']} 个检查项未通过, 请查看报告修复。")
        sys.exit(1)
    else:
        print("\n[PASS] 所有检查项通过!")


if __name__ == "__main__":
    main()
