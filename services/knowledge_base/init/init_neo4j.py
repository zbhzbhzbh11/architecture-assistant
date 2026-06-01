"""Neo4j 知识图谱初始化脚本 — 双驱动架构 (规则引擎 + 图谱引擎).

从 architecture_styles.json 读取风格数据, 创建完整的评分图谱:

节点 (7 类):
  - ArchitectureStyle: 架构风格 (含 is_mainstream 属性)
  - QualityAttribute: 质量属性 (风格所具备的)
  - Feature: 评分特征维度 (用于 HAS_PENALTY 关系)
  - Scenario: 适用场景
  - Risk: 风险点 (含 suggestion 属性)
  - ScoringRule: 特定评分规则 (替代硬编码 if-then)
  - Feedback: 种子反馈

关系 (8 类):
  - HAS_QUALITY:  (Style)-[:HAS_QUALITY]->(QualityAttribute)
  - SUITABLE_FOR: (Style)-[:SUITABLE_FOR]->(Scenario)
  - HAS_RISK:     (Style)-[:HAS_RISK]->(Risk)
  - HAS_PENALTY:  (Feature)-[:HAS_PENALTY {weight}]->(Style)   ← 替代 JSON penalty_tags
  - COMPLEMENTS:  (Style)-[:COMPLEMENTS]->(Style)
  - LEARNED_FOR:  (Style)-[:LEARNED_FOR {weight}]->(QualityAttribute)  ← 学习权重
  - REQUIRES:     (ScoringRule)-[:REQUIRES]->(Feature)
  - APPLIES_TO:   (ScoringRule)-[:APPLIES_TO {bonus}]->(Style)

用法:
  python init/init_neo4j.py
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime as _dt

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "neo4jneo4j")

# ── 12 个特征维度 (Feature 节点) ──
FEATURE_NAMES = [
    "high_concurrency", "real_time", "reliability", "scalability",
    "complex_business", "strict_consistency", "deployment_constraint",
    "data_intensive", "team_size_large", "security",
    "simple_crud", "resource_constrained",
]

# ── HAS_PENALTY 关系 (Feature → Style, 负权重) — 替代 JSON penalty_tags ──
PENALTY_MAP = {
    "Layered Architecture": {
        "high_concurrency": -2, "real_time": -2, "data_intensive": -2,
    },
    "Microservices": {
        "simple_crud": -3, "resource_constrained": -4,
    },
    "Event-Driven Architecture": {
        "simple_crud": -3, "resource_constrained": -3,
    },
    "CQRS": {
        "simple_crud": -2, "resource_constrained": -3,
    },
    "Space-Based": {
        "resource_constrained": -4,
    },
    "Client-Server": {
        "high_concurrency": -4, "scalability": -3, "team_size_large": -4,
    },
    "Batch-Sequential": {
        "real_time": -3, "high_concurrency": -2,
    },
    "Object-Oriented Architecture": {
        "simple_crud": -2, "resource_constrained": -1,
    },
    "Repository Architecture": {
        "real_time": -2, "simple_crud": -1,
    },
    "Rule-Based Architecture": {
        "simple_crud": -2, "resource_constrained": -2, "high_concurrency": -1,
    },
}

# ── 6 条特定规则 (ScoringRule 节点) — 替代硬编码 if-then ──
SCORING_RULES = [
    {"name": "EDA高并发加成", "required": ["high_concurrency"],
     "style": "Event-Driven Architecture", "bonus": 1},
    {"name": "微服务团队协作加成", "required": ["team_size_large"],
     "style": "Microservices", "bonus": 1},
    {"name": "分层强一致性加成", "required": ["strict_consistency"],
     "style": "Layered Architecture", "bonus": 1},
    {"name": "管道实时数据流加成", "required": ["data_intensive", "real_time"],
     "style": "Pipeline-Filter", "bonus": 1},
    {"name": "CQRS高并发数据加成", "required": ["data_intensive", "high_concurrency"],
     "style": "CQRS", "bonus": 1},
    {"name": "微服务高并发强一致加成", "required": ["high_concurrency", "strict_consistency"],
     "style": "Microservices", "bonus": 1},
]

# ── 互补关系 — 补全到 10 种风格 ──
COMPLEMENTS_MAP = {
    "CQRS": ["Event-Driven Architecture", "Repository Architecture"],
    "Event-Driven Architecture": ["CQRS", "Microservices", "Pipeline-Filter", "Rule-Based Architecture"],
    "Microservices": ["Event-Driven Architecture", "Hexagonal Architecture", "SOA", "Object-Oriented Architecture", "Rule-Based Architecture"],
    "Hexagonal Architecture": ["Microservices", "Layered Architecture", "Object-Oriented Architecture"],
    "Layered Architecture": ["Hexagonal Architecture", "Client-Server"],
    "Pipeline-Filter": ["Event-Driven Architecture", "Batch-Sequential"],
    "SOA": ["Microservices"],
    "Serverless": ["Event-Driven Architecture"],
    "Space-Based": ["CQRS"],
    "Client-Server": ["Layered Architecture"],
    "Batch-Sequential": ["Pipeline-Filter"],
    "Object-Oriented Architecture": ["Hexagonal Architecture", "Microservices"],
    "Repository Architecture": ["CQRS", "Pipeline-Filter"],
    "Rule-Based Architecture": ["Microservices", "Event-Driven Architecture"],
}

# ── 风险 + 建议 (Risk 节点) ──
RISK_DATA = {
    "Event-Driven Architecture": [
        ("事件溯源实现复杂度高，调试困难", "引入消息队列（Kafka/RabbitMQ）并设置死信队列"),
        ("事件一致性设计难度大，需额外处理幂等与乱序", "建立事件Schema版本管理，保证向前兼容"),
        ("分布式链路追踪和监控成本较高", "部署分布式追踪系统（Jaeger/Zipkin）"),
    ],
    "Microservices": [
        ("分布式系统复杂度高，事务一致性难保障", "采用Saga模式处理分布式事务"),
        ("服务间通信延迟和网络故障风险增大", "引入服务网格（Istio）管理服务间通信"),
        ("运维成本高，需完善CI/CD和容器编排", "建立统一的API网关和认证授权中心"),
    ],
    "Layered Architecture": [
        ("跨层调用带来性能开销，高并发场景可能成为瓶颈", "严格遵循单向依赖，避免跨层直接调用"),
        ("层级耦合可能导致变更影响面大", "核心业务层可结合CQRS读写分离缓解性能压力"),
        ("横向扩展能力有限，不适合极端流量场景", "通过水平扩展+负载均衡提升吞吐量"),
    ],
    "SOA": [
        ("ESB总线可能成为性能瓶颈", "提前规划ESB扩容与高可用方案"),
        ("治理机制繁重增加开发开销", "定义清晰的服务契约与版本管理策略"),
        ("服务粒度划分困难容易导致过度拆分或欠拆分", "引入轻量级集成层简化通信"),
    ],
    "Hexagonal Architecture": [
        ("学习曲线较陡团队上手成本高", "从核心领域层开始逐步向外扩展"),
        ("样板代码较多增加维护负担", "通过代码生成减少端口-适配器样板代码"),
        ("简单CRUD场景存在过度设计风险", "定期评审架构边界避免抽象泄漏"),
    ],
    "Pipeline-Filter": [
        ("分布式管道调试复杂定位困难", "建立统一的结构化日志采集与追踪"),
        ("阶段间状态传递有额外性能开销", "定义标准化的阶段间数据格式减少转换开销"),
        ("单个过滤器故障可能导致级联失败", "为每个过滤器设置独立健康检查和超时熔断"),
    ],
    "CQRS": [
        ("读写模型同步复杂度高", "从单库起逐步拆分读写模型（渐进式CQRS）"),
        ("系统整体复杂度显著增加需额外维护两套模型", "引入事件溯源或CDC机制保证同步"),
        ("最终一致性窗口期可能影响用户体验", "明确标注哪些查询走最终一致性供前端处理"),
    ],
    "Serverless": [
        ("云供应商锁定风险", "抽象云厂商接口避免深度绑定"),
        ("冷启动延迟影响用户体验", "配置预置并发保持函数热启动"),
        ("执行时间限制不适合长任务，分布式函数调试困难", "混合使用容器承载长时任务仅事件触发走Serverless"),
    ],
    "Space-Based": [
        ("分布式一致性模型复杂", "配置异步写穿策略保证数据持久化"),
        ("内存成本较高不适合大规模持久化场景", "设计数据淘汰与分页策略控制内存占用"),
        ("内存中数据在持久化前存在丢失风险", "实现跨节点数据冗余降低单点风险"),
    ],
    "Client-Server": [
        ("服务器端可能成为集中式性能瓶颈", "增加负载均衡与集群化部署提升容量"),
        ("弹性扩展能力有限不适合极端并发场景", "使用CDN卸载静态资源请求减轻服务器压力"),
        ("客户端升级维护成本高", "建立客户端自动更新机制降低运维成本"),
    ],
    "Batch-Sequential": [
        ("延迟高不适合实时场景", "将批处理与实时管道结合形成Lambda架构"),
        ("中间数据存储占用大，磁盘IO可能成为瓶颈", "使用列式存储格式减少IO开销"),
        ("某步骤失败可能导致全量重跑耗时长", "建立步骤级断点续传和增量处理机制"),
    ],
    "Object-Oriented Architecture": [
        ("设计复杂度高，继承层次过深难以维护", "遵循组合优于继承原则，控制继承深度不超过3层"),
        ("与关系数据库阻抗失配增加ORM开销", "核心领域采用富领域模型，辅助查询可走简单映射"),
        ("重量级设计不适合简单CRUD场景", "评估复杂度后选择是否引入完整OO设计"),
    ],
    "Repository Architecture": [
        ("中心存储成为单点瓶颈影响全局性能", "对中心存储做读写分离和水平分片"),
        ("分布式环境ACID难以保持", "根据业务场景进行BASE柔性事务权衡"),
        ("数据模型演进时需协调所有接入方", "建立Schema版本管理并为各接入方预留适配窗口"),
    ],
    "Rule-Based Architecture": [
        ("规则冲突检测复杂易导致非预期结果", "建立规则优先级和冲突消解策略"),
        ("推理引擎性能低不适合高并发场景", "将高频规则预编译为决策树降低推理开销"),
        ("规则数量爆炸后维护困难", "引入规则分类和版本管理限制单次推理的规则集大小"),
    ],
}

# ── 种子反馈 ──
SEED_FEEDBACK = [
    ("高并发场景的即时通讯系统，支持万人同时在线，需要保证消息的实时性和可靠性", "Event-Driven Architecture"),
    ("高并发场景的电商秒杀平台，需支持海量用户同时购买", "Event-Driven Architecture"),
    ("高并发场景的实时数据推送服务", "Event-Driven Architecture"),
    ("高并发场景的直播弹幕系统，需要低延迟消息分发", "Event-Driven Architecture"),
    ("高并发场景的在线游戏匹配服务", "Microservices"),
    ("高并发场景的社交媒体信息流服务，多团队协作", "Microservices"),
    ("实时性要求高的在线协作编辑平台", "Event-Driven Architecture"),
    ("实时性要求高的股票行情推送系统", "Event-Driven Architecture"),
    ("实时性要求高的物联网设备监控平台", "Event-Driven Architecture"),
    ("复杂业务逻辑的企业ERP系统，含审批流和工作流引擎", "Layered Architecture"),
    ("复杂业务逻辑的保险理赔核心系统", "Layered Architecture"),
    ("批量处理数据的银行日终结算和报表生成系统", "Batch-Sequential"),
    ("采用领域驱动设计的复杂业务电商核心域模型", "Object-Oriented Architecture"),
    ("整合多业务系统数据的企业数据中台和大数据分析平台", "Repository Architecture"),
    ("基于规则库动态判定的保险核保和风控决策引擎", "Rule-Based Architecture"),
]


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

        # ── 1. Feature 节点 (12 个评分维度) ──
        for feat in FEATURE_NAMES:
            session.run("CREATE (:Feature {name: $name})", {"name": feat})
        print(f"  Created {len(FEATURE_NAMES)} Feature nodes")

        # ── 2. ArchitectureStyle + QualityAttribute + Scenario ──
        mainstream_names = {"Layered Architecture", "Microservices", "Event-Driven Architecture"}
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
            is_main = name in mainstream_names

            session.run("""
                CREATE (s:ArchitectureStyle {
                    name: $name, name_zh: $name_zh,
                    topology_mermaid: $topo,
                    pros: $pros, pros_zh: $pros_zh,
                    cons: $cons, cons_zh: $cons_zh,
                    is_mainstream: $is_main
                })
            """, {
                "name": name, "name_zh": name_zh, "topo": topo,
                "pros": pros, "pros_zh": pros_zh,
                "cons": cons, "cons_zh": cons_zh, "is_main": is_main,
            })

            for tag in tags:
                session.run("""
                    MERGE (q:QualityAttribute {name: $tag})
                    WITH q
                    MATCH (s:ArchitectureStyle {name: $style_name})
                    MERGE (s)-[:HAS_QUALITY]->(q)
                """, {"tag": tag, "style_name": name})

            for scenario in best_for:
                session.run("""
                    MERGE (sc:Scenario {name: $scenario})
                    WITH sc
                    MATCH (s:ArchitectureStyle {name: $style_name})
                    MERGE (s)-[:SUITABLE_FOR]->(sc)
                """, {"scenario": scenario, "style_name": name})

            print(f"  [+] {name} ({len(tags)} qualities, {len(best_for)} scenarios, mainstream={is_main})")

        # ── 3. HAS_PENALTY 关系 (Feature → Style, 替代 JSON penalty_tags) ──
        penalty_count = 0
        for style_name, penalties in PENALTY_MAP.items():
            for feat_name, weight in penalties.items():
                session.run("""
                    MATCH (f:Feature {name: $feat})
                    MATCH (s:ArchitectureStyle {name: $style})
                    CREATE (f)-[:HAS_PENALTY {weight: $weight}]->(s)
                """, {"feat": feat_name, "style": style_name, "weight": weight})
                penalty_count += 1
        print(f"  Created {penalty_count} HAS_PENALTY relationships")

        # ── 3b. 同时将 penalty_tags 存为节点属性 (JSON 字符串, 供 get_styles() 读取) ──
        for style_name, penalties in PENALTY_MAP.items():
            import json as _json
            penalty_json = _json.dumps(penalties, ensure_ascii=False)
            session.run("""
                MATCH (s:ArchitectureStyle {name: $name})
                SET s.penalty_tags = $penalty
            """, {"name": style_name, "penalty": penalty_json})

        # ── 4. ScoringRule 节点 (替代硬编码 if-then) ──
        for rule in SCORING_RULES:
            session.run("""
                CREATE (r:ScoringRule {name: $name, bonus: $bonus, required_features: $required})
            """, {"name": rule["name"], "bonus": rule["bonus"],
                  "required": rule["required"]})
            # REQUIRES 关系
            for feat_name in rule["required"]:
                session.run("""
                    MATCH (r:ScoringRule {name: $name})
                    MATCH (f:Feature {name: $feat})
                    CREATE (r)-[:REQUIRES]->(f)
                """, {"name": rule["name"], "feat": feat_name})
            # APPLIES_TO 关系
            session.run("""
                MATCH (r:ScoringRule {name: $name})
                MATCH (s:ArchitectureStyle {name: $style})
                CREATE (r)-[:APPLIES_TO {bonus: $bonus}]->(s)
            """, {"name": rule["name"], "style": rule["style"], "bonus": rule["bonus"]})
        print(f"  Created {len(SCORING_RULES)} ScoringRule nodes")

        # ── 5. Risk 节点 + HAS_RISK ──
        risk_count = 0
        for style_name, risks in RISK_DATA.items():
            for risk_text, suggestion_text in risks:
                session.run("""
                    MERGE (r:Risk {name: $risk})
                    ON CREATE SET r.suggestion = $suggestion
                    WITH r
                    MATCH (s:ArchitectureStyle {name: $style_name})
                    MERGE (s)-[:HAS_RISK]->(r)
                """, {"risk": risk_text, "suggestion": suggestion_text,
                      "style_name": style_name})
                risk_count += 1
        print(f"  Created {risk_count} HAS_RISK relationships (10 styles × 3 risks)")

        # ── 6. COMPLEMENTS 关系 ──
        comp_count = 0
        for style_name, complements in COMPLEMENTS_MAP.items():
            for target in complements:
                session.run("""
                    MATCH (a:ArchitectureStyle {name: $a})
                    MATCH (b:ArchitectureStyle {name: $b})
                    MERGE (a)-[:COMPLEMENTS]->(b)
                """, {"a": style_name, "b": target})
                comp_count += 1
        print(f"  Created {comp_count} COMPLEMENTS relationships")

        # ── 7. 种子反馈 + LEARNED_FOR 关系 ──
        now_ts = _dt.now().isoformat(timespec="seconds")
        for req, rec_style in SEED_FEEDBACK:
            session.run("""
                CREATE (f:Feedback {
                    timestamp: $ts, requirement: $req,
                    recommended_style: $rec, user_choice: $rec,
                    comment: '种子反馈', is_confirmed: true
                })
            """, {"ts": now_ts, "req": req, "rec": rec_style})
        print(f"  Created {len(SEED_FEEDBACK)} seed Feedback nodes")

        # ── 8. 从种子反馈计算 LEARNED_FOR 权重 ──
        # 统计每个 (style, quality) 的反馈次数，写入 LEARNED_FOR 关系
        raw_counts = session.run("""
            MATCH (f:Feedback)
            RETURN f.recommended_style AS style, f.requirement AS req
        """)
        from collections import Counter
        counts: dict = {}
        for row in raw_counts:
            s = row["style"]
            r = row["req"]
            if s and r:
                counts.setdefault(s, []).append(r)

        learned_count = 0
        lexicon_path = Path(__file__).resolve().parent.parent / "data" / "feature_lexicon.json"
        if lexicon_path.exists():
            with open(lexicon_path, "r", encoding="utf-8") as f:
                lex = json.load(f).get("lexicon", {})
        else:
            lex = {}

        for style_name, reqs in counts.items():
            feat_counts: dict = {}
            for req_text in reqs:
                text_lower = req_text.lower()
                for feat, keywords in lex.items():
                    if any(kw in text_lower for kw in keywords):
                        feat_counts[feat] = feat_counts.get(feat, 0) + 1

            if not feat_counts:
                continue
            max_count = max(feat_counts.values())
            for feat, count in feat_counts.items():
                norm_weight = count / max_count  # 归一化到 [0,1]
                session.run("""
                    MATCH (s:ArchitectureStyle {name: $style})
                    MATCH (q:QualityAttribute {name: $feat})
                    MERGE (s)-[r:LEARNED_FOR]->(q)
                    SET r.weight = $weight
                """, {"style": style_name, "feat": feat, "weight": norm_weight})
                learned_count += 1

        print(f"  Created {learned_count} LEARNED_FOR relationships ({len(counts)} styles)")

        # ── 统计 ──
        node_count = session.run("MATCH (n) RETURN count(n) AS cnt").single()["cnt"]
        rel_count = session.run("MATCH ()-[r]->() RETURN count(r) AS cnt").single()["cnt"]

    driver.close()
    print(f"\nInit complete: {node_count} nodes, {rel_count} relationships created.")
    print("Graph is ready for dual-drive scoring (rule engine + graph engine).")


if __name__ == "__main__":
    init_graph()
