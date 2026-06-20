from astrbot.core.utils.path_util import path_Mapping


def test_path_mapping_target_single_dot_does_not_crash():
    # A mapping whose target is "." reduces srcPath to "." (one character).
    # The relative-path branch indexed srcPath[1] unconditionally and raised
    # IndexError. path_Mapping is reachable from the respond stage, so a user
    # configuring such a rule could crash message handling.
    assert path_Mapping(["somepath:."], "somepath") == "."


def test_path_mapping_target_double_dot_does_not_crash():
    # ".." is two characters, so the inner srcPath[2] access also overran.
    assert path_Mapping(["somepath:.."], "somepath") == ".."


def test_path_mapping_relative_target_still_normalized():
    # Regression: a normal relative target keeps its existing behaviour.
    assert path_Mapping(["somepath:./sub"], "somepath") == "./sub"
