"""L'atelier dans un vrai navigateur (I-WEB-04) : ce que les tests HTTP ne voient pas, le JavaScript exécuté.

Chromium piloté par Playwright, sans fenêtre, contre un serveur lancé dans un fil. Facultatif : sauté si Playwright ou
Chromium manquent (`pip install -e .[browser]`, puis `python -m playwright install chromium`).

Une page rechargée perd ses variables : `window.__same` posée au début prouve, si elle est toujours là, que la page n'a
pas été rechargée.
"""

from __future__ import annotations

import socket
import threading
import time

import pytest

pytest.importorskip("uvicorn")
sync_api = pytest.importorskip("playwright.sync_api")

FILLER = "Les brumes montent du port chaque matin, et les marchands comptent leurs caisses sur les quais."
TEXT = "# Notes du baron\n\n" + "\n\n".join(
    [f"{FILLER} Paragraphe {i}." for i in range(1, 13)]
    + ["Bertille tient l'échoppe du quai. Le Loup de cendre hante Hautval.",
       "Odon de Brume est le baron de Brume ; on le dit massif."]) + "\n"


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except sync_api.Error:
            pytest.skip("Chromium absent : python -m playwright install chromium")
        yield b
        b.close()


@pytest.fixture
def served(tmp_path):
    import uvicorn
    from test_service import make_world
    from worldkit.service.session import Session
    from worldkit.web import create_app
    db = tmp_path / "valmont.db"
    make_world(db)
    with Session(db) as s:
        doc_id = s.call("atelier.import", {"text": TEXT}).output["doc_id"]
        s.call("atelier.run", {"doc_id": doc_id})
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(db), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}", doc_id, db
    server.should_exit = True
    thread.join(5)


@pytest.fixture
def page(browser):
    context = browser.new_context(viewport={"width": 1100, "height": 500})
    yield context.new_page()
    context.close()


def test_a_gesture_keeps_the_page_and_its_scroll_I_WEB_04(served, page):
    base, doc_id, _ = served
    page.goto(f"{base}/atelier/{doc_id}")
    page.evaluate("window.__same = 'oui'")
    odon = page.locator(".passage").last.locator("a.ann", has_text="Odon de Brume")
    odon.scroll_into_view_if_needed()
    y = page.evaluate("scrollY")
    assert y > 0
    odon.click()
    page.wait_for_url("**?ann=*")  # l'adresse suit la sélection (I-WEB-01)
    sync_api.expect(page.locator(".panel h3").first).to_contain_text("Odon de Brume")
    assert page.evaluate("window.__same") == "oui" and abs(page.evaluate("scrollY") - y) < 5
    page.get_by_role("button", name="Garder", exact=True).click()
    page.wait_for_url(f"{base}/atelier/{doc_id}")  # l'adresse de la source, jamais celle de l'envoi
    sync_api.expect(page.locator(".passage").last.locator("a.ann-author")).to_have_count(1)
    assert page.evaluate("window.__same") == "oui" and abs(page.evaluate("scrollY") - y) < 50


def test_selecting_a_word_fills_the_add_form_and_adds_without_reloading(served, page):
    base, doc_id, _ = served
    page.goto(f"{base}/atelier/{doc_id}")
    page.evaluate("window.__same = 'oui'")
    page.evaluate("""() => {
        const text = [...document.querySelectorAll('.ptext')].find(e => e.textContent.includes('Bertille'));
        const walker = document.createTreeWalker(text, NodeFilter.SHOW_TEXT);
        let node; while ((node = walker.nextNode()) && !node.textContent.includes('Bertille')) {}
        const range = document.createRange(), at = node.textContent.indexOf('Bertille');
        range.setStart(node, at); range.setEnd(node, at + 'Bertille'.length);
        const sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(range);
        document.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
    }""")
    sync_api.expect(page.locator("#add-text")).to_contain_text("« Bertille »")
    sync_api.expect(page.locator("#add-button")).to_be_enabled()
    page.locator("#add-button").click()
    sync_api.expect(page.locator("a.ann-author", has_text="Bertille")).to_have_count(1)
    assert page.evaluate("window.__same") == "oui"


def test_a_model_pass_is_followed_live_then_shown_without_reloading_I_WEB_04(served, page, monkeypatch):
    from worldkit.periphery import llm
    from worldkit.periphery.llm.usage import UsageMeter
    from worldkit.service import jobs
    from worldkit.service.session import Session
    base, doc_id, db = served
    gate = threading.Event()

    class Held:
        """Un modèle simulé qui attend que le test le libère : la passe reste « en cours » le temps de regarder."""
        meter = UsageMeter()

        def complete(self, system, prompt, schema):
            assert gate.wait(30)
            return {"notes": []}
    monkeypatch.setattr(llm, "make_adapter", lambda profile: Held())
    page.goto(f"{base}/atelier/{doc_id}")
    page.locator("form:has(input[name=layer][value=notes]) button").click()  # estimation (I-LLM-01)
    page.get_by_role("button", name="Confirmer et lancer").click()
    sync_api.expect(page.locator("#job-live")).to_be_visible()
    sync_api.expect(page.locator("#job-step")).to_have_text("descriptions")
    page.evaluate("window.__same = 'oui'")
    run_id = int(page.locator("#job-live").get_attribute("data-run"))
    with Session(db) as s:  # une progression écrite par la tâche arrive d'elle-même (Server-Sent Events)
        s.runs.set_progress(run_id, {"stage": "critic", "label": "critique", "done": 1, "total": 3, "calls": 4})
    sync_api.expect(page.locator("#job-step")).to_have_text("critique, appel 2 sur 3")
    sync_api.expect(page.locator("#job-calls")).to_contain_text("4 appel(s) faits")
    gate.set()
    jobs.wait(db, run_id, 30)
    sync_api.expect(page.locator("#job-live")).to_have_count(0)  # fin : la zone de travail est remplacée une fois
    sync_api.expect(page.get_by_text("bribe(s) de description proposée(s)")).to_be_visible()
    assert page.evaluate("window.__same") == "oui"
