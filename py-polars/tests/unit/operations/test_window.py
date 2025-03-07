from __future__ import annotations

import numpy as np
import pytest

import polars as pl
from polars.testing import assert_frame_equal, assert_series_equal


def test_over_args() -> None:
    df = pl.DataFrame(
        {
            "a": ["a", "a", "b"],
            "b": [1, 2, 3],
            "c": [3, 2, 1],
        }
    )

    # Single input
    expected = pl.Series("c", [3, 3, 1]).to_frame()
    result = df.select(pl.col("c").max().over("a"))
    assert_frame_equal(result, expected)

    # Multiple input as list
    expected = pl.Series("c", [3, 2, 1]).to_frame()
    result = df.select(pl.col("c").max().over(["a", "b"]))
    assert_frame_equal(result, expected)

    # Multiple input as positional args
    result = df.select(pl.col("c").max().over("a", "b"))
    assert_frame_equal(result, expected)


@pytest.mark.parametrize("dtype", [pl.Float32, pl.Float64, pl.Int32])
def test_std(dtype: type[pl.DataType]) -> None:
    if dtype == pl.Int32:
        df = pl.DataFrame(
            [
                pl.Series("groups", ["a", "a", "b", "b"]),
                pl.Series("values", [1, 2, 3, 4], dtype=dtype),
            ]
        )
    else:
        df = pl.DataFrame(
            [
                pl.Series("groups", ["a", "a", "b", "b"]),
                pl.Series("values", [1.0, 2.0, 3.0, 4.0], dtype=dtype),
            ]
        )

    out = df.select(pl.col("values").std().over("groups"))
    assert np.isclose(out["values"][0], 0.7071067690849304)

    out = df.select(pl.col("values").var().over("groups"))
    assert np.isclose(out["values"][0], 0.5)
    out = df.select(pl.col("values").mean().over("groups"))
    assert np.isclose(out["values"][0], 1.5)


def test_issue_2529() -> None:
    def stdize_out(value: str, control_for: str) -> pl.Expr:
        return (pl.col(value) - pl.mean(value).over(control_for)) / pl.std(value).over(
            control_for
        )

    df = pl.from_dicts(
        [
            {"cat": cat, "val1": cat + _, "val2": cat + _}
            for cat in range(2)
            for _ in range(2)
        ]
    )

    out = df.select(
        [
            "*",
            stdize_out("val1", "cat").alias("out1"),
            stdize_out("val2", "cat").alias("out2"),
        ]
    )
    assert out["out1"].to_list() == out["out2"].to_list()


def test_window_function_cache() -> None:
    # ensures that the cache runs the flattened first (that are the sorted groups)
    # otherwise the flattened results are not ordered correctly
    out = pl.DataFrame(
        {
            "groups": ["A", "A", "B", "B", "B"],
            "groups_not_sorted": ["A", "B", "A", "B", "A"],
            "values": range(5),
        }
    ).with_columns(
        [
            pl.col("values")
            .implode()
            .over("groups")
            .alias("values_list"),  # aggregation to list + join
            pl.col("values")
            .implode()
            .over("groups")
            .flatten()
            .alias("values_flat"),  # aggregation to list + explode and concat back
            pl.col("values")
            .reverse()
            .implode()
            .over("groups")
            .flatten()
            .alias("values_rev"),  # use flatten to reverse within a group
        ]
    )

    assert out["values_list"].to_list() == [
        [0, 1],
        [0, 1],
        [2, 3, 4],
        [2, 3, 4],
        [2, 3, 4],
    ]
    assert out["values_flat"].to_list() == [0, 1, 2, 3, 4]
    assert out["values_rev"].to_list() == [1, 0, 4, 3, 2]


def test_arange_no_rows() -> None:
    df = pl.DataFrame({"x": [5, 5, 4, 4, 2, 2]})
    expr = pl.arange(0, pl.count()).over("x")
    out = df.with_columns(expr)
    assert_frame_equal(
        out, pl.DataFrame({"x": [5, 5, 4, 4, 2, 2], "arange": [0, 1, 0, 1, 0, 1]})
    )

    df = pl.DataFrame({"x": []})
    out = df.with_columns(expr)
    print(out)
    expected = pl.DataFrame(
        {"x": [], "arange": []}, schema={"x": pl.Float32, "arange": pl.Int64}
    )
    assert_frame_equal(out, expected)


