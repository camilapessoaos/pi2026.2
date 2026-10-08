from app.services.analysis import summarize_climate, summarize_quality


def test_climate_summary_uses_pandas_numpy_for_current_average_min_max_and_series():
    result = summarize_climate([
        {
            "capturedAt": "2026-10-07T10:00:00Z",
            "measurements": {"temperature": 20, "humidity": 50},
            "qualityStatus": "VALID",
        },
        {
            "capturedAt": "2026-10-07T11:00:00Z",
            "measurements": {"temperature": 24},
            "qualityStatus": "REVIEW",
        },
    ], channel_id="42")

    assert result.available is True
    assert result.records == 2
    assert result.metrics["temperature"].current == 24
    assert result.metrics["temperature"].average == 22
    assert result.metrics["temperature"].minimum == 20
    assert result.metrics["temperature"].maximum == 24
    assert result.metrics["temperature"].unit == "°C"
    assert result.metrics["humidity"].samples == 1
    assert result.series[1].values == {"temperature": 24.0}


def test_quality_summary_reports_sensor_completeness_and_status_counts():
    result = summarize_quality([
        {"qualityStatus": "VALID", "measurements": {"temperature": 20, "humidity": 40}},
        {"qualityStatus": "REVIEW", "measurements": {"temperature": 21}},
    ], expected_metrics={"temperature", "humidity"})

    assert result == {
        "available": True,
        "totalRecords": 2,
        "validRecords": 1,
        "reviewRecords": 1,
        "rejectedRecords": 0,
        "completenessPercent": 75.0,
    }


def test_empty_history_returns_explicit_unavailable_state_without_fake_samples():
    result = summarize_climate([], channel_id=None)

    assert result.available is False
    assert result.records == 0
    assert result.metrics == {}
    assert result.series == []
