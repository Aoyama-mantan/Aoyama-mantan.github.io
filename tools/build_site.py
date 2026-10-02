#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 docs/ 里的 markdown 渲染成站内页面（d/），并重建 index.html 的索引。

权威数据：docs/**/*.md
  front matter（都可以省）：
    title:   文档标题；省略时用文件名
    type:    类型（笔记 / 论文 / 项目 …）；省略时显示「—」
    date:    更新日期 YYYY-MM-DD；省略时用文件最后修改时间
    slug:    自定义输出路径（不含 .html）；省略时沿用 docs/ 下的相对路径
    summary: 页面 description；省略时留空
    draft:   true 时跳过：不渲染、不进索引
  不进索引的文件：文件名以 _ 开头，或名为 README.md（写作说明用）。

派生视图（每次都会整段重建，手改会被覆盖）：
  d/**/*.html                     由 tools/templates/doc.html 渲染
  index.html 里 <ol class="docs"> 内部的标记区间，以及数据行的「共 N 份文档」
  docs/ 里的非 markdown 附件（图片等）按原相对路径复制到 d/
  d/ 下不再属于任何文档的旧文件会被删除

用法：
  pip install -r tools/requirements.txt
  python3 tools/build_site.py --root .
  python3 tools/build_site.py --root . --check     # 只报告是否有待更新（有则退出码 3）
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import pathlib
import posixpath
import re
import sys
import urllib.parse

BEGIN = "<!-- index:start -->"
END = "<!-- index:end -->"
OUT_DIR = "d"
TEMPLATE = "tools/templates/doc.html"
TYPE_FALLBACK = "—"
SKIP_NAMES = {"readme.md"}
# 需要带内容指纹引用的样式/脚本（GitHub Pages 的缓存是 max-age=600，
# 不加指纹的话改了 CSS 之后最多 10 分钟内访客（包括自己）看到的还是旧的）
VERSIONED_ASSETS = ("assets/css/style.css", "assets/js/theme.js")
ASSET_REF_RE = re.compile(r"(assets/(?:css/style\.css|js/theme\.js))(?:\?v=[0-9a-f]+)?")
# 站点版本：页面里写一份，version.json 里写一份；两者不一致说明浏览器缓存了旧页面
SITE_VERSION_RE = re.compile(r'<meta name="site-version" content="[0-9a-f]*">')
VERSION_JSON = "version.json"
KEEP = {".gitkeep"}

try:
    import markdown
except ImportError:  # pragma: no cover
    print("缺少依赖：先跑 pip install -r tools/requirements.txt", file=sys.stderr)
    raise SystemExit(1)


def parse_front_matter(text: str) -> dict:
    """极简 front matter：首行 --- 到下一个 --- 之间的 key: value。"""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    fm: dict = {}
    for line in text[3:end].strip().splitlines():
        if ":" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition(":")
            fm[key.strip()] = value.strip().strip('"').strip("'")
    return fm


def split_document(path: pathlib.Path) -> tuple[dict, str]:
    """返回 (front matter, 去掉 front matter 的正文)。"""
    text = path.read_text(encoding="utf-8", errors="replace")
    fm = parse_front_matter(text)
    body = text
    if fm:
        end = text.find("\n---", 3)
        body = text[end + 4:]
    return fm, body


def is_skipped(path: pathlib.Path) -> bool:
    return path.name.startswith("_") or path.name.lower() in SKIP_NAMES


def collect(docs_dir: pathlib.Path) -> tuple[list, list]:
    """扫描 docs/，返回 (文档列表, 附件列表)。"""
    docs, assets = [], []
    for path in sorted(docs_dir.rglob("*")):
        if path.is_dir() or is_skipped(path):
            continue
        rel = path.relative_to(docs_dir)
        if path.suffix.lower() not in (".md", ".markdown"):
            assets.append((path, f"{OUT_DIR}/{rel.as_posix()}"))
            continue
        fm, _ = split_document(path)
        if str(fm.get("draft", "")).strip().lower() in ("true", "yes", "1"):
            continue
        slug = (fm.get("slug") or rel.with_suffix("").as_posix()).strip("/")
        out_rel = f"{OUT_DIR}/{slug}.html"
        docs.append({
            "src": path,
            "src_rel": rel.as_posix(),
            "fm": fm,
            "slug": slug,
            "out_rel": out_rel,
            "title": fm.get("title") or path.stem,
            "type": fm.get("type") or TYPE_FALLBACK,
            "date": (fm.get("date") or dt.date.fromtimestamp(path.stat().st_mtime).isoformat())[:10],
            "summary": fm.get("summary", ""),
        })
    docs.sort(key=lambda d: (d["date"], d["out_rel"]), reverse=True)   # 日期倒序，同日按路径倒序（结果稳定）
    return docs, assets


