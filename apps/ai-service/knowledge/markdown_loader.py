import re
import json
from pathlib import Path
from typing import Optional


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML-like frontmatter from markdown text.

    Returns (metadata_dict, body_without_frontmatter).
    """
    m = re.match(r'^---\s*\n(.*?)\n---\s*\n', text, re.DOTALL)
    if not m:
        return {}, text

    fm_text = m.group(1)
    body = text[m.end():]
    meta = {}
    for line in fm_text.split('\n'):
        line = line.strip()
        if ':' not in line:
            continue
        key, _, val = line.partition(':')
        key = key.strip()
        val = val.strip()
        if val.startswith('[') and val.endswith(']'):
            val = [v.strip().strip('"').strip("'") for v in val[1:-1].split(',') if v.strip()]
        meta[key] = val
    return meta, body


def _extract_json_block(text: str) -> Optional[dict]:
    """Extract the structured JSON block from the markdown body."""
    m = re.search(r'```json\s*\n(.*?)\n```', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            return None
    return None


def _split_sections(body: str) -> list[dict]:
    """Split markdown body by ## headings. Returns list of {heading, content}."""
    sections = []
    # Find the h1 title
    h1_m = re.match(r'^# (.+)$', body.strip(), re.MULTILINE)
    title = h1_m.group(1).strip() if h1_m else ""

    # Split by ## headings
    parts = re.split(r'\n## ', body)
    intro = parts[0]
    # Remove the h1 line from intro
    intro = re.sub(r'^# .+\n', '', intro).strip()

    for part in parts[1:]:
        lines = part.split('\n', 1)
        heading = lines[0].strip()
        content = lines[1].strip() if len(lines) > 1 else ''
        sections.append({"heading": heading, "content": content})

    return sections, title


class MarkdownLoader:
    """Load markdown files from the AiwearRag knowledge base.

    Each file is parsed into frontmatter metadata + body sections (split by ## headings).
    Gender is inferred from section headings (男生适配/女生适配).
    """

    def __init__(self, knowledge_dir: str):
        self.knowledge_dir = Path(knowledge_dir)

    def load_all(self) -> list[dict]:
        """Load all markdown files and return list of chunk dicts."""
        chunks = []
        for md_file in sorted(self.knowledge_dir.glob("*.md")):
            chunks.extend(self._load_file(md_file))
        return chunks

    def _load_file(self, filepath: Path) -> list[dict]:
        text = filepath.read_text(encoding="utf-8")
        meta, body = _parse_frontmatter(text)
        sections, title = _split_sections(body)
        json_block = _extract_json_block(body)

        # File-level metadata
        file_meta = {
            "file": filepath.name,
            "title": meta.get("title", title),
            "category": meta.get("category", ""),
            "tags": meta.get("tags", []),
            "source": meta.get("source", ""),
            "created": meta.get("created", ""),
        }

        chunks = []
        for sec in sections:
            heading = sec["heading"]
            content = sec["content"]
            if not content.strip():
                continue

            # Infer gender from section heading
            gender = None
            if "男生" in heading:
                gender = "male"
            elif "女生" in heading:
                gender = "female"

            chunk_meta = dict(file_meta)
            chunk_meta["section"] = heading
            if gender:
                chunk_meta["gender"] = gender
            if json_block:
                chunk_meta["recommended_items"] = json_block.get("recommended_items", [])
                chunk_meta["avoid"] = json_block.get("avoid", [])

            chunks.append({
                "id": f"{filepath.stem}_{_safe_slug(heading)}",
                "content": content,
                "metadata": chunk_meta,
            })

        return chunks


def _safe_slug(text: str) -> str:
    return re.sub(r'[^\w]', '_', text)[:30]
