"""
SQLite Prompt 存储：基于 SQLite 数据库的持久化 Prompt 管理。

适合生产环境，Prompt 模板和版本持久化到数据库，重启不丢失。
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.common.constants import DATA_DIR
from src.prompt_manager.base import (
    PromptManager,
    PromptTemplate,
    PromptVersion,
    extract_variables,
    render_prompt,
)
from src.prompt_manager.registry import prompt_manager_registry
from src.utils.logger import get_logger

logger = get_logger("gateway.prompt_manager.sqlite")


@prompt_manager_registry.register("sqlite")
class SQLitePromptManager(PromptManager):
    """SQLite Prompt 管理器。

    参数:
        provider: 实现名
        db_path: SQLite 数据库文件路径
        **kwargs: 其他配置（忽略）
    """

    def __init__(
        self,
        provider: str = "sqlite",
        db_path: str = "data/prompts.db",
        **kwargs,
    ) -> None:
        # 解析相对路径
        path = Path(db_path)
        if not path.is_absolute():
            path = DATA_DIR / path
        path.parent.mkdir(parents=True, exist_ok=True)

        self.db_path = str(path)
        self._lock = threading.Lock()
        self._init_db()
        logger.info("SQLitePromptManager 初始化: db=%s", self.db_path)

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """初始化数据库表结构。"""
        with self._lock, self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS prompts (
                    name TEXT PRIMARY KEY,
                    description TEXT DEFAULT '',
                    current_version TEXT DEFAULT '',
                    created_at REAL DEFAULT 0,
                    updated_at REAL DEFAULT 0,
                    tags TEXT DEFAULT '[]',
                    metadata TEXT DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS prompt_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prompt_name TEXT NOT NULL,
                    version TEXT NOT NULL,
                    content TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    created_at REAL DEFAULT 0,
                    created_by TEXT DEFAULT '',
                    variables TEXT DEFAULT '[]',
                    metadata TEXT DEFAULT '{}',
                    UNIQUE(prompt_name, version),
                    FOREIGN KEY (prompt_name) REFERENCES prompts(name) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_versions_prompt ON prompt_versions(prompt_name);
            """)
            conn.commit()

    def _row_to_template(self, row: sqlite3.Row, versions: Optional[List[PromptVersion]] = None) -> PromptTemplate:
        return PromptTemplate(
            name=row["name"],
            description=row["description"],
            current_version=row["current_version"],
            versions=versions or [],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            tags=json.loads(row["tags"]),
            metadata=json.loads(row["metadata"]),
        )

    def _row_to_version(self, row: sqlite3.Row) -> PromptVersion:
        return PromptVersion(
            version=row["version"],
            content=row["content"],
            description=row["description"],
            created_at=row["created_at"],
            created_by=row["created_by"],
            variables=json.loads(row["variables"]),
            metadata=json.loads(row["metadata"]),
        )

    def create_prompt(
        self,
        name: str,
        content: str,
        description: str = "",
        tags: Optional[List[str]] = None,
        created_by: str = "",
    ) -> PromptTemplate:
        now = time.time()
        variables = extract_variables(content)
        version = "1.0"

        with self._lock, self._get_conn() as conn:
            # 检查是否已存在
            existing = conn.execute("SELECT name FROM prompts WHERE name=?", (name,)).fetchone()
            if existing:
                raise ValueError(f"Prompt '{name}' 已存在")

            conn.execute(
                """INSERT INTO prompts (name, description, current_version, created_at, updated_at, tags, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (name, description, version, now, now, json.dumps(tags or []), json.dumps({})),
            )
            conn.execute(
                """INSERT INTO prompt_versions (prompt_name, version, content, description, created_at, created_by, variables, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (name, version, content, "初始版本", now, created_by, json.dumps(variables), json.dumps({})),
            )
            conn.commit()

        logger.info("创建 Prompt: %s (v%s)", name, version)
        return self.get_prompt(name)  # type: ignore[return-value]

    def get_prompt(self, name: str) -> Optional[PromptTemplate]:
        with self._lock, self._get_conn() as conn:
            row = conn.execute("SELECT * FROM prompts WHERE name=?", (name,)).fetchone()
            if row is None:
                return None
            version_rows = conn.execute(
                "SELECT * FROM prompt_versions WHERE prompt_name=? ORDER BY created_at",
                (name,),
            ).fetchall()
            versions = [self._row_to_version(v) for v in version_rows]
            return self._row_to_template(row, versions)

    def list_prompts(self, tag: Optional[str] = None) -> List[PromptTemplate]:
        with self._lock, self._get_conn() as conn:
            if tag:
                rows = conn.execute("SELECT * FROM prompts ORDER BY updated_at DESC").fetchall()
                templates = []
                for row in rows:
                    t = self._row_to_template(row)
                    if tag in t.tags:
                        templates.append(t)
                return templates
            else:
                rows = conn.execute("SELECT * FROM prompts ORDER BY updated_at DESC").fetchall()
                return [self._row_to_template(r) for r in rows]

    def update_prompt(
        self,
        name: str,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> bool:
        with self._lock, self._get_conn() as conn:
            existing = conn.execute("SELECT name FROM prompts WHERE name=?", (name,)).fetchone()
            if existing is None:
                return False

            updates = []
            params: List[Any] = []
            if description is not None:
                updates.append("description=?")
                params.append(description)
            if tags is not None:
                updates.append("tags=?")
                params.append(json.dumps(tags))
            updates.append("updated_at=?")
            params.append(time.time())
            params.append(name)

            conn.execute(f"UPDATE prompts SET {', '.join(updates)} WHERE name=?", params)
            conn.commit()
        logger.info("更新 Prompt: %s", name)
        return True

    def delete_prompt(self, name: str) -> bool:
        with self._lock, self._get_conn() as conn:
            cursor = conn.execute("DELETE FROM prompts WHERE name=?", (name,))
            conn.execute("DELETE FROM prompt_versions WHERE prompt_name=?", (name,))
            conn.commit()
            deleted = cursor.rowcount > 0
        if deleted:
            logger.info("删除 Prompt: %s", name)
        return deleted

    def create_version(
        self,
        name: str,
        content: str,
        description: str = "",
        version: Optional[str] = None,
        created_by: str = "",
    ) -> Optional[PromptVersion]:
        with self._lock, self._get_conn() as conn:
            existing = conn.execute("SELECT name FROM prompts WHERE name=?", (name,)).fetchone()
            if existing is None:
                return None

            # 自动生成版本号
            if version is None:
                last_row = conn.execute(
                    "SELECT version FROM prompt_versions WHERE prompt_name=? ORDER BY created_at DESC LIMIT 1",
                    (name,),
                ).fetchone()
                if last_row:
                    try:
                        major, minor = last_row["version"].split(".")
                        version = f"{major}.{int(minor) + 1}"
                    except (ValueError, IndexError):
                        version = f"{int(time.time())}"
                else:
                    version = "1.0"

            # 检查版本是否已存在
            ver_exists = conn.execute(
                "SELECT id FROM prompt_versions WHERE prompt_name=? AND version=?",
                (name, version),
            ).fetchone()
            if ver_exists:
                raise ValueError(f"Prompt '{name}' 版本 '{version}' 已存在")

            now = time.time()
            variables = extract_variables(content)
            conn.execute(
                """INSERT INTO prompt_versions (prompt_name, version, content, description, created_at, created_by, variables, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (name, version, content, description, now, created_by, json.dumps(variables), json.dumps({})),
            )
            conn.execute("UPDATE prompts SET updated_at=? WHERE name=?", (now, name))
            conn.commit()

        logger.info("创建 Prompt 版本: %s v%s", name, version)
        return self.get_version(name, version)

    def get_version(self, name: str, version: str) -> Optional[PromptVersion]:
        with self._lock, self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM prompt_versions WHERE prompt_name=? AND version=?",
                (name, version),
            ).fetchone()
            if row is None:
                return None
            return self._row_to_version(row)

    def list_versions(self, name: str) -> List[PromptVersion]:
        with self._lock, self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM prompt_versions WHERE prompt_name=? ORDER BY created_at",
                (name,),
            ).fetchall()
            return [self._row_to_version(r) for r in rows]

    def set_current_version(self, name: str, version: str) -> bool:
        with self._lock, self._get_conn() as conn:
            ver_exists = conn.execute(
                "SELECT id FROM prompt_versions WHERE prompt_name=? AND version=?",
                (name, version),
            ).fetchone()
            if ver_exists is None:
                return False
            conn.execute(
                "UPDATE prompts SET current_version=?, updated_at=? WHERE name=?",
                (version, time.time(), name),
            )
            conn.commit()
        logger.info("设置当前版本: %s v%s", name, version)
        return True

    def render(
        self,
        name: str,
        variables: Dict[str, Any],
        version: Optional[str] = None,
    ) -> Optional[str]:
        template = self.get_prompt(name)
        if template is None:
            return None

        ver = version or template.current_version
        if not ver:
            return None

        prompt_version = self.get_version(name, ver)
        if prompt_version is None:
            return None

        return render_prompt(prompt_version.content, variables)
