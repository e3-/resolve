# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.16.2
#   kernelspec:
#     display_name: Python 3 (ipykernel)
#     language: python
#     name: python3
# ---
# %% [markdown]
# ---
#
# # Netload Distribution Matching Using Optimal Transport
#
# This notebook demonstrates how to use optimal transport—specifically, the Earth Mover's Distance (also known as EMD, EM distance, Wasserstein $W_1$)—to match netload distributions for power system analysis.
#
# **Objective:**
# Assign each day of one year to a representative day ("repday") so that the reconstructed annual netload profile closely approximates the multi-weather-year history, while preserving seasonal and statistical characteristics.
#
# **Approach:**
# - A small set of representative days and their weights are given as inputs.
# - Employ optimal transport to assign a repday to each day-of-year, minimizing the overall distributional difference (EMD) between the repday-synthesized full-year and a set of historical weather years of netload.
#
# This strategy successfully generates a single-year netload profile that respects the required weights and has defensible optimality.
# %% [markdown]
# ---
#
# # Python Dependencies
#
# This notebook requires the following Python packages:
#
# - numpy
# - pandas
# - plotly
# - ot (POT: Python Optimal Transport)
# - loguru
# - pathlib
#
# Install with:
#
# ```bash
# pip install numpy pandas plotly pot loguru
# ```
# %% [markdown]
# ---
# # Background: The Repday Assignment Problem
#
# - Need to represent one full-year netload profile using a small set of representative days ("repdays")
# - Repdays and their weights are pre-selected
# - Goal
#     - Assign a repday to each day-of-year
#     - Reconstruction should approximate the original netload distribution across all weather years
#     - Repday frequency in the solution must respect the given repday weights
#
# ### Challenges
# - Limited number of repdays (e.g. 36) vs. 365 days in a year
# - Maintaining seasonal and statistical fidelity
# - Avoiding unrealistic assignments (e.g., winter day mapped to summer repday)
#
# ### Note
# - This problem is distinct from the question of choosing a set of repdays.
# This workflow is downstream of repday selection, and specifically facilitates avoiding revisiting the repday selection step.
# %% [markdown]
# ---
# # Why Optimal Transport (OT)?   What is Earth Mover's distance (EMD)?
# - Consider netload sample data as empirical  _distributions_
#     - Each sample $x$ is 24 hours of netload data occurring on some date
#     - Distribution $P$ is a set of 36 dates with weights (akin to "probabilities") that sum to 365
#     - Distribution $Q$ is a set of 365 days-of-year each with weight 1. $Q$ also sums to 365
#     - The assignment problem requires P and Q to have equal total weight, here 365.
# - Optimal Transport provides a principled way to match two distributions, not just single statistics
# - A Transport plan is a **joint distribution**
#     - From Wikipedia [Wasserstein metric](https://en.wikipedia.org/w/index.php?title=Wasserstein_metric&oldid=1290488444):
#     "Two one-dimensional distributions μ  and ν, plotted on the x and  y axes,
#     and one possible **joint distribution** that defines a transport plan between them.
#     The joint distribution/transport plan is **not unique**."
#
#     - <p><a href="https://commons.wikimedia.org/wiki/File:Transport-plan.svg#/media/File:Transport-plan.svg"><img src="https://upload.wikimedia.org/wikipedia/commons/7/74/Transport-plan.svg" alt="Transport-plan.svg" height="540" width="540"></a><br>By <a href="//commons.wikimedia.org/w/index.php?title=User:Lambdabadger&amp;action=edit&amp;redlink=1" class="new" title="User:Lambdabadger (page does not exist)">Lambdabadger</a> - <span class="int-own-work" lang="en">Own work</span>, <a href="https://creativecommons.org/licenses/by-sa/4.0" title="Creative Commons Attribution-Share Alike 4.0">CC BY-SA 4.0</a>, <a href="https://commons.wikimedia.org/w/index.php?curid=64872543">Link</a></p>
#
# - Earth Mover’s Distance (EM distance, EMD) quantifies the minimum effort to transform one distribution into another
#     - Finding EMD value requires solving an **Optimal Transport** problem
# - Optimal Transport solution comprises two parts
#     - a **value** which is the EM distance, and
#     - a **transportation plan** which is a sparse matrix $G\in[0,1]^{36\times 365}$ from which we extract our **assigment map** ${g: \{1,2,\ldots,365\}\mapsto\{1,\ldots,36\}}$
# %% [markdown]
# ---
# # Repday Assignment with EMD
#
# We use the `RepdayToDayofyearEmdAssigner` class to assign days-of-year to repdays using EMD, enforcing seasonal realism and supporting both hard and soft assignments.
#
# ### Key Steps
# - Load and align netload data
# - Load repday definitions and weights
# - Augment OT cost matrix with a penalty to preserve seasonality
# - Solve the optimal assignment using EMD
# - Analyze and visualize results
# %%
# Import Repday EMD assignment class
import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path().resolve()))
from new_modeling_toolkit.resolve.repday_emd_assigner import RepdayToDayofyearEmdAssigner

