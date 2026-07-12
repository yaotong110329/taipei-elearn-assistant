from taipei_elearn.support.settings import AppSettings


def test_profile_path_persists(tmp_path):
    first = AppSettings.load(tmp_path)
    second = AppSettings.load(tmp_path)
    assert first.profile_dir == second.profile_dir
    assert second.config_file.exists()

