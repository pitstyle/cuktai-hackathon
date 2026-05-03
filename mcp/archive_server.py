#!/usr/bin/env python3
"""CUKTAI Archive MCP Server — gives Hermes agents access to the archive database.

Implements Model Context Protocol (stdio) for Hermes Agent integration.
Config in Hermes config.yaml:
  mcp_servers:
    cuktai_archive:
      command: "python3"
      args: ["/home/macstorm/cuktai/repo/mcp/archive_server.py"]
"""

import json
import os
import sys
import psycopg2
import psycopg2.extras

DB_CONFIG = {
    "dbname": "cuktai_archive",
    "user": "cuktai",
    "password": os.environ.get("CUKTAI_DB_PASS", "cuktai"),
    "host": "localhost",
    "port": 5434,
}


OLLAMA_URL = "http://localhost:11434/api/embeddings"
EMBED_MODEL = "nomic-embed-text"


def get_conn():
    return psycopg2.connect(**DB_CONFIG)


def get_embedding(text):
    """Get embedding from Ollama for semantic search."""
    import requests
    text = text[:8000] if text else ""
    if not text.strip():
        return None
    try:
        resp = requests.post(OLLAMA_URL, json={"model": EMBED_MODEL, "prompt": text}, timeout=10)
        resp.raise_for_status()
        return resp.json().get("embedding")
    except Exception:
        return None


def search(query: str, bank: str = None, limit: int = 10) -> list:
    """Hybrid search: semantic (vector) + keyword (ILIKE). Returns best of both."""
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    results = []

    # 1. Semantic search (if embeddings available)
    emb = get_embedding(query)
    if emb:
        where_bank = "AND bank = %s" if bank else ""
        emb_str = json.dumps(emb)
        if bank:
            cur.execute(f"""
                SELECT id, bank, title, date_original, authors, location, source_type,
                       project_name, LEFT(content_text, 500) as content_preview, tags,
                       1 - (embedding <=> %s::vector) as similarity
                FROM archive_items
                WHERE embedding IS NOT NULL AND bank = %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            """, [emb_str, bank, emb_str, limit])
        else:
            cur.execute("""
                SELECT id, bank, title, date_original, authors, location, source_type,
                       project_name, LEFT(content_text, 500) as content_preview, tags,
                       1 - (embedding <=> %s::vector) as similarity
                FROM archive_items
                WHERE embedding IS NOT NULL
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            """, [emb_str, emb_str, limit])
        results = [dict(r) for r in cur.fetchall()]

    # 2. Keyword fallback/supplement
    where_kw = "AND bank = %s" if bank else ""
    params_kw = [f"%{query}%", f"%{query}%", f"%{query}%"] + ([bank] if bank else []) + [limit]
    cur.execute(f"""
        SELECT id, bank, title, date_original, authors, location, source_type,
               project_name, LEFT(content_text, 500) as content_preview, tags
        FROM archive_items
        WHERE (content_text ILIKE %s OR title ILIKE %s OR project_name ILIKE %s) {where_kw}
        ORDER BY date_original ASC NULLS LAST
        LIMIT %s
    """, params_kw)
    kw_results = [dict(r) for r in cur.fetchall()]

    # Merge: keyword FIRST (exact matches > semantic guesses), then semantic supplement
    merged = list(kw_results)
    seen_ids = {r['id'] for r in merged}
    for r in results:
        if r['id'] not in seen_ids:
            merged.append(r)
            seen_ids.add(r['id'])

    conn.close()
    return merged[:limit]


