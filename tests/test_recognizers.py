import json

from sidecar.recognizers.httpx_lines import parse_httpx_lines
from sidecar.recognizers.nmap_xml import parse_nmap_xml
from sidecar.recognizers.nuclei_jsonl import parse_nuclei_jsonl


def test_parse_nmap_xml_returns_open_tcp_and_udp_records(tmp_path):
    scan = tmp_path / "scan.xml"
    scan.write_text(
        """<?xml version="1.0"?>
        <nmaprun>
          <host>
            <address addr="10.0.0.5" addrtype="ipv4"/>
            <ports>
              <port protocol="tcp" portid="22">
                <state state="open"/>
                <service name="ssh" product="OpenSSH"/>
              </port>
              <port protocol="tcp" portid="80">
                <state state="closed"/>
                <service name="http"/>
              </port>
              <port protocol="udp" portid="53">
                <state state="open"/>
                <service name="domain"/>
              </port>
            </ports>
          </host>
        </nmaprun>
        """,
        encoding="utf-8",
    )

    facts = parse_nmap_xml(str(scan))

    assert facts["hosts"] == ["10.0.0.5"]
    assert facts["open_tcp"] == [{"host": "10.0.0.5", "port": 22, "service": "ssh", "product": "OpenSSH"}]
    assert facts["open_udp"] == [{"host": "10.0.0.5", "port": 53, "service": "domain", "product": ""}]


def test_parse_nuclei_jsonl_accepts_string_and_list_tags(tmp_path):
    findings = tmp_path / "nuclei.jsonl"
    rows = [
        {"template-id": "exposure", "matched-at": "https://a.test", "info": {"severity": "medium", "tags": "web,exposure"}},
        {"id": "misconfig", "host": "https://b.test", "info": {"severity": "low", "tags": ["cloud", "config"]}},
    ]
    findings.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    parsed = parse_nuclei_jsonl(str(findings))

    assert parsed["nuclei"] == [
        {"severity": "medium", "id": "exposure", "url": "https://a.test", "tags": ["web", "exposure"]},
        {"severity": "low", "id": "misconfig", "url": "https://b.test", "tags": ["cloud", "config"]},
    ]


def test_parse_httpx_lines_extracts_status_url_and_tech(tmp_path):
    output = tmp_path / "httpx.txt"
    output.write_text("[200] https://app.example [nginx,cloudflare]\nno match\n", encoding="utf-8")

    parsed = parse_httpx_lines(str(output))

    assert parsed == {"web_tech": [{"host": "https://app.example", "tech": "nginx,cloudflare", "evidence": "200"}]}
