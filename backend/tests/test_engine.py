import numpy as np
import pytest

from app.services import billing, finance
from app.services.dispatch import Battery, Inverter, dispatch
from app.services.load import MONTH_IDX, estimate_load


# ---- dispatch ---------------------------------------------------------------------------------
def solar_curve(peak=3.0):
    h = np.arange(8760) % 24
    return np.where((h >= 6) & (h <= 17), peak * np.sin(np.pi * (h - 6) / 12.0), 0.0)


@pytest.mark.parametrize("battery", [None, Battery(usable_kwh=5.0, max_kw=3.0, round_trip_eff=0.9)])
def test_energy_balance_every_hour(battery):
    rng = np.random.default_rng(1)
    pv = solar_curve(4.0) * rng.uniform(0.3, 1.0, 8760)
    load = rng.uniform(0.1, 2.5, 8760)
    inv = Inverter(ac_kw=3.0, efficiency=0.97)
    r = dispatch(pv, load, inv, battery)
    assert np.allclose(r.pv_ac, r.direct + r.charge + r.export, atol=1e-9)
    assert np.allclose(load, r.direct + r.discharge + r.import_, atol=1e-9)
    assert (r.export >= -1e-12).all() and (r.import_ >= -1e-12).all()
    assert r.pv_ac.max() <= 3.0 + 1e-12  # inverter clipping
    if battery:
        assert r.soc.max() <= battery.usable_kwh + 1e-9 and r.soc.min() >= -1e-9
        assert r.charge.max() <= battery.max_kw + 1e-9 and r.discharge.max() <= battery.max_kw + 1e-9


def test_battery_reduces_imports_and_losses_are_accounted():
    pv = solar_curve(4.0)
    load = estimate_load(monthly_kwh=450, template="night_heavy").hourly_kw
    inv = Inverter(ac_kw=4.0, efficiency=1.0)
    no_b = dispatch(pv, load, inv)
    with_b = dispatch(pv, load, inv, Battery(usable_kwh=10.0, max_kw=5.0, round_trip_eff=0.9))
    assert with_b.import_kwh < no_b.import_kwh
    # energy out of the battery cannot exceed energy in, times the round-trip efficiency
    assert with_b.discharge.sum() <= with_b.charge.sum() * 0.9 + 1e-6


def test_max_dc_clips_input():
    pv = np.full(8760, 5.0)
    r = dispatch(pv, np.zeros(8760), Inverter(ac_kw=10, efficiency=1.0, max_dc_kw=4.0))
    assert r.pv_ac.max() == pytest.approx(4.0)


def test_dispatch_rejects_wrong_length():
    with pytest.raises(ValueError):
        dispatch(np.zeros(10), np.zeros(10), Inverter(ac_kw=1))


def test_monthly_aggregates_sum_to_totals():
    r = dispatch(solar_curve(), estimate_load(monthly_kwh=300).hourly_kw, Inverter(ac_kw=3))
    assert r.monthly_import.sum() == pytest.approx(r.import_kwh)
    assert r.monthly_export.sum() == pytest.approx(r.export_kwh)
    assert len(r.monthly_import) == 12 and MONTH_IDX.max() == 11


# ---- billing: hand-calculated -----------------------------------------------------------------------
def three_month_inputs():
    imp = np.zeros((1, 12)); exp = np.zeros((1, 12)); load = np.full(12, 200.0)
    imp[0, :3] = [100, 100, 100]
    exp[0, :3] = [150, 50, 20]
    return imp, exp, load


def test_net_metering_banking_hand_calculation():
    imp, exp, load = three_month_inputs()
    res = billing.annual_bills(imp, exp, load, tariff=10.0, tariff_growth_pct=0, export_credit=6.0,
                               export_credit_growth_pct=0, fixed_php_month=50.0, net_metering=True)
    # Jan: energy 1000, credit 900  -> bill 50+1000-900=150, bank 0
    # Feb: energy 1000, credit 300  -> bill 50+1000-300=750, bank 0
    # Mar: energy 1000, credit 120  -> bill 50+1000-120=930
    # Apr..Dec: imports 0 -> bill = fixed 50 each (9 months) = 450
    assert res.solar[0] == pytest.approx(150 + 750 + 930 + 450)
    # baseline: 12 x (50 + 200*10) = 12 x 2050
    assert res.baseline[0] == pytest.approx(12 * 2050)
    assert res.credit_used[0] == pytest.approx(900 + 300 + 120)