def test_no_panic_on_nan_3067() -> None:
    df = pl.DataFrame(
        {
            "group": ["a", "a", "a", "b", "b", "b"],
            "total": [1.0, 2, 3, 4, 5, np.NaN],
        }
    )

    expected = [None, 1.0, 2.0, None, 4.0, 5.0]
    assert (
        df.select([pl.col("total").shift().over("group")])["total"].to_list()
        == expected
    )


def test_quantile_as_window() -> None:
    result = (
        pl.DataFrame(
            {
                "group": [0, 0, 1, 1],
                "value": [0, 1, 0, 2],
            }
        )
        .select(pl.quantile("value", 0.9).over("group"))
        .to_series()
    )
    expected = pl.Series("value", [1.0, 1.0, 2.0, 2.0])
    assert_series_equal(result, expected)


def test_cumulative_eval_window_functions() -> None:
    df = pl.DataFrame(
        {
            "group": [0, 0, 0, 1, 1, 1],
            "val": [20, 40, 30, 2, 4, 3],
        }
    )

    result = df.with_columns(
        pl.col("val")
        .cumulative_eval(pl.element().max())
        .over("group")
        .alias("cumulative_eval_max")
    )
    expected = pl.DataFrame(
        {
            "group": [0, 0, 0, 1, 1, 1],
            "val": [20, 40, 30, 2, 4, 3],
            "cumulative_eval_max": [20, 40, 40, 2, 4, 4],
        }
    )
    assert_frame_equal(result, expected)

    # 6394
    df = pl.DataFrame({"group": [1, 1, 2, 3], "value": [1, None, 3, None]})
    result = df.select(
        pl.col("value").cumulative_eval(pl.element().mean()).over("group")
    )
    expected = pl.DataFrame({"value": [1.0, 1.0, 3.0, None]})
    assert_frame_equal(result, expected)


def test_count_window() -> None:
    assert (
        pl.DataFrame(
            {
                "a": [1, 1, 2],
            }
        )
        .with_columns(pl.count().over("a"))["count"]
        .to_list()
    ) == [2, 2, 1]


def test_window_cached_keys_sorted_update_4183() -> None:
    df = pl.DataFrame(
        {
            "customer_ID": ["0", "0", "1"],
            "date": [1, 2, 3],
        }
    )
    result = df.sort(by=["customer_ID", "date"]).select(
        [
            pl.count("date").over(pl.col("customer_ID")).alias("count"),
            pl.col("date")
            .rank(method="ordinal")
            .over(pl.col("customer_ID"))
            .alias("rank"),
        ]
    )
    expected = pl.DataFrame(
        {"count": [2, 2, 1], "rank": [1, 2, 1]},
        schema={"count": pl.UInt32, "rank": pl.UInt32},
    )
    assert_frame_equal(result, expected)


def test_window_functions_list_types() -> None:
    df = pl.DataFrame(
        {
            "col_int": [1, 1, 2, 2],
            "col_list": [[1], [1], [2], [2]],
        }
    )
    assert (df.select(pl.col("col_list").shift(1).alias("list_shifted")))[
        "list_shifted"
    ].to_list() == [None, [1], [1], [2]]

    # filling with None is allowed, but does not make any sense
    # as it is the same as shift.
    # that's why we don't add it to the allowed types.
    assert (
        df.select(
            pl.col("col_list")
            .shift_and_fill(None, periods=1)  # type: ignore[arg-type]
            .alias("list_shifted")
        )
    )["list_shifted"].to_list() == [None, [1], [1], [2]]

    assert (
        df.select(
            pl.col("col_list").shift_and_fill([], periods=1).alias("list_shifted")
        )
    )["list_shifted"].to_list() == [[], [1], [1], [2]]


def test_sorted_window_expression() -> None:
    size = 10
    df = pl.DataFrame(
        {"a": np.random.randint(10, size=size), "b": np.random.randint(10, size=size)}
    )
    expr = (pl.col("a") + pl.col("b")).over("b").alias("computed")

    out1 = df.with_columns(expr).sort("b")

    # explicit sort
    df = df.sort("b")
    out2 = df.with_columns(expr)

    assert_frame_equal(out1, out2)


