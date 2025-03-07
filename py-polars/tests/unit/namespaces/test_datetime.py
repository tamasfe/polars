from __future__ import annotations

import sys
from datetime import date, datetime, time, timedelta, timezone
from typing import TYPE_CHECKING

import pytest

import polars as pl
from polars.datatypes import DTYPE_TEMPORAL_UNITS
from polars.dependencies import _ZONEINFO_AVAILABLE
from polars.exceptions import ComputeError, InvalidOperationError
from polars.testing import assert_series_equal

if sys.version_info >= (3, 9):
    from zoneinfo import ZoneInfo
elif _ZONEINFO_AVAILABLE:
    # Import from submodule due to typing issue with backports.zoneinfo package:
    # https://github.com/pganssle/zoneinfo/issues/125
    from backports.zoneinfo._zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from polars.type_aliases import TimeUnit


@pytest.fixture()
def series_of_int_dates() -> pl.Series:
    return pl.Series([10000, 20000, 30000], dtype=pl.Date)


@pytest.fixture()
def series_of_str_dates() -> pl.Series:
    return pl.Series(["2020-01-01 00:00:00.000000000", "2020-02-02 03:20:10.987654321"])


def test_dt_to_string(series_of_int_dates: pl.Series) -> None:
    expected_str_dates = pl.Series(["1997-05-19", "2024-10-04", "2052-02-20"])

    assert series_of_int_dates.dtype == pl.Date
    assert_series_equal(series_of_int_dates.dt.to_string("%F"), expected_str_dates)

    # Check strftime alias as well
    assert_series_equal(series_of_int_dates.dt.strftime("%F"), expected_str_dates)


@pytest.mark.parametrize(
    ("unit_attr", "expected"),
    [
        ("year", pl.Series(values=[1997, 2024, 2052], dtype=pl.Int32)),
        ("month", pl.Series(values=[5, 10, 2], dtype=pl.UInt32)),
        ("week", pl.Series(values=[21, 40, 8], dtype=pl.UInt32)),
        ("day", pl.Series(values=[19, 4, 20], dtype=pl.UInt32)),
        ("ordinal_day", pl.Series(values=[139, 278, 51], dtype=pl.UInt32)),
    ],
)
def test_dt_extract_year_month_week_day_ordinal_day(
    unit_attr: str,
    expected: pl.Series,
    series_of_int_dates: pl.Series,
) -> None:
    assert_series_equal(getattr(series_of_int_dates.dt, unit_attr)(), expected)


@pytest.mark.parametrize(
    ("unit_attr", "expected"),
    [
        ("hour", pl.Series(values=[0, 3], dtype=pl.UInt32)),
        ("minute", pl.Series(values=[0, 20], dtype=pl.UInt32)),
        ("second", pl.Series(values=[0, 10], dtype=pl.UInt32)),
        ("millisecond", pl.Series(values=[0, 987], dtype=pl.UInt32)),
        ("microsecond", pl.Series(values=[0, 987654], dtype=pl.UInt32)),
        ("nanosecond", pl.Series(values=[0, 987654321], dtype=pl.UInt32)),
    ],
)
def test_strptime_extract_times(
    unit_attr: str,
    expected: pl.Series,
    series_of_int_dates: pl.Series,
    series_of_str_dates: pl.Series,
) -> None:
    s = series_of_str_dates.str.strptime(pl.Datetime, format="%Y-%m-%d %H:%M:%S.%9f")

    assert_series_equal(getattr(s.dt, unit_attr)(), expected)


@pytest.mark.parametrize("time_zone", [None, "Asia/Kathmandu", "+03:00"])
@pytest.mark.parametrize(
    ("attribute", "expected"),
    [
        ("date", date(2022, 1, 1)),
        ("time", time(23)),
    ],
)
def test_dt_date_and_time(
    attribute: str, time_zone: None | str, expected: date | time
) -> None:
    ser = pl.Series([datetime(2022, 1, 1, 23)]).dt.replace_time_zone(time_zone)
    result = getattr(ser.dt, attribute)().item()
    assert result == expected


