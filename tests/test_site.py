"""/site 站点读取的绝对链接改写回归测试。

发布含 ``<a href="/docs/guide.html?lang=zh#intro">`` 的 /index.html 与真实
目标页后，/site 返回的 HTML 中绝对站内 href 指向 /site 下可读取的页面
（查询串与片段原文保留）；相对链接、纯片段、纯查询、外部链接与非链接 HTML
保持原样；/pages 返回的正文与历史修订快照不被读取改写；搬迁后链接仍到达
新页面，旧址保持一次 308 直达 /site 下的真实页。

运行：pytest tests/test_site.py
"""

from __future__ import annotations

import os
import tempfile

import pytest

# 必须在导入 app 之前指定数据库文件
_TMP = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP.close()
os.environ["DOCS_DB_PATH"] = _TMP.name

from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.main import app  # noqa: E402
from app.site import rewrite_site_hrefs  # noqa: E402


@pytest.fixture(scope="module")
def client():
    # 与其他测试模块隔离：直接改用本模块专属的数据库文件
    db.DB_PATH = _TMP.name
    db.init_db()
    with TestClient(app) as c:
        yield c


def publish(client, rev, changes):
    resp = client.post("/publish", json={"expected_revision": rev, "changes": changes})
    assert resp.status_code == 200, resp.text
    return resp.json()["revision"]


INDEX_HTML = (
    '<h1 id="top">Home</h1>\n'
    '<a href="/docs/guide.html?lang=zh#intro">abs query+frag</a>\n'
    '<a href="/docs/guide.html">abs plain</a>\n'
    '<a href="/">root</a> <a href="/#top">root frag</a>\n'
    '<a href="docs/guide.html">relative</a>\n'
    '<a href="#top">pure frag</a> <a href="?v=2">pure query</a>\n'
    '<a href="https://ext.com/x">ext</a> <a href="//cdn.example/lib.js">cdn</a>'
    ' <a href="mailto:a@b.com">mail</a>\n'
    "<a  href = '/docs/guide.html#intro' >single quoted</a>\n"
    '<a href="/docs/guide.html?a=1&amp;b=2">entity query</a>\n'
    '<a data-href="/docs/guide.html">no href attr</a>\n'
    '<img src="/docs/guide.html">\n'
    '<p>正文中的 /docs/guide.html 不改</p>\n'
    '<!-- <a href="/docs/guide.html">commented</a> -->\n'
)

GUIDE_HTML = (
    '<h2 id="intro">Guide</h2>'
    '<a href="../index.html#top">home rel</a> '
    '<a href="/index.html">home abs</a>'
)


# ---------- 改写纯函数 ----------

def test_rewrite_unit_edges():
    # 绝对站内 href 加 /site 前缀，查询串与片段原文保留
    assert rewrite_site_hrefs('<a href="/a.html?x=1#f">t</a>') == \
        '<a href="/site/a.html?x=1#f">t</a>'
    assert rewrite_site_hrefs('<a href="/">t</a>') == '<a href="/site/">t</a>'
    # 相对链接 / 纯片段 / 纯查询 / 外部链接 / 空 href 不改
    assert rewrite_site_hrefs('<a href="b.html">t</a>') == '<a href="b.html">t</a>'
    assert rewrite_site_hrefs('<a href="#f">t</a>') == '<a href="#f">t</a>'
    assert rewrite_site_hrefs('<a href="?x=1">t</a>') == '<a href="?x=1">t</a>'
    assert rewrite_site_hrefs('<a href="//cdn.example/x.js">t</a>') == \
        '<a href="//cdn.example/x.js">t</a>'
    assert rewrite_site_hrefs('<a href="https://e.com/a.html">t</a>') == \
        '<a href="https://e.com/a.html">t</a>'
    assert rewrite_site_hrefs('<a href="">t</a>') == '<a href="">t</a>'
    # 非链接 HTML（无 href 的 <a>、其他标签、正文文本）不改
    assert rewrite_site_hrefs('<a name="x">t</a>') == '<a name="x">t</a>'
    assert rewrite_site_hrefs('<p>/a.html</p>') == '<p>/a.html</p>'
    assert rewrite_site_hrefs('<img src="/a.png">') == '<img src="/a.png">'


# ---------- 建景：发布入口页（含绝对站内链接）与真实目标页 ----------

def test_01_publish_index_with_absolute_href(client):
    rev = publish(client, 0, [
        {"op": "upsert", "path": "/index.html", "content": INDEX_HTML},
        {"op": "upsert", "path": "/docs/guide.html", "content": GUIDE_HTML},
    ])
    assert rev == 1  # 发布校验通过（绝对链接指向真实页面与现存锚点）


# ---------- /site 返回的 HTML：绝对站内 href 指向 /site 下可读页面 ----------

def test_02_site_rewrites_absolute_hrefs(client):
    resp = client.get("/site/index.html")
    assert resp.status_code == 200
    body = resp.text
    # 绝对站内 href 加 /site 前缀，查询串与 #片段 原文保留
    assert 'href="/site/docs/guide.html?lang=zh#intro"' in body
    assert 'href="/site/docs/guide.html"' in body
    assert 'href="/site/"' in body
    assert 'href="/site/#top"' in body
    # 单引号与等号两侧空白的排版保留，实体查询串原文保留
    assert "href = '/site/docs/guide.html#intro'" in body
    assert 'href="/site/docs/guide.html?a=1&amp;b=2"' in body
    # 改写后的地址在站点路由下真实可读（回归：不再是 /docs/guide.html -> 404）
    assert client.get("/site/docs/guide.html?lang=zh").status_code == 200


