import json, sys, pathlib
from playwright.sync_api import sync_playwright
root = pathlib.Path(__file__).resolve().parent.parent
posts = json.loads((root/"posts"/"queue.json").read_text())
tpl = (root/"tools"/"banner.html").read_text()
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium", args=["--no-sandbox"])
    pg = b.new_page(viewport={"width":1080,"height":1350})
    for post in posts:
        html = (tpl.replace("{{KICKER}}", post["kicker"]).replace("{{HEADLINE}}", post["headline"])
                   .replace("{{SUB}}", post["sub"]).replace("{{CTA}}", post["cta"]))
        pg.set_content(html)
        pg.screenshot(path=str(root/"posts"/f"{post['id']}.jpg"), type="jpeg", quality=92)
    b.close()