@pytest.mark.parametrize("time_zone", [None, "Asia/Kathmandu", "+03:00"])
@pytest.mark.parametrize("time_unit", ["us", "ns", "ms"])
def test_dt_datetime(time_zone: str | None, time_unit: TimeUnit) -> None:
    ser = (
        pl.Series([datetime(2022, 1, 1, 23)])
        .dt.cast_time_unit(time_unit)
        .dt.replace_time_zone(time_zone)
    )
    result = ser.dt.datetime()
    expected = datetime(2022, 1, 1, 23)
    assert result.dtype == pl.Datetime(time_unit, None)
    assert result.item() == expected


def test_dt_datetime_date_time_invalid() -> None:
    with pytest.raises(ComputeError, match="expected Datetime"):
        pl.Series([date(2021, 1, 2)]).dt.datetime()
    with pytest.raises(ComputeError, match="expected Datetime or Date"):
        pl.Series([time(23)]).dt.date()
    with pytest.raises(ComputeError, match="expected Datetime"):
        pl.Series([time(23)]).dt.datetime()
    with pytest.raises(ComputeError, match="expected Datetime or Date"):
        pl.Series([timedelta(1)]).dt.date()
    with pytest.raises(ComputeError, match="expected Datetime"):
        pl.Series([timedelta(1)]).dt.datetime()
    with pytest.raises(ComputeError, match="expected Datetime, Date, or Time"):
        pl.Series([timedelta(1)]).dt.time()


@pytest.mark.parametrize(
    ("dt", "expected"),
    [
        (datetime(2022, 3, 15, 3), datetime(2022, 3, 1, 3)),
        (datetime(2022, 3, 15, 3, 2, 1, 123000), datetime(2022, 3, 1, 3, 2, 1, 123000)),
        (datetime(2022, 3, 15), datetime(2022, 3, 1)),
        (datetime(2022, 3, 1), datetime(2022, 3, 1)),
    ],
)
@pytest.mark.parametrize(
    ("tzinfo", "time_zone"),
    [
        (None, None),
        (ZoneInfo("Asia/Kathmandu"), "Asia/Kathmandu"),
        (timezone(timedelta(hours=1)), "+01:00"),
    ],
)
@pytest.mark.parametrize("time_unit", ["ms", "us", "ns"])
def test_month_start_datetime(
    dt: datetime,
    expected: datetime,
    time_unit: TimeUnit,
    tzinfo: ZoneInfo | timezone | None,
    time_zone: str | None,
) -> None:
    ser = pl.Series([dt]).dt.replace_time_zone(time_zone).dt.cast_time_unit(time_unit)
    result = ser.dt.month_start().item()
    assert result == expected.replace(tzinfo=tzinfo)


@pytest.mark.parametrize(
    ("dt", "expected"),
    [
        (date(2022, 3, 15), date(2022, 3, 1)),
        (date(2022, 3, 31), date(2022, 3, 1)),
    ],
)
def test_month_start_date(dt: date, expected: date) -> None:
    ser = pl.Series([dt])
    result = ser.dt.month_start().item()
    assert result == expected


