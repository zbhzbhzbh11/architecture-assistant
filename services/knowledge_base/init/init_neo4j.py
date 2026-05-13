"""Neo4j 知识图谱初始化脚本.

从 services/knowledge_base/data/architecture_styles.json 读取 10 种风格,
创建以下节点和关系:

节点:
  - ArchitectureStyle: 架构风格 (name, name_zh, topology_mermaid, pros, cons, ...)
  - QualityAttribute: 质量属性/特征标签 (name)
  - Scenario: 适用场景 (name)
  - Risk: 风险点 (name)

关系:
  - HAS_QUALITY:  (Style)-[:HAS_QUALITY]->(QualityAttribute)
  - SUITABLE_FOR: (Style)-[:SUITABLE_FOR]->(Scenario)
  - HAS_RISK:     (Style)-[:HAS_RISK]->(Risk)
  - COMPLEMENTS:  (Style)-[:COMPLEMENTS]->(Style)  双向互补关系

用法:
  python init/init_neo4j.py

环境变量:
  NEO4J_URI      (默认 bolt://localhost:7687)
  NEO4J_USER     (默认 neo4j)
  NEO4J_PASSWORD (默认 neo4jneo4j)
"""

import json
import os
import sys
from pathlib import Path

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "neo4jneo4j")

# 互补关系定义: 哪些风格经常组合使用
COMPLEMENTS_MAP = {
    "CQRS": ["Event-Driven Architecture"],
    "Event-Driven Architecture": ["CQRS", "Microservices"],
    "Microservices": ["Event-Driven Architecture", "Hexagonal Architecture"],
    "Hexagonal Architecture": ["Microservices", "Layered Architecture"],
    "Layered Architecture": ["Hexagonal Architecture"],
    "Pipeline-Filter": ["Event-Driven Architecture"],
}

# 各风格的主要风险 (与 evaluation_agent 的 STYLE_RISK_MAP 一致)
STYLE_RISK_MAP = {
    "Event-Driven Architecture": [
        "事件溯源实现复杂度高，调试困难",
        "事件一致性设计难度大，需额外处理幂等与乱序",
        "分布式链路追踪和监控成本较高",
    ],
    "Microservices": [
        "分布式系统复杂度高，事务一致性难保障",
        "服务间通信延迟和网络故障风险增大",
        "运维成本高，需完善CI/CD和容器编排",
    ],
    "Layered Architecture": [
        "跨层调用带来性能开销，高并发场景可能成为瓶颈",
        "层级耦合可能导致变更影响面大",
        "横向扩展能力有限，不适合极端流量场景",
    ],
}


def load_styles() -> list:
    data_path = Path(__file__).resolve().parent.parent / "data" / "architecture_styles.json"
    with open(data_path, "r", encoding="utf-8") as f:
        return json.load(f)["styles"]


def init_graph():
    try:
        from neo4j import GraphDatabase
    except ImportError:
        print("ERROR: neo4j package not installed. Run: pip install neo4j")
        sys.exit(1)

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        driver.verify_connectivity()
    except Exception as e:
        print(f"ERROR: Cannot connect to Neo4j at {NEO4J_URI}: {e}")
        sys.exit(1)

    print(f"Connected to Neo4j at {NEO4J_URI}")

    styles = load_styles()
    print(f"Loaded {len(styles)} styles from architecture_styles.json")

    with driver.session() as session:
        # 清空现有数据
        session.run("MATCH (n) DETACH DELETE n")
        print("Cleared existing graph data.")

        # ── 创建架构风格节点 + 关联 ──
        for style in styles:
            name = style["name"]
            name_zh = style.get("name_zh", name)
            topo = style.get("topology_mermaid", "")
            pros = style.get("pros", [])
            pros_zh = style.get("pros_zh", [])
            cons = style.get("cons", [])
            cons_zh = style.get("cons_zh", [])
            tags = style.get("tags", [])
            best_for = style.get("best_for", [])

            # 创建 ArchitectureStyle 节点
            session.run("""
                CREATE (s:ArchitectureStyle {
                    name: $name,
                    name_zh: $name_zh,
                    topology_mermaid: $topo,
                    pros: $pros,
                    pros_zh: $pros_zh,
                    cons: $cons,
                    cons_zh: $cons_zh
                })
            """, {
                "name": name, "name_zh": name_zh, "topo": topo,
                "pros": pros, "pros_zh": pros_zh,
                "cons": cons, "cons_zh": cons_zh,
            })

            # 创建 QualityAttribute 节点 + HAS_QUALITY 关系
            for tag in tags:
                session.run("""
                    MERGE (q:QualityAttribute {name: $tag})
                    WITH q
                    MATCH (s:ArchitectureStyle {name: $style_name})
                    MERGE (s)-[:HAS_QUALITY]->(q)
                """, {"tag": tag, "style_name": name})

            # 创建 Scenario 节点 + SUITABLE_FOR 关系
            for scenario in best_for:
                session.run("""
                    MERGE (sc:Scenario {name: $scenario})
                    WITH sc
                    MATCH (s:ArchitectureStyle {name: $style_name})
                    MERGE (s)-[:SUITABLE_FOR]->(sc)
                """, {"scenario": scenario, "style_name": name})

            # 创建 Risk 节点 + HAS_RISK 关系
            risks = STYLE_RISK_MAP.get(name, [])
            for risk_text in risks:
                session.run("""
                    MERGE (r:Risk {name: $risk})
                    WITH r
                    MATCH (s:ArchitectureStyle {name: $style_name})
                    MERGE (s)-[:HAS_RISK]->(r)
                """, {"risk": risk_text, "style_name": name})

            print(f"  [+] {name} ({len(tags)} qualities, {len(best_for)} scenarios, {len(risks)} risks)")

        # ── 创建互补关系 ──
        for style_name, complements in COMPLEMENTS_MAP.items():
            for target in complements:
                session.run("""
                    MATCH (a:ArchitectureStyle {name: $a})
                    MATCH (b:ArchitectureStyle {name: $b})
                    MERGE (a)-[:COMPLEMENTS]->(b)
                """, {"a": style_name, "b": target})

        # ── 统计 ──
        node_count = session.run("MATCH (n) RETURN count(n) AS cnt").single()["cnt"]
        rel_count = session.run("MATCH ()-[r]->() RETURN count(r) AS cnt").single()["cnt"]

    driver.close()
    print(f"\nInit complete: {node_count} nodes, {rel_count} relationships created.")
    print("Graph is ready for use.")


if __name__ == "__main__":
    init_graph()
