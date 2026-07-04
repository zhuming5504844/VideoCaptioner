from pathlib import Path

from tools.update_ytdlp_no_cookie_download import build_ydl_options


def test_build_options_are_no_cookie(tmp_path: Path):
    options = build_ydl_options(tmp_path, "mweb,ios", disable_proxy=True)

    assert options["cookiefile"] is None
    assert options["cookiesfrombrowser"] is None
    assert options["proxy"] == ""
    assert options["paths"]["home"] == str(tmp_path)
    assert options["extractor_args"]["youtube"]["player_client"] == ["mweb", "ios"]