@pytest.mark.parametrize(
    ("dt", "expected"),
    [
        (datetime(2022, 3, 15, 3), datetime(2022, 3, 31, 3)),
        (
            datetime(2022, 3, 15, 3, 2, 1, 123000),
            datetime(2022, 3, 31, 3, 2, 1, 123000),
        ),
        (datetime(2022, 3, 15), datetime(2022, 3, 31)),
        (datetime(2022, 3, 31), datetime(2022, 3, 31)),
    ],
)
@pytest.mark.parametrize(
    ("tzinfo", "time_zone"),
    [
        (None, None),
        (ZoneInfo("Asia/Kathmandu"), "Asia/Kathmandu"),
        (timezone(timedelta(hours=1)), "+01:00"),
    ],
)
@pytest.mark.parametrize("time_unit", ["ms", "us", "ns"])
def test_month_end_datetime(
    dt: datetime,
    expected: datetime,
    time_unit: TimeUnit,
    tzinfo: ZoneInfo | timezone | None,
    time_zone: str | None,
) -> None:
    ser = pl.Series([dt]).dt.replace_time_zone(time_zone).dt.cast_time_unit(time_unit)
    result = ser.dt.month_end().item()
    assert result == expected.replace(tzinfo=tzinfo)


@pytest.mark.parametrize(
    ("dt", "expected"),
    [
        (date(2022, 3, 15), date(2022, 3, 31)),
        (date(2022, 3, 31), date(2022, 3, 31)),
    ],
)
def test_month_end_date(dt: date, expected: date) -> None:
    ser = pl.Series([dt])
    result = ser.dt.month_end().item()
    assert result == expected


def test_month_start_end_invalid() -> None:
    ser = pl.Series([time(1, 2, 3)])
    with pytest.raises(
        InvalidOperationError,
        match=r"`month_start` operation not supported for dtype `time` \(expected: date/datetime\)",
    ):
        ser.dt.month_start()
    with pytest.raises(
        InvalidOperationError,
        match=r"`month_end` operation not supported for dtype `time` \(expected: date/datetime\)",
    ):
        ser.dt.month_end()


@pytest.mark.parametrize(
    ("time_unit", "expected"),
    [
        ("d", pl.Series(values=[18262, 18294], dtype=pl.Int32)),
        ("s", pl.Series(values=[1_577_836_800, 1_580_613_610], dtype=pl.Int64)),
        (
            "ms",
            pl.Series(values=[1_577_836_800_000, 1_580_613_610_000], dtype=pl.Int64),
        ),
    ],
)
def test_strptime_epoch(
    time_unit: TimeUnit,
    expected: pl.Series,
    series_of_str_dates: pl.Series,
) -> None:
    s = series_of_str_dates.str.strptime(pl.Datetime, format="%Y-%m-%d %H:%M:%S.%9f")

    assert_series_equal(s.dt.epoch(time_unit=time_unit), expected)


def test_strptime_fractional_seconds(series_of_str_dates: pl.Series) -> None:
    s = series_of_str_dates.str.strptime(pl.Datetime, format="%Y-%m-%d %H:%M:%S.%9f")

    assert_series_equal(
        s.dt.second(fractional=True),
        pl.Series([0.0, 10.987654321], dtype=pl.Float64),
    )


@pytest.mark.parametrize(
    ("unit_attr", "expected"),
    [
        ("days", pl.Series([1])),
        ("hours", pl.Series([24])),
        ("minutes", pl.Series([24 * 60])),
        ("seconds", pl.Series([3600 * 24])),
        ("milliseconds", pl.Series([3600 * 24 * int(1e3)])),
        ("microseconds", pl.Series([3600 * 24 * int(1e6)])),
        ("nanoseconds", pl.Series([3600 * 24 * int(1e9)])),
    ],
)
def test_duration_extract_times(
    unit_attr: str,
    expected: pl.Series,
) -> None:
    duration = pl.Series([datetime(2022, 1, 2)]) - pl.Series([datetime(2022, 1, 1)])

    assert_series_equal(getattr(duration.dt, unit_attr)(), expected)