# %%
# Establish file system context
src_path = Path(__file__) if "__file__" in globals() else Path().resolve()  # Result may be a file or folder
this_script_folder = src_path.parent if src_path.is_file() else src_path  # Folder that contains the .py or .ipynb
repo_root = this_script_folder.parent  # Repository folder
print("Repo root:", repo_root)

# %%
# Somewhere to save results for all cases
EMD_ASSIGNMENT_SANDBOX = repo_root / "data-test/processed/Day Sampling Net Load Analysis/"
EMD_ASSIGNMENT_SANDBOX.mkdir(parents=True, exist_ok=True)

# %% [markdown]
# ### Generic setup template

# %%
WRITE_DIR = EMD_ASSIGNMENT_SANDBOX / "generic"
WRITE_DIR.mkdir(parents=True, exist_ok=True)

# Cases point to an hourly netload timeseries file that contains multiple historical weather years of data.
NETLOAD_INPUT_FILES = {
    "case1": {
        "fpath": (repo_root / "data-test/profiles/CAISO-agg.csv").resolve(),
        # CAISO-agg.csv file is for demo only; bears no specific relation to netload.
        "output_year": 2035,
        # Netload generally exists w.r.t. a generation portfolio of a specific future year; this is that year. Does not affect computation; may affect displays.
        "target_variable": "profile_model_years",
        # The target_variable column must exist in the specified file; that column is renamed to "netload" internally.
    },
}

REPDAY_INPUT_FILE = (repo_root / "data-test/settings/timeseries/6 Days/chrono_periods_map.csv").resolve()
# File contains either a list of repdays and weights, or a mapping of weather datas to repdays from which a weighting can be derived.
# In the latter case, if the number of dispatch windows is very numerous (e.g. in Production Cost Modeling files), RepdayToDayofyearEmdAssigner will warn of too many repdays.
# E.g.
# YES: data-test\settings\timeseries\6 Days\chrono_periods_map.csv
# NO: data-test\settings\timeseries\PCM\chrono_periods_map.csv.

unit_str = "(frac of 1)"  # Units of netload data in input files. Suggest "MW" or or "(frac of 1)"
# It happens that the CAISO-agg.csv file is a normalized profile, so we use "(frac of 1)" here.

optimizer = RepdayToDayofyearEmdAssigner(WRITE_DIR, REPDAY_INPUT_FILE, NETLOAD_INPUT_FILES, unit_str, one_case=True)

# %% [markdown]
# Run the optimization

# %%
result_list = optimizer.get_dayofyear_repday_maps(vintage_years=[2035])
# Use vintage_year to run the case of interest (matches output_year in NETLOAD_INPUT_FILES)

# %% [markdown]
# ### Run the Repday EMD assignment

# %% [markdown]
# #### Instantiate the optimization

# %%
# Run the Repday EMD assignment
optimizer = RepdayToDayofyearEmdAssigner(WRITE_DIR, REPDAY_INPUT_FILE, NETLOAD_INPUT_FILES, unit_str, one_case=False)
# Manual modification of the parameters below to explore sensitivity. If one_case=False, all combinations of the parameters below will be run.
optimizer.dayofyear_difference_limits = [20, 35]
optimizer.day_difference_penalties = [
    0.5,
]
optimizer.emd_cost_metrics = [
    "cityblock",
]
optimizer.force_int_repweights_choices = [True]
total_cases = (
    len(optimizer.emd_cost_metrics)
    * len(optimizer.force_int_repweights_choices)
    * len(optimizer.day_difference_penalties)
    * len(optimizer.dayofyear_difference_limits)
)
print(f"Total cases to analyze: {total_cases}")

# %% [markdown]
# #### Run the optimization

# %%
result_list = optimizer.get_dayofyear_repday_maps(vintage_years=[2035])

# %% [markdown]
# # Results display

# %% [markdown]
# Precondition for this section is having a `result_list`

# %%
# Inspect all the runs so as to choose one to inspect
key_list = list(result_list[0].keys())
display(key_list)

# %% [markdown]
# multi-case summary

# %%
# make a dataframe
focus_keys = [
    "day_difference_compliance",
    "avg_wy_maes",
    "em_distance_value",
    "penalized_em_distance_value",
    "profile_day_peak_avg",
    "profile_day_valley_avg",
]
focus_dict = {}
key_list = list(result_list[0].keys())
for case in key_list:
    focus_dict[case] = {key: result_list[0][case][key] for key in focus_keys if key in result_list[0][case]}

df = pd.DataFrame.from_dict(focus_dict, orient="index")

summary_df = (
    df.reset_index()
    .rename(
        columns={
            "level_0": "cost_metric",
            "level_1": "force_integer_repweights",
            "level_2": "dayofyear_difference_penalty",
            "level_3": "dayofyear_difference_limit",
        }
    )
    .round(1)
)
display(summary_df)
summary_df.to_csv(WRITE_DIR / "emd_assignment_summary.csv", index=False)

# %% [markdown]
# List of cases have been run

# %%
key_list

# %% [markdown]
# Choose one specific case to inspect

