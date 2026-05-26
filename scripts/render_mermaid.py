#!/usr/bin/env python3
"""从 Marp markdown 中提取 Mermaid 代码块, 通过 Kroki API 渲染为 PNG。

Usage:
    python scripts/render_mermaid.py docs/defense/答辩PPT-marp.md
"""

import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import requests

KROKI_URL = "https://kroki.io/mermaid/png"


def extract_mermaid_blocks(md_path: Path) -> list[dict]:
    """从 markdown 中提取所有 mermaid 代码块。返回 [{code, line_num}]."""
    content = md_path.read_text(encoding="utf-8")
    blocks = []
    pattern = re.compile(r"```mermaid\n(.*?)```", re.DOTALL)
    for match in pattern.finditer(content):
        code = match.group(1).strip()
        line_num = content[: match.start()].count("\n") + 1
        blocks.append({"code": code, "line": line_num})
    return blocks


def render_via_kroki(mermaid_code: str, output_format: str = "png") -> bytes | None:
    """通过 Kroki API 渲染 Mermaid 代码为图片."""
    try:
        resp = requests.post(
            f"https://kroki.io/mermaid/{output_format}",
            data=mermaid_code.encode("utf-8"),
            headers={"Content-Type": "text/plain"},
            timeout=30,
        )
        if resp.status_code == 200:
            return resp.content
        print(f"    Kroki returned HTTP {resp.status_code}")
        return None
    except Exception as e:
        print(f"    Kroki request failed: {e}")
        return None


def render_and_save(blocks: list[dict], output_dir: Path) -> list[str | None]:
    """渲染所有 Mermaid 代码块为 PNG 并保存."""
    output_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for i, block in enumerate(blocks, 1):
        print(f"[{i}/{len(blocks)}] Rendering diagram (line {block['line']}, {len(block['code'])} chars)...")

        # 尝试 PNG
        data = render_via_kroki(block["code"], "png")
        if data:
            path = output_dir / f"diagram_{i:02d}.png"
            path.write_bytes(data)
            print(f"    -> Saved {path.name} ({len(data)} bytes)")
            saved.append(path.name)
            continue

        # 回退 SVG
        data = render_via_kroki(block["code"], "svg")
        if data:
            path = output_dir / f"diagram_{i:02d}.svg"
            path.write_bytes(data)
            print(f"    -> Saved {path.name} (SVG, {len(data)} bytes)")
            saved.append(path.name)
            continue

        print(f"    -> FAILED (diagram too complex?)")
        saved.append(None)
    return saved


def replace_mermaid_with_images(md_path: Path, saved: list[str | None], diagrams_dir: Path):
    """将 Marp 文件中的 Mermaid 代码块替换为图片引用，输出新文件."""
    content = md_path.read_text(encoding="utf-8")
    diagrams_rel = diagrams_dir.relative_to(md_path.parent).as_posix()

    counter = 0

    def replacer(match):
        nonlocal counter
        counter += 1
        name = saved[counter - 1]
        if name is None:
            return match.group(0)
        return f"![bg fit 90%]({diagrams_rel}/{name})"

    pattern = re.compile(r"```mermaid\n.*?```", re.DOTALL)
    new_content = pattern.sub(replacer, content)

    out_path = md_path.parent / f"{md_path.stem}_rendered.md"
    out_path.write_text(new_content, encoding="utf-8")
    print(f"\nRendered Marp file: {out_path}")
    print(f"  {counter} Mermaid blocks -> {sum(1 for s in saved if s)} images, "
          f"{sum(1 for s in saved if s is None)} failed")


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/render_mermaid.py <marp-file>")
        sys.exit(1)

    md_path = Path(sys.argv[1]).resolve()
    if not md_path.exists():
        print(f"File not found: {md_path}")
        sys.exit(1)

    diagrams_dir = md_path.parent / "diagrams"

    print(f"Extracting Mermaid blocks from {md_path.name}...")
    blocks = extract_mermaid_blocks(md_path)
    print(f"Found {len(blocks)} diagram(s).\n")

    if not blocks:
        print("No Mermaid blocks found — nothing to render.")
        return

    saved = render_and_save(blocks, diagrams_dir)
    success = sum(1 for s in saved if s)
    print(f"\nResult: {success}/{len(saved)} diagrams rendered.\n")

    replace_mermaid_with_images(md_path, saved, diagrams_dir)


if __name__ == "__main__":
    main()
