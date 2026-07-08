from sidecar.rag.retriever import ingest_html, retrieve


def test_ingest_html_chunks_and_retrieves_with_temp_database(tmp_path, monkeypatch):
    monkeypatch.setenv("AIC_RAG_DB", str(tmp_path / "rag.sqlite"))
    notes = tmp_path / "notes.html"
    notes.write_text(
        """
        <html><body>
          <h1>Web</h1>
          <p>Directory brute forcing and login testing.</p>
          <h2>Kerberos</h2>
          <p>Enumerate users before password spraying.</p>
        </body></html>
        """,
        encoding="utf-8",
    )

    assert ingest_html(str(notes)) == 2

    hits = retrieve("Kerberos", k=1)

    assert len(hits) == 1
    assert hits[0]["title"] == "Kerberos"
    assert "Enumerate users" in hits[0]["text"]