def get_project(name: str) -> list:
    """Get all records for a specific project."""
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT id, bank, title, date_original, authors, location, source_type,
               project_name, content_text, tags
        FROM archive_items
        WHERE project_name ILIKE %s OR title ILIKE %s
        ORDER BY date_original ASC NULLS LAST
    """, (f"%{name}%", f"%{name}%"))

    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_person(name: str) -> list:
    """Get person page and all projects they participated in."""
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT id, bank, title, date_original, authors, location, source_type,
               project_name, LEFT(content_text, 500) as content_preview, tags
        FROM archive_items
        WHERE %s = ANY(authors)
           OR title ILIKE %s
           OR content_text ILIKE %s
        ORDER BY date_original ASC NULLS LAST
    """, (name, f"%{name}%", f"%{name}%"))

    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_projects(bank: str = None) -> list:
    """List all unique projects in a bank."""
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    where = "WHERE bank = %s" if bank else ""
    params = (bank,) if bank else ()

    cur.execute(f"""
        SELECT DISTINCT project_name, MIN(date_original) as earliest_date,
               COUNT(*) as record_count
        FROM archive_items
        {where}
        GROUP BY project_name
        HAVING project_name IS NOT NULL
        ORDER BY earliest_date ASC NULLS LAST
    """, params)

    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_images(project_name: str = None, item_id: int = None, limit: int = 10) -> list:
    """Get images attached to archive items, filtered by project name or item ID."""
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    if item_id:
        cur.execute("""
            SELECT a.id, a.filename, a.file_path, a.mime_type, a.size_bytes,
                   a.triage_tag, i.project_name, i.title
            FROM archive_attachments a
            JOIN archive_items i ON a.archive_item_id = i.id
            WHERE a.archive_item_id = %s
              AND (a.mime_type LIKE 'image/%%' OR a.filename LIKE '%%.jpg' OR a.filename LIKE '%%.png')
            LIMIT %s
        """, [item_id, limit])
    elif project_name:
        cur.execute("""
            SELECT a.id, a.filename, a.file_path, a.mime_type, a.size_bytes,
                   a.triage_tag, i.project_name, i.title
            FROM archive_attachments a
            JOIN archive_items i ON a.archive_item_id = i.id
            WHERE i.project_name ILIKE %s
              AND (a.mime_type LIKE 'image/%%' OR a.filename LIKE '%%.jpg' OR a.filename LIKE '%%.png')
            LIMIT %s
        """, [f"%{project_name}%", limit])
    else:
        cur.execute("""
            SELECT a.id, a.filename, a.file_path, a.mime_type, a.size_bytes,
                   a.triage_tag, i.project_name, i.title
            FROM archive_attachments a
            JOIN archive_items i ON a.archive_item_id = i.id
            WHERE (a.mime_type LIKE 'image/%%' OR a.filename LIKE '%%.jpg' OR a.filename LIKE '%%.png')
            ORDER BY random()
            LIMIT %s
        """, [limit])

    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def stats(bank: str = None) -> dict:
    """Get statistics for a bank or all banks."""
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    where = "WHERE bank = %s" if bank else ""
    params = (bank,) if bank else ()

    cur.execute(f"SELECT COUNT(*) as total FROM archive_items {where}", params)
    total = cur.fetchone()["total"]

    cur.execute(f"""
        SELECT bank, COUNT(*) as records FROM archive_items
        {where} GROUP BY bank ORDER BY bank
    """, params)
    banks = [dict(r) for r in cur.fetchall()]

    cur.execute(f"""
        SELECT source_type, COUNT(*) as count FROM archive_items
        {where} GROUP BY source_type ORDER BY count DESC
    """, params)
    types = [dict(r) for r in cur.fetchall()]

    cur.execute(f"SELECT COUNT(*) as total FROM archive_attachments")
    attachments = cur.fetchone()["total"]

    conn.close()
    return {"total_items": total, "banks": banks, "source_types": types, "total_attachments": attachments}


def get_questions(project_name=None, addressed_to=None, unanswered_only=True):
    """Get investigation questions from archive_questions."""
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    conditions = []
    params = []
    if project_name:
        conditions.append("project_name ILIKE %s")
        params.append(f"%{project_name}%")
    if addressed_to:
        conditions.append("addressed_to ILIKE %s")
        params.append(f"%{addressed_to}%")
    if unanswered_only:
        conditions.append("answer IS NULL")
    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    cur.execute(f"SELECT * FROM archive_questions {where} ORDER BY created_at DESC LIMIT 50", params)
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_faces(person_name=None, project_name=None):
    """Get face sightings from archive_faces."""
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    conditions = []
    params = []
    if person_name:
        conditions.append("person_name ILIKE %s")
        params.append(f"%{person_name}%")
    if project_name:
        conditions.append("project_name ILIKE %s")
        params.append(f"%{project_name}%")
    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    cur.execute(f"SELECT * FROM archive_faces {where} ORDER BY created_at DESC LIMIT 50", params)
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_art_objects(object_name=None, project_name=None):
    """Get art objects from archive_art_objects."""
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    conditions = []
    params = []
    if object_name:
        conditions.append("object_name ILIKE %s")
        params.append(f"%{object_name}%")
    if project_name:
        conditions.append("(project_name ILIKE %s OR %s = ANY(seen_in_projects))")
        params.extend([f"%{project_name}%", project_name])
    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    cur.execute(f"SELECT * FROM archive_art_objects {where} ORDER BY created_at DESC LIMIT 50", params)
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# === MCP Protocol (stdio JSON-RPC) ===