def test_banked_credit_carries_to_next_month_and_is_never_paid_out():
    imp = np.zeros((1, 12)); exp = np.zeros((1, 12)); load = np.full(12, 0.0)
    exp[0, 0] = 500   # credit 3000 in January, no imports
    imp[0, 1] = 100   # February energy charge 1000
    res = billing.annual_bills(imp, exp, load, tariff=10.0, tariff_growth_pct=0, export_credit=6.0,
                               export_credit_growth_pct=0, fixed_php_month=0.0, net_metering=True)
    assert res.solar[0] == pytest.approx(0.0)       # February fully offset by the bank
    assert res.final_bank == pytest.approx(3000 - 1000)  # unused credit is forfeited, not cashed out


def test_net_metering_off_gives_no_credit():
    imp, exp, load = three_month_inputs()
    off = billing.annual_bills(imp, exp, load, tariff=10.0, tariff_growth_pct=0, export_credit=6.0,
                               export_credit_growth_pct=0, fixed_php_month=50.0, net_metering=False)
    assert off.solar[0] == pytest.approx(3 * 1050 + 9 * 50)
    assert off.credit_used[0] == 0


def test_export_credit_is_capped_at_retail_rate_and_growth_applies():
    imp = np.zeros((2, 12)); exp = np.zeros((2, 12)); load = np.full(12, 100.0)
    imp[:, 0] = 100; exp[:, 0] = 100
    res = billing.annual_bills(imp, exp, load, tariff=5.0, tariff_growth_pct=10, export_credit=9.0,
                               export_credit_growth_pct=0, fixed_php_month=0.0, net_metering=True)
    # credit 9 is capped to retail 5 in year 1, so Jan bill = 500 - min(500, 100*5) = 0
    assert res.solar[0] == pytest.approx(0.0)
    # year 2 tariff 5.5; credit 9 capped at 5.5 -> still fully offset
    assert res.solar[1] == pytest.approx(0.0)
    assert res.baseline[1] == pytest.approx(12 * 100 * 5.5)


# ---- finance ---------------------------------------------------------------------------------------------
def test_constant_cash_flow_closed_forms():
    net = np.full(25, 10_000.0)
    capex = 50_000.0
    cf = finance.build_cashflow(net, capex, om_pct_of_capex=0, inverter_price=0, inverter_life=12,
                                inverter_replacement_pct=100, battery_price=0, battery_life=12)
    assert cf.cumulative[0] == -capex and cf.cumulative[-1] == pytest.approx(200_000)
    assert finance.payback_years(cf.cumulative) == pytest.approx(5.0)
    r = 0.08
    annuity = 10_000 * (1 - (1 + r) ** -25) / r
    assert finance.npv(cf.net, capex, 8) == pytest.approx(annuity - capex, rel=1e-9)
    irr = finance.irr_pct(cf.net, capex)
    assert finance.npv(cf.net, capex, irr) == pytest.approx(0, abs=1e-3)


def test_payback_interpolates_and_none_when_never():
    cum = np.array([-100.0, -40.0, 20.0, 80.0])
    assert finance.payback_years(cum) == pytest.approx(1 + 40 / 60)
    assert finance.payback_years(np.array([-100.0, -90.0, -80.0])) is None
    assert finance.irr_pct(np.full(5, -1.0), 100.0) is None


def test_replacements_hit_the_right_years():
    cf = finance.build_cashflow(np.zeros(25), 100_000, om_pct_of_capex=1.0, inverter_price=20_000, inverter_life=12,
                                inverter_replacement_pct=100, battery_price=30_000, battery_life=12)
    assert cf.replacements[11] == 50_000 and cf.replacements[23] == 50_000
    assert cf.replacements.sum() == 100_000
    assert cf.om[0] == 1_000


def test_lcoe_simple_case():
    gen = np.full(25, 1000.0)
    cost = finance.lcoe(10_000, np.zeros(25), np.zeros(25), gen, 0.0)
    assert cost == pytest.approx(10_000 / 25_000)
    assert finance.lcoe(10_000, np.zeros(25), np.zeros(25), np.zeros(25), 8) is None