def test_03_site_keeps_relative_pure_external_and_non_link(client):
    body = client.get("/site/index.html").text
    # 相对链接、纯片段、纯查询保持原样（浏览器以 /site/... 为基准解析）
    assert 'href="docs/guide.html"' in body
    assert 'href="#top"' in body
    assert 'href="?v=2"' in body
    # 外部链接保持原样
    assert 'href="https://ext.com/x"' in body
    assert 'href="//cdn.example/lib.js"' in body
    assert 'href="mailto:a@b.com"' in body
    # 非链接 HTML 保持原样：无 href 的 <a>、其他标签属性、正文文本、注释
    assert '<a data-href="/docs/guide.html">no href attr</a>' in body
    assert '<img src="/docs/guide.html">' in body
    assert '<p>正文中的 /docs/guide.html 不改</p>' in body
    assert '<!-- <a href="/docs/guide.html">commented</a> -->' in body


def test_04_site_subpage_rewrites_absolute_keeps_relative(client):
    body = client.get("/site/docs/guide.html").text
    assert 'href="../index.html#top"' in body  # 相对链接不改
    assert 'href="/site/index.html"' in body  # 绝对链接加前缀
    # 入口页的 /site 与 /site/ 同样返回改写后的 HTML
    assert 'href="/site/docs/guide.html' in client.get("/site").text
    assert 'href="/site/docs/guide.html' in client.get("/site/").text


# ---------- 存储与快照不被读取改写 ----------

def test_05_pages_and_snapshots_keep_original_content(client):
    current = client.get("/pages").json()
    assert current["revision"] == 1
    index = current["pages"]["/index.html"]
    assert index == INDEX_HTML  # 正文与发布时逐字节一致
    assert 'href="/docs/guide.html?lang=zh#intro"' in index
    assert "/site/" not in index
    assert current["pages"]["/docs/guide.html"] == GUIDE_HTML

    rev1 = client.get("/pages", params={"revision": 1}).json()["pages"]
    assert rev1["/index.html"] == INDEX_HTML  # 历史修订快照同样原样


# ---------- 未知地址仍 404 ----------

def test_06_unknown_addresses_still_404(client):
    assert client.get("/site/unknown.html").status_code == 404
    # 不带 /site 前缀的绝对路径仍不是站点路由（原始 404 场景）
    assert client.get("/docs/guide.html").status_code == 404


# ---------- 搬迁后：链接仍到达新页面，旧址一次 308 直达 ----------

def test_07_relocate_keeps_links_reaching_new_page(client):
    resp = client.post("/relocate", json={
        "expected_revision": 1,
        "old_path": "/docs/guide.html",
        "new_path": "/manual/guide.html",
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["revision"] == 2

    body = client.get("/site/index.html").text
    # 存储中的绝对 href 已被搬迁改指新页，/site 再加前缀：仍到达新页面
    assert 'href="/site/manual/guide.html?lang=zh#intro"' in body
    # 存储中的相对 href 被搬迁改写为 manual/guide.html，/site 下原样保留
    assert 'href="manual/guide.html"' in body
    assert client.get("/site/manual/guide.html?lang=zh").status_code == 200

    # 旧址保持一次 308 直达 /site 下的真实页（不形成跳转链）
    resp = client.get("/site/docs/guide.html", follow_redirects=False)
    assert resp.status_code == 308
    assert resp.headers["location"] == "/site/manual/guide.html"
    resp = client.get("/site/docs/guide.html")
    assert resp.status_code == 200
    assert len(resp.history) == 1  # 只经过一次 308
    assert '<h2 id="intro">Guide</h2>' in resp.text


def test_08_snapshots_unaffected_by_relocate_and_serving(client):
    # 搬迁前的历史快照：旧路径与原始链接原样保留
    rev1 = client.get("/pages", params={"revision": 1}).json()["pages"]
    assert rev1["/index.html"] == INDEX_HTML
    assert rev1["/docs/guide.html"] == GUIDE_HTML

    # 搬迁后的快照：存储正文由搬迁改写（指向新页），但不含 /site 前缀
    rev2 = client.get("/pages", params={"revision": 2}).json()["pages"]
    assert "/docs/guide.html" not in rev2
    assert 'href="/manual/guide.html?lang=zh#intro"' in rev2["/index.html"]
    assert "/site/" not in rev2["/index.html"]
    assert client.get("/pages").json()["pages"] == rev2


# ---------- 现有 API 继续可用 ----------

def test_09_existing_apis_still_work(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/revision").json() == {"revision": 2}
    assert client.get("/redirects").json()["redirects"] == {
        "/docs/guide.html": "/manual/guide.html"
    }
    # 过期修订号仍按既有规则返回 409
    resp = client.post("/publish", json={"expected_revision": 1, "changes": []})
    assert resp.status_code == 409
    assert resp.json()["current"] == 2
    # 发布校验仍然生效：链接到不存在的页面 -> 422
    resp = client.post("/publish", json={
        "expected_revision": 2,
        "changes": [{"op": "upsert", "path": "/x.html",
                     "content": '<a href="/ghost.html">g</a>'}],
    })
    assert resp.status_code == 422
    assert client.get("/revision").json() == {"revision": 2}