def render_doc_page(doc: dict, template: str, doc_map: dict, docs_dir: str, unresolved: list) -> str:
    _, body = split_document(doc["src"])
    body_html = markdown.Markdown(extensions=["extra", "sane_lists"]).convert(body)
    body_html = rewrite_md_links(body_html, doc, doc_map, docs_dir, unresolved)
    depth = len(pathlib.PurePosixPath(doc["out_rel"]).parts) - 1   # d/2026/x.html → 2 层 → ../../
    root = "../" * depth
    meta_bits = [f"更新 {doc['date']}"]
    if doc["type"] != TYPE_FALLBACK:
        meta_bits.append(doc["type"])
    return (template
            .replace("{{root}}", root)
            .replace("{{title}}", html.escape(doc["title"]))
            .replace("{{meta}}", html.escape(" · ".join(meta_bits)))
            .replace("{{summary}}", html.escape(doc["summary"], quote=True))
            .replace("{{body}}", body_html))


def rewrite_md_links(body_html: str, doc: dict, doc_map: dict, docs_dir: str, unresolved: list) -> str:
    """把正文里指向另一份 markdown 的相对链接改写成站内渲染页地址。

    doc_map: {docs/ 下的相对路径: 输出路径}。指向未发布的 md（README、_ 开头的文件）
    的链接改指回 docs/ 里的原文件，其余原样保留并记进 unresolved 供人工检查。
    """
    src_dir = pathlib.PurePosixPath(doc["src_rel"]).parent
    out_dir = pathlib.PurePosixPath(doc["out_rel"]).parent

    def repl(m: re.Match) -> str:
        attr, href = m.group(1), m.group(2)
        if re.match(r"^(?:[a-zA-Z][a-zA-Z0-9+.-]*:|#|//)", href):
            return m.group(0)
        if not href.lower().endswith((".md", ".markdown")):
            return m.group(0)
        target = posixpath.normpath((src_dir / href).as_posix())          # 必须用 posix 版：os.path 在 Windows 上会转成反斜杠
        if target in doc_map:
            new = posixpath.relpath(doc_map[target], out_dir.as_posix())
        elif (pathlib.Path(docs_dir) / target).exists():
            new = posixpath.relpath(f"{docs_dir}/{target}", out_dir.as_posix())
        else:
            unresolved.append(f'{doc["src_rel"]} → {href}')
            return m.group(0)
        return f'{attr}="{urllib.parse.quote(new)}"'

    return re.sub(r'(href)="([^"]+)"', repl, body_html)


def asset_version(root: pathlib.Path) -> str:
    """样式/脚本的内容指纹：内容一变，页面引用的 URL 就变，浏览器必然重新取。"""
    digest = hashlib.sha256()
    for rel in VERSIONED_ASSETS:
        path = root / rel
        digest.update(path.read_bytes() if path.exists() else b"")
    return digest.hexdigest()[:8]


def version_assets(markup: str, version: str) -> str:
    return ASSET_REF_RE.sub(lambda m: "%s?v=%s" % (m.group(1), version), markup)


def site_version(root: pathlib.Path, index_html: str, docs_dir: pathlib.Path, template: str) -> str:
    """整站内容指纹：样式、脚本、构建脚本、模板、首页（去掉版本号本身）、docs/ 下所有源文件。
    任何一处改动都会让它变化，页面里的 meta 与 version.json 随之不同，旧缓存页面就会自愈。"""
    digest = hashlib.sha256()
    for rel in VERSIONED_ASSETS + (TEMPLATE, "tools/build_site.py"):
        path = root / rel
        digest.update(rel.encode())
        digest.update(path.read_bytes() if path.exists() else b"")
    digest.update(SITE_VERSION_RE.sub("", ASSET_REF_RE.sub(r"\1", index_html)).encode())
    digest.update(template.replace("{{version}}", "").encode())
    if docs_dir.exists():
        for path in sorted(docs_dir.rglob("*")):
            if path.is_file() and not is_skipped(path):
                digest.update(path.relative_to(docs_dir).as_posix().encode())
                digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def stamp_version(markup: str, version: str) -> str:
    markup = markup.replace('content="{{version}}"', 'content="%s"' % version)   # 模板里的占位
    if SITE_VERSION_RE.search(markup):
        return SITE_VERSION_RE.sub('<meta name="site-version" content="%s">' % version, markup, count=1)
    return markup.replace('<meta charset="UTF-8">',
                          '<meta charset="UTF-8">\n  <meta name="site-version" content="%s">' % version, 1)


