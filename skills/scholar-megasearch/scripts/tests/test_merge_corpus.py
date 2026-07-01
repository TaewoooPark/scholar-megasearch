import importlib.util, os
_here = os.path.dirname(__file__)
_spec = importlib.util.spec_from_file_location(
    "merge_corpus", os.path.join(_here, "..", "merge_corpus.py"))
mc = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(mc)


def test_norm_title_preserves_hangul():
    assert mc.norm_title("표면유속 산정") == "표면유속 산정"


def test_korean_record_without_doi_survives_dedupe():
    recs = [{"title": "하천 표면영상유속계 적용성 평가", "source": "kisti", "year": 2024}]
    out = mc.dedupe(recs)
    assert len(out) == 1
    assert out[0].get("title") == "하천 표면영상유속계 적용성 평가"


def test_norm_title_english_unchanged():
    assert mc.norm_title("Surface  Velocity!! Estimation") == "surface velocity estimation"


def test_english_dedupe_still_merges():
    recs = [
        {"title": "Surface Velocity Estimation Method", "source": "arxiv"},
        {"title": "Surface Velocity Estimation Method", "source": "crossref"},
    ]
    out = mc.dedupe(recs)
    assert len(out) == 1


def test_different_korean_titles_do_not_merge():
    recs = [
        {"title": "하천 표면영상유속계 적용성 평가", "source": "kisti"},
        {"title": "도시 침수 모니터링 시스템 개발", "source": "kisti"},
    ]
    out = mc.dedupe(recs)
    assert len(out) == 2


def test_norm_title_collapses_underscore():
    assert mc.norm_title("deep_learning models") == "deep learning models"