def test_nested_aggregation_window_expression() -> None:
    df = pl.DataFrame(
        {
            "x": [1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 2, 13, 4, 15, 6, None, None, 19],
            "y": [0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1],
        }
    )

    result = df.with_columns(
        pl.when(pl.col("x") >= pl.col("x").quantile(0.1))
        .then(1)
        .otherwise(None)
        .over("y")
        .alias("foo")
    )
    expected = pl.DataFrame(
        {
            "x": [1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 2, 13, 4, 15, 6, None, None, 19],
            "y": [0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1],
            "foo": [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, None, None, 1],
        },
        # Resulting column is Int32, see https://github.com/pola-rs/polars/issues/8041
        schema_overrides={"foo": pl.Int32},
    )
    assert_frame_equal(result, expected)


def test_window_5868() -> None:
    df = pl.DataFrame({"value": [None, 2], "id": [None, 1]})

    result_df = df.with_columns(pl.col("value").max().over("id"))
    expected_df = pl.DataFrame({"value": [None, 2], "id": [None, 1]})
    assert_frame_equal(result_df, expected_df)

    df = pl.DataFrame({"a": [None, 1, 2, 3, 3, 3, 4, 4]})

    result = df.select(pl.col("a").sum().over("a")).get_column("a")
    expected = pl.Series("a", [None, 1, 2, 9, 9, 9, 8, 8])
    assert_series_equal(result, expected)

    result = (
        df.with_columns(pl.col("a").set_sorted())
        .select(pl.col("a").sum().over("a"))
        .get_column("a")
    )
    assert_series_equal(result, expected)

    result = df.drop_nulls().select(pl.col("a").sum().over("a")).get_column("a")
    expected = pl.Series("a", [1, 2, 9, 9, 9, 8, 8])
    assert_series_equal(result, expected)

    result = (
        df.drop_nulls()
        .with_columns(pl.col("a").set_sorted())
        .select(pl.col("a").sum().over("a"))
        .get_column("a")
    )
    assert_series_equal(result, expected)


def test_window_function_implode_contention_8536() -> None:
    df = pl.DataFrame(
        data={
            "policy": ["a", "b", "c", "c", "d", "d", "d", "d", "e", "e"],
            "memo": ["LE", "RM", "", "", "", "LE", "", "", "", "RM"],
        },
        schema={"policy": pl.Utf8, "memo": pl.Utf8},
    )

    assert df.select(
        [
            (pl.lit("LE").is_in(pl.col("memo").implode().over("policy")))
            | (pl.lit("RM").is_in(pl.col("memo").implode().over("policy")))
        ]
    ).to_series().to_list() == [
        True,
        True,
        False,
        False,
        True,
        True,
        True,
        True,
        True,
        True,
    ]


def test_cached_windows_sync_8803() -> None:
    assert (
        pl.DataFrame(
            [
                pl.Series("id", [4, 5, 4, 6, 4, 5], dtype=pl.Int64),
                pl.Series(
                    "is_valid",
                    [True, False, False, False, False, False],
                    dtype=pl.Boolean,
                ),
            ]
        )
        .with_columns(
            a=pl.col("is_valid").implode().arr.contains(True).over("id"),
            b=pl.col("is_valid").sum().gt(0).over("id"),
        )
        .sum()
    ).to_dict(False) == {"id": [28], "is_valid": [1], "a": [3], "b": [3]}


def test_window_filtered_aggregation() -> None:
    df = pl.DataFrame(
        {
            "group": ["A", "A", "B", "B"],
            "field1": [2, 4, 6, 8],
            "flag": [1, 0, 1, 1],
        }
    )
    out = df.with_columns(
        pl.col("field1").filter(pl.col("flag") == 1).mean().over("group").alias("mean")
    )
    expected = pl.DataFrame(
        {
            "group": ["A", "A", "B", "B"],
            "field1": [2, 4, 6, 8],
            "flag": [1, 0, 1, 1],
            "mean": [2.0, 2.0, 7.0, 7.0],
        }
    )
    assert_frame_equal(out, expected)