TOOLS = [
    {
        "name": "archive_search",
        "description": "Szukaj w archiwum CUKTAI. Przeszukuje tytuły i treść. Parametr bank opcjonalny: 'cukt-archiwum' (historia 1995-2000), 'cuktai-aktualne' (2024+), lub imię agenta (baza indywidualna).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Szukana fraza"},
                "bank": {"type": "string", "description": "Bank do przeszukania (opcjonalny)"},
                "limit": {"type": "integer", "description": "Max wyników (domyślnie 10)", "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "archive_get_project",
        "description": "Pobierz wszystkie rekordy dla projektu CUKT (np. Technopera, Testy na Cyborga, Antyelekcja).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Nazwa projektu"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "archive_get_person",
        "description": "Znajdź informacje o osobie — profil i projekty w których uczestniczył/a.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Imię i nazwisko osoby"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "archive_list_projects",
        "description": "Lista wszystkich projektów w archiwum z datami i liczbą rekordów.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "bank": {"type": "string", "description": "Bank (opcjonalny)"},
            },
        },
    },
    {
        "name": "archive_stats",
        "description": "Statystyki archiwum — liczba rekordów, podział na banki i typy.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "bank": {"type": "string", "description": "Bank (opcjonalny)"},
            },
        },
    },
    {
        "name": "archive_get_images",
        "description": "Znajdź zdjęcia z archiwum. Szukaj po nazwie projektu (np. 'Technopera') lub ID rekordu. Zwraca nazwy plików, ścieżki, triage_tag i projekty. Bazowy folder: /home/macstorm/cuktai/raw/archive-usb/",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string", "description": "Nazwa projektu (np. Technopera, Antyelekcja)"},
                "item_id": {"type": "integer", "description": "ID rekordu archiwum"},
                "limit": {"type": "integer", "description": "Max wyników (domyślnie 10)", "default": 10},
            },
        },
    },
    {
        "name": "archive_get_questions",
        "description": "Pobierz pytania śledcze — otwarte pytania wygenerowane przez Archiwistę. Filtruj po projekcie lub adresacie.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string", "description": "Nazwa projektu"},
                "addressed_to": {"type": "string", "description": "Do kogo pytanie (Piotr, Mikołaj, Ewa)"},
                "unanswered_only": {"type": "boolean", "description": "Tylko bez odpowiedzi", "default": True},
            },
        },
    },
    {
        "name": "archive_get_faces",
        "description": "Pobierz rozpoznane twarze z archiwum. Filtruj po osobie lub projekcie.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "person_name": {"type": "string", "description": "Imię osoby"},
                "project_name": {"type": "string", "description": "Nazwa projektu"},
            },
        },
    },
    {
        "name": "archive_get_art_objects",
        "description": "Pobierz obiekty artystyczne z archiwum. Filtruj po nazwie lub projekcie.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "object_name": {"type": "string", "description": "Nazwa obiektu"},
                "project_name": {"type": "string", "description": "Nazwa projektu"},
            },
        },
    },
]


def handle_request(request):
    """Handle a single JSON-RPC request."""
    method = request.get("method", "")
    req_id = request.get("id")
    params = request.get("params", {})

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "cuktai-archive", "version": "1.0.0"},
            },
        }

    elif method == "notifications/initialized":
        return None  # no response needed

    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": TOOLS},
        }

    elif method == "tools/call":
        tool_name = params.get("name", "")
        args = params.get("arguments", {})

        try:
            if tool_name == "archive_search":
                result = search(args["query"], args.get("bank"), args.get("limit", 10))
            elif tool_name == "archive_get_project":
                result = get_project(args["name"])
            elif tool_name == "archive_get_person":
                result = get_person(args["name"])
            elif tool_name == "archive_list_projects":
                result = list_projects(args.get("bank"))
            elif tool_name == "archive_stats":
                result = stats(args.get("bank"))
            elif tool_name == "archive_get_images":
                result = get_images(args.get("project_name"), args.get("item_id"), args.get("limit", 10))
            elif tool_name == "archive_get_questions":
                result = get_questions(args.get("project_name"), args.get("addressed_to"), args.get("unanswered_only", True))
            elif tool_name == "archive_get_faces":
                result = get_faces(args.get("person_name"), args.get("project_name"))
            elif tool_name == "archive_get_art_objects":
                result = get_art_objects(args.get("object_name"), args.get("project_name"))
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"},
                }

            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, default=str)}],
                },
            }

        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f"Error: {str(e)}"}],
                    "isError": True,
                },
            }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main():
    """Run MCP server on stdio."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
            response = handle_request(request)
            if response:
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
        except json.JSONDecodeError:
            sys.stderr.write(f"Invalid JSON: {line}\n")
            sys.stderr.flush()


if __name__ == "__main__":
    main()
