import pandas as pd
import pytest

from sg_estate.contracts import ContractError
from sg_estate.domain import value


def _scores():
    return pd.DataFrame(
        {
            "estate": ["BISHAN", "TAMPINES"],
            "score": [3.6, 3.5],
            "score_private": [3.7, 3.6],
        }
    )


def _complete_private_rows():
    rows = []
    for planning_area, base_price in (("BISHAN", 1_200_000), ("TAMPINES", 980_000)):
        for index in range(5):
            rows.append(
                {
                    "planning_area": planning_area,
                    "transacted_price": base_price + index * 25_000,
                    "area_sqm": 75 + index,
                    "property_type": "Condominium",
                    "type_of_area": "Strata",
                    "tenure": "99-year leasehold",
                    "project_age_years": 4 + index,
                    "sale_month": f"2025-{index + 1:02d}",
                }
            )
    return rows


def test_private_value_excludes_unknown_date_and_age_from_n(capsys):
    rows = _complete_private_rows()
    rows.extend(
        [
            {
                **rows[0],
                "transacted_price": 1_410_000,
                "sale_month": None,
            },
            {
                **rows[1],
                "transacted_price": 1_435_000,
                "project_age_years": None,
            },
        ]
    )
    transactions = pd.DataFrame(rows)

    residuals = value.fit_segment(transactions, "private_resale", _scores())

    assert residuals is not None
    counts = residuals.set_index("estate")["n"].to_dict()
    assert counts == {"BISHAN": 5, "TAMPINES": 5}
    assert pd.isna(transactions.iloc[-2]["sale_month"])
    assert pd.isna(transactions.iloc[-1]["project_age_years"])
    assert "excluded 2 of 12 rows before model fitting" in capsys.readouterr().out


@pytest.mark.parametrize("unavailable", [None, "unknown"])
def test_private_value_rejects_wholly_unavailable_required_control(unavailable):
    transactions = pd.DataFrame(_complete_private_rows())
    transactions["project_age_years"] = unavailable

    with pytest.raises(
        ContractError,
        match=(
            "private_resale required control 'project_age_years' has no usable "
            "values"
        ),
    ):
        value.fit_segment(transactions, "private_resale", _scores())