@pytest.mark.parametrize(
    ("time_unit", "every"),
    [
        ("ms", "1h"),
        ("us", "1h0m0s"),
        ("ns", timedelta(hours=1)),
    ],
    ids=["milliseconds", "microseconds", "nanoseconds"],
)
def test_truncate(
    time_unit: TimeUnit,
    every: str | timedelta,
) -> None:
    start, stop = datetime(2022, 1, 1), datetime(2022, 1, 2)
    s = pl.date_range(
        start,
        stop,
        timedelta(minutes=30),
        name=f"dates[{time_unit}]",
        time_unit=time_unit,
        eager=True,
    )

    # can pass strings and time-deltas
    out = s.dt.truncate(every)
    assert out.dt[0] == start
    assert out.dt[1] == start
    assert out.dt[2] == start + timedelta(hours=1)
    assert out.dt[3] == start + timedelta(hours=1)
    # ...
    assert out.dt[-3] == stop - timedelta(hours=1)
    assert out.dt[-2] == stop - timedelta(hours=1)
    assert out.dt[-1] == stop


@pytest.mark.parametrize(
    ("time_unit", "every"),
    [
        ("ms", "1h"),
        ("us", "1h0m0s"),
        ("ns", timedelta(hours=1)),
    ],
    ids=["milliseconds", "microseconds", "nanoseconds"],
)
def test_round(
    time_unit: TimeUnit,
    every: str | timedelta,
) -> None:
    start, stop = datetime(2022, 1, 1), datetime(2022, 1, 2)
    s = pl.date_range(
        start,
        stop,
        timedelta(minutes=30),
        name=f"dates[{time_unit}]",
        time_unit=time_unit,
        eager=True,
    )

    # can pass strings and time-deltas
    out = s.dt.round(every)
    assert out.dt[0] == start
    assert out.dt[1] == start + timedelta(hours=1)
    assert out.dt[2] == start + timedelta(hours=1)
    assert out.dt[3] == start + timedelta(hours=2)
    # ...
    assert out.dt[-3] == stop - timedelta(hours=1)
    assert out.dt[-2] == stop
    assert out.dt[-1] == stop


@pytest.mark.parametrize(
    ("time_unit", "date_in_that_unit"),
    [
        ("ns", [978307200000000000, 981022089000000000]),
        ("us", [978307200000000, 981022089000000]),
        ("ms", [978307200000, 981022089000]),
    ],
    ids=["nanoseconds", "microseconds", "milliseconds"],
)
def test_cast_time_units(
    time_unit: TimeUnit,
    date_in_that_unit: list[int],
) -> None:
    dates = pl.Series([datetime(2001, 1, 1), datetime(2001, 2, 1, 10, 8, 9)])

    assert dates.dt.cast_time_unit(time_unit).cast(int).to_list() == date_in_that_unit