def render_rows(docs: list, indent: str = "        ") -> str:
    if not docs:
        return (f'{indent}<li class="is-empty">\n'
                f'{indent}  <span class="d">—</span>\n'
                f'{indent}  <span class="t">暂无文档。<b>把 markdown 放进 docs/，这里就多一行</b>：'
                f'日期在左，标题占主栏，类型靠右。</span>\n'
                f'{indent}  <span class="k">—</span>\n'
                f'{indent}</li>')
    rows = []
    for doc in docs:
        href = urllib.parse.quote(doc["out_rel"])
        rows.append(
            f'{indent}<li>\n'
            f'{indent}  <span class="d">{doc["date"]}</span>\n'
            f'{indent}  <span class="t"><a href="{href}">{html.escape(doc["title"])}</a></span>\n'
            f'{indent}  <span class="k">{html.escape(doc["type"])}</span>\n'
            f'{indent}</li>')
    return "\n".join(rows)


def rebuild_index(index_html: str, docs: list) -> str:
    pattern = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END), re.S)
    new = pattern.sub(BEGIN + "\n" + render_rows(docs) + "\n" + END, index_html, count=1)
    new = re.sub(r'(<span class="micro">)共 \d+ 份文档(</span>)',
                 lambda m: f"{m.group(1)}共 {len(docs)} 份文档{m.group(2)}", new, count=1)
    return new


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--docs", default="docs")
    ap.add_argument("--index", default="index.html")
    ap.add_argument("--check", action="store_true", help="只检查是否需要更新")
    args = ap.parse_args()

    root = pathlib.Path(args.root).resolve()
    docs_dir = root / args.docs
    index_path = root / args.index
    template_path = root / TEMPLATE

    for required in (index_path, template_path):
        if not required.exists():
            print(f"缺少 {required}", file=sys.stderr)
            return 1
    index_html = index_path.read_text(encoding="utf-8")
    if BEGIN not in index_html or END not in index_html:
        print(f"index.html 缺少 {BEGIN} / {END} 标记，拒绝改写", file=sys.stderr)
        return 1
    if '<ol class="docs">' not in index_html or index_html.index(END) > index_html.index("</ol>"):
        print('标记必须放在 <ol class="docs"> 内部（否则会把容器一起替换掉），拒绝改写', file=sys.stderr)
        return 1

    template = template_path.read_text(encoding="utf-8")
    docs, assets = collect(docs_dir) if docs_dir.exists() else ([], [])
    out_root = root / OUT_DIR

    # 该存在的东西
    expected: dict[pathlib.Path, str] = {}
    doc_map = {doc["src_rel"]: doc["out_rel"] for doc in docs}
    unresolved: list = []
    version = asset_version(root)
    site_v = site_version(root, index_html, docs_dir, template)
    for doc in docs:
        page = version_assets(render_doc_page(doc, template, doc_map, args.docs, unresolved), version)
        expected[(root / doc["out_rel"])] = stamp_version(page, site_v)
    for src, out_rel in assets:
        expected[root / out_rel] = None            # None = 直接复制字节

    new_index = stamp_version(version_assets(rebuild_index(index_html, docs), version), site_v)
    expected[root / VERSION_JSON] = '{"v": "%s"}\n' % site_v

    # 对比现状，列出变化
    changes = []
    if new_index != index_html:
        changes.append(index_path.name)
    for target, content in expected.items():
        if content is None:
            if not target.exists() or target.read_bytes() != target_src_bytes(target, root, assets):
                changes.append(str(target.relative_to(root).as_posix()))
        elif not target.exists() or target.read_text(encoding="utf-8") != content:
            changes.append(str(target.relative_to(root).as_posix()))
    stale = [p for p in (out_root.rglob("*") if out_root.exists() else [])
             if p.is_file() and p.name not in KEEP and p not in expected]

    print(f"文档 {len(docs)} 份，附件 {len(assets)} 个")
    for doc in docs:
        print(f"   {doc['date']}  {doc['type']:<4} {doc['title']}  → {doc['out_rel']}")
    print("待更新：%s" % (", ".join(changes) or "无"))
    if unresolved:
        print("提醒：这些站内链接指向不存在的文档，原样保留了 —— %s" % "; ".join(sorted(set(unresolved))))
    print("待删除的旧文件：%s" % (", ".join(sorted(p.as_posix() for p in stale)) or "无"))

    if args.check:
        return 3 if (changes or stale) else 0

    # 写盘
    index_path.write_text(new_index, encoding="utf-8", newline="\n")
    for target, content in expected.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        if content is None:
            target.write_bytes(target_src_bytes(target, root, assets))
        else:
            target.write_text(content, encoding="utf-8", newline="\n")
    for path in stale:
        path.unlink()
        parent = path.parent
        while parent != out_root and parent.exists() and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent
    if not out_root.exists():
        out_root.mkdir(parents=True, exist_ok=True)
    (out_root / ".gitkeep").touch()
    print("已写回 %s 与 %s/" % (index_path.name, OUT_DIR))
    return 0


def target_src_bytes(target: pathlib.Path, root: pathlib.Path, assets: list) -> bytes:
    """通过输出路径反查源附件字节。"""
    for src, out_rel in assets:
        if (root / out_rel) == target:
            return src.read_bytes()
    return b""


if __name__ == "__main__":
    sys.exit(main())