# %%
# See details about a specific run
key_num = 0  # which run to use for analysis
cost_metric, force_integer_repweights, dayofyear_difference_penalty, dayofyear_difference_limit = key_list[key_num]
# key_num = None
# cost_metric, force_integer_repweights, dayofyear_difference_penalty, dayofyear_difference_limit = ('cityblock', True, 0.5, 20)

unit_str = optimizer.units_str


# Detail about one case
print(
    f"\nSelected run {key_num} for analysis with\n cost_metric= '{cost_metric}' \n force_integer_repweights= {force_integer_repweights} \n dayofyear_difference_penalty= {dayofyear_difference_penalty}\n dayofyear_difference_limit= {dayofyear_difference_limit}.\n"
)

result = result_list[0][key_list[key_num]]
print(f"Available info {list(result.keys())}\n")

num_repdays_used = len(result["map_doy_repday_pr_df"].filter(like="repday_").stack().unique())
print(
    f"{num_repdays_used} repdays assigned to {result['map_doy_repday_pr_df'].shape[0]} days of the year with {cost_metric}-EMD = {result['em_distance_value']:.4f} ({unit_str})."
)
df = result["dispatched_vs_profile_netload_df"]
net_load_col = df.filter(like="Netload").columns[0]
# df0 = df.filter(like="wy-20")
wy_maes = [(df[net_load_col] - df[wy]).abs().mean() for wy in df.filter(like="wy-20")]
avg_mae = sum(wy_maes) / len(wy_maes)
print(f"Netload reconstruction MAE is {avg_mae:.6f} {unit_str} over {len(wy_maes)} weather-years.\n")


# %%
profile_netload_df = result["profile_netload_df"]
profile_netload_df

# %%
# This is the main output of the Repday EMD assignment!
print("Mapping of repdays to days of the year:")
result["map_doy_repday_pr_df"]

# %% [markdown]
# Plot repday dispatch of the vintage year

# %%
# Plot repday dispatch of the vintage year
result["fig_netload_discrepancy"].show()

# %% [markdown]
# Visualize Cost Matrix for Optimal Transport

# %%
# Visualize Cost Matrix for Optimal Transport
result["fig_cost_matrix_with_penalty"].show()

# %% [markdown]
# Visualize Transport Plan with Weight distributions

# %%
# Visualize Transport Plan with Weight distributions
result["fig_ot_marginals"].show()

# %% [markdown]
# ---
# # Repday Assignment Summary
#
# - The EMD-based assignment produces a mapping from each day-of-year to one or more repdays, with probabilities.
#     - `emd_repday_map_*.csv`
#     - **LIMITATION:** Leap years are not handled in the current implementation.
# - The approach enforces a maximum day-of-year difference (e.g., 45 days) to maintain seasonal realism.
#     - `day_offset_compliance_*.csv`
# - The resulting dispatched netload closely matches the profile netload across all weather years.
#     - `dispatched_vs_profile_netload_*.csv`
#     - `dispatched_vs_profile_netload_*.html`
# - Visualize optimization
#     - `cost_matrix_heatmap_*.html`
#     - `cost_matrix_with_penalty_*.html`
#     - `transport_plan_*.html`
#
#
#
# #### Advantages
# - Maintains seasonal realism
# - Supports both hard (integer) and soft (fractional) assignments
# - EM distance is expressed in the _same physical units_ as the problem (e.g. MW)
# - EMD value provides a bound on the impact of approximation
# - More robust and interpretable than matching single statistics
#
# #### Disadvantages
# - Regardless of mutual compatibility between distributions $P$ and $Q$, solving Optimal Transport _will_ deliver an assigment map
# - In particular, consider if one of the distribution contains an outlier
#     - that value _will_ appear in the output of the map with the specified frequency of occurrence (weight)
#     - that element may own a large contribution to the total EM distance
# - Fortunately, in the repday assignment problem, the netload representative days are highly curated to be typical one-day profiles

# %% [markdown]
# ## Approximation Guarantees
#
# EM distance (Wasserstein $W_1$ distance) provides helpful probabilistic guarantees.
# Details are in [Scipy references](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.wasserstein_distance_nd.html).
#
# $$\left|E_Q[f(x)] - E_P[f(x)]\right| < K_f\cdot \operatorname{EMD}(P,Q)$$
#
# where
# - $\operatorname{EMD}(P,Q)$ is the EM distance between $P$ and $Q$
# - $K_f$ is akin to the maximum slope of $f$
# - $E_Q$ is expectation under law $Q$, and
# - $E_P$ is expectation under law $P$.
#
# For example, to estimate **average load peak** in a simulation that uses samples from $Q$ instead of samples from $P$, the implied function $f$ for peak extraction is $f(x)=\operatorname{max}(x_1,x_2,\ldots,x_{24})$ and $K_f=\sqrt{24}=4.9$.
# $K_f$ is affected by normalizations, such as power vs energy, and should be re-confirmed in each problem context ([search Lipschitz constant](https://en.wikipedia.org/wiki/Wasserstein_metric)).
#
# ## Conclusion
#
# - **Distribution-level matching with OT (EMD) provides a principled, flexible, and effective solution for repday assignment.**
# - EMD-based assignment enables robust scenario analysis and supports regulatory/analytical needs.

# %% [markdown]
#
