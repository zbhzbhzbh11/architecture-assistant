#!/usr/bin/env python3
"""纯标准库生成答辩 PPT —— 无需 python-pptx, 仅用 zipfile + xml."""

import datetime
import os
import shutil
import zipfile
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring


def _tag(ns, name):
    return f"{{{ns}}}{name}"


# ————————————————————————————————————————————
# 1. 基础 XML 片段
# ————————————————————————————————————————————
NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "ct": "http://schemas.openxmlformats.org/package/2006/content-types",
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcterms": "http://purl.org/dc/terms/",
    "cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
}

A = lambda name: _tag(NS["a"], name)
P = lambda name: _tag(NS["p"], name)
R = lambda name: _tag(NS["r"], name)
CT = lambda name: _tag(NS["ct"], name)

SLIDE_W, SLIDE_H = 12192000, 6858000  # 16:9 EMU


def _make_rels():
    """ppt/_rels/presentation.xml.rels"""
    el = Element("Relationships", xmlns="http://schemas.openxmlformats.org/package/2006/relationships")
    items = [
        ("rId1", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster",
         "slideMasters/slideMaster1.xml"),
        ("rId2", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme",
         "theme/theme1.xml"),
    ]
    for i, (rid, rtype, target) in enumerate(items, 1):
        se = SubElement(el, "Relationship", Id=rid, Type=rtype, Target=target)
    return el


def _theme_xml():
    """最小可用的主题 XML."""
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="Office Theme">'
        '<a:themeElements>'
        '<a:clrScheme name="DeepBlue">'
        '<a:dk1><a:srgbClr val="1E293B"/></a:dk1>'
        '<a:lt1><a:srgbClr val="FFFFFF"/></a:lt1>'
        '<a:dk2><a:srgbClr val="1E40AF"/></a:dk2>'
        '<a:lt2><a:srgbClr val="DBEAFE"/></a:lt2>'
        '<a:accent1><a:srgbClr val="2563EB"/></a:accent1>'
        '<a:accent2><a:srgbClr val="059669"/></a:accent2>'
        '<a:accent3><a:srgbClr val="D97706"/></a:accent3>'
        '<a:accent4><a:srgbClr val="7C3AED"/></a:accent4>'
        '<a:accent5><a:srgbClr val="0EA5E9"/></a:accent5>'
        '<a:accent6><a:srgbClr val="EF4444"/></a:accent6>'
        '<a:hlink><a:srgbClr val="2563EB"/></a:hlink>'
        '<a:folHlink><a:srgbClr val="7C3AED"/></a:folHlink>'
        '</a:clrScheme>'
        '<a:fontScheme name="Office">'
        '<a:majorFont><a:latin typeface="Microsoft YaHei"/><a:ea typeface="Microsoft YaHei"/></a:majorFont>'
        '<a:minorFont><a:latin typeface="Microsoft YaHei"/><a:ea typeface="Microsoft YaHei"/></a:minorFont>'
        '</a:fontScheme>'
        '<a:fmtScheme name="Office"><a:fillStyleLst>'
        '<a:solidFill><a:srgbClr val="1E40AF"/></a:solidFill>'
        '</a:fillStyleLst></a:fmtScheme>'
        '</a:themeElements></a:theme>'
    )


