import pyomo.environ as pyo

from resolve.resolve import run_opt


_EXPECTED_OBJECTIVE_FN_VALUE = 20_524_743_556


def test_main_test_case():
    """Test that toy case objective function value is close to defined value of 19,533,897,426.26."""
    resolve_cases = run_opt.main(
        "test",
        data_folder="data-test",
        extras=None,
        log_level="WARNING",
        log_json=False,
        raw_results=False,
        solver_name="appsi_highs",
        symbolic_solver_labels=False,
        return_cases=True,
        raise_on_error=True,
    )
    ofv_delta = pyo.value(resolve_cases[0].model.Total_Cost) - _EXPECTED_OBJECTIVE_FN_VALUE
    print(f"Objective function value for test case was {ofv_delta:.2f} different than expected.")
    assert abs(ofv_delta) < 2.0
