from typing import List, Union
import warnings
import itertools
import math
import re

import numpy.typing as npt
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

plt.style.use("fivethirtyeight")

from marketing_attribution_models.utils import reduce_mem_usage


class MAM:
    """MAM (Marketing Attribution Models) is a class inspired on the R Package.

    `GameTheoryAllocation` from Alejandro Saavedra-Nieves and `ChannelAttribution` from
    Davide Altomare and David Loris that was created to bring these concepts to Python
    and to help us understand how the different marketing channels behave during the
    customer journey.

    Parameters:
    df = None by default, but should only be None if choosing to use a random dataframe.
         Otherwise, it has to receive a Pandas dataframe;
    attribution_window = 30 by default.
        Number of days before the conversion to be considered.
    time_till_conv_colname = None by default.
        Column name in the df containing the time in hours untill the
        moment of the conversion. The column must have the same elements as the
        channels_colname has. Values could be on a list ou a string with a separator;
        If your session is crashing here, try setting the variable
        time_till_conv_colname equal to 'skip_column'. But skipping this column you will
        not be able to run all the models in this class
    round_values_to = 4 by default.
        Round the values of the attribution models to this number of decimals.
    conversion_value = 1 by default.
        Integer that represents a monetary value of a 'conversion', can also receive a
        string indicating the column name on the dataframe containing the conversion
        values;
    channels_colname = None by default.
        Column name in the df containing the different channels during the customer
        journey. The column must have the same elements as the time_till_conv_colname
        has. Values could be on a list ou a string with a separator;
    journey_with_conv_colname = None by default.
        Column name in the df indicating if the journey (row) was a successfully
        conversion (True), or not (False).
    group_channels = False by default.
        Most important parameter on this class. This indicates the input format of the
        dataframe.
            True  = Each row represents a user session that will be grouped into a user
                    journey;
            False = Each row represents a user journey and the columns
    group_channels_by_id_list = Empty list by default.
    group_timestamp_colname = None by default.
    create_journey_id_based_on_conversion = False by default.
    path_separator = ' > ' by default.
        If using 'group_channels = True', this should match the separator being used on
        the inputed dataframe in the channels_colname;
    verbose = False by default.
        Internal parameter for printing while working with MAM;
    random_df = False by default.
        Will create a random dataframe with testing purpose;

    OBS: If your session is crashing, try setting the variable verbose True and some
    status and tips will be printed;
    """

    def __init__(
        self,
        df=None,
        attribution_window: int = 30,
        session_id_col: str = "session_id",
        time_till_conv_colname: str = None,
        round_values_to: int = 4,
        conversion_value: int = 1,
        channels_colname: str = None,
        journey_with_conv_colname: str = None,
        group_channels: bool = False,
        group_channels_by_id_list: List = [],
        group_timestamp_colname: str = None,
        create_journey_id_based_on_conversion: bool = False,
        path_separator: str = " > ",
        verbose: bool = False,
        random_df: bool = False,
    ):

        self.attribution_window = attribution_window * 24  # number of hours, actually
        self.session_id_col = session_id_col
        self.verbose = verbose
        self.sep = path_separator
        self.group_by_channels_models = None
        self.round_values_to = round_values_to
        self.journey_with_conv_colname = journey_with_conv_colname
        self.channels_colname = channels_colname
        self.conversion_value_colname = conversion_value

        ##########################################################
        ################## Instance attributes ###################
        ##########################################################

        self.__first_click = None
        self.__last_click = None
        self.__last_click_non = None
        self.__linear = None
        self.__position_based = None
        self.__time_decay = None

        ##########################################################
        ##### Section 0: Funcions needed to create the class #####
        ##########################################################

        def journey_id_based_on_conversion(df, group_id, transaction_colname):
            """Internal function that creates a journey_id column into a DF
            containing a User ID and Boolean column that indicates if there has
            been a conversion on that instance."""
            df_temp = df.copy()

            for i in group_id:
                df_temp[i] = df_temp[i].apply(str)

            # Converting bool column to int
            df_temp["journey_id"] = df_temp[transaction_colname].map(
                lambda x: 0 if x == False else 1
            )

            # Cumsum for each transaction to expand the value for the rows that did not
            # have a transaction
            df_temp["journey_id"] = df_temp.groupby(group_id)["journey_id"].cumsum()

            # Subtracting 1 only for the row that had a transaction
            t = df_temp["journey_id"] - 1
            df_temp["journey_id"] = (
                df_temp["journey_id"]
                .where((df_temp[transaction_colname] == False), t)
                .apply(str)
            )
            df_temp["journey_rnk"] = df_temp["journey_id"].astype("int")
            df_temp["journey_id"] = (
                "id:" + df_temp[group_id[0]] + "_J:" + df_temp["journey_id"]
            )

            del t
            return df_temp

        def random_mam_data_frame(user_id=300, k=50000, conv_rate=0.4):
            import random

            channels = [
                "Direct",
                "Direct",
                "Facebook",
                "Facebook",
                "Facebook",
                "Google Search",
                "Google Search",
                "Google Search",
                "Google Search",
                "Google Display",
                "Organic",
                "Organic",
                "Organic",
                "Organic",
                "Organic",
                "Organic",
                "Email Marketing",
                "Youtube",
                "Instagram",
            ]
            has_transaction = ([True] * int(conv_rate * 100)) + (
                [False] * int((1 - conv_rate) * 100)
            )
            user_id = list(range(0, 700))
            day = range(1, 30)
            month = range(1, 12)

            res = []
            for i in [channels, has_transaction, user_id, day, month]:
                res.append(random.choices(population=i, k=k))

            df = pd.DataFrame(res).transpose()
            df.columns = ["channels", "has_transaction", "user_id", "day", "month"]
            df["visitStartTime"] = (
                "2020-"
                + df["month"].apply(lambda val: str(val) if val > 9 else "0" + str(val))
                + "-"
                + df["day"].apply(lambda val: str(val) if val > 9 else "0" + str(val))
            )

            return df

        #####################################################
        ##### Section 1: Creating object and attributes #####
        #####################################################

        ###########################
        #### random_df == True ####
        ###########################

        if random_df:
            df = random_mam_data_frame()
            group_channels = True
            channels_colname = "channels"
            journey_with_conv_colname = "has_transaction"
            group_channels_by_id_list = ["user_id"]
            group_timestamp_colname = "visitStartTime"
            create_journey_id_based_on_conversion = True

        ################################
        #### group_channels == True ####
        ################################

        if group_channels:
            # Sorting and converting variables
            df[group_timestamp_colname] = pd.to_datetime(df[group_timestamp_colname])
            df.sort_values(
                group_channels_by_id_list + [group_timestamp_colname], inplace=True
            )
            self.original_df = df.copy()

            if create_journey_id_based_on_conversion:

                df = journey_id_based_on_conversion(
                    df=df,
                    group_id=group_channels_by_id_list,
                    transaction_colname=journey_with_conv_colname,
                )
                group_channels_by_id_list = [
                    "journey_id",
                    "journey_rnk",
                ] + group_channels_by_id_list
                # Reduce memory consumption
                reduce_mem_usage(df)

            # Grouping timestamp based on group_channels_by_id_list
            ####################################################
            self.print("Grouping timestamp...")
            df_temp = df[
                group_channels_by_id_list + [session_id_col, group_timestamp_colname]
            ]
            # mantém NaN nos casos em que não teve conversão
            df_temp = df_temp.merge(
                df[df[journey_with_conv_colname]]
                .groupby(group_channels_by_id_list)
                .agg({group_timestamp_colname: "max", session_id_col: "min"}),
                on=group_channels_by_id_list,
                how="left",
            )
            # calculating the time till conversion
            ######################################
            df_temp["time_till_conv"] = (
                df_temp[group_timestamp_colname + "_y"]
                - df_temp[group_timestamp_colname + "_x"]
            ).astype("timedelta64[s]") / 3600
            df_temp["time_till_conv"] = df_temp["time_till_conv"].round(4)
            df_temp.rename(
                columns={
                    group_timestamp_colname + "_y": "conversion_time",
                    session_id_col + "_y": session_id_col + "_conv",
                    session_id_col + "_x": session_id_col,
                },
                inplace=True,
            )

            # filter by attribution window
            df_temp = df_temp[
                (df_temp.time_till_conv.isnull())
                | (df_temp.time_till_conv <= self.attribution_window)
            ]
            valid_sessions = df_temp[
                session_id_col
            ]  # only sessions in attribution window

            self.df_conversion_time = df_temp[~df_temp.conversion_time.isnull()][
                ["journey_id", "conversion_time", session_id_col + "_conv"]
            ].drop_duplicates()

            # merge time till conv into original df
            self.original_df = (
                self.original_df.merge(
                    df_temp[
                        [
                            session_id_col,
                            "time_till_conv",
                            "conversion_time",
                            session_id_col + "_conv",
                        ]
                    ],
                    on=session_id_col,
                    how="inner",
                )
                .drop_duplicates()
                .reset_index(drop=True)
            )

            df_temp = (
                df_temp.groupby(group_channels_by_id_list, sort=False)["time_till_conv"]
                .apply(list)
                .reset_index()
            )
            self.time_till_conv = df_temp["time_till_conv"]
            self.print("Status: Done")

            # Filter whole df by valid sessions
            df = df[df[session_id_col].isin(valid_sessions)]

            # Grouping sessions based on group_channels_by_id_list
            ######################################################
            sessions = (
                df.groupby(group_channels_by_id_list, sort=False)[session_id_col]
                .apply(list)
                .reset_index()
            )
            self.sessions = sessions[session_id_col]

            # Grouping channels based on group_channels_by_id_list
            ######################################################

            self.print("group_channels == True")
            self.print("Grouping channels...")
            temp_channels = (
                df.groupby(group_channels_by_id_list, sort=False)[channels_colname]
                .apply(list)
                .reset_index()
            )
            self.channels = temp_channels[channels_colname]
            self.print("Status: Done")

            if journey_with_conv_colname is None:

                # If journey_with_conv_colname is None, we will assume that
                # all journeys ended in a conversion
                ###########################################################
                self.journey_with_conv = self.channels.apply(lambda x: True)
                self.journey_id = pd.Series(df[group_channels_by_id_list].unique())

            else:
                # Grouping unique journeys and whether the journey ended with a
                # conversion
                ##########################################################
                self.print("Grouping journey_id and journey_with_conv...")
                df_temp = df[group_channels_by_id_list + [journey_with_conv_colname]]
                # df_temp = df[group_channels_by_id_list + [journey_with_conv_colname]][
                #     df[session_id_col].isin(valid_sessions)
                # ]
                temp_journey_id_conv = (
                    df_temp.groupby(group_channels_by_id_list, sort=False)[
                        journey_with_conv_colname
                    ]
                    .max()
                    .reset_index()
                )
                self.journey_id = temp_journey_id_conv[group_channels_by_id_list]
                self.print("Status: Done")
                self.journey_with_conv = temp_journey_id_conv[journey_with_conv_colname]
                self.print("Status: Done")

            # conversion_value could be a single int value or a panda series
            if isinstance(conversion_value, int):
                self.conversion_value = self.journey_with_conv.apply(
                    lambda valor: conversion_value if valor else 0
                )
            else:
                self.conversion_value = (
                    df.groupby(group_channels_by_id_list, sort=False)[conversion_value]
                    .sum()
                    .reset_index()[conversion_value]
                )

        #################
        ### DataFrame ###
        #################

        self.DataFrame = None
        self.as_pd_dataframe()

    ######################################
    ##### Section 2: Output methods  #####
    ######################################

    def print(self, *args, **kwargs):
        if self.verbose:
            print(*args, **kwargs)

    def as_pd_dataframe(self):
        """Return inputed attributes as a Pandas Data Frame on
        self.DataFrame."""
        if not (isinstance(self.DataFrame, pd.DataFrame)):
            if isinstance(self.journey_id, pd.DataFrame):
                self.DataFrame = self.journey_id
                self.DataFrame["channels_agg"] = self.channels.apply(
                    lambda x: self.sep.join(x)
                )
                self.DataFrame["sessions_agg"] = self.sessions
                self.DataFrame["converted_agg"] = self.journey_with_conv
                self.DataFrame["conversion_value"] = self.conversion_value
                self.DataFrame = self.DataFrame.merge(
                    self.df_conversion_time, on="journey_id", how="left"
                ).rename(columns={self.session_id_col + "_conv": "session_id"})
            else:
                self.DataFrame = pd.DataFrame(
                    {
                        "journey_id": self.journey_id,
                        "channels_agg": self.channels.apply(lambda x: self.sep.join(x)),
                        "converted_agg": self.journey_with_conv,
                        "conversion_value": self.conversion_value,
                    }
                )
            if self.time_till_conv is None:
                self.DataFrame["time_till_conv_agg"] = None
            else:
                self.DataFrame["time_till_conv_agg"] = self.time_till_conv.apply(
                    lambda x: self.sep.join([str(value) for value in x])
                )

        return self.DataFrame

    def attribution_all_models(
        self,
        model_type: str = "all",
        exclude_models: list = None,
        last_click_non_but_not_this_channel="Direct",
        time_decay_decay_over_time=0.5,
        time_decay_frequency=128,
        shapley_size=4,
        shapley_order=False,
        shapley_values_col="conv_rate",
        markov_transition_to_same_state=False,
        group_by_channels_models=True,
    ):
        """Runs all heuristic models on this class and returns a data frame.

        Models:
           - attribution_last_click_non
           - attribution_first_click
           - attribution_linear
           - attribution_position_based
           - attribution_time_decay
        Parameters:
        model_type = 'all',
                     'heuristic',
                     'algorithmic'
        """

        if model_type == "all":
            heuristic = True
            algorithmic = True
        elif model_type == "heuristic":
            heuristic = True
            algorithmic = False
        else:
            heuristic = False
            algorithmic = True

        if heuristic:
            # Running attribution_last_click
            if (
                exclude_models
                and "attribution_last_click" not in exclude_models
                and exclude_models
            ):
                self.attribution_last_click(
                    group_by_channels_models=group_by_channels_models
                )

            # Running attribution_last_click_non
            if exclude_models and "attribution_last_click_non" not in exclude_models:
                self.attribution_last_click_non(
                    but_not_this_channel=last_click_non_but_not_this_channel
                )

            # Running attribution_first_click
            if exclude_models and "attribution_first_click" not in exclude_models:
                self.attribution_first_click(
                    group_by_channels_models=group_by_channels_models
                )

            # Running attribution_linear
            if exclude_models and "attribution_linear" not in exclude_models:
                self.attribution_linear(
                    group_by_channels_models=group_by_channels_models
                )

            # Running attribution_position_based
            if exclude_models and "attribution_position_based" not in exclude_models:
                self.attribution_position_based(
                    group_by_channels_models=group_by_channels_models
                )

            # Running attribution_time_decay
            if exclude_models and "attribution_time_decay" not in exclude_models:
                self.attribution_time_decay(
                    decay_over_time=time_decay_decay_over_time,
                    frequency=time_decay_frequency,
                    group_by_channels_models=group_by_channels_models,
                )

        if algorithmic:

            # Running attribution_shapley
            if exclude_models and "attribution_shapley" not in exclude_models:
                self.attribution_shapley(
                    size=shapley_size,
                    order=shapley_order,
                    group_by_channels_models=group_by_channels_models,
                    values_col=shapley_values_col,
                )

            # Running attribution markov
            if exclude_models and "attribution_markov" not in exclude_models:
                self.attribution_markov(
                    transition_to_same_state=markov_transition_to_same_state
                )

        return self.group_by_channels_models

    def plot(
        self,
        model_type="all",
        sort_model=None,
        number_of_channels=10,
        other_df=None,
        *args,
        **kwargs,
    ):

        """Barplot of the results that were generated and stored on the
        variable self.group_by_channels_models.

        Parameters:
        model_type = ['all',
                       'heuristic'
                       'algorithmic']
        sort_model = has to be a string and accept regex by inputing r'example'
        other_df = None. In case the user wants to use a new data frame
        """

        model_types = {
            "all": "all",
            "heuristic": r"heuristic",
            "algorithmic": r"algorithmic",
        }

        if not isinstance(other_df, pd.DataFrame):
            # Checking if there are any results on self.group_by_channels_models
            if isinstance(self.group_by_channels_models, pd.DataFrame):
                df_plot = self.group_by_channels_models
            else:
                ax = "self.group_by_channels_models == None"
        else:
            df_plot = other_df

        # Sorting self.group_by_channels_models
        if sort_model != None:
            # List comprehension to accept regex
            df_plot = df_plot.sort_values(
                [[x for x in df_plot.columns if (re.search(sort_model, x))]][0],
                ascending=True,
            )

        # Selecting columns that matches the pattern
        if model_types[model_type] != "all":
            df_plot = df_plot[
                ["channels"]
                + [x for x in df_plot.columns if re.search(model_types[model_type], x)]
            ]

        # Subsetting the results based on the number of channels to be shown
        df_plot = df_plot.tail(number_of_channels)

        # Melting DF so the results are devided into 'channels', 'variable' and 'value'
        df_plot = pd.melt(df_plot, id_vars="channels")

        # Plot Parameters
        ax, fig = plt.subplots(figsize=(20, 7))
        ax = sns.barplot(
            data=df_plot, hue="variable", y="value", x="channels", *args, **kwargs
        )
        plt.xticks(rotation=15)
        ax.legend(loc="upper left", frameon=True, fancybox=True)
        ax.axhline(0, color="black", linestyle="-", alpha=1, lw=2)
        ax.grid(color="gray", linestyle=":", linewidth=1, axis="y")
        ax.set_frame_on(False)

        return ax

    def channels_journey_time_based_overwrite(
        self, selected_channel="Direct", time_window=24, order=1, inplace=False
    ):
        """Overwrites channels in the conversion jorney that matches the
        criteria with the previous channel in the journey:

          - Is equal to the selected_channel;
          - The diference between the contacts is less than the time_window selected;

        Parameters:
        selected_channel =
            Channel to be overwritten;
        time_window =
            The time window in hours that the selected channel will be overwritten;
        order =
            How many times the function will loop throught the same journey;
            ex: journey [Organic > Direct > Direct]
              order 1 output: [Organic > Organic > Direct]
              order 2 output: [Organic > Organic > Organic]
        """
        frame = self.channels.to_frame(name="channels")
        frame["time_till_conv_window"] = self.time_till_conv.apply(
            lambda time_till_conv: [time_window + 1]
            + [
                time - time_till_conv[i + 1]
                for i, time in enumerate(time_till_conv)
                if i < len(time_till_conv) - 1
            ]
        )
        frame["time_till_conv_window"] = frame["time_till_conv_window"].apply(
            lambda time_till_conv: np.absolute(np.asarray(time_till_conv)).tolist()
        )
        loop_count = 0
        while loop_count < order:
            frame["channels"] = frame.apply(
                lambda x: [
                    x.channels[i - 1]
                    if ((canal == selected_channel) & (time < time_window))
                    else canal
                    for i, (canal, time) in enumerate(
                        zip(x.channels, x.time_till_conv_window)
                    )
                ],
                axis=1,
            )
            loop_count += 1

        if inplace:
            self.channels = frame["channels"].copy()
            new_channels = None
        else:
            new_channels = frame["channels"].copy()

        return new_channels

    def group_by_results_function(self, channels_value, model_name):
        """Internal function to generate the group_by_channels_models.

        A pandas DF containing the attributed values for each channel
        """
        channels_list = []
        self.channels.apply(lambda x: channels_list.extend(x))
        values_list = []
        channels_value.apply(lambda x: values_list.extend(x))

        frame = pd.DataFrame({"channels": channels_list, "value": values_list})
        frame = frame.groupby(["channels"])["value"].sum()

        if isinstance(self.group_by_channels_models, pd.DataFrame):
            frame = frame.reset_index()
            frame.columns = ["channels", model_name]
            self.group_by_channels_models = pd.merge(
                self.group_by_channels_models, frame, how="outer", on=["channels"]
            ).fillna(0)
        else:
            self.group_by_channels_models = frame.reset_index()
            self.group_by_channels_models.columns = ["channels", model_name]

        return frame

    ##############################################
    #
    #
    #  Begin of new methods
    #
    #
    #################################

    def first_click_journeys(self):
        """Returns an object that contains First Click results with journey
        granularity."""
        if self.__first_click is None:
            warnings.warn(
                "In order to call this method, attribution_first_click method must "
                + "be called first."
            )
        else:
            return self.__first_click[0]

    def first_click_channels(self):
        """Returns an object that contains First Click results with channel
        granularity."""
        if self.__first_click is None:
            warnings.warn(
                "In order to call this method, attribution_first_click method must "
                + "be called first."
            )
        else:
            return self.__first_click[1]

    def last_click_journeys(self):
        """Returns an object that contains Last Click results with journey
        granularity."""
        if self.__last_click is None:
            warnings.warn(
                "In order to call this method, attribution_last_click method must "
                + "be called first."
            )
        else:
            return self.__last_click[0]

    def last_click_channels(self):
        """Returns an object that contains Last Click results with channel
        granularity."""
        if self.__last_click is None:
            warnings.warn(
                "In order to call this method, attribution_last_click method must "
                + "be called first."
            )
        else:
            return self.__last_click[1]

    def last_click_non_journeys(self):
        """Returns an object that contains Last Click ignoring a specific
        channel results with journey granularity."""
        if self.__last_click_non is None:
            warnings.warn(
                "In order to call this method, attribution_last_click_non method "
                + "must be called first."
            )
        else:
            return self.__last_click_non[0]

    def last_click_non_channels(self):
        """Returns an object that contains Last Click ignoring a specific
        channel results with channel granularity."""
        if self.__last_click_non is None:
            warnings.warn(
                "In order to call this method, attribution_last_click_non method "
                + "must be called first."
            )
        else:
            return self.__last_click_non[1]

    def linear_journeys(self):
        """Returns an object that contains Linear results with journey
        granularity."""
        if self.__linear is None:
            warnings.warn(
                "In order to call this method, attribution_linear method must be "
                + "called first."
            )
        else:
            return self.__linear[0]

    def linear_channels(self):
        """Returns an object that contains Linear results with channel
        granularity."""
        if self.__linear is None:
            warnings.warn(
                "In order to call this method, attribution_linear method must be "
                + "called first."
            )
        else:
            return self.__linear[1]

    def position_based_journeys(self):
        """Returns an object that contains Position based results with journey
        granularity."""
        if self.__position_based is None:
            warnings.warn(
                "In order to call this method, attribution_position_based method "
                + "must be called first."
            )
        else:
            return self.__position_based[0]

    def position_based_channels(self):
        """Returns an object that contains Position Based results with channel
        granularity."""
        if self.__position_based is None:
            warnings.warn(
                "In order to call this method, attribution_position_based method "
                + "must be called first."
            )
        else:
            return self.__position_based[1]

    def time_decay_journeys(self):
        """Returns an object that contains Time Decay results with journey
        granularity."""
        if self.__time_decay is None:
            warnings.warn(
                "In order to call this method, attribution_time_decay method must "
                + "be called first."
            )
        else:
            return self.__time_decay[0]

    def time_decay_channels(self):
        """Returns an object that contains Time Decay results with channel
        granularity."""
        if self.__first_click is None:
            warnings.warn(
                "In order to call this method, attribution_time_decay method must "
                + "be called first"
            )
        else:
            return self.__time_decay[1]

    ###################################################
    ##### Section 3: Channel Attribution methods  #####
    ###################################################

    def attribution_last_click(self, group_by_channels_models=True):
        """The last touchpoint receives all the credit.

        Parameters:
        group_by_channels_models = True by default.
            Will aggregate the attributed results by each channel on
            self.group_by_channels_models
        """
        model_name = "attribution_last_click_heuristic"

        # Results part 1: Column values
        # Results in the same format as the DF
        channels_value = self.channels.apply(
            lambda channels: np.asarray(([0] * (len(channels) - 1)) + [1])
        )
        # multiplying the results with the conversion value
        channels_value = channels_value * self.conversion_value
        # multiplying with the boolean column that indicates whether the conversion
        # happened
        channels_value = channels_value * self.journey_with_conv.apply(int)
        channels_value = channels_value.apply(lambda values: values.tolist())

        # Adding the results to self.DataFrame
        self.as_pd_dataframe()
        self.DataFrame[model_name] = channels_value.apply(
            lambda x: self.sep.join([str(value) for value in x])
        )

        # Add results to original DataFrame
        self.original_df[model_name] = channels_value.explode().reset_index(drop=True)

        # Results part 2: Results
        if group_by_channels_models:

            # Selecting last channel from the series
            channels_series = self.channels.apply(lambda x: x[-1])

            # Creating a data_frame where we have the last channel and the
            # conversion values
            frame = channels_series.to_frame(name="channels")
            # multiplying with the boolean column that indicates if the conversion
            # happened
            frame["value"] = self.conversion_value * self.journey_with_conv.apply(int)

            # Grouping by channels and adding the values
            frame = frame.groupby(["channels"])["value"].sum()

            # Grouped Results
            if isinstance(self.group_by_channels_models, pd.DataFrame):
                frame = frame.reset_index()
                frame.columns = ["channels", model_name]
                self.group_by_channels_models = pd.merge(
                    self.group_by_channels_models, frame, how="outer", on=["channels"]
                ).fillna(0)
            else:
                self.group_by_channels_models = frame.reset_index()
                self.group_by_channels_models.columns = ["channels", model_name]
        else:
            frame = "group_by_channels_models = False"

        self.__last_click = (channels_value, frame)

        return self.__last_click

    def attribution_last_click_non(
        self, but_not_this_channel="Direct", group_by_channels_models=True
    ):
        """All the traffic from a Specific channel is ignored, and 100% of the credit
        for the sale goes to the last channel that the customer clicked through from
        before converting.

        Parameters:
        but_not_this_channel =
            Channel to be overwritten.
        group_by_channels_models = True by default.
            Will aggregate the attributed results by each channel on
            self.group_by_channels_models
        """
        model_name = "attribution_last_click_non_" + but_not_this_channel + "_heuristic"

        # Results part 1: Column values
        # Results in the same format as the DF
        channels_value = self.channels.apply(
            lambda canais: np.asarray(
                [
                    1
                    if i
                    == max(
                        [
                            i if canal != but_not_this_channel else 0
                            for i, canal in enumerate(canais)
                        ]
                    )
                    else 0
                    for i, canal in enumerate(canais)
                ]
            )
        )
        # multiplying the results with the conversion value
        channels_value = channels_value * self.conversion_value
        # multiplying with the boolean column that indicates if the conversion
        # happened
        channels_value = channels_value * self.journey_with_conv.apply(int)
        channels_value = channels_value.apply(lambda values: values.tolist())

        # Adding the results to self.DataFrame
        self.as_pd_dataframe()
        self.DataFrame[model_name] = channels_value.apply(
            lambda x: self.sep.join([str(value) for value in x])
        )

        # Add results to original DataFrame
        self.original_df[model_name] = channels_value.explode().reset_index(drop=True)

        # Results part 2: Results
        if group_by_channels_models:

            # Selecting the last channel that is not the one chosen
            channels_series = self.channels.apply(
                lambda canais: (
                    canais[-1]
                    if len([canal for canal in canais if canal != but_not_this_channel])
                    == 0
                    else canais[
                        max(
                            [
                                i
                                for i, canal in enumerate(canais)
                                if canal != but_not_this_channel
                            ]
                        )
                    ]
                )
            )

            # Creating a data_frame where we have the last channel and the
            # conversion values
            frame = channels_series.to_frame(name="channels")
            # multiplying with the boolean column that indicates whether the conversion
            # happened
            frame["value"] = self.conversion_value * self.journey_with_conv.apply(int)

            # Grouping by channels and adding the values
            frame = frame.groupby(["channels"])["value"].sum()

            if isinstance(self.group_by_channels_models, pd.DataFrame):
                frame = frame.reset_index()
                frame.columns = ["channels", model_name]
                self.group_by_channels_models = pd.merge(
                    self.group_by_channels_models, frame, how="outer", on=["channels"]
                ).fillna(0)
            else:
                self.group_by_channels_models = frame.reset_index()
                self.group_by_channels_models.columns = ["channels", model_name]

        self.__last_click_non = (channels_value, frame)

        return self.__last_click_non

    def attribution_first_click(self, group_by_channels_models=True):
        """The first touchpoint recieves all the credit.

        Parameters:
        group_by_channels_models = True by default.
            Will aggregate the attributed results by each channel on
            self.group_by_channels_models.
        """
        model_name = "attribution_first_click_heuristic"

        # Results part 1: Column values
        ###############################

        # Results in the same format as the DF
        channels_value = self.channels.apply(
            lambda channels: np.asarray([1] + ([0] * (len(channels) - 1)))
        )
        # multiplying the results with the conversion value
        channels_value = channels_value * self.conversion_value
        # multiplying with the boolean column that indicates if the conversion
        # happened
        channels_value = channels_value * self.journey_with_conv.apply(int)
        channels_value = channels_value.apply(lambda values: values.tolist())

        # Adding the results to self.DataFrame
        self.as_pd_dataframe()
        self.DataFrame[model_name] = channels_value.apply(
            lambda x: self.sep.join([str(value) for value in x])
        )
        # Add results to original DataFrame
        self.original_df[model_name] = channels_value.explode().reset_index(drop=True)

        # Results part 2: Grouped Results
        #################################

        if group_by_channels_models:
            # Selecting first channel from the series
            channels_series = self.channels.apply(lambda x: x[0])

            # Creating a data_frame where we have the last channel and the
            # conversion values
            frame = channels_series.to_frame(name="channels")
            # multiplying with the boolean column that indicates if the conversion
            # happened
            frame["value"] = self.conversion_value * self.journey_with_conv.apply(int)

            # Grouping by channels and adding the values
            frame = frame.groupby(["channels"])["value"].sum()

            if isinstance(self.group_by_channels_models, pd.DataFrame):
                frame = frame.reset_index()
                frame.columns = ["channels", model_name]
                self.group_by_channels_models = pd.merge(
                    self.group_by_channels_models, frame, how="outer", on=["channels"]
                ).fillna(0)
            else:
                self.group_by_channels_models = frame.reset_index()
                self.group_by_channels_models.columns = ["channels", model_name]

        self.__first_click = (channels_value, frame)

        return self.__first_click

    def attribution_linear(self, group_by_channels_models=True):
        """Each touchpoint in the conversion path has an equal value.

        Parameters:
        group_by_channels_models = True by default.
            Will aggregate the attributed results by each channel on
            self.group_by_channels_models.
        """
        model_name = "attribution_linear_heuristic"

        channels_count = self.channels.apply(lambda x: len(x))
        channels_value = (
            self.conversion_value * self.journey_with_conv.apply(int) / channels_count
        ).apply(lambda x: [x]) * channels_count

        # Adding the results to self.DataFrame
        self.as_pd_dataframe()
        self.DataFrame[model_name] = channels_value.apply(
            lambda x: self.sep.join(
                [str(round(value, self.round_values_to)) for value in x]
            )
        )
        # Add results to original DataFrame
        self.original_df[model_name] = channels_value.explode().reset_index(drop=True)

        # Grouping the attributed values for each channel
        if group_by_channels_models:
            frame = self.group_by_results_function(channels_value, model_name)
        else:
            frame = "group_by_channels_models = False"

        self.__linear = (channels_value, frame)

        return self.__linear

    def attribution_position_based(
        self,
        list_positions_first_middle_last=[0.4, 0.2, 0.4],
        group_by_channels_models=True,
    ):
        """First and last contact have preset values, middle touchpoints are evenly
        distributed with the chosen weight.

        default:
         - First channel = 0.4
         - Distributed among the middle channels = 0.2
         - Last channel = 0.4

        Parameters:
        list_positions_first_middle_last =
            List with percentages that will be given to each position
        group_by_channels_models = True by default.
            Will aggregate the attributed results by each channel on
            self.group_by_channels_models
        """
        model_name = (
            "attribution_position_based_"
            + "_".join([str(value) for value in list_positions_first_middle_last])
            + "_heuristic"
        )

        # Selecting last channel from the series
        channels_value = self.channels.apply(
            lambda canais: np.asarray([1])
            if len(canais) == 1
            else np.asarray(
                [
                    list_positions_first_middle_last[0]
                    + list_positions_first_middle_last[1] / 2,
                    list_positions_first_middle_last[2]
                    + list_positions_first_middle_last[1] / 2,
                ]
            )
            if len(canais) == 2
            else np.asarray(
                [list_positions_first_middle_last[0]]
                + [list_positions_first_middle_last[1] / (len(canais) - 2)]
                * (len(canais) - 2)
                + [list_positions_first_middle_last[0]]
            )
        )
        # multiplying the results with the conversion value
        channels_value = channels_value * self.conversion_value
        # multiplying with the boolean column that indicates if the conversion
        # happened
        channels_value = channels_value * self.journey_with_conv.apply(int)
        channels_value = channels_value.apply(lambda values: values.tolist())

        # Adding the results to self.DataFrame
        self.as_pd_dataframe()
        self.DataFrame[model_name] = channels_value.apply(
            lambda x: self.sep.join([str(value) for value in x])
        )
        # Add results to original DataFrame
        self.original_df[model_name] = channels_value.explode().reset_index(drop=True)

        # Grouping the attributed values for each channel
        if group_by_channels_models:
            frame = self.group_by_results_function(channels_value, model_name)
        else:
            frame = "group_by_channels_models = False"

        self.__position_based = (channels_value, frame)

        return self.__position_based

    def attribution_position_decay(self, group_by_channels_models=True):
        """Linear decay for each touchpoint further from conversion.

        Parameters:
        group_by_channels_models = True by default.
            Will aggregate the attributed results by each channel on
            self.group_by_channels_models

        OBS: This function is WIP.
        """
        model_name = "attribution_position_decay_heuristic"

        channels_value = self.channels.apply(
            lambda channels: np.asarray([1])
            if len(channels) == 1
            else (
                np.asarray(list(range(1, len(channels) + 1)))
                / np.sum(np.asarray(list(range(1, len(channels) + 1))))
            )
        )
        # multiplying the results with the conversion value
        channels_value = channels_value * self.conversion_value
        # multiplying with the boolean column that indicates if the conversion
        # happened
        channels_value = channels_value * self.journey_with_conv.apply(int)
        channels_value = channels_value.apply(lambda values: values.tolist())

        # Adding the results to self.DataFrame
        self.as_pd_dataframe()
        self.DataFrame[model_name] = channels_value.apply(
            lambda x: self.sep.join([str(value) for value in x])
        )
        # Add results to original DataFrame
        self.original_df[model_name] = channels_value.explode().reset_index(drop=True)

        # Grouping the attributed values for each channel
        if group_by_channels_models:
            frame = self.group_by_results_function(channels_value, model_name)
        else:
            frame = "group_by_channels_models = False"

        return (channels_value, frame)

    def attribution_time_decay(
        self, decay_over_time=0.5, frequency=24, group_by_channels_models=True
    ):
        """Decays for each touchpoint further from conversion.

        Parameters:
        decay_over_time =
            Percentage that will be lost by time away from the conversion.
        frequency =
            The frequency in hours that the decay will happen.
        group_by_channels_models = True by default.
            Will aggregate the attributed results by each channel on
            self.group_by_channels_models
        """
        model_name = (
            "attribution_time_decay"
            + str(decay_over_time)
            + "_freq"
            + str(frequency)
            + "_heuristic"
        )

        if self.time_till_conv is None:
            print("time_till_conv is None, attribution_time_decay model will not work")

        else:
            # Removing zeros and dividing by the frequency
            time_till_conv_window = self.time_till_conv.apply(
                lambda time_till_conv: np.exp(
                    math.log(decay_over_time)
                    * np.floor(np.asarray(time_till_conv) / frequency)
                )
                / sum(
                    np.exp(
                        math.log(decay_over_time)
                        * np.floor(np.asarray(time_till_conv) / frequency)
                    )
                )
            )

            # multiplying the results with the conversion value
            channels_value = time_till_conv_window * self.conversion_value
            # multiplying with the boolean column that indicates if the conversion
            # happened
            channels_value = channels_value * self.journey_with_conv.apply(int)
            channels_value = channels_value.apply(lambda values: values.tolist())

            # Adding the results to self.DataFrame
            self.as_pd_dataframe()
            self.DataFrame[model_name] = channels_value.apply(
                lambda x: self.sep.join([str(value) for value in x])
            )
            # Add results to original DataFrame
            self.original_df[model_name] = channels_value.explode().reset_index(
                drop=True
            )

            # Grouping the attributed values for each channel
            if group_by_channels_models:
                frame = self.group_by_results_function(channels_value, model_name)
            else:
                frame = "group_by_channels_models = False"

        self.__time_decay = (channels_value, frame)

        return self.__time_decay

    def attribution_markov(
        self,
        transition_to_same_state=False,
        group_by_channels_models=True,
        conversion_value_type="binary",
    ):
        model_name = "attribution_markov"
        model_type = "_algorithmic"
        model_name = model_name + model_type

        allowed_conversion_value_types = ["binary", "integer", "frequency", "monetary"]
        if conversion_value_type not in allowed_conversion_value_types:
            raise ValueError(
                "conversion_value_type must be one of the following: "
                + ", ".join(allowed_conversion_value_types)
            )

        def power_to_infinity(matrix):
            """Raises a square matrix to an infinite power using eigendecomposition.

            All matrix rows must add to 1.
            M = Q*L*inv(Q), where L = eigenvalue diagonal values, Q = eigenvector matrix
            M^N = Q*(L^N)*inv(Q)
            """
            eigen_value, eigen_vectors = np.linalg.eig(matrix)

            # At infinity everything converges to 0 or 1, thus we use np.trunc()
            diagonal = np.diag(np.trunc(eigen_value.real + 0.001))
            try:
                result = (eigen_vectors @ diagonal @ np.linalg.inv(eigen_vectors)).real
            except np.linalg.LinAlgError as err:
                if "Singular matrix" in str(err):
                    warnings.warn(
                        "Warning... Singular matrix error. Check for lines or cols "
                        + "fully filled with zeros."
                    )
                    result = (
                        eigen_vectors @ diagonal @ np.linalg.pinv(eigen_vectors)
                    ).real
                else:
                    raise
            return result

        def normalize_rows(matrix: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
            size = matrix.shape[0]
            mean = matrix.sum(axis=1).reshape((size, 1))
            mean = np.where(mean == 0, 1, mean)
            return matrix / mean

        def calc_total_conversion(matrix) -> float:
            normal_matrix = normalize_rows(matrix)
            infinity_matrix = power_to_infinity(normal_matrix)
            return infinity_matrix[0, -1]

        def removal_effect(matrix) -> npt.NDArray[np.float64]:
            size = matrix.shape[0]
            conversions = np.zeros(size)
            for column in range(1, size - 2):
                temp = matrix.copy()
                temp[:, -2] = temp[:, -2] + temp[:, column]
                temp[:, column] = 0
                conversions[column] = calc_total_conversion(temp)
            conversion_orig: float = calc_total_conversion(matrix)
            return 1 - (conversions / conversion_orig)

        def path_to_matrix(paths: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
            channel_max = int(paths[:, 0:2].max()) + 1
            matrix = np.zeros((channel_max, channel_max), dtype="float")
            for x, y, val in paths:
                matrix[int(x), int(y)] = val
            matrix[-1, -1] = 1
            matrix[-2, -2] = 1
            return matrix

        temp = self.channels.apply(
            lambda x: ["(inicio)"] + x
        ) + self.journey_with_conv.apply(lambda x: ["(conversion)" if x else "(null)"])

        orig = []
        dest = []
        journey_length = []

        def save_orig_dest(arr):
            orig.extend(arr[:-1])
            dest.extend(arr[1:])
            journey_length.append(len(arr))

        temp.apply(save_orig_dest)

        # copying conversion_quantity to each new row
        if (
            np.issubdtype(self.conversion_value.dtype, float)
            and conversion_value_type == "integer"
        ):
            # we do not hava a frequency column yet so we are using
            # self.conversion_value.apply(lambda x: 1) to count each line
            conversion_quantity = self.conversion_value.apply(lambda x: 1)
        else:
            if conversion_value_type == "binary":
                freq_values = self.conversion_value.apply(lambda x: 1)
            elif conversion_value_type == "frequency":
                freq_values = self.conversion_value
            elif conversion_value_type in ["monetary", "integer"]:
                # in this case, we count 1 for non-conversions
                # and some n>0 for multiple conversions in the same journey
                freq_values = self.conversion_value.apply(lambda x: max(x, 1))

            conversion_quantity = []

            for a, b in zip(freq_values, journey_length):
                conversion_quantity.extend([a] * (b - 1))

        temp = pd.DataFrame({"orig": orig, "dest": dest, "count": conversion_quantity})
        temp = temp.groupby(["orig", "dest"], as_index=False).sum()
        self.print(temp)

        if not transition_to_same_state:
            temp = temp[temp.orig != temp.dest]

        # Converting channels_names to index and pass a numpy array foward
        channels_names = list(
            (set(temp.orig) - set(["(inicio)"]))
            | (set(temp.dest) - set(["(conversion)", "(null)"]))
        )
        channels_names.sort()
        channels_names = ["(inicio)"] + channels_names + ["(null)", "(conversion)"]
        temp["orig"] = temp.orig.apply(channels_names.index)
        temp["dest"] = temp.dest.apply(channels_names.index)
        matrix = path_to_matrix(temp[["orig", "dest", "count"]].values)
        removal_effect_result = removal_effect(matrix)[1:-2]
        results = removal_effect_result / removal_effect_result.sum(axis=0)

        # Channels weights
        frame = pd.DataFrame({"value": results}, index=channels_names[1:-2])
        removal_effect_result = pd.DataFrame(
            {"removal_effect": removal_effect_result}, index=channels_names[1:-2]
        )

        # Transition matrix
        matrix = normalize_rows(matrix)
        matrix = pd.DataFrame(matrix, columns=channels_names, index=channels_names)

        # Apply weights back to each journey
        chmap = {a: b[0] for a, b in zip(frame.index.values, frame.values)}
        _df = pd.concat([self.channels, self.conversion_value], axis=1)
        channels_value = _df.apply(
            lambda row: [
                chmap[x] * row[self.conversion_value_colname]
                for x in row[self.channels_colname]
            ],
            axis=1,
        )
        # normalize
        channels_value = channels_value.apply(lambda x: list(np.array(x) / sum(x)))

        # Adding the results to self.DataFrame
        self.as_pd_dataframe()
        self.DataFrame[model_name] = pd.Series(
            [
                self.sep.join(
                    [
                        str(round(value, self.round_values_to) * n_purchases)
                        for value in value_list
                    ]
                )
                for value_list, n_purchases in zip(channels_value, freq_values)
            ]
        )
        # Add results to original DataFrame
        # self.original_df[model_name] = channels_value.explode().reset_index(drop=True)
        self.original_df[model_name] = (
            pd.Series(
                [
                    [value * n_purchases for value in value_list]
                    for value_list, n_purchases in zip(channels_value, freq_values)
                ]
            )
            .explode()
            .reset_index(drop=True)
        )

        # Grouping the attributed values for each channel
        total_conv_value = self.journey_with_conv * self.conversion_value
        if group_by_channels_models:
            if isinstance(self.group_by_channels_models, pd.DataFrame):
                frame = frame.reset_index()
                frame.columns = ["channels", model_name]
                frame[model_name] = frame[model_name] * total_conv_value.sum()
                self.group_by_channels_models = pd.merge(
                    self.group_by_channels_models, frame, how="outer", on=["channels"]
                ).fillna(0)
            else:
                frame = frame.reset_index()
                frame.columns = ["channels", model_name]
                frame[model_name] = frame[model_name] * total_conv_value.sum()
                self.group_by_channels_models = frame
        else:
            frame = "group_by_channels_models = False"

        return (channels_value, frame, matrix, removal_effect_result)

    def journey_conversion_table(self, order=False, size=None):
        """Transforms journey channels in boolean columns, count the number of
        conversions and journeys and compute the conversion rate of the channel
        combination.
        """
        # Creating Channels DF
        df_temp = self.journey_id.copy()

        if order:
            df_temp["combinations"] = self.channels.apply(
                lambda channels: sorted(
                    list(set(channels)), key=lambda x: channels.index(x)
                )
            ).copy()
        else:
            df_temp["combinations"] = self.channels.apply(
                lambda channels: sorted(list(set(channels)))
            ).copy()

        if size != None:
            df_temp["combinations"] = df_temp["combinations"].apply(
                lambda channels: self.sep.join(channels[size * -1 :])
            )
        else:
            df_temp["combinations"] = df_temp["combinations"].apply(
                lambda channels: self.sep.join(channels)
            )

        # Adding journey_with_conv column
        df_temp["journey_with_conv"] = self.journey_with_conv.apply(int)
        df_temp["conversion_value"] = self.conversion_value

        # Grouping journey_with_conv
        conv_val = (
            df_temp.groupby(["combinations"])["conversion_value"]
            .sum()
            .reset_index()["conversion_value"]
        )
        df_temp = (
            df_temp.groupby(["combinations"])["journey_with_conv"]
            .agg([("conversions", "sum"), ("total_sequences", "count")])
            .reset_index()
        )
        df_temp["conversion_value"] = conv_val
        # Calculating the conversion rate
        df_temp["conv_rate"] = df_temp["conversions"] / df_temp["total_sequences"]

        return df_temp

    def coalitions(self, size=4, unique_channels=None, order=False):
        """This function gives all the coalitions of different channels in a matrix.
        Most of the extra parameters are used when calculating Shapley's value with
        order.

        Parameters:
        size =
            Limits max size of unique channels in a single journey
        unique_channels =
            By default will check self.channels unique values, or a list of channels can
            be passed as well.
        order =
            Boolean that indicates if the order of channels matters during the process.
        """
        if unique_channels is None:
            unique_channels = list(set(sum(self.channels.values, [])))
        else:
            unique_channels = unique_channels
        channels_combination = []

        # Creating a list with all the permutations if order is True
        if order is True:
            for L in range(0, size + 1):
                for subset in itertools.combinations(unique_channels, L):
                    channels_combination.append(list(subset))
        else:
            for L in range(0, size + 1):
                for subset in itertools.combinations(sorted(unique_channels), L):
                    channels_combination.append(list(subset))

        # Creating a DF with the channels as the boolean columns
        df_temp = pd.Series(channels_combination).to_frame(name="combinations")
        for channel in unique_channels:
            df_temp[channel] = df_temp.combinations.apply(
                lambda channels: any(channel in s for s in channels)
            )

        return df_temp

    def attribution_shapley(
        self,
        size=4,
        order=False,
        values_col="conv_rate",
        merge_custom_values=None,
        group_by_channels_models=True,
    ):
        """Defined by Wikipedia: The Shapley value is a solution concept in Cooperative
        Game Theory.

        It was named in honor of Lloyd Shapley, who introduced it in 1953. To each
        cooperative game it assigns a unique distribution (among the players) of a total
        surplus generated by the coalition of all players. Here in the context of
        marketing channels we can use the model to understand the value of the
        cooperation of channels to generate a conversion.

        Parameters:
        size =
            Limits max size of unique channels in a single journey. If there is a
            journey that has more channels than the defined limit, the last N channels
            will be considered. It's also important to accentuate that increasing the
            number of channels, increases the number calculations exponentially.
        order =
            Boolean that indicates if the order of channels matters during the process.
        values_col =
            The conversion rate is used by default, but the other columns in the
            journey_conversion_table can be used as well like 'conversions',
            'conversion_value'.
        merge_custom_values = None by defaut.
            Can be passed a Pandas Data Frame with two columns only, the first one
            representing the channels combination and the secong the custom value that
            you want to apply as the values_col. Will be merged(Left Join) with grouped
            self.journey_conversion_table() and applied a .fillna().
        group_by_channels_models = True by default.
            Will aggregate the attributed results by each channel on
            self.group_by_channels_models.
        """

        # Creating conv_table that will contain the aggregated results based on the journeys
        conv_table = self.journey_conversion_table(order=order, size=size)

        # Merge merge_custom_values
        if merge_custom_values is not None:
            if not isinstance(merge_custom_values, pd.DataFrame):
                print(
                    "Warning: variable merge_custom_values has to be a Pandas "
                    + "DataFrame containing two columns representing the channels "
                    + "combination and his conv value."
                )
            else:
                try:
                    merge_custom_values.columns = ["combinations", "custom_value"]
                except:
                    print(
                        "merge_custom_values must have two columns only, the first "
                        + "one representing the channels combination and the secong "
                        + "the custom value that you want to apply..."
                    )

                conv_table = pd.merge(
                    conv_table, merge_custom_values, on="combinations", how="left"
                ).fillna(0)
                values_col = "custom_value"

        # Removing all jouneys that have not converted
        conv_table = conv_table[conv_table.conversions > 0]
        channels_shapley = conv_table.combinations.apply(
            lambda x: x.split(self.sep)
        ).copy()
        results = []

        for journey in channels_shapley:

            n = len(journey)

            coalitions = self.coalitions(n, journey, order=order)
            coalitions.combinations = coalitions.combinations.apply(
                lambda x: self.sep.join(x)
            )
            coa = (
                coalitions[1:]
                .drop("combinations", axis=1)
                .astype(int)
                .astype(float)
                .reset_index(drop=True)
            )

            # Merging the coalitions table with the grouped results on conv_table
            valores = (
                pd.merge(coalitions, conv_table, on="combinations", how="left")[
                    values_col
                ]
                .fillna(0)
                .values
            )

            v = valores[1:]
            coaux = coa.copy()

            for line in list(range(0, ((2**n) - 1))):

                for channel in coa.columns:
                    s = len(coaux.iloc[line, :][coaux.iloc[line, :] != 0])
                    if coa[channel][line] == 0:
                        a = (
                            -(math.factorial(s) * math.factorial(n - s - 1))
                            / math.factorial(n)
                            * v[line]
                        )
                        coa[channel][line] = a
                    else:
                        b = (
                            (math.factorial(s - 1) * math.factorial(n - s))
                            / math.factorial(n)
                            * v[line]
                        )
                        coa[channel][line] = b

            results.append(list(coa.sum()))

        # Model col_name
        model_name = "attribution_shapley_size" + str(size) + "_" + values_col
        model_type = "_algorithmic"
        if order:
            model_name = model_name + "_order" + model_type
        else:
            model_name = model_name + model_type

        if (values_col == "conv_rate") or (values_col == "custom_value"):
            conv_table[model_name] = results
            conv_table[model_name] = (
                conv_table[model_name].apply(lambda x: np.asarray(x))
                * conv_table["total_sequences"]
            )
            conv_table[model_name] = (
                conv_table[model_name].apply(lambda x: x / x.sum())
                * conv_table["conversion_value"]
            )
            conv_table[model_name] = conv_table[model_name].apply(lambda x: x.tolist())
        else:
            conv_table[model_name] = results

        ##########################
        # group_by_channels_models#
        ##########################

        # Aggregating the results by unique channel
        if group_by_channels_models:
            channels_list = sum(channels_shapley, [])
            values_list = sum(conv_table[model_name].values, [])
            frame = pd.DataFrame({"channels": channels_list, "value": values_list})
            frame = frame.groupby(["channels"])["value"].sum()

            if isinstance(self.group_by_channels_models, pd.DataFrame):
                frame = frame.reset_index()
                frame.columns = ["channels", model_name]
                self.group_by_channels_models = pd.merge(
                    self.group_by_channels_models, frame, how="outer", on=["channels"]
                ).fillna(0)
            else:
                self.group_by_channels_models = frame.reset_index()
                self.group_by_channels_models.columns = ["channels", model_name]
        else:
            frame = "group_by_channels_models=False"

        return (conv_table, frame)

    def plot_attributions(
        self,
        sort_by_col: str = None,
        number_of_channels: int = 10,
        avoid_models: List = None,
        kind_of_conversion: str = None,
        ax: plt.Axes = None,
        **kwargs,
    ):
        """
        Plot the attributions of the channels. Does not work yet for shapley.
        """

        df = self.group_by_channels_models.copy()
        if avoid_models:
            df = df.drop(columns=avoid_models)
        for col in df.columns[1:]:
            df["perc_" + col] = (df[col] / df[col].sum()).round(4)

        # Sorting self.group_by_channels_models
        if sort_by_col != None:
            df.sort_values(by=sort_by_col, ascending=False, inplace=True)

        df = df[["channels"] + [c for c in df.columns if "perc_" in c]]

        # Subsetting the results based on the number of channels to be shown
        df = df.head(number_of_channels)

        # Melting DF so the results are devided into 'channels', 'variable' and 'value'
        df_plot = pd.melt(df, id_vars="channels")

        # Plot Parameters
        sns.barplot(data=df_plot, hue="variable", x="value", y="channels", **kwargs)
        if not ax:
            f, ax = plt.subplots(1, 1, figsize=(15, 10))
        ax.grid(color="gray", linestyle=":", linewidth=1, axis="both")
        sort_string = (
            f"sorted desc by {re.sub('attribution_', '', sort_by_col)})"
            if sort_by_col
            else ")"
        )
        kind_of_conversion_string = (
            "for " + kind_of_conversion.lower().capitalize()
            if kind_of_conversion
            else ""
        )
        ax.set_title(
            f"Attribution Models {kind_of_conversion_string}\n(top {number_of_channels}{sort_string}"
        )
        ax.set_frame_on(False)
        ax.set_xticks(np.arange(0.0, 1.0, 0.05))
        plt.tight_layout()

        return df
