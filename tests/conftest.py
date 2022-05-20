from typing import List, Dict, Any, Callable
from grpc import Call
import pytest

import pandas as pd
import numpy as np
from marketing_attribution_models import MAM


_df = None


def get_intermediate(df):
    global _df
    _df = df
    return df


df = (
    pd.read_csv("data/test_dataset.csv")
    .pipe(get_intermediate)
    .assign(event_time=pd.to_datetime(_df.event_time))
    .assign(is_conversion=_df.is_conversion.astype("bool"))
    .assign(session_id=_df.session_id.astype("str"))
)


@pytest.fixture
def dataframe_generator() -> Callable:
    def factory(size=1000000, prob_conversion=0.05) -> pd.DataFrame:
        user_ids = set(np.random.randint(low=1, size=size))
        df = pd.DataFrame(
            columns=[
                "user_pseudo_id",
                "session_id",
                "event_time",
                "user_id",
                "is_conversion",
                "source_medium",
            ]
        )
        for user in user_ids:
            n_events: int = np.random.randint(1, 10, 1)
            session_id: List[int] = list(range(1, n_events + 1))
            event_time: List[np.datetime64] = [
                np.datetime64("2022-01-01") + np.timedelta64(i, "h")
                for i in session_id
            ]
            user_id: List[int] = [None] * (n_events - 1) + [np.random.randint(low=1, size=1)]
            is_conversion: List[bool] = [None] * (n_events - 1) + [np.random.binomial(n=1, p=prob_conversion, size=1)]
            

    return factory


@pytest.fixture
def model_fixture() -> Callable:
    """Fixture to create a model."""

    def factory(attribution_window=30) -> MAM:
        return MAM(
            df,
            attribution_window=attribution_window,
            channels_colname="source_medium",
            group_channels=True,
            group_channels_by_id_list=["user_pseudo_id"],
            group_timestamp_colname="event_time",
            journey_with_conv_colname="is_conversion",
            create_journey_id_based_on_conversion=True,
        )

    return factory
