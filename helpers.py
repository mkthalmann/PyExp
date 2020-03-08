import statistics
from itertools import cycle

import pandas as pd
from plotnine import *

import experiment


def generate_plot(df, dv, by=""):
    """Generate a and return plot to have an overview of the results. Only works for numerical data.

    Arguments:
        df {pandas DF} -- DataFrame containing the results (e.g. from self.merge_all_results)
        dv {str} -- Dependent variable (judgment; reaction_time)

    Keyword Arguments:
        by {str} -- add to generate facets; e.g. 'item' or 'item + id' (default: {""})

    Returns:
        plot -- Seaborn plot object that can be printed
    """
    plot = (ggplot(df, aes("cond", dv, color="cond", pch="cond", group=1))
            # points and lines for means
            + geom_point(stat="summary", fun_y=statistics.mean)
            + geom_line(stat="summary",
                        fun_y=statistics.mean, color="gray")
            # error bars with 95 % CI
            + stat_summary(fun_data='mean_cl_normal',
                           geom="errorbar", width=0.25)
            # single observations as points
            + geom_jitter(alpha=.3, width=.2)
            # no legend
            + guides(color=False, pch=False)
            + theme_minimal()
            + labs(y=f"{dv} +/- 95%CI"))
    # with a faceting argument, add facets to the plot
    if by:
        plot = (plot + facet_wrap(f"~ {by}"))
    return plot


def to_latin_square(df, outname, sub_exp_col="sub_exp", cond_col="cond", item_col="item", item_number_col="item_number"):
    """Take a dataframe with all conditions and restructure it with Latin Square. Saves the files.

    Arguments:
        df {df} -- pandas Dataframe with all conditions for each item
        outname {str} -- Name for the saved files (uniqueness handled automatically); include extension

    Keyword Arguments:
        sub_exp_col {str} -- Column containing the subexperiment identifier (default: {"sub_exp"})
        cond_col {str} -- Column containing the condition identifiers (default: {"cond"})
        item_col {str} -- Column with the item text (default: {"item"})
        item_number_col {str} -- Column with the item number (default: {"item_number"})

    Returns:
        list -- List with all the names of the files that were saved to disk
    """
    # two lists we will be adding the split-up dfs to
    dfs_critical = []
    dfs_filler = []
    # get the extension so we can reuse it for saving process
    name, extension = os.path.splitext(outname)
    # split the dataframe by the sub experiment value
    dfs = [pd.DataFrame(x) for _, x in df.groupby(
        sub_exp_col, as_index=False)]
    for frame in dfs:
        # get the unique condition values and sort them
        conditions = sorted(list(set(frame[cond_col])))

        # do a cartesian product of item numbers and conditions
        products = [(item, cond) for item in set(frame[item_number_col])
                    for cond in conditions]
        # check if all such products exist in the dataframe
        check_list = [((frame[item_number_col] == item)
                       & (frame[cond_col] == cond)).any() for item, cond in products]
        # list the missing combinations
        missing_combos = ', '.join([''.join(map(str, product)) for product, boolean in zip(
            products, check_list) if not boolean])

        # stop the process if not all permutations are present
        if not all(check_list):
            raise Exception(
                f"Not all items-cond combinations in the data. Missing: {missing_combos}")

        # generate the appropriate amount of lists
        for k in range(len(conditions)):
            # order the conditions to match the list being created
            lat_conditions = conditions[k:] + conditions[:k]
            # generate (and on subsequent runs reset) the new df with all the columns in the argument df
            out_df = pd.DataFrame(columns=frame.columns)
            # look for the appropriate rows in the argument df (using the conditions multiple times with 'cycle')
            for item, cond in zip(set(sorted(frame[item_number_col])), cycle(lat_conditions)):
                # find the row in questions
                out_l = [out_df, frame.loc[(frame[item_number_col] == item) &
                                           (frame[cond_col] == cond)]]
                # add it at the end of the dataframe
                out_df = pd.concat(out_l)
            # reorder the most important columns
            columns_to_order = [item_col, sub_exp_col,
                                item_number_col, cond_col]
            # and just add the rest (if any)
            new_columns = columns_to_order + \
                (out_df.columns.drop(columns_to_order).tolist())
            out_df = out_df[new_columns]
            # add multi-list dfs to the critical list
            if len(lat_conditions) > 1:
                dfs_critical.append(out_df)
            # add single-condition dfs to the filler dict
            else:
                dfs_filler.append(out_df)

    # add all filler lists to the critical ones
    for filler in dfs_filler:
        # replace the current df with the longer version containing the fillers as well
        for i, df in enumerate(dfs_critical):
            dfs_critical[i] = pd.concat([df, filler])

    # save all lists individually with a suffix corresponding to the differnt lists
    for i, df in enumerate(dfs_critical):
        experiment.save_multi_ext(df, f"{name}{i+1}{extension}")