def _content_types(n_slides):
    """[Content_Types].xml"""
    el = Element("Types", xmlns="http://schemas.openxmlformats.org/package/2006/content-types")
    defaults = [
        ("rels", "application/vnd.openxmlformats-package.relationships+xml"),
        ("xml", "application/xml"),
    ]
    for ext, ct in defaults:
        SubElement(el, "Default", Extension=ext, ContentType=ct)
    overrides = [
        ("/ppt/presentation.xml", "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"),
        ("/ppt/theme/theme1.xml", "application/vnd.openxmlformats-officedocument.theme+xml"),
        ("/ppt/slideMasters/slideMaster1.xml",
         "application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"),
        ("/ppt/slideLayouts/slideLayout1.xml",
         "application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"),
        ("/docProps/core.xml", "application/vnd.openxmlformats-package.core-properties+xml"),
        ("/docProps/app.xml", "application/vnd.openxmlformats-officedocument.extended-properties+xml"),
    ]
    for path, ct in overrides:
        SubElement(el, "Override", PartName=path, ContentType=ct)
    for i in range(1, n_slides + 1):
        SubElement(el, "Override",
                   PartName=f"/ppt/slides/slide{i}.xml",
                   ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml")
    return el


def _presentation_xml(n_slides):
    el = Element(P("presentation"), {
        "xmlns:a": NS["a"],
        "xmlns:r": NS["r"],
        "xmlns:p": NS["p"],
    })
    SubElement(el, P("sldMasterIdLst")).append(
        SubElement(Element("dummy"), P("sldMasterId"), {"id": "2147483648", R("id"): "rId1"})
    )
    sldIdLst = SubElement(el, P("sldIdLst"))
    for i in range(1, n_slides + 1):
        SubElement(sldIdLst, P("sldId"), {"id": str(255 + i), R("id"): f"rId{i + 2}"})
    SubElement(el, P("sldSz"), {"cx": str(SLIDE_W), "cy": str(SLIDE_H)})
    return el


def _slide_master_xml():
    el = Element(P("sldMaster"), {"xmlns:p": NS["p"], "xmlns:a": NS["a"], "xmlns:r": NS["r"]})
    cSld = SubElement(el, P("cSld"))
    bg = SubElement(cSld, P("bg"))
    bgPr = SubElement(bg, P("bgPr"))
    sf = SubElement(bgPr, A("solidFill"))
    SubElement(sf, A("srgbClr"), {"val": "FFFFFF"})
    # simple text-only layout id
    SubElement(el, P("sldLayoutIdLst")).append(
        SubElement(Element("dummy"), P("sldLayoutId"), {"id": "2147483649", R("id"): "rId1"})
    )
    return el


def _slide_layout_xml():
    el = Element(P("sldLayout"), {"xmlns:p": NS["p"], "xmlns:a": NS["a"], "xmlns:r": NS["r"]})
    cSld = SubElement(el, P("cSld"))
    SubElement(cSld, P("spTree")).append(SubElement(Element("dummy"), P("nvGrpSpPr")))
    return el


def _make_pres_rels(n_slides):
    el = Element("Relationships", xmlns="http://schemas.openxmlformats.org/package/2006/relationships")
    items = [
        ("rId1", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster",
         "slideMasters/slideMaster1.xml"),
        ("rId2", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme",
         "theme/theme1.xml"),
    ]
    for i, (rid, rtype, target) in enumerate(items, 1):
        SubElement(el, "Relationship", Id=rid, Type=rtype, Target=target)
    for i in range(1, n_slides + 1):
        SubElement(el, "Relationship", Id=f"rId{i + 2}",
                   Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide",
                   Target=f"slides/slide{i}.xml")
    return el


# ————————————————————————————————————————————
# 2. 幻灯片生成
# ————————————————————————————————————————————

def _emu(inches):
    return int(inches * 914400)


def _shape(el_id, name, x, y, cx, cy):
    sp = Element(P("sp"))
    nvSpPr = SubElement(sp, P("nvSpPr"))
    cNvPr = SubElement(nvSpPr, P("cNvPr"), {"id": str(el_id), "name": name})
    cNvSpPr = SubElement(nvSpPr, P("cNvSpPr"))
    SubElement(cNvSpPr, A("spLocks"), {"noGrp": "1"})

    spPr = SubElement(sp, P("spPr"))
    SubElement(spPr, A("xfrm")).append(
        SubElement(Element("dummy"), A("off"), {"x": str(x), "y": str(y)})
    )
    SubElement(spPr[-1], A("ext"), {"cx": str(cx), "cy": str(cy)})
    prstGeom = SubElement(spPr, A("prstGeom"), {"prst": "rect"})
    SubElement(prstGeom, A("avLst"))

    txBody = SubElement(sp, P("txBody"))
    SubElement(txBody, A("bodyPr"), {"wrap": "square", "rtlCol": "0"})
    return sp


def _add_paragraph(txBody, text, font_size=1800, bold=False, color="1E293B",
                   alignment="l", space_after=600, level=0, latin="Microsoft YaHei"):
    p = SubElement(txBody, A("p"))
    SubElement(p, A("pPr"), {"algn": alignment, "marL": "0", "indent": "0"})
    r = SubElement(p, A("r"))
    SubElement(r, A("rPr"), {
        "sz": str(font_size), "b": "1" if bold else "0",
        "latin": '{"typeface":"' + latin + '"}',
        "ea": '{"typeface":"Microsoft YaHei"}',
    })
    SubElement(SubElement(r, A("solidFill")), A("srgbClr"), {"val": color})
    SubElement(r, A("t")).text = text
    SubElement(p, A("endParaRPr"), {"sz": str(font_size)})
    return p


def _title_slide(title, subtitle=""):
    """封面幻灯片."""
    sp_tree = Element(P("spTree"))
    SubElement(sp_tree, P("nvGrpSpPr")).append(SubElement(Element("dummy"), P("cNvPr"), {"id": "1", "name": ""}))
    SubElement(sp_tree, P("grpSpPr"))

    # 蓝色背景矩形
    rect = Element(P("sp"))
    nv = SubElement(rect, P("nvSpPr"))
    SubElement(nv, P("cNvPr"), {"id": "64", "name": "bg"})
    SubElement(nv, P("cNvSpPr")).append(SubElement(Element("dummy"), A("spLocks"), {"noGrp": "1"}))
    rpr = SubElement(rect, P("spPr"))
    SubElement(rpr, A("xfrm")).append(SubElement(Element("dummy"), A("off"), {"x": "0", "y": "0"}))
    SubElement(rpr[-1], A("ext"), {"cx": str(SLIDE_W), "cy": str(SLIDE_H)})
    SubElement(rpr, A("prstGeom"), {"prst": "rect"}).append(SubElement(Element("dummy"), A("avLst")))
    SubElement(SubElement(rpr, A("solidFill")), A("srgbClr"), {"val": "1E3A5F"})
    sp_tree.append(rect)

    # 标题
    title_shape = _shape(2, "Title", _emu(1), _emu(1.8), _emu(8), _emu(1.5))
    txBody = title_shape[-1]
    _add_paragraph(txBody, title, font_size=3600, bold=True, color="FFFFFF", alignment="l")
    sp_tree.append(title_shape)

    # 副标题
    if subtitle:
        sub_shape = _shape(3, "Subtitle", _emu(1), _emu(3.3), _emu(8), _emu(1.2))
        txBody2 = sub_shape[-1]
        for line in subtitle.split("\n"):
            _add_paragraph(txBody2, line, font_size=1800, bold=False, color="93C5FD", alignment="l",
                           space_after=300)
        sp_tree.append(sub_shape)

    # 底部横线
    line_shape = _shape(4, "Line", _emu(1), _emu(4.8), _emu(3), _emu(0.05))
    lpr = line_shape[1]  # spPr
    SubElement(SubElement(lpr, A("solidFill")), A("srgbClr"), {"val": "3B82F6"})
    sp_tree.append(line_shape)

    return sp_tree


def _content_slide(title, bullets, note=""):
    """标准内容页."""
    sp_tree = Element(P("spTree"))
    SubElement(sp_tree, P("nvGrpSpPr")).append(SubElement(Element("dummy"), P("cNvPr"), {"id": "1", "name": ""}))
    SubElement(sp_tree, P("grpSpPr"))

    # 顶部蓝色条
    bar = _shape(10, "TopBar", 0, 0, SLIDE_W, _emu(0.12))
    bar_pr = bar[1]
    SubElement(SubElement(bar_pr, A("solidFill")), A("srgbClr"), {"val": "1E40AF"})
    sp_tree.append(bar)

    # 标题
    t_shape = _shape(2, "Title", _emu(0.6), _emu(0.3), _emu(9), _emu(0.8))
    _add_paragraph(t_shape[-1], title, font_size=2800, bold=True, color="1E3A5F", alignment="l")
    sp_tree.append(t_shape)

    # 标题下划线
    uline = _shape(3, "ULine", _emu(0.6), _emu(1.05), _emu(2), _emu(0.04))
    SubElement(SubElement(uline[1], A("solidFill")), A("srgbClr"), {"val": "3B82F6"})
    sp_tree.append(uline)

    # 内容区
    content = _shape(4, "Content", _emu(0.6), _emu(1.4), _emu(8.8), _emu(5))
    txBody = content[-1]
    for b in bullets:
        lines = b.split("\n")
        for li, line in enumerate(lines):
            is_first = (li == 0)
            prefix = "● " if is_first else "   "
            fs = 1600 if is_first else 1400
            clr = "1E293B" if is_first else "475569"
            bld = is_first
            _add_paragraph(txBody, prefix + line, font_size=fs, bold=bld, color=clr,
                           alignment="l", space_after=400 if is_first else 200,
                           level=0 if is_first else 1)
    sp_tree.append(content)

    # 底部注释
    if note:
        n_shape = _shape(5, "Note", _emu(0.6), _emu(6.6), _emu(9), _emu(0.3))
        _add_paragraph(n_shape[-1], note, font_size=1000, bold=False, color="9CA3AF", alignment="l")
        sp_tree.append(n_shape)

    # 页码
    page_num = _shape(6, "PageNum", _emu(8.5), _emu(6.9), _emu(1.2), _emu(0.3))
    _add_paragraph(page_num[-1], "", font_size=1000, bold=False, color="9CA3AF", alignment="r")
    sp_tree.append(page_num)

    return sp_tree


def _make_slide_xml(sp_tree):
    slide = Element(P("sld"), {"xmlns:p": NS["p"], "xmlns:a": NS["a"], "xmlns:r": NS["r"]})
    cSld = SubElement(slide, P("cSld"))
    bg = SubElement(cSld, P("bg"))
    bgPr = SubElement(bg, P("bgPr"))
    SubElement(SubElement(bgPr, A("solidFill")), A("srgbClr"), {"val": "FFFFFF"})
    cSld.append(sp_tree)
    return slide


def _pretty(el):
    s = tostring(el, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + s


def _write_zip_entry(zf: zipfile.ZipFile, path, content):
    if isinstance(content, str):
        content = content.encode("utf-8")
    zf.writestr(path, content)


# ————————————————————————————————————————————
# 3. 幻灯片内容
# ————————————————————————————————————————————

SLIDES = [
    # 第 1 页：封面
    ("cover", _title_slide(
        "基于大模型的\n软件架构风格智能助手",
        "软件体系结构课程大作业\n2026年X月\n\n将自然语言需求 → 可解释的架构推荐"
    )),

    # 第 2 页：作业目标
    ("content", _content_slide(
        "作业目标与核心功能",
        [
            "需求分析 — 接收自然语言需求，提取10维度关键特征（高并发/实时性/安全性/可扩展性...）",
            "架构推荐 — 推荐至少3种候选架构风格，含分层/微服务/事件驱动等主流架构",
            "决策支持 — 多维度对比矩阵 + 最终推荐 + 优缺点分析 + 风险评估报告",
            "知识进化 — 可扩展知识库（10种风格）+ 案例反馈学习机制",
        ],
        "软件体系结构大作业要求 — 四大核心能力闭环"
    )),

    # 第 3 页：系统总体架构
    ("content", _content_slide(
        "系统总体架构（C4-Context）",
        [
            "用户（浏览器/API调用者）→ 架构风格智能助手（6个容器）→ LLM服务（DeepSeek v4-flash）",
            "前端：Nginx + 原生 HTML/CSS/JS + Mermaid.js",
            "后端：5个独立微服务（FastAPI + Uvicorn），Docker Compose 编排",
            "LLM：OpenAI兼容协议，支持 DeepSeek / 通义千问 / OpenAI 一键切换",
            "知识库：JSON结构化存储，10种架构风格 × 6个字段",
        ],
        "LLM是外部依赖而非系统内核，可替换"
    )),

    # 第 4 页：微服务划分
    ("content", _content_slide(
        "微服务划分（C4-Container）",
        [
            "api-gateway (:8000) — 统一入口、编排调用、聚合响应",
            "requirements-agent (:8001) — 10维度词典 + LLM语义补全 + 否定过滤",
            "matching-agent (:8002) — 标签评分 + 额外规则 + Top3候选生成",
            "evaluation-agent (:8003) — LLM混合推理 + 最终报告 + 动态风险评估",
            "knowledge-base (:8004) — 架构风格数据 + 反馈收集接口",
            "划分理由：异构成分隔离（规则 vs LLM）、故障隔离、独立演进",
        ],
        "5个后端微服务 + 1个前端容器，Docker Compose编排"
    )),

    # 第 5 页：Agent 协作
    ("content", _content_slide(
        "Pipeline-Agent 协作机制",
        [
            "Gateway → Requirements Agent  POST /extract  → {10维特征 + 关键词证据}",
            "Gateway → Matching Agent     POST /match    → {Top3候选 + 评分理由}",
            "Gateway → Evaluation Agent   POST /evaluate → {最终推荐 + 矩阵 + 风险}",
            "",
            "设计原则：",
            "  ● 每个Agent只解决一类问题（单一职责）",
            "  ● 上一个输出 = 下一个输入（数据驱动流转）",
            "  ● LLM仅在evaluation-agent参与（降低不确定性扩散）",
        ],
        "Pipeline模式：职责清晰、可独立测试、可替换"
    )),

    # 第 6 页：LLM 集成
    ("content", _content_slide(
        "LLM 集成方案",
        [
            "配置方式：OpenAI兼容协议 → DeepSeek v4-flash / 通义千问 / OpenAI 一键切换",
            "两套Prompt：llm_vote(t=0.0 确定性投票) / llm_summary(t=0.3 结构化中文报告)",
            "四层防护：20s超时 → try-except全量捕获 → 格式化降级摘要 → 未配置时自动跳过",
            "环境隔离：.env文件配置 → .env自动加载 → Key不硬编码 → 代码0敏感信息",
            "降级保障：LLM完全不可用时，规则引擎独立运行，核心推荐链路不中断",
        ],
        "鲁棒性设计：降级后仍可输出完整推荐报告"
    )),

    # 第 7 页：知识库设计
    ("content", _content_slide(
        "架构知识库设计",
        [
            "10种架构风格：Layered / Microservices / Event-Driven / SOA / Hexagonal",
            "               Pipeline-Filter / CQRS / Serverless / Space-Based / Client-Server",
            "每风格6字段：name / tags / best_for / pros / cons / topology_mermaid",
            "扩展接口：POST /styles 动态新增 / POST /feedback 案例收集 / GET /feedback/stats 准确率统计",
            "拓扑图数据驱动：每种风格预定义Mermaid图语法，API动态返回，前端实时渲染",
            "演进路径：JSON → Neo4j图数据库（tags→图边, best_for→属性约束）",
        ],
        "恰好10种风格，满足作业≥10要求；每种含完整属性+拓扑图定义"
    )),

    # 第 8 页：混合推理
    ("content", _content_slide(
        "规则引擎 + LLM 混合推理（核心创新点）",
        [
            "规则引擎（确定性）：tags匹配计分 +2/tag | 额外专家规则 +1 | 主流风格白名单兜底",
            "LLM增强（语义性）：投票 +1分 tie-break | 中文结构化分析报告 | 失败静默降级",
            "",
            "协同价值：规则保下限（确定/可审计）→ LLM提上限（语义理解/自然语言解释）",
            "",
            "为什么两者都需要？",
            "  ● 纯规则：泛化弱 — '大量用户同时查询'无法区分读压力还是写压力",
            "  ● 纯LLM：不稳定 — 相同需求两次调用可能不同，有幻觉风险",
            "  ● 协同：规则生成确定性候选集 → LLM在基线上做轻量语义增强",
        ],
        "最大创新点：LLM投票仅+1分，不会颠覆规则排序"
    )),

    # 第 9 页：推荐流程
    ("content", _content_slide(
        "架构推荐全链路",
        [
            "Step 1：需求理解 — 10维度词典 × ~100个关键词 → 特征提取 + 否定过滤",
            "        命中≤2 → 触发LLM语义补全(t=0.1, 返回严格JSON)",
            "Step 2：架构匹配 — 10种风格逐一标签评分 + 额外规则 + 主流白名单 → Top3",
            "Step 3：混合评估 — 规则排序 + LLM投票(+1) + LLM结构化中文报告生成",
            "Step 4：输出 — recommended_style + alternative_styles + comparison_matrix",
            "                        + risk_and_suggestions + topology_mermaid",
        ],
        "全链路可追溯：每步输出都可映射到中间证据"
    )),

    # 第 10 页：对比矩阵与拓扑图
    ("content", _content_slide(
        "可视化展示：对比矩阵与拓扑图",
        [
            "前端四区域展示：",
            "  1. 推荐摘要 — 核心推荐 + 备选架构 + LLM结构化分析报告（√优点/×缺点）",
            "  2. 特征卡片 — 命中的需求维度 + 关键词证据（如'高并发(万人)'）",
            "  3. 对比矩阵 — 6列表格（推荐类型/风格/得分/理由/优点/缺点）",
            "  4. 拓扑图   — Mermaid.js动态渲染，10种风格各有专属定义",
            "",
            "数据流向：知识库JSON → matching → evaluation → 前端动态读取 → Mermaid渲染",
        ],
        "拓扑图不是静态图片——修改图定义只需改JSON，无需改代码"
    )),

    # 第 11 页：系统演示
    ("content", _content_slide(
        "系统演示流程（参考案例）",
        [
            "输入：'开发跨平台即时通讯系统，支持万人同时在线，消息实时可靠，后续扩展视频通话'",
            "",
            "输出展示：",
            "  [1] 特征提取 → 高并发(万人) + 实时性(实时/在线/消息) + 可靠性(可靠) + 可扩展性(扩展)",
            "  [2] 候选架构 → 核心推荐：Event-Driven(7分) / 备选：Microservices(5分), CQRS(4分)",
            "  [3] LLM报告  → 推荐理由(3条) + √优点(3条) + ×缺点(3条) + 风险建议",
            "  [4] 拓扑图   → Client→Gateway→Producer→EventBus→Consumers（Mermaid渲染）",
            "  [5] 测试验证 → 20/20通过，5项指标100%，平均时延~10s",
        ],
        "一条完整链路的端到端展示"
    )),

    # 第 12 页：测试验证
    ("content", _content_slide(
        "测试验证",
        [
            "三层测试体系：",
            "  ● 单元测试(pytest) — 核心算法4条（需求提取 + 风格评分）",
            "  ● 冒烟测试(smoke) — 20条用例端到端快速验证",
            "  ● 回归测试(regression) — 20条用例 + 5项指标自动统计",
            "",
            "回归测试结果（实测）：",
            "  通过率 100%(20/20) | Top3完整率 100% | 主流覆盖率 100%",
            "  推荐产出率 100% | 可解释率 100% | 矩阵产出率 100%",
            "  平均时延 ~10s（含LLM两次串行调用）",
            "",
            "自动验收检查：python scripts/check_assignment.py → 21/21全部通过",
        ],
        "20条用例覆盖10+领域，全部指标100%"
    )),

    # 第 13 页：异常处理与可靠性
    ("content", _content_slide(
        "异常处理与可靠性设计",
        [
            "网关层：统一 HttpException → 502/500标准返回 | trust_env=False绕过系统代理",
            "LLM层：20s超时 → try-except全量捕获 → 降级为规则引擎格式化摘要",
            "         Key未配置 → 自动跳过LLM调用，不影响核心链路",
            "前端层：按钮防重复提交(disabled切换) | 网络失败 → 显示错误信息，不白屏",
            "",
            "容错性成果：",
            "  ● 单个Agent故障不会导致网关崩溃",
            "  ● LLM完全不可用时，规则引擎可独立输出完整推荐报告",
        ],
        "降级后核心推荐链路不中断，保证系统可用性下限"
    )),

    # 第 14 页：创新点
    ("content", _content_slide(
        "项目创新点",
        [
            "1. 混合推理机制 — 规则保下限 + LLM提上限 + 三层证据可追溯",
            "   (10维度关键词 → 规则评分 → LLM投票/说明 → 风险建议)",
            "",
            "2. Pipeline-Agent协作 — 职责单一体现在独立容器中，非单体内部模块划分",
            "   每个Agent可独立替换、测试、演进",
            "",
            "3. 数据驱动拓扑图 — 10种风格Mermaid定义存储于知识库，API动态返回，前端实时渲染",
            "   修改图定义只需改JSON，无需改代码",
            "",
            "4. 案例学习闭环 — 反馈收集(POST /feedback) → 统计(GET /feedback/stats)",
            "   → 积累数据 → 可驱动自动权重更新",
        ],
        "每个创新点都与课程评分标准对齐"
    )),

    # 第 15 页：总结与展望
    ("content", _content_slide(
        "总结与展望",
        [
            "当前成果：",
            "  ✓ 功能完整 — 需求→推荐→解释 全链路闭环",
            "  ✓ 测试充分 — 20/20通过，全部指标100%",
            "  ✓ 工程完善 — 6容器编排 / logging / 异常处理 / LLM降级",
            "  ✓ 文档齐全 — 需求+架构+测试+答辩 四份文档",
            "",
            "后续改进：",
            "  → 案例学习：基于反馈数据自动更新标签权重（贝叶斯/TF-IDF）",
            "  → 知识库：JSON → Neo4j 图数据库（关系推理）",
            "  → 性能：LLM两次调用并行化（asyncio.gather，减少~40%时延）",
            "  → 测试：补充单元测试覆盖（evaluation / knowledge-base）",
            "",
            "谢谢各位老师！",
        ],
        "诚实说明不足，展示改进路线"
    )),
]


# ————————————————————————————————————————————
# 4. 组装 PPTX
# ————————————————————————————————————————————

def build_pptx(out_path):
    n = len(SLIDES)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(str(out_path), "w", zipfile.ZIP_DEFLATED) as zf:
        # [Content_Types].xml
        _write_zip_entry(zf, "[Content_Types].xml",
                         '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                         + tostring(_content_types(n), encoding="unicode"))

        # _rels/.rels
        rels_root = Element("Relationships",
                            xmlns="http://schemas.openxmlformats.org/package/2006/relationships")
        SubElement(rels_root, "Relationship", Id="rId1",
                   Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument",
                   Target="ppt/presentation.xml")
        _write_zip_entry(zf, "_rels/.rels",
                         '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                         + tostring(rels_root, encoding="unicode"))

        # ppt/presentation.xml
        _write_zip_entry(zf, "ppt/presentation.xml", _pretty(_presentation_xml(n)))
        _write_zip_entry(zf, "ppt/_rels/presentation.xml.rels", _pretty(_make_pres_rels(n)))

        # ppt/theme/theme1.xml
        _write_zip_entry(zf, "ppt/theme/theme1.xml", _theme_xml())

        # ppt/slideMasters/slideMaster1.xml
        _write_zip_entry(zf, "ppt/slideMasters/slideMaster1.xml", _pretty(_slide_master_xml()))
        _write_zip_entry(zf, "ppt/slideLayouts/slideLayout1.xml", _pretty(_slide_layout_xml()))

        # slides
        for i, (_, sp_tree) in enumerate(SLIDES, 1):
            slide_xml = _pretty(_make_slide_xml(sp_tree))
            _write_zip_entry(zf, f"ppt/slides/slide{i}.xml", slide_xml)

        # docProps
        now = datetime.datetime.now().isoformat()
        core = Element("cp:coreProperties", {
            "xmlns:cp": NS["cp"], "xmlns:dc": NS["dc"], "xmlns:dcterms": NS["dcterms"],
            "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
        })
        SubElement(core, "dc:title").text = "软件架构风格智能助手 — 答辩PPT"
        SubElement(core, "dc:creator").text = "软件体系结构课程"
        SubElement(core, "dcterms:created", {"xsi:type": "dcterms:W3CDTF"}).text = now
        _write_zip_entry(zf, "docProps/core.xml",
                         '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                         + tostring(core, encoding="unicode"))

        app = Element("Properties", xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties")
        SubElement(app, "Application").text = "Architecture Assistant PPT Generator"
        SubElement(app, "Slides").text = str(n)
        _write_zip_entry(zf, "docProps/app.xml",
                         '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                         + tostring(app, encoding="unicode"))

    print(f"PPT generated: {out_path} ({n} slides)")


if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "docs" / "答辩PPT.pptx"
    build_pptx(str(out))
