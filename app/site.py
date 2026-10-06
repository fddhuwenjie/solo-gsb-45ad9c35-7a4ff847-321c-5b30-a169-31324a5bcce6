"""站点读取（/site）时的呈现层 href 改写。

存储在 SQLite 中的页面正文与 ``/pages`` 返回的内容（含历史修订快照）始终
保持发布时的原样；只有 ``/site`` 返回 HTML 时在内存中改写：

- 绝对站内 href（以 ``/`` 开头）加上 ``/site`` 前缀，使其指向站点读取路由下
  可读取的页面（``/docs/guide.html?lang=zh#intro`` ->
  ``/site/docs/guide.html?lang=zh#intro``），查询串与 ``#片段`` 原文保留；
- 相对链接（浏览器以 ``/site/...`` 为基准解析，自然落在前缀下）、纯片段
  （``#x``）、纯查询（``?x``）、外部链接与非链接 HTML 一律不改。

改写复用 :func:`app.relocate.rewrite_anchor_hrefs`，只触碰 ``<a>`` 标签的
href 属性值，其余字节（正文、注释、其他标签、属性排版、HTML 实体）原样保留。
"""

from __future__ import annotations

from .linkcheck import is_external
from .relocate import _split_href, rewrite_anchor_hrefs

# 站点读取路由前缀：绝对站内 href 改写后指向该前缀下的可读页面。
SITE_PREFIX = "/site"


def _prefix_absolute_href(raw: str) -> str | None:
    """绝对站内 href 加 /site 前缀（查询串与片段原文保留）；其余返回 None（不改）。"""
    h = raw.strip()
    if not h or is_external(h):
        return None
    path_part, query, fragment = _split_href(h)
    if not path_part.startswith("/"):
        return None  # 相对链接 / 纯片段 / 纯查询：保持原样
    return SITE_PREFIX + path_part + query + fragment


def rewrite_site_hrefs(html: str) -> str:
    """返回把绝对站内 ``<a href>`` 改写为 /site 前缀地址后的 HTML。"""
    return rewrite_anchor_hrefs(html, _prefix_absolute_href)
