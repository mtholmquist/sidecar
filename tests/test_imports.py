def test_imports():
    import sidecar
    from sidecar.cli import main

    assert sidecar.__version__
    assert callable(main)
