import pytest

from leaderkit.timecode import (FrameRate, TimecodeError, duration_to_frames,
                                frames_to_tc, tc_to_frames)


@pytest.mark.parametrize("value,df,label,nominal", [
    ("24", None, "24 fps", 24),
    ("23.976", None, "23.976 fps", 24),
    ("25", None, "25 fps", 25),
    ("29.97", True, "29.97 fps DF", 30),
    ("29.97 DF", None, "29.97 fps DF", 30),
    ("29.97", False, "29.97 fps NDF", 30),
    ("59.94", True, "59.94 fps DF", 60),
    (50, None, "50 fps", 50),
    ("23.98", None, "23.976 fps", 24),
])
def test_parse(value, df, label, nominal):
    r = FrameRate.parse(value, df)
    assert r.label() == label
    assert r.nominal == nominal


def test_drop_frame_only_ntsc():
    with pytest.raises(TimecodeError):
        FrameRate.parse("25", True)
    with pytest.raises(TimecodeError):
        FrameRate.parse("23.976", True)


@pytest.mark.parametrize("rate", ["23.976", "24", "25", "30", "50", "60"])
def test_ndf_roundtrip(rate):
    r = FrameRate.parse(rate, False)
    for f in (0, 1, r.nominal - 1, r.nominal * 3600, 1234567):
        assert tc_to_frames(frames_to_tc(f, r), r) == f
    assert tc_to_frames("01:00:00:00", r) == 3600 * r.nominal


def test_df_known_values():
    r = FrameRate.parse("29.97", True)
    # Valori di riferimento SMPTE 12M: 1h DF = 107892 fotogrammi.
    assert tc_to_frames("01:00:00;00", r) == 107892
    assert tc_to_frames("00:01:00;02", r) == 1800
    assert frames_to_tc(1799, r) == "00:00:59;29"
    assert frames_to_tc(1800, r) == "00:01:00;02"
    assert frames_to_tc(17982, r) == "00:10:00;00"
    with pytest.raises(TimecodeError):
        tc_to_frames("00:01:00;00", r)


@pytest.mark.parametrize("rate", ["29.97", "59.94"])
def test_df_roundtrip_exhaustive_first_hour(rate):
    r = FrameRate.parse(rate, True)
    step = 7 if r.nominal == 30 else 13
    for f in range(0, r.nominal * 3600 + 1000, step):
        assert tc_to_frames(frames_to_tc(f, r), r) == f


def test_df_5994():
    r = FrameRate.parse("59.94", True)
    assert tc_to_frames("01:00:00;00", r) == 215784
    assert frames_to_tc(3600, r) == "00:01:00;04"


def test_durations():
    r = FrameRate.parse("25")
    assert duration_to_frames("-2s", r) == -50
    assert duration_to_frames("8s", r) == 200
    assert duration_to_frames("5s+12f", r) == 137
    assert duration_to_frames("-1s-1f", r) == -26
    assert duration_to_frames("20m", r) == 30000
    assert duration_to_frames(48, r) == 48
    assert duration_to_frames("00:00:08:00", r) == 200
    r24 = FrameRate.parse("23.976")
    assert duration_to_frames("-2s", r24) == -48  # sync mark a 48 fotogrammi
    with pytest.raises(TimecodeError):
        duration_to_frames("0.5s", FrameRate.parse("25"))
    with pytest.raises(TimecodeError):
        duration_to_frames("abc", r)
