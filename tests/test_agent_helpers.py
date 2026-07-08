from sidecar.agent.agent import _coerce_plan, _detect_output_paths, _resolve_path


def test_resolve_path_expands_relative_paths_against_cwd(tmp_path):
    assert _resolve_path("reports/out.json", str(tmp_path)) == str(tmp_path / "reports" / "out.json")


def test_detect_output_paths_returns_existing_outputs(tmp_path):
    output = tmp_path / "scan.xml"
    missing = tmp_path / "missing.xml"
    output.write_text("<xml />", encoding="utf-8")

    paths = _detect_output_paths(["nmap", "-oX", output.name, "-oN", str(missing)], str(tmp_path))

    assert paths == [str(output)]


def test_coerce_plan_handles_scalar_notes_and_filters_bad_actions():
    raw = {
        "next_actions": [{"cmd": "nmap -sV 10.0.0.5"}, "not a dict"],
        "notes": "single note",
        "escalation_paths": "try creds",
    }

    plan = _coerce_plan(raw)

    assert plan == {
        "next_actions": [{"cmd": "nmap -sV 10.0.0.5"}],
        "notes": ["single note"],
        "escalation_paths": ["try creds"],
    }
