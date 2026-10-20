from app.services.views import render_map_html


def test_map_html_escapes_names():
    html = render_map_html("<script>", [{"unit": "<script>", "x": 1, "y": 2, "state": "on_table"}])
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
