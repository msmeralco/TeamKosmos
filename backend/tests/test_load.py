import numpy as np
import pytest

from app.errors import ApiError
from app.services import load


def test_shape_and_totals():
    lp = load.estimate_load(monthly_kwh=450, template="balanced")
    assert lp.hourly_kw.shape == (8760,)
    assert lp.hourly_kw.sum() == pytest.approx(450 * 12, rel=1e-9)
    assert lp.monthly_kwh.sum() == pytest.approx(450 * 12, rel=1e-9)
    assert (lp.hourly_kw > 0).all()
    for m in range(12):
        assert lp.hourly_kw[load.MONTH_IDX == m].sum() == pytest.approx(lp.monthly_kwh[m], rel=1e-9)


def test_hot_months_use_more():
    lp = load.estimate_load(monthly_kwh=300)
    assert lp.monthly_kwh[4] > lp.monthly_kwh[0]  # May vs January


def test_deterministic():
    a = load.estimate_load(monthly_kwh=450, template="night_heavy")
    b = load.estimate_load(monthly_kwh=450, template="night_heavy")
    assert np.array_equal(a.hourly_kw, b.hourly_kw)


def test_templates_differ_in_daytime_share():
    def day_share(t):
        lp = load.estimate_load(monthly_kwh=450, template=t)
        day = (load.HOUR_IDX >= 9) & (load.HOUR_IDX < 16)
        return lp.hourly_kw[day].sum() / lp.hourly_kw.sum()

    assert day_share("night_heavy") < day_share("balanced") < day_share("day_heavy")


def test_bill_converts_through_tariff():
    kwh = load.bill_to_kwh(6780)
    assert kwh == pytest.approx(6780 / 15.0615, rel=1e-6)
    lp = load.estimate_load(bill_php=6780, template="balanced")
    assert lp.base_monthly_kwh == pytest.approx(kwh)
    assert lp.basis == "bill"


@pytest.mark.parametrize("kw", [{"monthly_kwh": 10}, {"monthly_kwh": 99999}, {}, {"monthly_kwh": 100, "bill_php": 100}])
def test_invalid_inputs(kw):
    with pytest.raises(ApiError):
        load.estimate_load(**kw)


def test_invalid_template():
    with pytest.raises(ApiError):
        load.estimate_load(monthly_kwh=300, template="weird")


def test_to_dict_flags_estimate():
    d = load.estimate_load(monthly_kwh=300).to_dict()
    assert d["is_estimate"] is True and len(d["hourly_kw"]) == 8760 and len(d["monthly_kwh"]) == 12
