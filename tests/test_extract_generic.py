from sidecar.extract.generic import extract_from_text, merge_facts


def test_extract_from_text_finds_core_entities_without_url_credential_false_positive():
    text = """
    Open port 443/tcp on 10.10.10.5 running https.
    Visit https://app.example.com/login and contact ops@example.com.
    username alice password hunter2
    Server: nginx/1.25.3
    CVE-2024-12345 caused a timeout.
    """

    facts = extract_from_text(text)

    assert facts["entities"]["ips"] == ["10.10.10.5"]
    assert facts["entities"]["urls"] == ["https://app.example.com/login"]
    assert facts["entities"]["emails"] == ["ops@example.com"]
    assert facts["vulns"]["cves"] == ["CVE-2024-12345"]
    assert facts["artifacts"]["ports"] == [443]
    assert "https://app.example.com/login" not in facts["creds"]["pairs"]
    assert facts["creds"]["pairs"] == ["alice:hunter2"]
    assert "urls:1" in facts["indicators"]
    assert "creds:1" in facts["indicators"]


def test_merge_facts_extends_nested_lists_without_duplicates():
    base = extract_from_text("host 10.0.0.1 open port 22 ssh")
    incoming = extract_from_text("host 10.0.0.1 open port 443 https CVE-2024-55555")

    merged = merge_facts(base, incoming)

    assert merged["entities"]["ips"] == ["10.0.0.1"]
    assert merged["artifacts"]["ports"] == [22, 443]
    assert merged["artifacts"]["services"] == ["ssh", "https"]
    assert merged["vulns"]["cves"] == ["CVE-2024-55555"]
