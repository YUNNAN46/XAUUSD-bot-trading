from backtest.fetch_histdata import parse_histdata_timestamp, convert_histdata_line


def test_parse_histdata_timestamp_fixed_est_to_utc():
    # 2023-01-02 18:00:00 fixed EST (UTC-5) == 2023-01-02 23:00:00 UTC
    # Expected value computed independently via:
    #   datetime(2023,1,2,23,0,0,tzinfo=timezone.utc).timestamp()*1000
    assert parse_histdata_timestamp("20230102 180000") == 1672700400000


def test_convert_histdata_line_end_to_end():
    line = "20230102 180000;1826.837000;1827.337000;1826.617000;1826.637000;0"
    out = convert_histdata_line(line)
    assert out == "1672700400000,1826.837000,1827.337000,1826.617000,1826.637000,1"