def test_epoch_matches_timestamp() -> None:
    dates = pl.Series([datetime(2001, 1, 1), datetime(2001, 2, 1, 10, 8, 9)])

    for unit in DTYPE_TEMPORAL_UNITS:
        assert_series_equal(dates.dt.epoch(unit), dates.dt.timestamp(unit))

    assert_series_equal(dates.dt.epoch("s"), dates.dt.timestamp("ms") // 1000)
    assert_series_equal(
        dates.dt.epoch("d"),
        (dates.dt.timestamp("ms") // (1000 * 3600 * 24)).cast(pl.Int32),
    )


@pytest.mark.parametrize(
    ("tzinfo", "time_zone"),
    [(None, None), (ZoneInfo("Asia/Kathmandu"), "Asia/Kathmandu")],
)
def test_date_time_combine(tzinfo: ZoneInfo | None, time_zone: str | None) -> None:
    # Define a DataFrame with columns for datetime, date, and time
    df = pl.DataFrame(
        {
            "dtm": [
                datetime(2022, 12, 31, 10, 30, 45),
                datetime(2023, 7, 5, 23, 59, 59),
            ],
            "dt": [
                date(2022, 10, 10),
                date(2022, 7, 5),
            ],
            "tm": [
                time(1, 2, 3, 456000),
                time(7, 8, 9, 101000),
            ],
        }
    )
    df = df.with_columns(pl.col("dtm").dt.replace_time_zone(time_zone))

    # Combine datetime/date with time
    df = df.select(
        [
            pl.col("dtm").dt.combine(pl.col("tm")).alias("d1"),  # datetime & time
            pl.col("dt").dt.combine(pl.col("tm")).alias("d2"),  # date & time
            pl.col("dt").dt.combine(time(4, 5, 6)).alias("d3"),  # date & specified time
        ]
    )

    # Assert that the new columns have the expected values and datatypes
    expected_dict = {
        "d1": [  # Time component should be overwritten by `tm` values
            datetime(2022, 12, 31, 1, 2, 3, 456000, tzinfo=tzinfo),
            datetime(2023, 7, 5, 7, 8, 9, 101000, tzinfo=tzinfo),
        ],
        "d2": [  # Both date and time components combined "as-is" into new datetime
            datetime(2022, 10, 10, 1, 2, 3, 456000),
            datetime(2022, 7, 5, 7, 8, 9, 101000),
        ],
        "d3": [  # New datetime should use specified time component
            datetime(2022, 10, 10, 4, 5, 6),
            datetime(2022, 7, 5, 4, 5, 6),
        ],
    }
    assert df.to_dict(False) == expected_dict

    expected_schema = {
        "d1": pl.Datetime("us", time_zone),
        "d2": pl.Datetime("us"),
        "d3": pl.Datetime("us"),
    }
    assert df.schema == expected_schema


def test_combine_unsupported_types() -> None:
    with pytest.raises(ComputeError, match="expected Date or Datetime, got time"):
        pl.Series([time(1, 2)]).dt.combine(time(3, 4))


@pytest.mark.parametrize("time_unit", ["ms", "us", "ns"])
@pytest.mark.parametrize("time_zone", ["Asia/Kathmandu", None])
def test_combine_lazy_schema_datetime(
    time_zone: str | None,
    time_unit: TimeUnit,
) -> None:
    df = pl.DataFrame({"ts": pl.Series([datetime(2020, 1, 1)])})
    df = df.with_columns(pl.col("ts").dt.replace_time_zone(time_zone))
    result = (
        df.lazy()
        .select(pl.col("ts").dt.combine(time(1, 2, 3), time_unit=time_unit))
        .dtypes
    )
    expected = [pl.Datetime(time_unit, time_zone)]
    assert result == expected


@pytest.mark.parametrize("time_unit", ["ms", "us", "ns"])
def test_combine_lazy_schema_date(time_unit: TimeUnit) -> None:
    df = pl.DataFrame({"ts": pl.Series([date(2020, 1, 1)])})
    result = (
        df.lazy()
        .select(pl.col("ts").dt.combine(time(1, 2, 3), time_unit=time_unit))
        .dtypes
    )
    expected = [pl.Datetime(time_unit, None)]
    assert result == expected


def test_is_leap_year() -> None:
    assert pl.date_range(
        datetime(1990, 1, 1), datetime(2004, 1, 1), "1y", eager=True
    ).dt.is_leap_year().to_list() == [
        False,
        False,
        True,  # 1992
        False,
        False,
        False,
        True,  # 1996
        False,
        False,
        False,
        True,  # 2000
        False,
        False,
        False,
        True,  # 2004
    ]


def test_quarter() -> None:
    assert pl.date_range(
        datetime(2022, 1, 1), datetime(2022, 12, 1), "1mo", eager=True
    ).dt.quarter().to_list() == [1, 1, 1, 2, 2, 2, 3, 3, 3, 4, 4, 4]


def test_date_offset() -> None:
    df = pl.DataFrame(
        {
            "dates": pl.date_range(
                datetime(2000, 1, 1), datetime(2020, 1, 1), "1y", eager=True
            )
        }
    )

    # Add two new columns to the DataFrame using the offset_by() method
    df = df.with_columns(
        [
            df["dates"].dt.offset_by("1y").alias("date_plus_1y"),
            df["dates"].dt.offset_by("-1y2mo").alias("date_min"),
        ]
    )

    # Assert that the day of the month for all the dates in new columns is 1
    assert (df["date_plus_1y"].dt.day() == 1).all()
    assert (df["date_min"].dt.day() == 1).all()

    # Assert that the 'date_min' column contains the expected list of dates
    expected_dates = [datetime(year, 11, 1, 0, 0) for year in range(1998, 2019)]
    assert df["date_min"].to_list() == expected_dates


@pytest.mark.parametrize("time_zone", ["US/Central", None])
def test_offset_by_crossing_dst(time_zone: str | None) -> None:
    ser = pl.Series([datetime(2021, 11, 7)]).dt.replace_time_zone(time_zone)
    result = ser.dt.offset_by("1d")
    expected = pl.Series([datetime(2021, 11, 8)]).dt.replace_time_zone(time_zone)
    assert_series_equal(result, expected)


def test_negative_offset_by_err_msg_8464() -> None:
    with pytest.raises(
        ComputeError, match=r"cannot advance '2022-03-30 00:00:00' by -1 month\(s\)"
    ):
        pl.Series([datetime(2022, 3, 30)]).dt.offset_by("-1mo")


@pytest.mark.parametrize(
    ("duration", "input_date", "expected"),
    [
        ("1mo_saturating", date(2018, 1, 31), date(2018, 2, 28)),
        ("1y_saturating", date(2024, 2, 29), date(2025, 2, 28)),
        ("1y1mo_saturating", date(2024, 1, 30), date(2025, 2, 28)),
    ],
)
def test_offset_by_saturating_8217_8474(
    duration: str, input_date: date, expected: date
) -> None:
    result = pl.Series([input_date]).dt.offset_by(duration).item()
    assert result == expected


def test_year_empty_df() -> None:
    df = pl.DataFrame(pl.Series(name="date", dtype=pl.Date))
    assert df.select(pl.col("date").dt.year()).dtypes == [pl.Int32]


@pytest.mark.parametrize(
    "time_unit",
    ["ms", "us", "ns"],
    ids=["milliseconds", "microseconds", "nanoseconds"],
)
def test_weekday(time_unit: TimeUnit) -> None:
    friday = pl.Series([datetime(2023, 2, 17)])

    assert friday.dt.cast_time_unit(time_unit).dt.weekday()[0] == 5
    assert friday.cast(pl.Date).dt.weekday()[0] == 5


@pytest.mark.parametrize(
    ("values", "expected_median"),
    [
        ([], None),
        ([None, None], None),
        ([date(2022, 1, 1)], date(2022, 1, 1)),
        ([date(2022, 1, 1), date(2022, 1, 2), date(2022, 1, 3)], date(2022, 1, 2)),
        ([date(2022, 1, 1), date(2022, 1, 2), date(2024, 5, 15)], date(2022, 1, 2)),
    ],
    ids=["empty", "Nones", "single", "spread_even", "spread_skewed"],
)
def test_median(values: list[date | None], expected_median: date | None) -> None:
    result = pl.Series(values).cast(pl.Date).dt.median()
    assert result == expected_median


@pytest.mark.parametrize(
    ("values", "expected_mean"),
    [
        ([], None),
        ([None, None], None),
        ([date(2022, 1, 1)], date(2022, 1, 1)),
        ([date(2022, 1, 1), date(2022, 1, 2), date(2022, 1, 3)], date(2022, 1, 2)),
        ([date(2022, 1, 1), date(2022, 1, 2), date(2024, 5, 15)], date(2022, 10, 16)),
    ],
    ids=["empty", "Nones", "single", "spread_even", "spread_skewed"],
)
def test_mean(values: list[date | None], expected_mean: date | None) -> None:
    result = pl.Series(values).cast(pl.Date).dt.mean()
    assert result == expected_mean
