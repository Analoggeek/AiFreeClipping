from scripts.report_test_failures import annotations


def test_failed_native_test_diagnostics_are_bounded_and_escaped(tmp_path):
    path=tmp_path/'report.xml'
    path.write_text('<testsuite><testcase classname="native" name="case"><failure>one\ntwo% ::error</failure></testcase><testcase name="ok"/></testsuite>')
    result=annotations(path)
    assert len(result)==1 and result[0].startswith('::error title=native.case::')
    assert 'one%0Atwo%25' in result[0]
